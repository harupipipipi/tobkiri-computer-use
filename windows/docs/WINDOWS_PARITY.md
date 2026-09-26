# Windows parity report

Tested 2026-09-22 on Windows 11 with Cua Driver 0.28.2. Codex Computer and Tobkiri both ran the
same disposable WinForms task: select the exact target window and press `Increment` once.

| Capability | Codex Computer baseline | Tobkiri Windows result |
| --- | --- | --- |
| Exact app/window selection | Yes | Yes; mandatory `(pid, window_id)` |
| Window screenshot | Yes | Yes, including an occluded background window |
| Accessibility tree | UIA tree returned for the fixture | UIA tree returned 73 elements in the fixture |
| Click | Yes; target activation observed | Background semantic and screenshot-point click succeeded without focus or cursor change |
| Replace/insert text | `set_value` / `type` surface | UIA `set_value` and background `type_text` succeeded with readback |
| Scroll | Coordinate scroll | Background UIA scroll succeeded; approved foreground pixel fallback also succeeded |
| Drag | Foreground/global input | Background is refused on 0.28.2; approved foreground fallback succeeded |
| Stale coordinates | Snapshot/index rules | Old `Element` and `Point` rejected before input |
| Focus isolation | API activates the chosen target | Background routes left witness focus and physical cursor unchanged |
| Consequential/physical input | Host confirmation rules | Same host rules plus a mandatory one-action foreground broker |

The live fixture report passed every required check. Foreground scroll produced a `-360` wheel event,
drag produced matching `drag_start` / `drag_end` events, and both restored the previous foreground window
and physical cursor. The unit suite contains 239 tests and sends no desktop input. The exact comparison
ended at `Count: 1` in both images; Codex Computer activated the target, while Tobkiri's background UIA
route left the pre-existing foreground HWND unchanged. Tobkiri also removes Cua 0.28.2's DPI/WGC black
allocation padding before exposing the screenshot, while preserving the driver's input coordinate contract.

## Isolation experiments

The test machine had two Windows virtual desktops, one physical DELL U2718Q monitor, and no indirect
display device. A disposable fixture was moved to the inactive desktop with the documented
`IVirtualDesktopManager::MoveWindowToDesktop` API without switching the user's desktop.

- Cua listed the off-desktop HWND and captured it; Tobkiri normalized the usable image to 604×516.
- UIA exposed only the top-level window controls there, not the fixture controls.
- A screenshot-bound background click returned `route=synthetic_events` but no application event arrived.
- The active virtual desktop ID and foreground window did not change.

Conclusion: a Windows virtual desktop is useful for visual separation, but Cua 0.28.2 cannot prove reliable
general input delivery there. Tobkiri fails closed rather than switching desktops or replaying the click.

A true virtual monitor requires an Indirect Display Driver (IDD/IddCx). That is a signed driver installation,
not a per-process Cua feature. No IDD was present on the test host, so no third-party display driver was installed.
The proven low-impact option is an occluded window on the current desktop: WGC captures it and UIA/PostMessage
routes operate it without taking focus for the tested controls.

## Limits

- Results cover the disposable WinForms fixture and one Calculator baseline, not every Windows framework.
- Minimized windows have no Cua 0.28.2 screenshot; Tobkiri reports that condition instead of restoring them.
- Some controls reject background wheel/key events. Tobkiri never silently escalates those to physical input.
- Foreground `SendInput` is inherently shared. It requires explicit per-action approval and briefly borrows input,
  even though Tobkiri restores the previous focus and pointer afterward.
- An off-desktop transport acknowledgement is not counted as success without an application-side event.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\build_fixture_windows.py --output .\artifacts\TobkiriWindowsFixture.exe
.\.venv\Scripts\python.exe .\scripts\live_acceptance_windows.py --driver C:\path\to\cua-driver.exe --output .\artifacts\windows.json --allow-foreground
.\.venv\Scripts\python.exe .\scripts\virtual_desktop_acceptance_windows.py --driver C:\path\to\cua-driver.exe --output .\artifacts\virtual-desktop.json
```
