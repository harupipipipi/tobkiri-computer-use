import { Character, fitCanvas } from "./engine.js";
const canvas = document.querySelector("canvas"),
  characters = new Map();
const query = new URLSearchParams(location.search),
  origin = [Number(query.get("x")), Number(query.get("y"))];
let { config, enabled } = await window.companion.getState();
window.companion.onConfig((state) => {
  config = state.config;
  enabled = state.enabled;
  for (const c of characters.values()) c.pack = config;
});
window.companion.onEvent((event) => {
  if ((config.mode === "pointer") !== (event.source === "pointer")) return;
  const key = event.source + ":" + event.session,
    local = {
      ...event,
      point: [event.point[0] - origin[0], event.point[1] - origin[1]],
    };
  if (!characters.has(key)) {
    if (characters.size >= 64) return;
    characters.set(key, new Character(config, ...local.point));
  }
  characters.get(key).receive(local);
});
let last = performance.now(),
  needsClear = false;
function frame(now) {
  if (!enabled || characters.size === 0) {
    if (needsClear) {
      const { ctx, width, height } = fitCanvas(canvas);
      ctx.clearRect(0, 0, width, height);
      needsClear = false;
    }
    last = now;
    requestAnimationFrame(frame);
    return;
  }
  const { ctx, width, height } = fitCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  needsClear = true;
  for (const [id, c] of characters) {
    if (now - c.lastSeen > (c.active ? 30000 : 3500)) {
      characters.delete(id);
      continue;
    }
    if ((config.mode === "pointer") !== id.startsWith("pointer:")) continue;
    c.update((now - last) / 1000);
    if (c.pending && c.tx >= 0 && c.tx < width && c.ty >= 0 && c.ty < height) {
      if (Math.hypot(c.x - c.tx, c.y - c.ty) < 3) {
        if (c.pending.posedAt === null) {
          c.play(c.pending.event.action, 2);
          c.pending.posedAt = now;
        } else if (now - c.pending.posedAt >= 140) {
          window.companion.ready(c.pending.event);
          c.pending = null;
        }
      }
    }
    if (c.x > -250 && c.x < width + 250 && c.y > -250 && c.y < height + 250)
      c.draw(ctx, { shadow: false });
  }
  last = now;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
