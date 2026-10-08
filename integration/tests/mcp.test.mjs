import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { fileURLToPath } from 'node:url';
import { Backend, runUnified, TAB_TOOLS } from '../mcp.mjs';
import { TOOLS } from '../../browser/extension/shared.mjs';
import { once } from 'node:events';

const fixture = fileURLToPath(new URL('./fixtures/backend.mjs', import.meta.url));
function connection(t, options = {}) {
  const computer = new Backend(process.execPath, [fixture, 'computer'], options);
  const browser = new Backend(process.execPath, [fixture, 'browser'], options);
  const input = new PassThrough(), output = new PassThrough(), messages = [], pending = new Map();
  let buffer = '', counter = 0;
  output.on('data', chunk => {
    buffer += chunk; let end;
    while ((end = buffer.indexOf('\n')) >= 0) {
      const message = JSON.parse(buffer.slice(0, end)); buffer = buffer.slice(end + 1);
      messages.push(message); pending.get(message.id)?.(message); pending.delete(message.id);
    }
  });
  const unified = runUnified({ computer, browser, input, output });
  t.after(() => { unified.close(); input.destroy(); });
  const notify = (method, params) => input.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
  const rpc = (method, params, id = ++counter) => new Promise(resolve => {
    pending.set(id, resolve); input.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
  return { computer, browser, unified, rpc, notify, messages, input };
}
async function initialize(c) {
  const response = await c.rpc('initialize', { protocolVersion: '2025-11-25', clientInfo: { name: 'integration-test', version: '1' }, capabilities: {} });
  assert.equal(response.result.protocolVersion, '2024-11-05');
  c.notify('notifications/initialized'); return response.result;
}

test('native schemas are unchanged; extension aliases keep the input schema', async t => {
  const c = connection(t); await initialize(c);
  const { result } = await c.rpc('tools/list', {});
  assert.equal(new Set(result.tools.map(t => t.name)).size, result.tools.length);
  assert.deepEqual(result.tools.find(t => t.name === 'browser_click').inputSchema,
    { type: 'object', properties: { target_id: { type: 'string' } } });
  for (let i = 0; i < TOOLS.length; i++) assert.deepEqual(TAB_TOOLS[i].inputSchema, TOOLS[i].inputSchema);
  const native = await c.rpc('tools/call', { name: 'browser_click', arguments: { target_id: 'cua', text: '日本語' } });
  assert.deepEqual(native.result.structuredContent, { kind: 'computer', name: 'browser_click', arguments: { target_id: 'cua', text: '日本語' } });
  const tab = await c.rpc('tools/call', { name: 'tobkiri_tabs_click', arguments: { tabId: 9, refuse: true } });
  assert.equal(tab.result.structuredContent.kind, 'browser'); assert.equal(tab.result.isError, true);
  assert.equal(tab.result.structuredContent.name, 'browser_click');
});

test('native resources survive aggregation and initialization is required', async t => {
  const c = connection(t);
  assert.equal((await c.rpc('tools/list', {})).error.code, -32000);
  await initialize(c);
  assert.equal((await c.rpc('resources/list', {})).result.resources[0].uri, 'skill://fixture');
  assert.equal((await c.rpc('resources/read', { uri: 'skill://fixture' })).result.contents[0].text, '日本語スキル');
});

test('concurrent host IDs and cancellation never collide across backends or replay input', async t => {
  const c = connection(t); await initialize(c);
  const waiting = c.rpc('tools/call', { name: 'tobkiri_tabs_click', arguments: { delay: 1000 } }, 'cancel-me');
  const native = c.rpc('tools/call', { name: 'browser_click', arguments: {} }, 500);
  c.notify('notifications/cancelled', { requestId: 'cancel-me' });
  assert.equal((await waiting).result.isError, true);
  assert.equal((await native).result.structuredContent.kind, 'computer');
  assert.equal(c.browser.pending.size, 0);
  assert.equal(c.messages.filter(m => m.id === 'cancel-me').length, 1);
});

test('a browser crash preserves native tools and returns uncertain effect without retry', async t => {
  const c = connection(t); await initialize(c);
  const failed = await c.rpc('tools/call', { name: 'tobkiri_tabs_click', arguments: { crash: true } });
  assert.equal(failed.result.isError, true); assert.match(failed.result.content[0].text, /unknown/);
  assert.equal((await c.rpc('tools/call', { name: 'browser_click', arguments: {} })).result.structuredContent.kind, 'computer');
  assert.equal((await c.rpc('tools/list', {})).result.tools.some(t => t.name === 'browser_click'), true);
  const status = (await c.rpc('tools/call', { name: 'tobkiri_integration_status', arguments: {} })).result.structuredContent;
  assert.equal(status.browser.connected, false); assert.equal(status.computer.connected, true);
});

test('a browser unavailable at startup still permits native initialization and schemas', async t => {
  const c = connection(t);
  const exited = once(c.browser.child, 'exit'); c.browser.child.kill(); await exited;
  await initialize(c);
  assert.ok((await c.rpc('tools/list', {})).result.tools.some(t => t.name === 'browser_click'));
  assert.equal((await c.rpc('tools/call', { name: 'tobkiri_tabs_click', arguments: {} })).result.isError, true);
  assert.equal((await c.rpc('tools/call', { name: 'browser_click', arguments: {} })).result.structuredContent.kind, 'computer');
});

test('timeouts cancel one backend request without restarting it', async t => {
  const c = connection(t, { timeoutMs: 2000 }); await initialize(c);
  c.browser.timeoutMs = 30;
  const result = await c.rpc('tools/call', { name: 'tobkiri_tabs_click', arguments: { delay: 1000 } });
  assert.equal(result.result.isError, true); assert.match(result.result.content[0].text, /inspect before retrying/);
  assert.equal(c.browser.counter, 2); // initialize + one action, no retries.
  assert.equal(c.browser.failure, null);
});

test('parse errors do not kill a healthy connection', async t => {
  const c = connection(t); await initialize(c); c.input.write('not-json\n');
  assert.equal((await c.rpc('ping', {})).result.constructor, Object);
  assert.ok(c.messages.some(m => m.error?.code === -32700));
});
