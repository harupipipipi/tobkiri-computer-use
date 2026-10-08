// Opt-in HEADLESS acceptance: a fresh Chromium profile, installed MV3 extension,
// production browser MCP + unified broker, and fictional loopback pages only.
// No user's browser, GUI window, account, pointer, keyboard, or profile is used.
import { chromium } from '../../companion/node_modules/playwright-core/index.mjs';
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
const output = resolve(root, 'integration/artifacts/browser-live');
await mkdir(output, { recursive: true });
const temp = await mkdtemp(resolve(output, 'run-'));
let context, bridge, local, first, second;
const checks = [], trusted = {};
const pass = (name, details) => { checks.push({ name, passed: true, ...(details ? { details } : {}) }); console.log('PASS ' + name); };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

try {
  const fixture = await readFile(resolve(root, 'browser/tests/fixture.html'));
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
  await writeFile(packFile, JSON.stringify({ ...defaults, displayMode: 'both', cursor: 'star', cursorColor: '#ce3452', reducedMotion: true }));
  first = new Client(configFile); await first.init();
  context = await chromium.launchPersistentContext(resolve(temp, 'profile'), {
    headless: true, channel: 'chromium', viewport: { width: 1200, height: 800 },
    ignoreDefaultArgs: ['--disable-extensions'],
    args: [`--disable-extensions-except=${resolve(root, 'browser/extension')}`, `--load-extension=${resolve(root, 'browser/extension')}`],
  });
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
  const native = await first.tool('browser_click', { target_id: 'mock-native' }); assert.equal(native.kind, 'computer');
  assert.ok((await first.rpc('resources/list', {})).resources.some(r => r.uri === 'skill://fixture'));
  pass('Cua tool-name collision and native resources remain separate from tab tools (native backend fixture)');

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
  const pointer = await isolated('({renderer:__tobkiriSharedCursor.host.dataset.renderer,x:__tobkiriSharedCursor.host.dataset.x,y:__tobkiriSharedCursor.host.dataset.y,cursor:__tobkiriSharedCursor.character.pack.cursor,hidden:document.hidden,pixels:[...__tobkiriSharedCursor.canvas.getContext("2d").getImageData(0,0,__tobkiriSharedCursor.canvas.width,__tobkiriSharedCursor.canvas.height).data].some((v,i)=>i%4===3&&v>0)})');
  assert.deepEqual([pointer.x, pointer.y, pointer.cursor], ['400', '320', 'star']); assert.equal(pointer.pixels, true, JSON.stringify(pointer));
  assert.equal(await worker.evaluate(async tabId => (await chrome.tabs.get(tabId)).active, tabId), false);
  pass('Same Studio renderer draws synchronously in the background tab at exact CSS coordinates', { trustedMove: !trusted.move.error, documentHidden: pointer.hidden });
  const shot = await first.tool('tobkiri_tabs_screenshot', { tabId });
  const image = shot.content?.find(c => c.type === 'image');
  assert.ok(image, 'This Chromium must return a raster screenshot for visual verification.');
  await writeFile(resolve(output, 'shared-cursor.png'), Buffer.from(image.data, 'base64'));
  pass('Real hidden-tab screenshot includes the shared cursor without activation');
  trusted.click = await first.tool('tobkiri_tabs_click', { tabId, selector: '#increment' }, true);
  const count = Number(await agent.locator('#count').textContent());
  if (!trusted.click.error) assert.equal(count, 1); else assert.equal(count, 0);
  trusted.type = await first.tool('tobkiri_tabs_type', { tabId, selector: '#entry', text: 'Trusted fixture' }, true);
  if (!trusted.type.error) assert.equal(await agent.locator('#entry').inputValue(), 'Trusted fixture');
  pass('Trusted input reports observed delivery without an automatic DOM retry', { click: trusted.click.error || 'delivered', type: trusted.type.error || 'delivered' });
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
  await first.tool('tobkiri_tabs_eval', { tabId, expression: 'document.getElementById("echo").textContent="Evaluated fixture"' });
  assert.equal(await agent.locator('#echo').textContent(), 'Evaluated fixture');
  await first.tool('tobkiri_tabs_scroll', { tabId, deltaY: 350, x: 900, y: 400 });
  assert.ok(await agent.evaluate(() => scrollY) > 0);
  pass('Granted main-world DOM evaluation and background scrolling work');

  await writeFile(packFile, JSON.stringify({ ...defaults, displayMode: 'pet', cursor: 'ring', reducedMotion: true }));
  await first.tool('tobkiri_tabs_move', { tabId, x: 600, y: 200 }, true);
  assert.equal(await isolated('__tobkiriSharedCursor.character.pack.displayMode'), 'pet');
  assert.equal(await isolated('__tobkiriSharedCursor.character.pack.cursor'), 'ring');
  pass('Shared Studio settings reload on the next operation, including pet-only mode');

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
  pass('Human takeover, popup pause and externally detached debugger block further input');

  const report = { passed: checks.length, failed: 0, platform: process.platform,
    browser: context.browser().version(), headless: true, installedExtension: true,
    nativeBackend: 'fixture; native hardware acceptance is a separate opt-in script',
    checks, trusted, limitations: 'Fresh isolated profile/local pages only. No arbitrary-site or production-host guarantee.' };
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`Headless installed-extension acceptance: ${checks.length} passed.`);
} catch (e) {
  await writeFile(resolve(output, 'report.json'), JSON.stringify({ passed: checks.length, failed: 1, checks, error: e.stack }, null, 2) + '\n');
  throw e;
} finally {
  await context?.close(); await second?.close(); await first?.close();
  await bridge?.stop(); if (local) await new Promise(resolve => local.close(resolve));
  // This exact fresh profile is the only directory removed by this test.
  assert.ok(temp.startsWith(output + '\\') || temp.startsWith(output + '/'));
  await rm(temp, { recursive: true, force: true });
}
