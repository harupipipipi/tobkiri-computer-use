# Source baseline

The browser runtime, MV3 extension, icons, tests and MIT license were imported
from [tobkiri-browser-use PR #1](https://github.com/harupipipipi/tobkiri-browser-use/pull/1),
commit `fbc67807a57b54d88a28925dcc4091d21c48981d`
(`feat/brand-icon-visible-cursor`). This is the requested PR baseline, rather
than the older main-branch cursor.

The import includes browser automation only. Unrelated data collection skills,
evaluation datasets, historical screenshots and raw test reports are excluded.
Historical validation prose is retained in `docs/VALIDATION.md` with its original
host/date scope. New integration evidence is documented separately there.

Local changes add the shared Cursor Studio renderer, presentation-only pack
loading, explicit `inputRoute`, and disconnected-debugger handling. The original
standalone `browser_*` interface is retained. The combined MCP exposes those
operations as `tobkiri_tabs_*` to avoid collisions with original Cua tools.
