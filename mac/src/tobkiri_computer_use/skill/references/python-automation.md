# Python automation: selectors, waiting, and measured grids

Use Python functions, loops and data structures on one persistent `Computer()`
connection. Each action retains the existing window, snapshot, delivery and
consent checks. These helpers never retry a dispatched input.

## Reuse selectors across observations

A Locator stores a semantic query and resolves a fresh element before each
action. Select labels and roles from the observed app. Duplicate matches are
errors; the helper never chooses the first arbitrary match. Element and Point
handles belong to one observation; a Locator can be retained across actions.

```python
name = window.locator("Name", role="AXTextField")
apply = window.locator("Apply", role="AXButton")

result = name.set_value("Ada")
state = window.wait_for(
    lambda s: s.find("Name", role="AXTextField").value == "Ada",
    timeout=5,
)
result = apply.click(timeout=5)
print(result.delivery)
print(result.observation.changes)
```

Locator actions default to `timeout=0`: resolve once, then dispatch once. A
positive timeout waits for a unique, enabled match before dispatch. It never
repeats an action with an unknown outcome. Ambiguity and native failures stop
immediately. Existing `expect`, `delivery_mode` and `fallback_reason` arguments
pass through to the Window methods. Physical/focus input keeps real approval.

`element = apply.wait(timeout=5)` returns a fresh Element, including `point`
and `to_dict()` for coordinate extraction. Use it before another observation
invalidates it. A Locator is not an identity guarantee if a page repurposes a
label; inspect changed pages and verify the result against the user's task.

## Wait for state instead of sleeping and clicking again

```python
import threading

stop = threading.Event()  # another part of your script can call stop.set()
state = window.wait_for(
    lambda s: s.find("Progress", role="AXProgressIndicator").value == 100,
    timeout=30, poll_interval=.5, stop_event=stop,
)
state.save("/absolute/output/completed.png", marks=False)
```

The predicate must be read-only and return a Python `bool`. Each poll preserves
the window's screenshot/tree options. `element_not_found` means not ready;
ambiguity and driver errors propagate. Timeout/cancellation includes the last
observation id and attempt count. Missing elements in a bounded tree do not
prove absence. Prefer positive evidence and inspect images for visual results.

Deadline/cancellation checks occur between native reads. A read already in
progress uses the transport timeout. `timeout=0` still permits one initial
observation. No input retry occurs in this waiting loop.

## Calculate a static grid from a measured region

For equal-sized cells, choose the bounds and counts from the screenshot. Do
not infer controls from app source or assume unequal keys form a uniform grid.

```python
from tobkiri_computer_use import ClickStep

state = window.observe()
state.save("/absolute/output/grid-before.png", marks=False)
# Inspect the image, then supply [left, top, right, bottom] in screenshot pixels.
cells = state.grid(OBSERVED_REGION, rows=OBSERVED_ROWS, columns=OBSERVED_COLUMNS)
point = cells[ROW][COLUMN]  # zero-based, center of the chosen cell
state.preview(point).save("/absolute/output/planned-cell.png")

# Only for controls whose geometry stays static throughout the sequence:
steps = [ClickStep(i * .5, cells[row][column])
         for i, (row, column) in enumerate(CHOSEN_CELLS)]
result = window.timeline(steps, on_late="stretch")
print(result.status, result.error)
if result.observation:
    result.observation.save("/absolute/output/grid-after.png")
```

`grid()` is local and returns a tuple of rows containing bound Points, at most
2000 cells. It sends no input, motion or observation. Bounds must lie wholly
inside the screenshot; invalid bounds are rejected, not clipped. Screenshot
pixels, desktop points and zoom pixels remain distinct.

Translation preserves these points. Resizing, another observation or a normal
action makes them stale. Do not loop over separate `click()` calls with an old
grid. Use `timeline()` for a known static surface, or Locators for changing UI.
Check the final result rather than assuming all scheduled steps succeeded.

For independent windows, use Python callables with `computer.parallel(...)`.
Each must retain its own window and observations. Same-window operations are
serialized and may invalidate each other's handles. Close Computer at the end.
