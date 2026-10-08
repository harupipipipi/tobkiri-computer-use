// Opt-in headless DOM/canvas validation; no desktop or user's profile.
import { chromium } from '../../companion/node_modules/playwright-core/index.mjs';
import { cursorRuntime } from '../../browser/extension/character-runtime.mjs';
import { renderSharedCursor } from '../../browser/extension/shared-cursor-overlay.mjs';
import { pageOp } from '../../browser/extension/page-ops.mjs';
import { defaults } from '../../companion/src/config.js';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 900, height: 700 }, deviceScaleFactor: 1.5 });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.setContent('<!doctype html><style>*{box-sizing:border-box}body{margin:0;background:#edf0f6}button{position:absolute;left:400px;top:320px;width:160px;height:55px}</style><button id="target">Fixture button</button>');
  await page.addScriptTag({ content: `globalThis.runtime=(${cursorRuntime.toString()})();globalThis.render=(${renderSharedCursor.toString()});globalThis.pageOp=(${pageOp.toString()});globalThis.pack=${JSON.stringify({ ...defaults, displayMode: 'both' })};` });
  const result = await page.evaluate(async () => {
    let count = 0;
    const check = (ok, message) => { if (!ok) throw Error(message); count++; };
    const host = () => globalThis.__tobkiriSharedCursor.host;
    const draw = (action, x = 480, y = 347, idle = 3500) => render(action, { x, y }, pack, runtime, idle);
    draw('down');
    check(host().dataset.renderer === 'cursor-studio', 'shared renderer');
    check(document.elementFromPoint(480, 347).id === 'target', 'overlay passes pointer hit tests');
    check(host().shadowRoot === null, 'closed shadow does not enter the AX/DOM ref tree');
    const c = __tobkiriSharedCursor.canvas;
    check(c.width === 840, 'DPI scales canvas resolution while coordinates stay CSS pixels');
    check([...c.getContext('2d').getImageData(0, 0, c.width, c.height).data].some((v, i) => i % 4 === 3 && v > 0), 'real canvas pixels');
    const first = host();
    for (const action of ['move', 'click', 'drag', 'type', 'key', 'scroll', 'scroll_up']) {
      draw(action); check(host() === first && host().dataset.action === action, action + ' reuses singleton');
    }
    check(pageOp('snapshot').elements.every(el => el.name !== pack.name), 'snapshot excludes cursor');
    for (const [x, y] of [[0, 0], [899, 0], [899, 699], [0, 699]]) {
      draw('move', x, y);
      check(host().style.left === x + 'px' && host().style.top === y + 'px', 'edge hotspot remains exact');
    }
    pack.displayMode = 'pet'; draw('type');
    check(__tobkiriSharedCursor.character.pack.displayMode === 'pet', 'pet-only mode');
    // Synthetic lifecycle simulation: intentionally suspend rAF, not a claim
    // that this headless Chromium naturally exposes hidden document visibility.
    render('hide', {}, null, null);
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    let frames = 0;
    const originalRAF = requestAnimationFrame;
    globalThis.requestAnimationFrame = () => { frames++; return 10000; };
    pack.displayMode = 'both'; draw('click', 480, 347, 35);
    check(frames === 0 && __tobkiriSharedCursor.host.isConnected, 'hidden mode draws without rAF');
    await new Promise(resolve => setTimeout(resolve, 65));
    check(!globalThis.__tobkiriSharedCursor, 'idle cleanup without frames');
    globalThis.requestAnimationFrame = originalRAF; delete document.hidden;
    draw('move'); window.dispatchEvent(new Event('resize'));
    check(!globalThis.__tobkiriSharedCursor, 'resize invalidates old viewport coordinates');
    draw('move'); render('move', { x: 900, y: 20 }, pack, runtime);
    check(!globalThis.__tobkiriSharedCursor, 'out-of-viewport removes old position');
    // Use the same custom PNG/hotspot contract as Studio.
    const png = document.createElement('canvas'); png.width = png.height = 32;
    png.getContext('2d').fillStyle = '#ee3344'; png.getContext('2d').fillRect(0, 0, 32, 32);
    pack.cursor = 'custom'; pack.cursorImage = png.toDataURL(); pack.hotspot = [16, 16];
    draw('move'); await new Promise(resolve => setTimeout(resolve, 40)); draw('move');
    check(__tobkiriSharedCursor.character.pack.cursor === 'custom', 'custom PNG shared pack');
    return count;
  });
  await mkdir(fileURLToPath(new URL('../artifacts/cursor-dom/', import.meta.url)), { recursive: true });
  await page.screenshot({ path: fileURLToPath(new URL('../artifacts/cursor-dom/preview.png', import.meta.url)) });
  assert.deepEqual(errors, []);
  console.log(`Shared cursor headless DOM/canvas: ${result} checks passed (hidden lifecycle simulated explicitly).`);
} finally { await browser.close(); }
