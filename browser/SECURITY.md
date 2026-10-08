# Security boundary / v0.1

This is a locally trusted browser-automation tool, **not an audited security product**.

## Trust model

The Node bridge, the installed extension source, the OS account holding the pairing token, and the MCP host are trusted. Website content is untrusted. An authorized browser tab can contain sensitive account data and perform real transactions with that browser profile's session.

The `debugger` permission is inherently broad. The allowlist is enforced by extension code, not a browser-enforced sandbox around the extension. Modifying the extension or compromising the OS user can defeat it. Do not install an untrusted fork into a sensitive browser profile.

## Implemented protections

- Bind only to numeric loopback `127.0.0.1`. Check the exact Host header. Reject ordinary web origins. Never serve permissive CORS responses.
- Authenticate all HTTP requests using a random 256-bit Bearer token. Compare tokens with constant-time comparison after length validation. Tokens are neither URL parameters nor tool outputs. Setup intentionally shows the private pairing code locally.
- Pair only one extension/browser instance to the broker at a time. Keep credentials in trusted extension storage, not content scripts or webpage globals. No `externally_connectable` permission.
- Use a new bridge-issued owner ID for every MCP process. Tab grants are checked against that owner before every browser command. MCP callers cannot enumerate unshared human tabs or claim a tab by its guessed ID.
- Only the extension's own popup context may grant existing tabs or change safety settings. The MCP tool set cannot disable active-tab protection, global pause, or new-tab-creation restrictions.
- The human grants a **tab**, not a single origin; later HTTP(S) navigations in that same tab are in scope. This is disclosed in the handoff UI. New-tab permission also permits navigating new AI tabs to HTTP(S) sites, including local development services.
- Browser internals, extensions, extension-store pages, embedded URL credentials, `file:`, `data:`, and `javascript:` navigation are rejected. There is no arbitrary JavaScript/CDP, cookie export, filesystem, clipboard, or OS input tool.
- CDP page helpers run in an isolated world. Tool arguments are JSON-encoded, not interpolated as executable selectors/text. DOM refs are invalidated on a new snapshot and navigation; disconnected elements are rejected.
- Serialize commands per tab. Separate tabs can run in parallel. Check ownership, pause state, active-tab protection, cancellation and deadline before each CDP step. An unacknowledged CDP command times out and revokes the grant rather than allowing blind repeated clicks.
- Chrome's user-canceled debugger attachment revokes the grant. The extension does not automatically attach again after that cancellation.
- Bound message sizes, pending commands, sessions, text sizes, element counts, image size, waits and command duration. No automatic replay of disconnected operations.
- Audit stores timestamps, tool names, tab IDs and outcome labels only, capped at 120 records in session storage. No page bodies, input text, passwords, screenshots or token logs. Raw page/tool results are still delivered to the MCP host and can be logged by that host.

## What is NOT guaranteed

This is not a semantic approval engine. The MCP host must request appropriate consent before purchases, posting, deletion, credential entry, transferring funds, or other consequential actions. The extension cannot reliably tell whether an arbitrary site's innocently labeled button will execute a consequential action.

Page content may contain prompt injection. Neither allowlists nor a “trusted event” flag make page instructions trustworthy. `isTrusted` indicates browser-generated input, not authorization or benignness.

Page-generated popups, new windows, native dialogs and site focus behavior are not comprehensively intercepted. The tool itself never requests `active:true`, `windows.update({focused:true})`, `Page.bringToFront` or `Target.activateTarget`, but that does not prove that a site can never interrupt the human.

Active-tab protection is cooperative, not an atomic OS-level lock. A human can change tabs between the final guard check and delivery of a browser event. Pause/cancel/disconnect cannot undo a submitted action or a command already in flight. Inspect state before retrying uncertain operations.

Two conversations sharing the **same MCP process** also share its session capabilities. Isolation is per MCP process, not per natural-language conversation. This tool does not provide hostile multi-tenant isolation against clients that can read the shared local token.

Password/OTP/card input values are suppressed in DOM snapshots, but arbitrary sensitive text elsewhere on an authorized page is not universally redacted. Screenshots expose whatever that page visually renders.

The complete installed-extension path is unverified in this distribution's build environment due to its managed install block. See `docs/VALIDATION.md`; do not represent the supplied unit/mocked tests as a browser security audit.

## Revoke access

Use the popup's pause/release/disconnect controls. `npm run stop` stops the local bridge without closing browser tabs. To rotate the token, stop the bridge, disconnect the extension, remove your local config file, and run setup/pairing again. Do not change enterprise-managed browser policy to install or run this extension.

## Reporting

This source archive is not a published hosted service/repository and has no claimed vulnerability-response address. Report issues privately to the maintainer of the copy you use. Do not attach pairing codes or sensitive browser screenshots.
