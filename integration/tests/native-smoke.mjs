// Opt-in production-native connection smoke. Reads schemas and packaged skills
// only; does not observe or send input to any desktop/window/browser tab.
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { startBridge } from '../../browser/src/bridge.mjs';
import { Client } from './client.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const artifacts = resolve(root, 'integration/artifacts');
await mkdir(artifacts, { recursive: true });
const temp = await mkdtemp(resolve(artifacts, 'native-smoke-'));
let client, bridge;
try {
  // A dedicated local bridge, no extension/user-profile connection.
  const configPath = resolve(temp, 'config.json');
  const config = { port: 0, token: randomBytes(32).toString('hex'), configDir: temp };
  bridge = await startBridge(config); config.port = bridge.server.address().port;
  await writeFile(configPath, JSON.stringify({ version: 1, port: config.port, token: config.token }), { mode: 0o600 });
  const computer = resolve(root, process.platform === 'win32'
    ? 'windows/.venv/Scripts/tobkiri-computer-use.exe' : 'mac/.venv/bin/tobkiri-computer-use');
  client = new Client(configPath, { computer, nativeArgs: ['--surface', 'all', '--approval', 'deny'] });
  await client.init();
  const { tools } = await client.rpc('tools/list', {});
  assert.ok(tools.some(t => t.name === 'tobkiri_observe'));
  assert.ok(tools.some(t => t.name === 'tobkiri_tabs_click'));
  assert.equal(new Set(tools.map(t => t.name)).size, tools.length);
  const { resources } = await client.rpc('resources/list', {});
  const skill = resources.find(r => r.uri === 'skill://tobkiri-computer-use/SKILL.md'); assert.ok(skill);
  const read = await client.rpc('resources/read', { uri: skill.uri });
  assert.ok(read.contents[0].text.includes('tobkiri'));
  const status = await client.tool('tobkiri_integration_status');
  assert.equal(status.computer.connected, true); assert.equal(status.browser.connected, true);
  const offline = await client.tool('tobkiri_tabs_status'); assert.equal(offline.connected, false);
  const refusal = await client.tool('tobkiri_tabs_click', { tabId: 1, x: 2, y: 3 }, true);
  assert.match(refusal.error, /EXTENSION_OFFLINE/);
  assert.equal((await client.tool('tobkiri_integration_status')).computer.connected, true);
  console.log(`Production native Cua + unified MCP: ${tools.length} tools, packaged skill, browser-offline refusal and native connection preservation passed. No desktop input.`);
} finally {
  await client?.close(); await bridge?.stop();
  assert.ok(temp.startsWith(artifacts + '\\') || temp.startsWith(artifacts + '/'));
  await rm(temp, { recursive: true, force: true });
}
