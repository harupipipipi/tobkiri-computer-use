// Offscreen renderer/IPC smoke only. No visible native windows, desktop input,
// global shortcut, tray, user settings, or user-profile operations.
import { _electron } from '../node_modules/playwright-core/index.mjs';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = resolve(root, 'test-results');
await mkdir(artifacts, { recursive: true });
const temp = await mkdtemp(resolve(artifacts, 'studio-export-'));
const packFile = resolve(temp, 'cursor-pack.json');
let app;
try {
  const env = { ...process.env, TOBKIRI_CURSOR_PACK: packFile, TOBKIRI_SMOKE_USER_DATA: resolve(temp, 'settings') };
  delete env.ELECTRON_RUN_AS_NODE;
  const require = createRequire(resolve(root, 'package.json'));
  app = await _electron.launch({ executablePath: require('electron'), args: [root, '--smoke-test', '--agent-mode'], env });
  let studio;
  for (let n = 0; n < 200 && !studio; n++) {
    studio = app.windows().find(w => w.url().endsWith('/index.html'));
    if (!studio) await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok(studio, 'Offscreen Studio editor did not load');
  await studio.waitForFunction(() => Boolean(window.companion));
  const state = await studio.evaluate(() => window.companion.getState());
  assert.equal(state.config.displayMode, 'both');
  assert.deepEqual(JSON.parse(await readFile(packFile, 'utf8')), state.config);
  const changed = { ...state.config, cursor: 'ring', cursorColor: '#aa3366', displayMode: 'pet' };
  await studio.evaluate(pack => window.companion.save(pack), changed);
  assert.deepEqual(JSON.parse(await readFile(packFile, 'utf8')), changed);
  assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().every(w => !w.isVisible())), true);
  console.log('Offscreen Studio: default cursor+pet and actual save IPC publish the shared pack; no visible window/input.');
} finally {
  await app?.close();
  assert.ok(temp.startsWith(artifacts + '\\') || temp.startsWith(artifacts + '/'));
  await rm(temp, { recursive: true, force: true });
}
