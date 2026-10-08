// Opt-in headless SNS demonstration through the production tab MCP/extension.
// Only fictional loopback users/posts; no visible window or desktop input.
import { chromium } from '../../../companion/node_modules/playwright-core/index.mjs';
import { mkdir, mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { randomBytes } from 'node:crypto';
import assert from 'node:assert/strict';
import { createSocialServer } from './server.mjs';
import { startBridge } from '../../../browser/src/bridge.mjs';
import { request } from '../../../browser/src/config.mjs';
import { defaults } from '../../../companion/src/config.js';
import { Client } from '../../tests/client.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const { values } = parseArgs({ options: { browser: { type: 'string', default: 'chrome' } } });
assert.ok(['chromium', 'chrome', 'msedge'].includes(values.browser));
const output = resolve(root, 'integration/artifacts/social-demo', values.browser);
await mkdir(output, { recursive: true });
const temp = await mkdtemp(resolve(output, 'run-'));
let social, bridge, client, context;
const steps = [], checks = [];
const pass = name => { checks.push(name); console.log('PASS ' + name); };
const report = extra => ({ browser: context?.browser()?.version(), channel: values.browser, headless: true,
  installedExtension: Boolean(context?.serviceWorkers().length), nativeBackend: 'routing fixture; SNS input uses the production tab extension',
  steps, checks, ...extra });
try {
  social = await createSocialServer({ stateFile: resolve(output, 'state.json'), fresh: true });
  const config = { port: 0, token: randomBytes(32).toString('hex'), configDir: temp };
  bridge = await startBridge(config); config.port = bridge.server.address().port;
  await request(config, '/status', undefined, undefined, 2000);
  const configFile = resolve(temp, 'config.json');
  await writeFile(configFile, JSON.stringify({ version: 1, port: config.port, token: config.token }));
  await writeFile(resolve(temp, 'cursor-pack.json'), JSON.stringify({ ...defaults, displayMode: 'both', cursor: 'star', cursorColor: '#26765f', reducedMotion: true }));
  client = new Client(configFile); await client.init();
  context = await chromium.launchPersistentContext(resolve(temp, 'profile'), {
    headless: true, channel: values.browser, viewport: { width: 1360, height: 1020 },
    ignoreDefaultArgs: ['--disable-extensions'],
    args: values.browser === 'chromium'
      ? [`--disable-extensions-except=${resolve(root, 'browser/extension')}`, `--load-extension=${resolve(root, 'browser/extension')}`]
      : ['--enable-unsafe-extension-debugging'],
  });
  if (values.browser !== 'chromium') {
    const cdp = await context.browser().newBrowserCDPSession();
    await cdp.send('Extensions.loadUnpacked', { path: resolve(root, 'browser/extension') }); await cdp.detach();
  }
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const popup = await context.newPage(); await popup.goto(`chrome-extension://${worker.url().split('/')[2]}/popup.html`);
  await popup.locator('#pair-code').fill(`tbt1.${config.port}.${config.token}`);
  await popup.locator('#pair-create').check(); await popup.locator('#pair').click();
  for (let n = 0; n < 100 && !(await client.tool('tobkiri_tabs_status')).connected; n++) await new Promise(r => setTimeout(r, 100));
  assert.equal((await client.tool('tobkiri_tabs_status')).connected, true);
  const human = await context.newPage(); await human.goto(social.base + '/human'); await human.bringToFront(); await human.locator('#human').focus();
  const humanId = await worker.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
  await worker.evaluate(() => { globalThis.demoActivations = []; chrome.tabs.onActivated.addListener(e => demoActivations.push(e.tabId)); });
  const workspace = await client.tool('tobkiri_tabs_workspace_create', { name: '架空SNS · こもれび', color: 'green', url: social.base + '/' });
  const tabId = workspace.tabId; assert.equal(workspace.active, false);
  const page = context.pages().find(p => p.url() === social.base + '/'); assert.ok(page);
  await client.tool('tobkiri_tabs_wait', { tabId, text: '葵' });
  const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
  async function screenshot(name) {
    const shot = await client.tool('tobkiri_tabs_screenshot', { tabId });
    const image = shot.content.find(item => item.type === 'image'); assert.ok(image);
    await writeFile(resolve(output, name), Buffer.from(image.data, 'base64'));
  }
  await screenshot('before.png');
  pass('Fictional SNS opened as an inactive, explicitly granted tab');
  async function click(label, inputRoute, kind, id, enabled) {
    // Every step observes a fresh ref; rerendering invalidates old DOM targets.
    const snapshot = await client.tool('tobkiri_tabs_snapshot', { tabId });
    const target = snapshot.elements.find(e => e.tag === 'button' && e.name === label);
    assert.ok(target, `Button not observed: ${label}`);
    const result = await client.tool('tobkiri_tabs_click', { tabId, ref: target.ref, inputRoute });
    if (inputRoute === 'dom') assert.equal(result.trusted, false);
    const expectedLength = steps.length + 1;
    await page.waitForFunction(expected => {
      const button = [...document.querySelectorAll('button[data-kind]')].find(b => b.dataset.kind === expected.kind && b.dataset.id === expected.id);
      return button && !button.disabled && button.getAttribute('aria-pressed') === String(expected.enabled);
    }, { kind, id, enabled });
    const state = social.getState();
    assert.equal(Number(await page.locator('#following-count').textContent()), state.users.filter(u => u.following).length);
    assert.equal(Number(await page.locator('#liked-count').textContent()), state.posts.filter(p => p.liked).length);
    assert.equal(state.activity.length, expectedLength, 'Exactly one server mutation per click');
    const mutation = state.activity.at(-1);
    assert.deepEqual([mutation.kind, mutation.id, mutation.enabled, mutation.browserReportedTrusted], [kind, id, enabled, inputRoute === 'trusted']);
    const saved = JSON.parse(await readFile(resolve(output, 'state.json'), 'utf8'));
    assert.deepEqual(saved, state, 'The server persisted the same state');
    steps.push({ label, inputRoute, kind, id, enabled, serverSequence: mutation.seq });
    console.log(`DONE ${label} (${inputRoute})`);
  }
  await click('葵をフォロー', 'trusted', 'follow', 'aoi', true);
  await click('葵の投稿にいいね', 'trusted', 'like', 'morning', true);
  pass('Trusted background clicks follow 葵 and like her post, with persisted server receipts');
  await click('凪をフォロー', 'dom', 'follow', 'nagi', true);
  await click('凪の投稿にいいね', 'dom', 'like', 'coffee', true);
  pass('Explicit DOM background clicks follow 凪 and like his post');
  await click('葵のフォローを解除', 'trusted', 'follow', 'aoi', false);
  await click('葵をフォロー', 'trusted', 'follow', 'aoi', true);
  await click('葵の投稿のいいねを取り消す', 'dom', 'like', 'morning', false);
  await click('葵の投稿にいいね', 'dom', 'like', 'morning', true);
  const state = social.getState();
  assert.deepEqual(state.users.filter(u => u.following).map(u => u.id), ['aoi', 'nagi']);
  assert.deepEqual(state.posts.filter(p => p.liked).map(p => p.id), ['morning', 'coffee']);
  assert.deepEqual(state.users.map(u => u.followers), [129, 97, 204]);
  assert.deepEqual(state.posts.map(p => p.likes), [19, 43, 9]);
  pass('Unfollow/unlike and reapply do not duplicate follower/like counts');
  await client.tool('tobkiri_tabs_tab_navigate', { tabId, url: social.base + '/?reloaded=1' });
  await client.tool('tobkiri_tabs_wait', { tabId, text: '葵の投稿にいいねしました' });
  assert.equal(await page.locator('#following-count').textContent(), '2');
  assert.equal(await page.locator('#liked-count').textContent(), '2');
  assert.equal(await page.locator('button[data-kind="follow"][data-id="aoi"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('button[data-kind="like"][data-id="morning"]').getAttribute('aria-pressed'), 'true');
  pass('Reload restores both follows and both likes from the server');
  await client.tool('tobkiri_tabs_scroll', { tabId, deltaY: -10000, x: 700, y: 100 });
  const snapshot = await client.tool('tobkiri_tabs_snapshot', { tabId });
  const liked = snapshot.elements.find(e => e.name === '葵の投稿のいいねを取り消す'); assert.ok(liked);
  await client.tool('tobkiri_tabs_move', { tabId, x: liked.rect.x + liked.rect.width / 2, y: liked.rect.y + liked.rect.height / 2 });
  await screenshot('after.png');
  assert.equal(await worker.evaluate(async tabId => (await chrome.tabs.get(tabId)).active, tabId), false);
  assert.deepEqual(await worker.evaluate(() => demoActivations), []);
  assert.equal(await worker.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id), humanId);
  assert.equal(await human.locator('#human').inputValue(), 'Human text untouched');
  assert.equal(await human.evaluate(() => document.activeElement.id), 'human');
  assert.deepEqual(pageErrors, []);
  pass('Shared cursor captured; zero tab activation; human focus/text preserved');
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report({ passed: checks.length, failed: 0, follows: 2, likes: 2, mutations: steps.length, tabActivations: 0,
    limitations: 'Fresh headless profile, fictional local SNS only. No real social service or natural hidden-window delivery claim.' }), null, 2) + '\n');
  console.log(`SNS demonstration: ${checks.length} checks, ${steps.length} persisted UI mutations, 2 follows + 2 likes.`);
} catch (e) {
  try { await writeFile(resolve(output, 'bridge.log'), await readFile(resolve(temp, 'bridge.log'))); } catch {}
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report({ passed: checks.length, failed: 1, error: e.stack, cause: e.cause?.message }), null, 2) + '\n');
  throw e;
} finally {
  await context?.close(); await client?.close(); await bridge?.stop(); await social?.close();
  const path = relative(output, temp); assert.ok(path && !path.startsWith('..') && !path.includes(':'));
  await rm(temp, { recursive: true, force: true });
}
