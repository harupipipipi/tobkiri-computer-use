import { readFile, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { cursorRuntime } from '../extension/character-runtime.mjs';

const { validatePack } = cursorRuntime();
export const cursorPackPath = config => resolve(config.cursorPackPath
  || process.env.TOBKIRI_CURSOR_PACK || resolve(config.configDir || '.', 'cursor-pack.json'));

// Local, read-only presentation data. An invalid pack never changes input delivery.
export function packReader(config) {
  const path = cursorPackPath(config);
  let signature, cached = { pack: null, error: null };
  return async () => {
    try {
      const info = await stat(path);
      if (info.size > 8000000) throw Error('Cursor pack exceeds 8 MB.');
      const next = `${info.mtimeMs}:${info.size}:${info.ctimeMs}`;
      if (next === signature) return cached;
      const pack = validatePack(JSON.parse(await readFile(path, 'utf8')));
      signature = next;
      return cached = { pack, error: null };
    } catch (e) {
      signature = undefined;
      return cached = { pack: null, error: e.code === 'ENOENT' ? null : 'Invalid shared cursor pack; standalone pointer is active.' };
    }
  };
}
