# Working on Tobkiri Tabs

Keep the following properties when modifying this project:

1. Never add implicit tab/window foreground activation or OS mouse/keyboard/clipboard use. A site may still open native UI; document this distinction.
2. Never let an MCP tool grant an unrelated existing tab, enumerate private tabs, disable protection, enable new-tab creation, or change pause settings.
3. Keep the explicit owner/grant ledger separate from tab-group membership. Group collapse must protect ANY active tab in the group, including a manually inserted ungranted tab.
4. Every browser command re-checks owner, revocation, pause, deadline and human-active-tab protection. A timed-out input must never be blindly retried.
5. Maintain isolated-world page helpers and JSON-encode all arguments for the structured ops. `browser_eval` (main-world) and `browser_cdp` (raw passthrough) are deliberately exposed per an explicit owner decision: the MCP client is trusted inside a granted tab. They still route through the full guard stack — owner, revocation, pause, deadline and active-tab protection — so never bypass it.
6. `npm test` runs without installing dependencies. Chrome API mocks do not constitute MV3 integration evidence.
7. `tests/cdp_core.py` tests real hidden-page CDP behavior with focus emulation OFF. It must not override managed browser policy. `tests/browser_e2e.py` is the distinct, actual installed-extension E2E.
8. Preserve the distinction between DOM scrolling/native select events and trusted CDP input. Hidden-tab wheel commands were observed to stall; do not “fix” that by activating the tab.
9. Update `docs/VALIDATION.md` honestly after changes. Never claim macOS, Windows, real-host or real-site coverage from an isolated Linux fixture test.
10. Runtime code is plain ESM and dependency-free. Tests that need a browser use optional Python test dependencies, never production dependencies.

Tests and example pages contain fictional data. Do not commit local configs, tokens, user-profile directories or real account screenshots.
