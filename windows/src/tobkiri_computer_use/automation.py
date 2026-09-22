"""Live semantic selectors and bounded read-only waits.

Every Locator action resolves against a fresh observation, then delegates one
time to the existing Window action.  Waiting retries observations only; it
never retries input whose outcome may be unknown.
"""
from __future__ import annotations

import math
import time

from .transport import ComputerError


_monotonic = time.monotonic


def _seconds(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        relation = "> 0" if positive else ">= 0"
        raise ValueError(f"{name} must be finite and {relation}")
    return value


def _read_evidence(window, observation, attempts, started):
    raw = observation.raw if observation is not None else {}
    return {
        "surface": {"pid": window.surface[0], "window_id": window.surface[1]},
        "attempts": attempts,
        "elapsed_seconds": max(0.0, _monotonic() - started),
        "last_observation_id": getattr(observation, "id", None),
        "last_driver_snapshot_id": getattr(observation, "driver_snapshot_id", None),
        "last_elements_complete": raw.get("elements_complete"),
        "last_degraded_reason": raw.get("degraded_reason"),
        "input_sent": False,
    }


def _cancelled(window, observation, attempts, started):
    raise ComputerError(
        "wait_cancelled",
        "The read-only wait was cancelled. No input was sent.",
        details=_read_evidence(window, observation, attempts, started),
    )


def _timed_out(window, observation, attempts, started, timeout, extra=None):
    details = _read_evidence(window, observation, attempts, started)
    details["timeout_seconds"] = timeout
    if extra:
        details.update(extra)
    raise ComputerError(
        "wait_timeout",
        "The condition was not observed before the wait deadline. No input was sent. "
        "This does not prove that the requested UI is absent.",
        details=details,
    )


def _sleep_or_cancel(stop_event, delay, window, observation, attempts, started):
    if stop_event is None:
        time.sleep(delay)
        return
    if stop_event.wait(delay):
        _cancelled(window, observation, attempts, started)


def wait_for(window, predicate, *, timeout=5, poll_interval=.25, stop_event=None):
    """Return the first fresh Observation for which ``predicate`` is true.

    ``element_not_found`` from the predicate is a waitable false result.
    Ambiguity, driver failures, and every other exception propagate at once.
    The window lock is held only by each individual native observation call.
    """
    if not callable(predicate):
        raise TypeError("predicate must be callable")
    timeout = _seconds(timeout, "timeout")
    poll_interval = _seconds(poll_interval, "poll_interval", positive=True)
    started = _monotonic()
    deadline = started + timeout
    attempts = 0
    observation = None

    while True:
        if stop_event is not None and stop_event.is_set():
            _cancelled(window, observation, attempts, started)
        if attempts and _monotonic() >= deadline:
            _timed_out(window, observation, attempts, started, timeout)

        observation = window._observe_current()
        attempts += 1
        if stop_event is not None and stop_event.is_set():
            _cancelled(window, observation, attempts, started)
        try:
            matched = predicate(observation)
        except ComputerError as exc:
            if exc.code == "element_not_found":
                matched = False
            else:
                raise
        if not isinstance(matched, bool):
            raise TypeError("predicate must return bool")
        if matched:
            return observation

        remaining = deadline - _monotonic()
        if remaining <= 0:
            _timed_out(window, observation, attempts, started, timeout)
        _sleep_or_cancel(
            stop_event,
            min(poll_interval, remaining),
            window,
            observation,
            attempts,
            started,
        )


class Locator:
    """A live, unique semantic selector bound to one Window.

    ``resolve`` and ``wait`` return an Element from the observation made by
    that call. Actions resolve again and dispatch once through the Window API.
    """

    def __init__(self, window, label=None, *, role=None, contains=False):
        if not isinstance(contains, bool):
            raise TypeError("contains must be bool")
        self.window = window
        self.label = label
        self.role = role
        self.contains = contains

    @property
    def selector(self):
        return {
            "label": None if self.label is None else str(self.label),
            "role": None if self.role is None else str(self.role),
            "contains": self.contains,
        }

    def _from_observation(self, observation):
        element = observation.find(
            self.label, role=self.role, contains=self.contains
        )
        if element.raw.get("enabled") is False:
            raise ComputerError(
                "element_disabled",
                "The uniquely matched element is disabled. No input was sent.",
                details={
                    "selector": self.selector,
                    "observation_id": observation.id,
                    "element": element.to_dict(),
                    "input_sent": False,
                },
            )
        return element

    def resolve(self, *, timeout=0, poll_interval=.25, stop_event=None):
        """Resolve one enabled Element; positive timeout retries reads only."""
        timeout = _seconds(timeout, "timeout")
        poll_interval = _seconds(poll_interval, "poll_interval", positive=True)
        if timeout == 0:
            started = _monotonic()
            if stop_event is not None and stop_event.is_set():
                _cancelled(self.window, None, 0, started)
            observation = self.window._observe_current()
            if stop_event is not None and stop_event.is_set():
                _cancelled(self.window, observation, 1, started)
            return self._from_observation(observation)

        matched = {"element": None}

        def predicate(observation):
            try:
                matched["element"] = self._from_observation(observation)
                return True
            except ComputerError as exc:
                if exc.code in ("element_not_found", "element_disabled"):
                    return False
                raise

        try:
            wait_for(
                self.window,
                predicate,
                timeout=timeout,
                poll_interval=poll_interval,
                stop_event=stop_event,
            )
        except ComputerError as exc:
            if exc.code == "wait_timeout" and isinstance(exc.details, dict):
                exc.details["selector"] = self.selector
            raise
        return matched["element"]

    def wait(self, *, timeout=5, poll_interval=.25, stop_event=None):
        """Wait for and return one fresh, uniquely matched, enabled Element."""
        return self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )

    def click(self, *, timeout=0, poll_interval=.25, stop_event=None, **kwargs):
        element = self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )
        return self.window.click(element, **kwargs)

    def set_value(
        self, value, *, timeout=0, poll_interval=.25, stop_event=None, **kwargs
    ):
        element = self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )
        return self.window.set_value(element, value, **kwargs)

    def type_text(
        self, text, *, timeout=0, poll_interval=.25, stop_event=None, **kwargs
    ):
        element = self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )
        return self.window.type_text(element, text, **kwargs)

    def scroll(
        self,
        direction,
        *,
        timeout=0,
        poll_interval=.25,
        stop_event=None,
        **kwargs,
    ):
        element = self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )
        return self.window.scroll(element, direction, **kwargs)

    def move(self, *, timeout=0, poll_interval=.25, stop_event=None, **kwargs):
        element = self.resolve(
            timeout=timeout, poll_interval=poll_interval, stop_event=stop_event
        )
        return self.window.move(element, **kwargs)
