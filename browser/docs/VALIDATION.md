# Validation record

## Unified Computer + Browser — 2026-10-08

Baseline: Browser Use PR #1, commit `fbc67807a57b54d88a28925dcc4091d21c48981d`.
This checkout imports its automation runtime; historical datasets and generated
test artifacts are excluded. Earlier records below retain their original scope.

Host: Windows, Node.js 22.23.1, isolated headless Chromium 153.0.8010.12.

- Node tests: **66 passed** (9 broker/shared-pack tests, 47 browser tests,
  10 Studio engine/protocol tests). Browser permission unit tests use Chrome API
  mocks; they are distinct from installed-extension acceptance.
- Installed MV3 extension + actual browser MCP + unified stdio broker:
  **12 acceptance checks passed** on fictional loopback pages. Trusted CDP
  move/click/type and empty replacement, explicit DOM click/type/check/Enter,
  native select, eval, DOM scroll, screenshots, shared Studio rendering/settings,
  ownership, active-tab protection, popup pause and debugger disconnection were
  exercised. The native backend in this browser test is a schema-routing fixture.
- The granted browser tab stayed `active:false`; **zero tab activation events**
  occurred during background operations, and the human fixture kept its focused
  field and text. With this Chromium/debugger combination `document.hidden` was
  **false**. This is background-tab evidence, not natural hidden-rAF throttling
  coverage. No focus emulation was enabled by the test or extension.
- Shared renderer DOM/canvas: **23 checks passed**, including CSS coordinates,
  DPI backing resolution, pointer-events passthrough, custom PNG, pet-only mode,
  snapshot exclusion, viewport edges, expiry and resize invalidation. Suspended
  rAF/hidden lifecycle is simulated explicitly in this separate rendering test.
- Actual Electron Studio save IPC was exercised with offscreen rendering and
  isolated settings: startup publishes cursor+pet defaults, saving changes
  updates the shared pack, and every native window remains invisible. This tests
  the publisher rather than replacing it with a fake file writer.
- Production native Cua 0.28.2 + combined MCP smoke: **95 tools**, skill resource,
  browser-offline refusal and retained native connection verified. No desktop
  input occurs in that smoke test.
- Windows Python: **250 passed**. Existing opt-in live acceptance also passed
  all required checks on WindowsComputerFixture, including covered background
  capture/click/type/UIA scroll and approved foreground scroll/drag with restoration.

Input probes now count required trusted events; beforeinput or a partial press
cannot by itself prove click/type/drag delivery. Lost page context reports an
uncertain result. DOM input is an explicit `inputRoute: "dom"` choice, with
`trusted:false`, rather than an automatic second attempt. An unacknowledged
navigation is not replayed. A missing debugger attachment revokes the grant.

Run from the repository root: `npm test`, `npm run test:browser`,
`npm run test:native`, `npm run test:studio`. Shared extension renderer code is generated locally from
Studio sources and excluded from Git. Images/reports are local under
`integration/artifacts`; they contain fictional test pages, no pairing secrets.

Not claimed: headed user Chrome/Edge, real user profiles, arbitrary sites,
production host UI, native browser dialogs, full cross-origin iframe DOM,
service-worker longevity, or macOS integrated GUI delivery. Running macOS pytest
on this Windows host gave 247 passes and 27 failures in OS-specific/runtime/
encoding paths; this is not a macOS validation result. Use a macOS host for the
documented macOS suite and fixture acceptance.

## Historical standalone Browser Use records

## Brand icon and visible pointer — 2026-10-03

Test host: macOS, Node.js 25.5.0. No production dependencies were installed.

- `npm test`: **45 passing, 0 failing**. The Chrome APIs remain mocks; the real
  local bridge and stdio MCP are exercised by the existing suite. New coverage
  includes `browser_move` target validation, isolated-world cursor dispatch,
  owner/pause/active-tab protection, dropped mouse-event delivery, drag feedback,
  and empty-string replacement dispatch.
- **Actual browser DOM rendering:** the local `tests/cursor-preview.html`
  fixture passed **17 checks in Google Chrome and the Codex in-app browser**.
  It imports the production page operations, cursor renderer, theme and bundled
  Lucide icon. Checks cover CSS-coordinate placement, pointer-events passthrough,
  pressed-state clearing, singleton reuse, resistance to page CSS, snapshot
  exclusion, input focus, empty DOM replacement, container scrolling, viewport
  edges, invalid coordinates and idle cleanup.
- **Visual inspection:** screenshots of the fixture confirm the blue pointer
  with a white outline on light and dark backgrounds. The popup preview uses the
  production HTML/CSS/JS with fictional, read-only extension state and displays
  the supplied artwork in its header. The original image is preserved; packaged
  PNGs are 16/32/48/128 pixels and are referenced by the manifest.
- The Lucide SVG is pinned and bundled locally with its license. Rendering uses
  a Shadow DOM overlay, synchronous CSS-pixel placement and no OS cursor or tab
  activation. The overlay expires after 2.4 seconds in production. The visual
  fixture has an optional 60-second hold for screenshot inspection only.

These browser checks validate rendering and DOM helpers, **not** the installed
MV3 extension, `chrome.debugger` transport, real hidden-tab mouse-event delivery,
native toolbar icon display or service-worker lifecycle. Those paths were not
run on this host for this change. `browser_move` verifies delivered mouse events
and reports `INPUT_NOT_APPLIED` if the host drops them; no synthetic CSS-hover
fallback is claimed. This change is an icon/cursor improvement, not full feature
parity with Codex's Browser/Chrome tool.

# Validation record — 0.2.9

## 0.2.8–0.2.9 changes — mock suite + LIVE verification on Windows Vivaldi (2026-09-21)

Driven through the real MCP bridge and the hot-reloaded unpacked extension on the
author's Windows Vivaldi session, with hidden background tabs.

- **Fixed — hidden-tab screenshots had no working path on this host.** `browser_screenshot`
  now escalates: plain `Page.captureScreenshot` → `captureBeyondViewport` with a viewport
  clip → `Page.startScreencast` frame capture → **`Page.printToPDF`**. Per-call CDP timeouts
  are bounded (~4s each) so the whole chain fits inside the command deadline.
- **Live-verified on this host (Vivaldi):** plain capture, `captureBeyondViewport`,
  `Page.setWebLifecycleState:active`+capture, and screencast (acknowledged but zero frames
  delivered) ALL time out on hidden tabs — the host never rasterizes background tabs.
  `fromSurface:false` is rejected outright ("Only screenshots from surface are allowed").
  **`Page.printToPDF` succeeded** on a hidden tab — the print pipeline rasterizes
  offscreen without a compositor surface. When only the PDF path works, the tool returns
  `{via:'printToPDF', pdf:{data, mimeType:'application/pdf'}}` instead of `image`.
- **Added — `browser_pdf`.** Explicit print-to-PDF capture (`printBackground`/`landscape`/
  `scale` params); same guard stack, read-only, bounded to ~22MB.
- Screencast fallback no longer leaks an unhandled rejected waiter when
  `startScreencast` itself fails; `stopScreencast`/`frameAck` cleanup is best-effort.
- **Added — `saveAs` on `browser_screenshot`/`browser_pdf`.** The MCP client writes the
  capture under `capturesDir` (or `<configDir>/captures`) and replies with
  `{imageSaved|pdfSaved:{path,bytes}}` instead of inline base64 — bulk captures no longer
  pay the JSON transcript cost. Relative paths only; absolute paths and `..` segments are
  rejected at validation and re-checked at write time.
- Live-verified on this host: `browser_screenshot` on a hidden tab returned the real
  rendered page via `via:'printToPDF'` after all image paths timed out.
- Mock suite: 40 passing / 0 failing (screenshot escalation chain, PDF fallback,
  `browser_pdf`, and saveAs disk-write/traversal are covered; the mock cannot reproduce
  "ack-but-no-frames" timing).

## 0.2.7

## 0.2.7 changes — Node mock-suite only, NOT verified on a real host (2026-09-21)

Field reports from dataset-collection sessions (Windows, Vivaldi) drove these fixes. Only
`npm test` (mock Chrome APIs + real bridge) has been run — no installed-extension
verification was performed for this version.

- **Fixed — revoked grants orphaned tabs.** `browser_tab_close` previously ran the full
  grant guard, so a tab whose grant was auto-revoked (CDP_TIMEOUT / debugger detach)
  returned `NOT_GRANTED` and could never be closed or reused — dead tabs accumulated.
  Close now requires only session ownership + workspace-not-paused + active-tab
  protection (closing is cleanup, not page interaction); it also works while paused.
- **Added — `browser_tab_regrant`.** The CDP_TIMEOUT message told callers to "explicitly
  re-grant" but no such command existed. Re-grant restores only a grant the same session
  already held, in the same still-owned workspace — it never grants an unrelated tab and
  is not a blind retry (the timed-out action may still have applied; inspect first).
- **Fixed — `PARTIAL_TAB_CREATION` misreport.** `browser_tab_open`/`workspace_create`
  reported partial creation even when the tab was fully created, grouped and granted and
  only the first navigation failed. Structural failures still throw
  `PARTIAL_TAB_CREATION`; a failed initial navigation now returns the tab handle with a
  `warning` (and `revoked` state) so callers can inspect/retry.
- **Improved — dom-click fallback fidelity.** The fallback now dispatches the full
  pointerover/mouseover/pointermove/mousemove → focus → pointerdown/mousedown →
  pointerup/mouseup → click sequence with real coordinates, `detail:1` and pointer
  identity, instead of bare `el.click()` (detail:0, no coords) that delegated handlers
  could ignore.
- Not fixed (host-level, documented): `CDP_TIMEOUT` on unacknowledged debugger commands
  still auto-revokes by design — a timed-out input must never be blindly retried. The
  recovery path (regrant/close) is what was missing, and now exists.

# Validation record — 0.2.4

## What was actually run

**Date:** 2026-09-19 Japan time (0.1.0 baseline). **Build/test platform:** Linux, Node.js 22.16.0, Chromium 144.0.7559.96, Xvfb for headed browser tests. The 0.2.0 additions passed the Node suite on the author's machine; installed-extension verification is noted below.

### 0.2.1–0.2.4 changes — verified on Windows + Vivaldi installed extension, 2026-09-19

Driven end-to-end through the real MCP bridge and the real unpacked extension on Windows, Vivaldi (Chromium-based), with hidden background tabs. `npm test`: 34 passing, 0 failing.

- **Fixed — fresh-hidden-tab wedge.** `browser_workspace_create`/`browser_tab_open` with a URL previously wedged 3/3 on this host (`PARTIAL_TAB_CREATION: CDP_TIMEOUT`, grant revoked). The create path now waits for the new tab to leave the loading state, `chrome.debugger.attach` and the idempotent init commands are bounded and retried once on a fresh session, and `Page.navigate` retries once after re-attach. Verified: URL-at-creation now succeeds repeatedly on the same host.
- **Fixed — false success on dropped trusted input.** On this host, `Input.*` dispatch on hidden tabs sometimes acknowledges while no DOM input event arrives (previously `inserted:true`/`clicked:true` with no effect). Capture-phase listeners are now armed in the isolated world before dispatch and checked afterwards (`armInput`/`inputProbe` page ops). When the probe proves zero events arrived, click/type/press fall back to DOM-level application (`elementFromPoint().click()`, native value setter + `input` event, synthetic `KeyboardEvent`/`execCommand('insertText')`) — proven non-delivery means this cannot double-apply. Such results report `trusted:false`/`via:'dom-*'` honestly because fallback events are `isTrusted:false` and cannot run browser default actions (e.g. Tab focus traversal). If the fallback also fails, the original `INPUT_NOT_APPLIED` still propagates; the grant survives either way. `browser_drag` has no meaningful DOM equivalent and still returns `INPUT_NOT_APPLIED`. Verified on this host end-to-end: `browser_type` fell back (`via:'dom-type'`) and the text was confirmed in the DOM; `browser_press` Enter fell back (`via:'dom-key'`, `submitted:true`) and the form POST actually navigated the hidden tab to the httpbin response echoing the typed value; `browser_check`/`browser_click` fell back (`via:'dom-click'`) and checkbox/radio state was confirmed applied. When trusted input did arrive, results returned normally with no `trusted:false` marker. Delivery on this host is flaky — both outcomes were observed within one session.
- **Fixed — screenshot timeout revoked the grant.** `Page.captureScreenshot` no longer revokes on an unacknowledged read-only capture; a timeout now returns `SCREENSHOT_UNAVAILABLE` and keeps the grant. On this host a hidden-tab viewport capture did complete, so the timeout path itself was not re-triggered here. `fromSurface:false` is rejected by this host ("Only screenshots from surface are allowed"), so no alternate capture mode exists.
- Remaining host limitation: hidden-tab input delivery on Windows Vivaldi is inconsistent (keyboard/`insertText` traffic is more likely to be dropped than mouse). Tools now report delivery truthfully and fall back to DOM-level application where meaningful; `trusted:false` marks those results because sites that gate on `isTrusted` may still ignore them. `Emulation.setFocusEmulationEnabled` was tested on this host and does NOT restore input delivery — it is deliberately not enabled (it would only make `document.hasFocus()` lie). Hidden-tab `Page.captureScreenshot` is likewise flaky; the tool now retries once on a fresh debugger session before returning `SCREENSHOT_UNAVAILABLE`.
- Visual feedback: successful clicks draw a self-removing ripple ring at the CSS-pixel point; DOM fallbacks additionally flash a highlight box on the target element. These are in-page overlays (visible to the user and in screenshots), not an OS cursor.
- Dev reload: the popup footer has a "⟳ 更新" button that calls `chrome.runtime.reload()` (response is delivered before the SW dies). Additionally the background SW hashes its own source files on each alarm poll and self-reloads once an unpacked copy's files stay changed across two polls — a packed install can never see a hash change, so this is a no-op outside development.

### 0.2.0 changes

`browser_eval` and `browser_cdp` were added at the owner's explicit request. `browser_eval` sends `Runtime.evaluate` with no `contextId`, so it runs in the page's MAIN world (DevTools-console equivalent). `browser_cdp` passes an arbitrary CDP method/params straight to the granted tab's debugger session. Both route through the unchanged guard stack (owner, revocation, pause, deadline, active-tab protection) and the bounded CDP acknowledgement timeout.

New Node tests cover: schema bounds for both tools (expression/method required, unknown fields rejected, free-form `params` object accepted), main-world dispatch (no isolated-world `contextId`), raw method/params passthrough, and enforcement of grants, cross-session isolation and active-tab protection.

**Installed-extension check on the author's Vivaldi 8.2 (Chromium 143) session, 2026-09-19:** a fresh `cli.mjs mcp` stdio client was driven end-to-end through the real bridge and the reloaded unpacked extension. Verified: both tools appear in `tools/list`; `browser_eval` returns `2` for `1+1`, the real `location.href`, and `done` for a resolved promise; a canvas-2d smiley drawn by eval on jspaint.app produced ~3,400 non-white pixels (visually confirmed); a thrown error maps to `PAGE_ERROR`; `browser_cdp` `Page.getFrameTree` returns the raw frame tree; ungranted tabs still reject with `NOT_GRANTED`. Note: `replMode` was removed because it silently disabled `awaitPromise` on this engine. The repeated `CDP_TIMEOUT` wedges seen with hidden-tab `Input`/`captureScreenshot` traffic on this Vivaldi build remain a host-level issue, unrelated to the new dispatch paths.

### 1. Node tests — 33 passing, 0 failing

`npm test` uses Node's built-in test runner and requires no npm install. The test-runner total includes a parent integration test and its subtests. See `test-results/node-tests.tap`.

The real local HTTP bridge and real stdio MCP implementation are exercised: schema/URL validation, auth, Origin/Host rejection, extension-vs-admin endpoint separation, offline errors, session routing, result delivery, cancellation on release, MCP initialization/version negotiation/listing/error handling, and screenshot pixel-dimension parsing.

The production `extension/background.mjs` is also imported and driven against **mock Chrome APIs** and the real bridge. Those checks cover new-tab consent, explicit inactive creation, group metadata, session/tab isolation, navigation dispatch, front-tab protection, global/workspace pause, CDP input dispatch, clipboard/shortcut rejection, DOM scroll dispatch, protection for ungranted human tabs added to a group, popup-sender checks, paused waits, cleanup/auto-discard restoration, group recreation, debugger revocation and session release.

**These are not tests of Chrome's actual extension APIs or the actual MV3 lifecycle.**

### 2. Real hidden-tab operation core — 12 passing, 0 failing

`tests/cdp_core.py` launches real headed Chromium under the existing managed policy. It uses allowed in-memory `about:blank` fixtures via CDP; it does not navigate to external websites or change the policy. It does **not** use Playwright's default focus emulation, and it does not turn off background throttling.

The test asserts that the human tab stays `visibilityState = visible`, the target stays `visibilityState = hidden`, and the human input element retains focus, including while foreground input and background input run concurrently.

The actual production `extension/page-ops.mjs` runs in a CDP isolated world. The following are checked: real hidden/visible distinction, DOM snapshot/redaction, concurrent text entry/clicking, trusted input events, hidden-tab screenshot, stale refs/open Shadow DOM, checkbox/select, clearing input with empty text, Enter/local form/wait predicate, offscreen element targeting/DOM scrolling, coordinate drag, and full-page screenshots.

See `test-results/cdp-core-report.json`, `background-tab.png` and `full-page.jpg`. The screenshots show fictional fixture data, not a real user's browser.

This verifies the **underlying tab-targeted CDP behavior**, not the `chrome.debugger` transport or the complete MCP→installed-extension path.

### 3. Installed-extension E2E — blocked by environment, not counted as passed

The environment's managed Chromium policy has `ExtensionInstallBlocklist: ["*"]`. The policy was inspected and **not modified or bypassed**. The test returns code 77 and writes `test-results/browser-e2e-report.json` explaining the block.

`tests/browser_e2e.py` is included for running against an extension-enabled local Chromium. It is intended to exercise actual popup pairing, stdio transport, native tab groups, foreground protection, trusted events, screenshot MCP responses, multiple sessions and revocation. Because that script could not run end-to-end here, its completeness and platform-specific behavior are themselves unverified.

### 4. Popup rendering preview

`docs/ui-preview.png` is a rendering of the actual popup HTML/CSS/JS with **simulated extension state**, using an in-memory browser document. It is for reviewing layout only, not evidence of extension installation or connectivity. Pairing secrets are not in the image.

## Issues discovered and addressed

A direct CDP `Input.dispatchMouseEvent` mouse-wheel request on a genuinely hidden tab did not acknowledge within the test timeout. It worked under more permissive test focus-emulation settings, which would have hidden the problem. The production scroll tool was therefore changed to instant DOM scrolling, without activating the target. All CDP operations now also have a bounded acknowledgement timeout that revokes the grant on an uncertain result.

Additional review addressed accidental collapse of a group containing an ungranted active human tab, stale group IDs after closing the last tab, auto-discard cleanup when returning a tab, same-extension-ID collisions across browser profiles, Retina image-to-CSS coordinate metadata, and verification of requested checkbox state.

## Unverified / not claimed

Actual extension installation and native popup/runtime behavior; managed-policy variations; service-worker suspend/restart over long real sessions; Chrome on macOS or Windows (0.2.0 was hand-verified on macOS Vivaldi only; 0.2.1 was verified on Windows Vivaldi as noted above); Edge/Brave; real websites beyond the single jspaint.app check and the Windows session above; external navigation and login flows; popups/native UI; full iframe handling; stress/load/security audit.

A successful local acceptance test in the user's chosen browser is still required. Start on a test page, not a financial account, checkout or irreversible action.
