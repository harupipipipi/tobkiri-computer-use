import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

export class Client {
  constructor(config, { computer, nativeArgs } = {}) {
    this.pending = new Map(); this.counter = 0;
    this.child = spawn(process.execPath, [resolve(root, 'integration/cli.mjs'), '--no-companion',
      '--computer', computer || process.execPath, '--browser-config', config, '--', ...(nativeArgs || [resolve(root, 'integration/tests/fixtures/backend.mjs'), 'computer'])],
      { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    this.child.stderr.pipe(process.stderr);
    createInterface({ input: this.child.stdout }).on('line', line => {
      const message = JSON.parse(line), pending = this.pending.get(message.id);
      if (!pending) return;
      clearTimeout(pending.timer); this.pending.delete(message.id);
      if (message.error) pending.reject(Error(JSON.stringify(message.error))); else pending.resolve(message.result);
    });
    this.child.on('exit', code => { for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(Error(`MCP exited ${code}`)); } this.pending.clear(); });
  }
  rpc(method, params) {
    const id = ++this.counter;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(Error(`MCP timeout: ${method}`)); }, 50000);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
    });
  }
  async init() {
    const response = await this.rpc('initialize', { protocolVersion: '2025-11-25', clientInfo: { name: 'headless-acceptance', version: '1' }, capabilities: {} });
    assert.equal(response.protocolVersion, '2024-11-05');
    this.child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');
  }
  async tool(name, args = {}, allowError = false) {
    const result = await this.rpc('tools/call', { name, arguments: args });
    if (result.isError) {
      if (allowError) return { error: result.content[0].text };
      throw Error(`${name}: ${result.content[0].text}`);
    }
    if (result.content.some(c => c.type === 'image')) return result;
    return JSON.parse(result.content[0].text);
  }
  async close() {
    this.child.stdin.end();
    await new Promise(resolve => {
      if (this.child.exitCode !== null) { resolve(); return; }
      const timer = setTimeout(() => this.child.kill(), 3000);
      this.child.once('exit', () => { clearTimeout(timer); resolve(); });
    });
  }
}
