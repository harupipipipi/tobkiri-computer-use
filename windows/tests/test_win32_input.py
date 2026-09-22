from tobkiri_computer_use import ConsentDecision
from tobkiri_computer_use import win32_input


def allow(request):
    return ConsentDecision(request.id, request.digest, True)


def test_window_pixel_mapping_uses_actual_hwnd_rectangle():
    assert win32_input._window_point([100, 200, 900, 800], (450, 300), (900, 600)) == (500, 500)


def test_windows_0282_foreground_scroll_uses_consent_gated_win32_fallback(rig, monkeypatch):
    computer, transport = rig
    transport.server_info = {"name": "cua-driver", "version": "0.28.2"}
    computer._approval_callback = allow
    calls = []

    def fake_scroll(**kwargs):
        calls.append(kwargs)
        return {"delivery": {"mode": "foreground"}, "route": "win32_sendinput",
                "effect": "unverifiable", "focus_restored": True, "cursor_restored": True}

    monkeypatch.setattr(win32_input, "foreground_scroll", fake_scroll)
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    result = window.scroll(state.point(100, 100), "down", amount=2,
                           delivery_mode="foreground", fallback_reason="fixture route refused")
    assert result.delivery["route"] == "win32_sendinput"
    assert calls[0]["point"] == (100, 100)
    assert calls[0]["image_size"] == (800, 600)
    assert not any(name == "scroll" for name, _ in transport.calls)


def test_windows_0282_foreground_drag_uses_consent_gated_win32_fallback(rig, monkeypatch):
    computer, transport = rig
    transport.server_info = {"name": "cua-driver", "version": "0.28.2"}
    computer._approval_callback = allow
    calls = []

    def fake_drag(**kwargs):
        calls.append(kwargs)
        return {"delivery": {"mode": "foreground"}, "route": "win32_sendinput",
                "effect": "unverifiable", "focus_restored": True, "cursor_restored": True}

    monkeypatch.setattr(win32_input, "foreground_drag", fake_drag)
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    result = window.drag(state.point(100, 100), state.point(200, 150),
                         delivery_mode="foreground", fallback_reason="fixture route refused")
    assert result.delivery["route"] == "win32_sendinput"
    assert calls[0]["start"] == (100, 100)
    assert calls[0]["end"] == (200, 150)
    assert calls[0]["image_size"] == (800, 600)
    assert not any(name == "drag" for name, _ in transport.calls)
