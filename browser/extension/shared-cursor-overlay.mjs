/** Serialized into an isolated page world. Browser points remain CSS viewport
 * pixels; hidden tabs are never projected onto a native desktop window. */
export function renderSharedCursor(action, point, pack, runtime, idleMs = 3500) {
  let state = globalThis.__tobkiriSharedCursor;
  function remove() {
    if (!state) return;
    clearTimeout(state.timer);
    cancelAnimationFrame(state.frame);
    document.removeEventListener('visibilitychange', state.onVisibility);
    window.removeEventListener('resize', state.onResize);
    state.host.remove();
    if (globalThis.__tobkiriSharedCursor === state) delete globalThis.__tobkiriSharedCursor;
  }
  if (action === 'hide') { remove(); return { rendered: false }; }
  const { x, y } = point;
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) {
    remove(); return { rendered: false };
  }
  if (!state?.host.isConnected) {
    remove();
    const host = document.createElement('div');
    host.setAttribute('data-tobkiri-cursor', '');
    host.setAttribute('aria-hidden', 'true');
    const styles = { all: 'initial', position: 'fixed', left: '0', top: '0',
      width: '0', height: '0', display: 'block', overflow: 'visible',
      'z-index': '2147483647', 'pointer-events': 'none', 'user-select': 'none',
      transform: 'none', zoom: '1', opacity: '1', visibility: 'visible' };
    for (const [key, value] of Object.entries(styles)) host.style.setProperty(key, value, 'important');
    const shadow = host.attachShadow({ mode: 'closed' });
    const canvas = document.createElement('canvas');
    // A bounded canvas around the point, independent of viewport/DPI size.
    canvas.style.cssText = 'position:absolute;left:-280px;top:-280px;width:560px;height:560px;pointer-events:none;';
    shadow.append(canvas);
    (document.documentElement || document.body).append(host);
    state = { host, canvas, character: new runtime.Character(pack, 280, 280),
      timer: null, frame: null, expiresAt: 0, last: performance.now(), x, y };
    state.onVisibility = () => {
      if (Date.now() >= state.expiresAt) remove();
      else { draw(); schedule(); }
    };
    // A resize invalidates the old browser viewport coordinates.
    state.onResize = remove;
    document.addEventListener('visibilitychange', state.onVisibility);
    window.addEventListener('resize', state.onResize);
    globalThis.__tobkiriSharedCursor = state;
  }
  function draw() {
    const dpr = Math.min(devicePixelRatio || 1, 2), size = Math.round(560 * dpr);
    if (state.canvas.width !== size) state.canvas.width = state.canvas.height = size;
    const ctx = state.canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, 560, 560);
    state.character.draw(ctx, { shadow: false });
  }
  function frame(now) {
    state.frame = null;
    if (!state.host.isConnected || Date.now() >= state.expiresAt) { remove(); return; }
    state.character.update(Math.min((now - state.last) / 1000, .05));
    state.last = now;
    draw();
    schedule();
  }
  function schedule() {
    if (!document.hidden && state.frame === null) state.frame = requestAnimationFrame(frame);
  }
  state.character.pack = pack;
  // Place the hotspot synchronously, including when the tab's rAF is suspended.
  state.x = x; state.y = y;
  state.character.x = state.character.tx = 280;
  state.character.y = state.character.ty = 280;
  state.host.style.setProperty('left', `${x}px`, 'important');
  state.host.style.setProperty('top', `${y}px`, 'important');
  state.host.dataset.action = action;
  state.host.dataset.x = String(x); state.host.dataset.y = String(y);
  state.host.dataset.renderer = 'cursor-studio';
  const motion = ({ down: 'click', click: 'click', drag: 'drag', type: 'type',
    key: 'key', scroll: 'scroll_down', scroll_up: 'scroll_up' })[action] || 'idle';
  state.character.play(motion, .8);
  state.character.pose = runtime.poseFor(motion, .1, pack);
  state.expiresAt = Date.now() + idleMs;
  clearTimeout(state.timer);
  state.timer = setTimeout(remove, idleMs);
  draw();
  schedule();
  return { rendered: true, renderer: 'cursor-studio', x, y, action };
}
