const actions = new Set([
  "idle",
  "move",
  "click",
  "double_click",
  "right_click",
  "type",
  "key",
  "scroll_up",
  "scroll_down",
  "drag",
  "hide",
]);
function parseEvent(buffer) {
  if (buffer.length > 4096) return null;
  try {
    const e = JSON.parse(buffer.toString());
    if (
      e.version !== 1 ||
      typeof e.source !== "string" ||
      e.source.length > 80 ||
      typeof e.session !== "string" ||
      e.session.length > 160 ||
      !Number.isSafeInteger(e.seq) ||
      e.seq < 0 ||
      !actions.has(e.action)
    )
      return null;
    if (
      !["anchor", "prepare", "start", "end", "hide"].includes(e.phase) ||
      !["physical", "dip"].includes(e.space)
    )
      return null;
    if (
      !Array.isArray(e.point) ||
      e.point.length !== 2 ||
      e.point.some((n) => !Number.isFinite(n) || Math.abs(n) > 100000)
    )
      return null;
    if (
      !["attempted", "refused", "error", "unknown"].includes(
        e.outcome ?? "unknown",
      )
    )
      return null;
    // Copy only the fields consumed by the renderer; never forward text or arbitrary payloads.
    return {
      version: 1,
      source: e.source,
      session: e.session,
      seq: e.seq,
      action: e.action,
      phase: e.phase,
      space: e.space,
      point: e.point,
      outcome: e.outcome ?? "unknown",
    };
  } catch {
    return null;
  }
}
module.exports = { parseEvent };
