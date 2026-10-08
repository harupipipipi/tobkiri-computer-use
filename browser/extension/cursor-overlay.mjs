/** Serialized into the CDP isolated world. All assets/theme values are explicit arguments. */
export function renderCursor(action, point, theme) {
  let state = globalThis.__tobkiriCursor;
  function remove() {
    if (!state) return;
    clearTimeout(state.timer);
    document.removeEventListener('visibilitychange', state.onVisibility);
    window.removeEventListener('resize', state.onResize);
    state.host.remove();
    if (globalThis.__tobkiriCursor === state) delete globalThis.__tobkiriCursor;
  }
  if (action === 'hide') { remove(); return {rendered: false}; }
  const {x, y} = point;
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) {
    remove(); return {rendered: false};
  }
  if (!state?.host.isConnected) {
    remove();
    const host = document.createElement('div');
    host.setAttribute('data-tobkiri-cursor', '');
    host.setAttribute('aria-hidden', 'true');
    // Page CSS cannot restyle the glyph; important host properties also resist broad * rules.
    const styles = {all:'initial', position:'fixed', left:'0', top:'0', width:'0', height:'0',
      display:'block', overflow:'visible', 'z-index':'2147483647', 'pointer-events':'none',
      'user-select':'none', transform:'none', zoom:'1', opacity:'1', visibility:'visible'};
    for (const [key, value] of Object.entries(styles)) host.style.setProperty(key, value, 'important');
    const shadow = host.attachShadow({mode:'open'});
    const holder = document.createElement('div');
    holder.style.cssText = 'position:absolute;pointer-events:none;user-select:none;';
    const ring = document.createElement('div');
    ring.style.cssText = `position:absolute;left:-14px;top:-14px;width:28px;height:28px;border:2px solid ${theme.color};border-radius:50%;box-sizing:border-box;background:${theme.color}20;pointer-events:none;`;
    ring.hidden = true;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const hotspot = {x:theme.icon.hotspot.x * theme.size / 24, y:theme.icon.hotspot.y * theme.size / 24};
    for (const [key, value] of Object.entries({viewBox:theme.icon.viewBox, width:theme.size, height:theme.size,
      fill:theme.color, stroke:theme.outline, 'stroke-width':1.8, 'stroke-linecap':'round', 'stroke-linejoin':'round', 'aria-hidden':'true'})) svg.setAttribute(key, String(value));
    svg.style.cssText = `position:absolute;left:${-hotspot.x}px;top:${-hotspot.y}px;overflow:visible;pointer-events:none;filter:drop-shadow(0 1px 2px #0007);transform-origin:${hotspot.x}px ${hotspot.y}px;`;
    for (const d of theme.icon.paths) { const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', d); svg.append(path); }
    holder.append(ring, svg); shadow.append(holder);
    (document.documentElement || document.body).append(host);
    state = {host, holder, ring, svg, timer:null, expiresAt:0, x, y};
    state.onVisibility = () => { if (Date.now() >= state.expiresAt) remove(); };
    state.onResize = () => { if (state.x >= innerWidth || state.y >= innerHeight) remove(); };
    document.addEventListener('visibilitychange', state.onVisibility);
    window.addEventListener('resize', state.onResize);
    globalThis.__tobkiriCursor = state;
  }
  state.x = x; state.y = y; state.expiresAt = Date.now() + theme.idleMs;
  state.host.dataset.action = action;
  state.host.dataset.x = String(x); state.host.dataset.y = String(y);
  // Synchronous CSS-pixel placement: hidden-tab rAF/animations must never gate the drawing.
  state.holder.style.left = `${x}px`; state.holder.style.top = `${y}px`;
  const pressed = action === 'down' || action === 'drag';
  state.svg.setAttribute('fill', pressed ? theme.pressedColor : theme.color);
  const scale = pressed ? .88 : 1;
  // Turn inward near viewport edges while keeping the SVG's hotspot at the same CSS point.
  state.svg.style.transform = `scale(${(x + theme.size > innerWidth ? -1 : 1) * scale},${(y + theme.size > innerHeight ? -1 : 1) * scale})`;
  state.ring.hidden = !['down', 'drag', 'click'].includes(action);
  clearTimeout(state.timer);
  state.timer = setTimeout(remove, theme.idleMs);
  return {rendered:true, x, y, action};
}
