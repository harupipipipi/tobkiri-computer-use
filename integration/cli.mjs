#!/usr/bin/env node
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { configPath } from '../browser/src/config.mjs';
import { Backend, runUnified } from './mcp.mjs';
import { syncCursor } from './sync-cursor.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2), separator = args.indexOf('--');
const options = separator < 0 ? args : args.slice(0, separator);
const nativeArgs = separator < 0 ? ['--surface', 'all', '--approval', process.platform === 'win32' ? 'windows-dialog' : 'macos-dialog'] : args.slice(separator + 1);
function option(name, fallback) {
  const index = options.indexOf(name);
  if (index < 0) return fallback;
  if (!options[index + 1] || options[index + 1].startsWith('--')) throw Error(`Missing value for ${name}`);
  return options[index + 1];
}
try {
  if (options.includes('--help')) {
    console.log('Tobkiri unified stdio MCP\n  node integration/cli.mjs [--computer EXE] [--browser-config PATH] [--cursor-pack PATH] [--no-companion] [-- NATIVE_ARGS]\n  npm run setup prints extension pairing and host configuration.');
    process.exit(0);
  }
  for (let i = 0; i < options.length; i++) {
    if (options[i] === '--no-companion') continue;
    if (!['--computer', '--browser-config', '--cursor-pack'].includes(options[i])) throw Error(`Unknown option: ${options[i]}. Use -- before native MCP arguments.`);
    option(options[i]); i++;
  }
  await syncCursor();
  const computerPath = option('--computer', resolve(root, process.platform === 'win32'
    ? 'windows/.venv/Scripts/tobkiri-computer-use.exe' : 'mac/.venv/bin/tobkiri-computer-use'));
  const browserConfig = configPath(option('--browser-config'));
  const env = { ...process.env, PYTHONUTF8: '1',
    TOBKIRI_CURSOR_PACK: resolve(option('--cursor-pack', process.env.TOBKIRI_CURSOR_PACK || resolve(dirname(browserConfig), 'cursor-pack.json'))) };
  if (!options.includes('--no-companion')) {
    env.TOBKIRI_COMPANION = '1';
    const rendererEnv = { ...env }; delete rendererEnv.ELECTRON_RUN_AS_NODE;
    try {
      const require = createRequire(resolve(root, 'companion/package.json'));
      const renderer = spawn(require('electron'), [resolve(root, 'companion'), '--agent-mode', '--cursor-pack', env.TOBKIRI_CURSOR_PACK],
        { env: rendererEnv, detached: true, stdio: 'ignore', windowsHide: true });
      renderer.on('error', e => console.error('Cursor Studio: ' + e.message)); renderer.unref();
    } catch (e) { console.error('Cursor Studio unavailable; run npm ci in companion/. Input remains available. ' + e.code); }
  } else env.TOBKIRI_COMPANION = '0';
  const computer = new Backend(computerPath, nativeArgs, { env });
  const browser = new Backend(process.execPath, [resolve(root, 'browser/src/cli.mjs'), 'mcp', '--config', browserConfig], { env });
  const server = runUnified({ computer, browser });
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => server.close());
} catch (e) { console.error(e.message); process.exitCode = 1; }
