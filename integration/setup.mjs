// Explicit host setup. Does not change native permissions or install extensions.
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { configPath, initConfig, pairingCode } from '../browser/src/config.mjs';
import { syncCursor } from './sync-cursor.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
function option(name, fallback) {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  if (!args[i + 1] || args[i + 1].startsWith('--')) throw Error(`Missing value for ${name}`);
  return args[i + 1];
}
const path = configPath(option('--browser-config'));
await syncCursor();
const c = await initConfig(path, Number(option('--port', 17653)));
const command = spawnSync(process.execPath, [resolve(root, 'browser/src/cli.mjs'), 'doctor', '--config', path], { encoding: 'utf8', windowsHide: true });
const computer = option('--computer', resolve(root, process.platform === 'win32'
  ? 'windows/.venv/Scripts/tobkiri-computer-use.exe' : 'mac/.venv/bin/tobkiri-computer-use'));
console.log(`Tobkiri Computer + Browser\n\nLoad this unpacked extension in Chrome/Chromium:\n${resolve(root, 'browser/extension')}\n\nPaste this PRIVATE pairing code only into its popup:\n${pairingCode(c)}\n\nKeep the code out of AI chats and repositories. Enable new AI tabs only if you want them.\n\nMCP stdio configuration:`);
console.log(JSON.stringify({ mcpServers: { 'tobkiri-use': { command: process.execPath,
  args: [resolve(root, 'integration/cli.mjs'), '--computer', computer, '--browser-config', path] } } }, null, 2));
console.log('\nInstall the OS Python package/Cua Driver and run npm ci in companion/ first. The unified MCP starts the local bridge automatically.');
if (command.status !== 0) console.log('The browser bridge is not connected yet. It will start with the MCP; pair the extension after starting it.');
