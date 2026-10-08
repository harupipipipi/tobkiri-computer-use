// Opt-in HEADLESS acceptance: a fresh Chromium/Chrome/Edge profile, installed MV3 extension,
// production browser MCP + unified broker, and fictional loopback pages only.
// No user's browser, GUI window, account, pointer, keyboard, or profile is used.
import { chromium, _electron } from '../../companion/node_modules/playwright-core/index.mjs';
import { createRequire } from 'node:module';
import { parseArgs } from 'node:util';
import { createServer } from 'node:http';
import { randomBytes } from 'node:crypto';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { startBridge } from '../../browser/src/bridge.mjs';
import { defaults } from '../../companion/src/config.js';
import { Client } from './client.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { values: options } = parseArgs({ options: {
  browser: { type: 'string', default: 'chromium' }, native: { type: 'boolean' }, studio: { type: 'boolean' },
  extended: { type: 'boolean' }, 'require-trusted': { type: 'boolean' },
} });
assert.ok(['chromium', 'chrome', 'msedge'].includes(options.browser), '--browser must be chromium, chrome or msedge');
const output = resolve(root, `integration/artifacts/browser-live${options.browser === 'chromium' ? '' : '-' + options.browser}`);
await mkdir(output, { recursive: true });
const temp = await mkdtemp(resolve(output, 'run-'));
let context, bridge, local, first, second, studioApp, studio;
const nativeOptions = options.native ? {
  computer: resolve(root, process.platform === 'win32' ? 'windows/.venv/Scripts/tobkiri-computer-use.exe' : 'mac/.venv/bin/tobkiri-computer-use'),
  nativeArgs: ['--surface', 'all', '--approval', 'deny'],
} : undefined;
const checks = [], trusted = {};
const pass = (name, details) => { checks.push({ name, passed: true, ...(details ? { details } : {}) }); console.log('PASS ' + name); };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

try {
  let fixture = await readFile(resolve(root, 'browser/tests/fixture.html'), 'utf8');
  if (options.extended) fixture = fixture.replace('</main>', '<label>Editable <div id="editable" contenteditable="true">old rich text</div></label><button id="gesture">Gesture fixture</button></main>');
  local = createServer((req, res) => {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(req.url === '/human' ? '<!doctype html><title>Human fixture</title><textarea id="human">Human text untouched</textarea>' : fixture);
  });
  await new Promise(resolve => local.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${local.address().port}`;
  const config = { port: 0, token: randomBytes(32).toString('hex'), configDir: temp };
  // Reserve an ephemeral port using the bridge itself; keep numeric Host checks.
  bridge = await startBridge(config); config.port = bridge.server.address().port;
  const configFile = resolve(temp, 'config.json'), packFile = resolve(temp, 'cursor-pack.json');
  await writeFile(configFile, JSON.stringify({ version: 1, port: config.port, token: config.token }), { mode: 0o600 });
  async function savePack(pack) {
    if (studio) await studio.evaluate(pack => window.companion.save(pack), pack);
    else await writeFile(packFile, JSON.stringify(pack));
    assert.deepEqual(JSON.parse(await readFile(packFile, 'utf8')), pack);
  }
  if (options.studio) {
    const require = createRequire(resolve(root, 'companion/package.json'));
    const env = { ...process.env, TOBKIRI_CURSOR_PACK: packFile, TOBKIRI_SMOKE_USER_DATA: resolve(temp, 'studio-settings') };
    delete env.ELECTRON_RUN_AS_NODE;
    studioApp = await _electron.launch({ executablePath: require('electron'), args: [resolve(root, 'companion'), '--smoke-test', '--agent-mode'], env });
    // Electron may create an overlay window before the editor. Only the editor
    // owns save IPC; firstWindow() is not an authority or ordering guarantee.
    for (let n = 0; n < 200 && !studio; n++) {
      studio = studioApp.windows().find(w => w.url().endsWith('/index.html'));
      if (!studio) await delay(100);
    }
    assert.ok(studio, 'Offscreen Studio editor did not load');
    await studio.waitForFunction(() => Boolean(window.companion));
    assert.equal((await studio.evaluate(() => window.companion.getState())).config.displayMode, 'both');
  }
  await savePack({ ...defaults, displayMode: 'both', cursor: 'star', cursorColor: '#ce3452', reducedMotion: true });
  first = new Client(configFile, nativeOptions); await first.init();
  context = await chromium.launchPersistentContext(resolve(temp, 'profile'), {
    headless: true, channel: options.browser, viewport: { width: 1200, height: 800 },
    ignoreDefaultArgs: ['--disable-extensions'],
    // Branded Chrome removed --load-extension. The explicit test-only CDP
    // installation flag is confined to this disposable headless profile.
    args: options.browser === 'chromium'
      ? [`--disable-extensions-except=${resolve(root, 'browser/extension')}`, `--load-extension=${resolve(root, 'browser/extension')}`]
      : ['--enable-unsafe-extension-debugging'],
  });
  if (options.browser !== 'chromium') {
    const cdp = await context.browser().newBrowserCDPSession();
    await cdp.send('Extensions.loadUnpacked', { path: resolve(root, 'browser/extension') });
    await cdp.detach();
  }
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker', { timeout: 15000 });
  const extensionId = worker.url().split('/')[2];
  const popup = await context.newPage(); await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  await popup.locator('#pair-code').fill(`tbt1.${config.port}.${config.token}`);
  await popup.locator('#pair-create').check(); await popup.locator('#pair').click();
  let status;
  for (let n = 0; n < 100; n++) {
    status = await first.tool('tobkiri_tabs_status');
    if (status.connected) break; await delay(100);
  }
  assert.equal(status.connected, true); assert.equal(status.cursor.renderer, 'cursor-studio');
  pass('Installed MV3 extension pairs through its UI with the unified stdio MCP');
  const human = await context.newPage(); await human.goto(base + '/human'); await human.bringToFront(); await human.locator('#human').focus();
  const humanId = await worker.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
  await worker.evaluate(() => { globalThis.testActivations = []; chrome.tabs.onActivated.addListener(e => testActivations.push(e.tabId)); });
  const workspace = await first.tool('tobkiri_tabs_workspace_create', { name: 'Unified fixture', color: 'cyan', url: base + '/fixture' });
  const tabId = workspace.tabId;
  assert.equal(workspace.active, false);
  const agent = context.pages().find(p => p.url() === base + '/fixture'); assert.ok(agent);
  const snapshot = await first.tool('tobkiri_tabs_snapshot', { tabId });
  assert.ok(snapshot.text.includes('AI works here')); assert.ok(!JSON.stringify(snapshot).includes('NOT-FOR-SNAPSHOT'));
  pass('Background workspace, DOM refs and password redaction');
  if (options.native) {
    const { tools } = await first.rpc('tools/list', {});
    assert.equal(new Set(tools.map(t => t.name)).size, tools.length);
    assert.ok(tools.some(t => t.name === 'browser_click'));
    assert.ok(tools.some(t => t.name === 'tobkiri_tabs_click'));
    const { resources } = await first.rpc('resources/list', {});
    const skill = resources.find(r => r.uri === 'skill://tobkiri-computer-use/SKILL.md'); assert.ok(skill);
    assert.ok((await first.rpc('resources/read', { uri: skill.uri })).contents[0].text.includes('tobkiri'));
    assert.equal((await first.tool('tobkiri_integration_status')).computer.connected, true);
    pass('Actual Cua tools/resources and installed tab extension coexist in one MCP without desktop input', { tools: tools.length });
  } else {
    const native = await first.tool('browser_click', { target_id: 'mock-native' }); assert.equal(native.kind, 'computer');
    assert.ok((await first.rpc('resources/list', {})).resources.some(r => r.uri === 'skill://fixture'));
    pass('Cua tool-name collision and native resources remain separate from tab tools (native backend fixture)');
  }

  async function isolated(expression) {
    return worker.evaluate(async ({ tabId, expression }) => {
      const { frameTree } = await chrome.debugger.sendCommand({ tabId }, 'Page.getFrameTree');
      const { executionContextId } = await chrome.debugger.sendCommand({ tabId }, 'Page.createIsolatedWorld', { frameId: frameTree.frame.id, worldName: 'tobkiri-tabs-isolated' });
      const result = await chrome.debugger.sendCommand({ tabId }, 'Runtime.evaluate', { expression, contextId: executionContextId, returnByValue: true });
      if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
      return result.result.value;
    }, { tabId, expression });
  }
  trusted.move = await first.tool('tobkiri_tabs_move', { tabId, x: 400, y: 320 }, true);
  if (options['require-trusted']) assert.ok(!trusted.move.error, trusted.move.error);
  const pointer = await isolated('({renderer:__tobkiriSharedCursor.host.dataset.renderer,x:__tobkiriSharedCursor.host.dataset.x,y:__tobkiriSharedCursor.host.dataset.y,cursor:__tobkiriSharedCursor.character.pack.cursor,hidden:document.hidden,pixels:[...__tobkiriSharedCursor.canvas.getContext("2d").getImageData(0,0,__tobkiriSharedCursor.canvas.width,__tobkiriSharedCursor.canvas.height).data].some((v,i)=>i%4===3&&v>0)})');
  assert.deepEqual([pointer.x, pointer.y, pointer.cursor], ['400', '320', 'star']); assert.equal(pointer.pixels, true, JSON.stringify(pointer));
  assert.equal(await worker.evaluate(async tabId => (await chrome.tabs.get(tabId)).active, tabId), false);
  pass('Same Studio renderer draws synchronously in the background tab at exact CSS coordinates', { trustedMove: !trusted.move.error, documentHidden: pointer.hidden });
  const shot = await first.tool('tobkiri_tabs_screenshot', { tabId });
  const image = shot.content?.find(c => c.type === 'image');
  assert.ok(image, 'This Chromium must return a raster screenshot for visual verification.');
  await writeFile(resolve(output, 'shared-cursor.png'), Buffer.from(image.data, 'base64'));
  pass('Real inactive-tab screenshot includes the shared cursor without activation');
  trusted.click = await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment' }, true);
  const count = Number(await agent.locator('#count').textContent());
  if (!trusted.click.error) assert.equal(count, 1);
  else {
    assert.match(trusted.click.error, /INPUT_NOT_APPLIED|INPUT_OUTCOME_UNKNOWN/);
    // An uncertain gesture may have affected the page. Only rule out a second
    // click; never interpret an error response as proof that nothing happened.
    assert.ok(count === 0 || count === 1);
  }
  trusted.type = await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: 'Trusted fixture' }, true);
  if (options['require-trusted']) {
    assert.ok(!trusted.click.error, trusted.click.error);
    assert.ok(!trusted.type.error, trusted.type.error);
  }
  if (!trusted.type.error) assert.equal(await agent.locator('#entry').inputValue(), 'Trusted fixture');
  pass('Trusted input reports observed delivery without an automatic DOM retry', { click: trusted.click.error || 'delivered', type: trusted.type.error || 'delivered', observedClickCount: count });
  if (!trusted.type.error) {
    await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: '' });
    assert.equal(await agent.locator('#entry').inputValue(), '');
    assert.equal((await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: '' })).changed, false);
    pass('Trusted empty replacement deletes selected text and repeated clearing is idempotent');
  }

  await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: 'DOM fixture 日本語', inputRoute: 'dom' });
  assert.equal(await agent.locator('#entry').inputValue(), 'DOM fixture 日本語');
  await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: '', inputRoute: 'dom' });
  assert.equal(await agent.locator('#entry').inputValue(), '');
  await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: 'Final fixture', inputRoute: 'dom' });
  const dom = await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment', inputRoute: 'dom' });
  assert.equal(dom.trusted, false); assert.equal(Number(await agent.locator('#count').textContent()), count + 1);
  await first.tool('tobkiri_tabs_check', { tabId, selector: '#check', checked: true, inputRoute: 'dom' });
  assert.equal(await agent.locator('#check').isChecked(), true);
  await first.tool('tobkiri_tabs_select', { tabId, selector: '#mode', value: 'background' });
  assert.equal(await agent.locator('#mode').inputValue(), 'background');
  await first.tool('tobkiri_tabs_type', { tabId, selector: '#submit-entry', text: 'Local form', inputRoute: 'dom' });
  await first.tool('tobkiri_tabs_press', { tabId, selector: '#submit-entry', key: 'Enter', inputRoute: 'dom' });
  assert.equal(await agent.locator('#submitted').textContent(), 'Submitted locally');
  pass('Explicit background DOM click/type/empty replacement/checkbox/select/Enter works');
  if (options.extended) {
    await first.tool('tobkiri_tabs_eval', { tabId, expression: `globalThis.gestures=[];for(const type of ['click','dblclick','contextmenu','auxclick','mousedown','mouseup'])document.getElementById('gesture').addEventListener(type,e=>{if(!['mousedown','mouseup'].includes(type))e.preventDefault();gestures.push({type,button:e.button,trusted:e.isTrusted});});` });
    await first.tool('tobkiri_tabs_click', { tabId, selector: '#gesture', clickCount: 2 });
    await first.tool('tobkiri_tabs_click', { tabId, selector: '#gesture', button: 'right' });
    await first.tool('tobkiri_tabs_eval', { tabId, expression: 'document.getElementById("canvas").scrollIntoView({block:"center",behavior:"instant"})' });
    const rect = await agent.locator('#canvas').boundingBox(); assert.ok(rect);
    const points = [20, 80, 160].map(dx => ({ x: rect.x + dx, y: rect.y + 45 }));
    trusted.drag = await first.tool('tobkiri_tabs_drag', { tabId, points, durationMs: 150 }, true);
    const dragMoves = Number(await agent.locator('#drag-count').textContent());
    if (trusted.drag.error) assert.match(trusted.drag.error, /INPUT_NOT_APPLIED|INPUT_OUTCOME_UNKNOWN/);
    else assert.ok(dragMoves >= 2);
    assert.equal(await isolated('__tobkiriSharedCursor.host.dataset.action'), 'move');
    pass('Background drag reports observed delivery/refusal and clears the pressed cursor', { result: trusted.drag.error || 'delivered', dragMoves, probe: await isolated('globalThis.__tbkInput.seen') });
    for (const inputRoute of ['trusted', 'dom']) {
      await first.tool('tobkiri_tabs_type', { tabId, selector: '#editable', text: 'Rich 日本語🙂', inputRoute });
      assert.equal(await agent.locator('#editable').textContent(), 'Rich 日本語🙂');
      await first.tool('tobkiri_tabs_type', { tabId, selector: '#editable', text: '', inputRoute });
      assert.equal(await agent.locator('#editable').textContent(), '');
    }
    pass('Trusted and DOM contenteditable replacement/clearing preserve Unicode text');
    const refs = await first.tool('tobkiri_tabs_snapshot', { tabId });
    const shadow = refs.elements.find(e => e.name === 'Shadow click'); assert.ok(shadow);
    await first.tool('tobkiri_tabs_click', { tabId, ref: shadow.ref });
    assert.equal(await agent.locator('#echo').textContent(), 'Shadow clicked');
    await first.tool('tobkiri_tabs_snapshot', { tabId });
    assert.match((await first.tool('tobkiri_tabs_click', { tabId, ref: shadow.ref }, true)).error, /STALE_REF/);
    assert.match((await first.tool('tobkiri_tabs_click', { tabId, selector: 'input', inputRoute: 'dom' }, true)).error, /AMBIGUOUS_TARGET/);
    assert.match((await first.tool('tobkiri_tabs_click', { tabId, x: 9000, y: 10 }, true)).error, /OUTSIDE_VIEWPORT/);
    pass('Open Shadow DOM refs work; stale/ambiguous/out-of-viewport targets refuse input');
    const middle = await first.tool('tobkiri_tabs_click', { tabId, selector: '#gesture', button: 'middle' }, true);
    const gestures = await agent.evaluate(() => gestures);
    trusted.middle = middle;
    if (middle.error) assert.match(middle.error, /INPUT_NOT_APPLIED|INPUT_OUTCOME_UNKNOWN/);
    else assert.equal(gestures.filter(e => e.type === 'auxclick' && e.button === 1 && e.trusted).length, 1);
    assert.equal(gestures.filter(e => e.type === 'click').length, 2);
    for (const type of ['dblclick', 'contextmenu']) assert.equal(gestures.filter(e => e.type === type && e.trusted).length, 1);
    assert.ok(gestures.every(e => e.trusted));
    pass('Trusted double/right clicks arrive; middle click reports delivery or explicit refusal without DOM replay', { middle: middle.error || 'delivered', middleEvents: gestures.filter(e => e.button === 1) });
  }
  await first.tool('tobkiri_tabs_eval', { tabId, expression: 'document.getElementById("echo").textContent="Evaluated fixture"' });
  assert.equal(await agent.locator('#echo').textContent(), 'Evaluated fixture');
  await first.tool('tobkiri_tabs_scroll', { tabId, deltaY: 350, x: 900, y: 400 });
  assert.ok(await agent.evaluate(() => scrollY) > 0);
  pass('Granted main-world DOM evaluation and background scrolling work');

  await savePack({ ...defaults, displayMode: 'pet', cursor: 'ring', reducedMotion: true });
  await first.tool('tobkiri_tabs_move', { tabId, x: 600, y: 200 }, true);
  assert.equal(await isolated('__tobkiriSharedCursor.character.pack.displayMode'), 'pet');
  assert.equal(await isolated('__tobkiriSharedCursor.character.pack.cursor'), 'ring');
  if (studioApp) assert.equal(await studioApp.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().every(w => !w.isVisible())), true);
  pass('Shared Studio settings reload on the next operation, including pet-only mode', { publisher: studio ? 'actual offscreen Electron save IPC' : 'test file writer' });
  if (options.extended) {
    await first.tool('tobkiri_tabs_tab_navigate', { tabId, url: base + '/fixture?after-navigation' });
    assert.ok((await first.tool('tobkiri_tabs_snapshot', { tabId })).url.endsWith('?after-navigation'));
    await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment' });
    assert.equal(await agent.locator('#count').textContent(), '1');
    pass('Explicit background navigation rebuilds the isolated page context without activating the tab');
  }

  second = new Client(configFile); await second.init();
  const denied = await second.tool('tobkiri_tabs_click', { tabId, selector: '#increment', inputRoute: 'dom' }, true);
  assert.match(denied.error, /NOT_GRANTED/);
  assert.deepEqual((await second.tool('tobkiri_tabs_tabs')).tabs, []);
  assert.deepEqual(await worker.evaluate(() => testActivations), []);
  assert.equal(await human.locator('#human').inputValue(), 'Human text untouched');
  assert.equal(await human.evaluate(() => document.activeElement.id), 'human');
  assert.equal(await worker.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id), humanId);
  pass('Ownership isolation, ZERO tab activation and human page focus/text preserved');

  await agent.bringToFront();
  assert.match((await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment', inputRoute: 'dom' }, true)).error, /HUMAN_ACTIVE_TAB/);
  await human.bringToFront(); await popup.locator('#toggle').click();
  assert.match((await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment', inputRoute: 'dom' }, true)).error, /PAUSED/);
  await popup.locator('#toggle').click();
  await first.tool('tobkiri_tabs_snapshot', { tabId });
  await worker.evaluate(tabId => chrome.debugger.detach({ tabId }), tabId); await delay(100);
  assert.match((await first.tool('tobkiri_tabs_snapshot', { tabId }, true)).error, /DEBUGGER_DETACHED|NOT_GRANTED/);
  assert.match((await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment', inputRoute: 'dom' }, true)).error, /NOT_GRANTED/);
  if (options.native) assert.equal((await first.tool('tobkiri_integration_status')).computer.connected, true);
  pass('Human takeover, popup pause and externally detached debugger block further input');

  const refusedInput = Object.entries(trusted).filter(([,r]) => r.error).map(([action, result]) => ({ action, error: result.error }));
  const report = { passed: checks.length, failed: 0, platform: process.platform,
    browser: context.browser().version(), channel: options.browser, headless: true, installedExtension: true,
    extensionInstall: options.browser === 'chromium' ? 'CLI' : 'test-only CDP Extensions.loadUnpacked',
    nativeBackend: options.native ? 'production Cua; schemas/resources only; desktop input denied' : 'fixture; native hardware acceptance is a separate opt-in script',
    studio: options.studio ? 'production offscreen Electron, isolated settings, save IPC' : 'test file writer',
    checks, trusted, refusedInput, tabActivationsDuringBackgroundWork: 0,
    limitations: 'Fresh isolated headless profiles/local pages only. Passing refusal checks are not successful input delivery. No headed-user-profile, naturally hidden rAF, arbitrary-site, or production-host guarantee.' };
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`Headless installed-extension acceptance: ${checks.length} passed.`);
  if (refusedInput.length) console.log(`Input explicitly refused: ${refusedInput.map(r => r.action).join(', ')} (not counted as delivered).`);
} catch (e) {
  await writeFile(resolve(output, 'report.json'), JSON.stringify({ passed: checks.length, failed: 1, platform: process.platform, channel: options.browser, headless: true, checks, trusted, error: e.stack }, null, 2) + '\n');
  throw e;
} finally {
  await context?.close(); await studioApp?.close(); await second?.close(); await first?.close();
  await bridge?.stop(); if (local) await new Promise(resolve => local.close(resolve));
  // This exact fresh profile is the only directory removed by this test.
  assert.ok(temp.startsWith(output + '\\') || temp.startsWith(output + '/'));
  await rm(temp, { recursive: true, force: true });
}
