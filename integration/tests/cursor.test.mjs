import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cursorRuntime } from '../../browser/extension/character-runtime.mjs';
import { defaults, validatePack } from '../../companion/src/config.js';
import { poseFor } from '../../companion/src/engine.js';
import { packReader } from '../../browser/src/cursor-pack.mjs';
import { syncCursor } from '../sync-cursor.mjs';

test('extension bundle equals the canonical desktop engine and all motion poses', async () => {
  await syncCursor(true);
  const runtime = cursorRuntime();
  assert.deepEqual(runtime.defaults, defaults);
  const pack = { ...defaults, color: '#aa3322', displayMode: 'both', cursor: 'ring' };
  assert.deepEqual(runtime.validatePack(pack), validatePack(pack));
  for (const motion of ['idle', 'click', 'type', 'key', 'scroll_up', 'drag', 'hip_pop'])
    assert.deepEqual(runtime.poseFor(motion, .21, pack), poseFor(motion, .21, pack));
  const c = new runtime.Character(pack, 200, 300);
  assert.deepEqual([c.tx, c.ty], [200, 300]);
});

test('shared presentation reloads edits and rejects invalid/missing data without input', async t => {
  const base = fileURLToPath(new URL('../artifacts/', import.meta.url));
  await mkdir(base, { recursive: true });
  const dir = await mkdtemp(join(base, 'cursor-test-'));
  t.after(() => { assert.ok(dir.startsWith(base)); return rm(dir, { recursive: true, force: true }); });
  const path = join(dir, 'cursor-pack.json'), read = packReader({ cursorPackPath: path });
  assert.deepEqual(await read(), { pack: null, error: null });
  await writeFile(path, JSON.stringify(defaults));
  assert.deepEqual((await read()).pack, defaults);
  await writeFile(path, JSON.stringify({ ...defaults, cursor: 'star', size: 150 }));
  assert.equal((await read()).pack.cursor, 'star');
  await writeFile(path, JSON.stringify({ ...defaults, cursorImage: 'https://example.org/image.png' }));
  assert.equal((await read()).pack, null); assert.match((await read()).error, /Invalid/);
});
