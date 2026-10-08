// Fictional, loopback-only SNS fixture. No external accounts or services.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const here = dirname(fileURLToPath(import.meta.url));
export function initialState() {
  return {
    viewer: { name: 'とびきり', handle: 'tobkiri', avatar: 'T' },
    users: [
      { id: 'aoi', name: '葵', handle: 'aoi.studio', avatar: '葵', color: 'purple', bio: '小さな風景を、ゆっくり集める。', followers: 128, following: false },
      { id: 'nagi', name: '凪', handle: 'nagi.labs', avatar: '凪', color: 'orange', bio: 'ものづくりと、午後のコーヒー。', followers: 96, following: false },
      { id: 'midori', name: 'ミドリ', handle: 'midori.walk', avatar: '緑', color: 'green', bio: '歩いて見つけた、今日の色。', followers: 204, following: false },
    ],
    posts: [
      { id: 'morning', userId: 'aoi', time: '12分前', text: '朝の光がきれいだったので、少しだけ遠回り。\nこういう余白を大事にしたい。', art: 'morning', likes: 18, liked: false, replies: 3 },
      { id: 'coffee', userId: 'nagi', time: '38分前', text: '新しいアイデアは、いつもコーヒーのあとに。\n今日は小さなプロトタイプをひとつ作った ☕', art: null, likes: 42, liked: false, replies: 5 },
      { id: 'walk', userId: 'midori', time: '1時間前', text: '帰り道で見つけた緑。日常にも、小さな発見がある。', art: null, likes: 9, liked: false, replies: 1 },
    ],
    activity: [],
  };
}

export async function createSocialServer({ stateFile, port = 0, fresh = false } = {}) {
  let state = initialState();
  if (stateFile && !fresh) {
    try { state = JSON.parse(await readFile(stateFile, 'utf8')); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
  }
  const html = await readFile(resolve(here, 'index.html'));
  let saveQueue = Promise.resolve();
  async function save() {
    if (!stateFile) return;
    const data = JSON.stringify(state, null, 2) + '\n';
    saveQueue = saveQueue.then(async () => {
      await mkdir(dirname(stateFile), { recursive: true });
      await writeFile(stateFile, data);
    });
    await saveQueue;
  }
  await save();
  let base;
  const server = createServer(async (req, res) => {
    const json = (status, value) => {
      res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify(value));
    };
    try {
      if (req.headers.host !== new URL(base).host) return json(403, { error: 'Loopback fixture only' });
      const url = new URL(req.url, base);
      if (req.method === 'GET' && url.pathname === '/api/state') return json(200, state);
      if (req.method === 'GET' && url.pathname === '/human') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end('<!doctype html><meta charset="utf-8"><title>Human fixture</title><textarea id="human">Human text untouched</textarea>');
      }
      if (req.method === 'GET' && url.pathname === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        return res.end(html);
      }
      const match = /^\/api\/(follow|like)\/([a-z]+)$/.exec(url.pathname);
      if (req.method !== 'PUT' || !match) return json(404, { error: 'Not found' });
      if (req.headers.origin !== base || !req.headers['content-type']?.startsWith('application/json')) return json(403, { error: 'Same-origin JSON required' });
      let body = '';
      for await (const chunk of req) {
        body += chunk;
        if (Buffer.byteLength(body) > 4096) return json(413, { error: 'Request too large' });
      }
      const input = JSON.parse(body);
      if (typeof input.enabled !== 'boolean') return json(400, { error: 'enabled must be boolean' });
      const [ , kind, id ] = match;
      const record = (kind === 'follow' ? state.users : state.posts).find(item => item.id === id);
      if (!record) return json(404, { error: 'Fictional target not found' });
      const flag = kind === 'follow' ? 'following' : 'liked', count = kind === 'follow' ? 'followers' : 'likes';
      if (record[flag] !== input.enabled) {
        record[flag] = input.enabled; record[count] += input.enabled ? 1 : -1;
        // The page supplies this diagnostic; it is not a permission/security assertion.
        state.activity.push({ seq: state.activity.length + 1, kind, id, enabled: input.enabled, browserReportedTrusted: input.trusted === true });
        await save();
      }
      return json(200, state);
    } catch (e) {
      return json(e instanceof SyntaxError ? 400 : 500, { error: e instanceof SyntaxError ? 'Invalid JSON' : 'Local fixture error' });
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  base = `http://127.0.0.1:${server.address().port}`;
  return { base, server, getState: () => structuredClone(state), close: async () => { await saveQueue; await new Promise(resolve => server.close(resolve)); } };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { port: { type: 'string', default: '0' }, state: { type: 'string', default: resolve(here, '../../artifacts/social-demo/msedge/state.json') } } });
  const port = Number(values.port);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw Error('Invalid port');
  const app = await createSocialServer({ port, stateFile: resolve(values.state) });
  const runtime = resolve(here, '../../artifacts/social-demo/runtime.json');
  await mkdir(dirname(runtime), { recursive: true });
  await writeFile(runtime, JSON.stringify({ url: app.base, stateFile: resolve(values.state) }, null, 2) + '\n');
  console.log(`架空SNS「こもれび」: ${app.base}`);
  process.on('SIGINT', async () => { await app.close(); process.exit(0); });
  process.on('SIGTERM', async () => { await app.close(); process.exit(0); });
}
