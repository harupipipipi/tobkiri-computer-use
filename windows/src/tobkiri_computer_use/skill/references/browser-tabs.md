## Native windows and browser tabs

Keep Cua's normal ladder: observe the requested window, use a fresh AX element,
then screenshot coordinates if AX is incomplete. A browser is still a native
window: `tobkiri_observe` and `tobkiri_act` work on the page currently displayed
inside that exact window, including when another application is in front.
You do not need a CDP/profile connection for these standard Cua operations.
After input, verify its actual effect; OS delivery can be unverifiable.

On Windows Cua 0.28.2, an off-virtual-desktop window can return only title-bar
UIA controls even when its screenshot is available. Treat this as a backend
limitation, not proof that an acknowledged input reached the application. Keep
exact-window checks; do not target a sibling window or switch the user's desktop
as recovery. A separately available Computer tool
can be compared using its own fresh observation.

Use `tobkiri_browser` when exact tab targeting is useful, especially an inactive
tab. Bind using current pid/window_id and keep its browser_id plus native
state.target_id/tab_id. Browser points are viewport CSS pixels, not the native
window screenshot pixels. This path must not select the user's tab.

A `browser_consent_required`, `browser_requires_setup` or `browser_route_unavailable`
refusal affects the tab/CDP route only. It does not mean Cua cannot operate the
browser, and it never disables native window tools. Inspect the requested native
window: if the intended page is already displayed there, continue through AX or
screenshot input. Do not overwrite another page's address, activate a different
tab, or use foreground input merely to recover. Native window input cannot reach
a hidden tab; say so when that distinction matters. Avoid repeating the same
unsuccessful input without a new observation and a reason to change approach.

For existing-profile attachment, `prepare` defaults to `isolated=false`; then
`bind` again with the same browser_id. The host's saved startup grant authorizes
attachment without a new login. Actually changing browser debugging settings
or borrowing physical input still needs the appropriate approval. Ordinary
background window operations do not depend on completing this setup.
When setup itself is requested, the host CLI
`tobkiri-computer-use-setup --existing-profile` configures the dedicated runtime
for Python and MCP. MCP 0.1.6+ can reload after finished updates; ordinary Python
uses a new process. See the runtime update section below.
An isolated launch explicitly uses `isolated=true, allow_launch=true` and the
system Chrome/Edge discovery path; bind its new PID/window. Check created_profile
and launched_browser: already_prepared alone does not prove isolation.

`input_route="trusted"` is virtual CDP input, although Chromium may activate on
that route. Cua can refuse it to preserve background posture. `dom_event` is an
explicit alternative using a current ref; verify whether the page accepts this
synthetic input. A tab-route refusal does not turn into an automatic window click.

Python uses one `browser = computer.browser(pid=PID, window_id=WINDOW_ID)`;
`browser.bind()` returns the native result containing target/tab IDs.
`browser.call("click", target_id=TARGET_ID, tab_id=TAB_ID, ref=REF,
input_route="dom_event")` keeps that same session. Use `"state"` to read back.
These results retain native MCP content/structuredContent; inspect refusal/effect.

Browser cursors report `not_projected` when tab-to-visible-window geometry is
unproven. Never draw a hidden tab's coordinates on the user's visible tab or
claim the cursor followed an action without position evidence.
Starting a page's Auto Play/animation does not generate agent input at each
animated element. Describe it as page playback, not individual agent clicks or
keystrokes. Do not replay a start/stop toggle just because completion is unknown.

