# Validation record

Test host: Windows / Python 3.13 / Node 22.23 / Electron 44.4.5 / Cua Driver 0.28.2.

## Automated checks

- Windows Python suite: **250 passed**, including ten companion cases covering
  text privacy, stale geometry, sessions, native-marker replacement, arrival
  acknowledgment, malformed replies and delayed Windows UDP ICMP errors.
- Engine/protocol: **10 passed**; 48 distinct continuous poses, frame-rate independence,
  stable hotspots, continuous turning, reduced motion, clips and bounded datagrams.
- Browser UI: 48 motions, appearance, persistence, pixel drawing, export/import,
  sprites and responsive layouts; no JavaScript errors.
- Electron: hidden isolated windows, nonfocusable transparent overlay, physical
  pixels to DIP, UDP, real renderer arrival replies, hide, ordering, expiry and save.
  Pet-only mode preserves the visible character while removing cursor pixels;
  mode switching, persistence and exported packs were also checked.
- macOS native behavior is unverified. The earlier full suite on this Windows host
  had 246 passes and 27 failures; its unmodified baseline had 239 passes and the
  same 27 failures. This is not a macOS acceptance result.
  The final eight companion-specific macOS-package tests pass on Windows.

## Actual Windows app recording — 2026-09-27

`test-results/recordings/mochi-desktop-final.mp4` records an actual Notepad document
and native character overlay. Tobkiri MCP inserted three separate text segments,
opened Notepad's heading menu and dismissed it with Escape. Fresh native
observations confirmed each inserted segment and the menu's open/closed state.
These are real application inputs, not autoplay or a simulated editor.

All five actions received the renderer's arrival acknowledgment before input.
Waits were 155.7, 659.0, 655.4, 155.9 and 159.2 ms. The driver often reported
`unverifiable` despite visible changes; Escape also returned a delivery escalation
hint. No foreground fallback or repeated input was sent. Verification uses fresh
UI state, rather than interpreting those receipts as success.

| Measurement | Final real-app recording |
| --- | ---: |
| Duration / capture area | 29.983 s / 800 × 600 |
| Renderer average | 60.00 fps |
| Renderer 95th-percentile interval | 16.8 ms |
| Longest renderer interval | 17.0 ms |
| Renderer intervals over 25 ms | 0 |
| Encoded video frames / average cadence | 1,725 / 57.53 fps |
| Longest video timestamp interval | 33.334 ms |
| Video intervals over 25 ms / over 50 ms | 74 / 0 |

Renderer timings cover 1,821 intervals around the recording. Independent MP4
timestamps reveal capture-frame loss even though rendering remained steady.
The video is not a perfect 60-fps capture. No interpolated frames were added.
FFmpeg uses Desktop Duplication with a bounded rectangle and the recording-only
`--recordable` overlay. The crop excludes other Notepad tabs; the character can
extend above the crop when operating the toolbar.

The whole-recording frame sheet and action transitions were inspected. The final
run has one active character, typing gestures, menu changes, breathing and stretching.
Raw intervals, receipts and capture logs accompany the MP4 and are excluded from Git.

The Codex MCP entry `tobkiri-computer-use` was installed and its exposed
`tobkiri_windows`, `tobkiri_observe`, `tobkiri_cursor` and `tobkiri_act` tools were exercised.
A final additional line was inserted using those actual Codex tools.
The disposable Windows fixture separately verified text, Increment, Apply and scroll.
Tests did not modify other Notepad documents.

## Fixes found through recording

- Removed an instantaneous 84px body jump on reversal. Turning interpolates joints
  without shrinking the circular head.
- Motion thumbnails update each render frame instead of approximately 12.5fps.
  The FPS indicator uses unclamped elapsed time.
- Corrected 150% Windows DPI mapping between screenshots, virtualized Win32 frames
  and Electron DIP. Fixed false stale-geometry errors in Notepad.
- Added bounded arrival synchronization. Delayed UDP port-unreachable errors no
  longer abort a new renderer wait immediately after its restart.
- Fixed Japanese Windows stdio encoding so the registered MCP initializes in UTF-8.
- Character-only cursor movement reports its own following state without querying
  the disabled native marker's null position. This fixes a Cua output-schema error;
  it does not claim pixel-level position verification.

The earlier Studio-only `final-smooth` recording measured 58.44 renderer fps and
a 166.5ms worst frame. It used a different capture path and workload; the final
real-app result does not establish a universal performance improvement.

## Limits and reproduction

The 18 added motion phrases include anticipation, lift, landing and recovery.
Tests sample every phrase across loop boundaries and check the pelvis lift and
return to the rest pose. The new idle sequence includes occasional hip lifts,
bounces, looks and yawns. `node tests/motions-preview.mjs` creates an eight-second
headless preview of six new motions using the real Character renderer. This is an
animation preview, not an additional real-application operation recording.
The hip-lift contact sheet was inspected from preparation through landing.

This is an editable procedural stick figure, not illustrated MV animation.
Measurements apply to this machine and scene. Mixed-DPI multi-monitor layouts,
macOS native overlays, protected desktops and exclusive fullscreen remain unverified.
Input support depends on Cua: this Notepad session refused some pixel clicks as busy;
semantic controls and text worked. Animation never turns refusal into success,
sends global fallback input or retries an unknown effect.

Run `npm test`, `npm run test:ui`, `npm run test:desktop` and the Windows Python suite.
`npm run record -- motion-check` records the Studio demo. For authorized real-app
recording use `tests/live-record.mjs` as described in the README. Observation and
input are separate MCP actions; the recording script itself does not operate apps.

## Independent Cursor Studio export — 2026-10-08

`npm run test:export` exercises the actual offscreen Electron editor and save IPC
with temporary isolated settings. `TOBKIRI_CURSOR_PACK` publishes cursor+pet
defaults, and saving updates the JSON. Every native window stays invisible.
This is presentation export only: no Browser process, desktop input, visible
window, global shortcut, tray or existing user profile is used. The test artifact
is ignored and the temporary settings are removed.
