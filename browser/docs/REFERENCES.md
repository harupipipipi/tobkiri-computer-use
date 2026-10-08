# Primary references

Checked while building this version on 2026-09-19 (Japan time). Links are reference documentation, not bundled dependencies.

- Chrome debugger API: https://developer.chrome.com/docs/extensions/reference/api/debugger
  Target tabs with `tabId`; permitted CDP domains; detach events; strong debugger permission.
- Chrome tabs API: https://developer.chrome.com/docs/extensions/reference/api/tabs
  `tabs.create({active:false})`, tab IDs, grouping, autoDiscardable.
- Chrome tabGroups API: https://developer.chrome.com/docs/extensions/reference/api/tabGroups
  Group naming, colors, collapsed state and group removal.
- MV3 service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
  Idle lifetime, extension API activity, persistent session state and bounded fetch response time.
- Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/
  Page, DOM, Runtime and Input commands. `browser_cdp` exposes generic raw CDP to the model within a granted tab.
- MCP 2025-11-25 lifecycle: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- MCP 2025-11-25 transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
  Newline-delimited JSON-RPC stdio, version negotiation, stdout cleanliness and shutdown.
- Related existing OSS: https://github.com/hangwin/mcp-chrome
  Extension-based automation of a user's existing Chrome. Its code is not bundled here.
- Another related server project: https://github.com/BrowserMCP/mcp
  Mentioned only as adjacent work; this archive does not claim its extension has any particular source-availability or background-focus guarantee.

This implementation intentionally uses a small, dependency-free stdio MCP subset rather than assuming SDK v1/v2 package names or pulling unverifiable dependencies in the build environment. It does not advertise unsupported MCP features or the latest protocol revision.
