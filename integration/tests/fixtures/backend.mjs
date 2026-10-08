import readline from 'node:readline';
const kind = process.argv[2] || 'computer';
const tools = kind === 'computer' ? [
  { name: 'browser_click', description: 'Original Cua click.', inputSchema: { type: 'object', properties: { target_id: { type: 'string' } } } },
  { name: 'tobkiri_observe', description: 'Native fixture.', inputSchema: { type: 'object', properties: {} } },
] : [{ name: 'browser_click', inputSchema: { type: 'object' } }];
const send = (id, result) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n');
const jobs = new Map();
readline.createInterface({ input: process.stdin }).on('line', line => {
  const m = JSON.parse(line);
  if (m.method === 'notifications/cancelled') {
    clearTimeout(jobs.get(m.params.requestId)); jobs.delete(m.params.requestId); return;
  }
  if (!Object.hasOwn(m, 'id')) return;
  if (m.method === 'initialize') send(m.id, { protocolVersion: m.params.protocolVersion, capabilities: { tools: {}, resources: {} }, instructions: 'Fixture.' });
  else if (m.method === 'tools/list') send(m.id, { tools });
  else if (m.method === 'resources/list') send(m.id, { resources: [{ uri: 'skill://fixture', name: 'fixture' }] });
  else if (m.method === 'resources/read') send(m.id, { contents: [{ uri: m.params.uri, text: '日本語スキル' }] });
  else if (m.method === 'tools/call') {
    if (m.params.arguments?.crash) { process.exit(3); return; }
    const reply = () => send(m.id, { content: [{ type: 'text', text: JSON.stringify({ kind, ...m.params }) }],
      structuredContent: { kind, ...m.params }, isError: m.params.arguments?.refuse || false });
    if (m.params.arguments?.delay) jobs.set(m.id, setTimeout(reply, m.params.arguments.delay)); else reply();
  }
}).on('close', () => { for (const timer of jobs.values()) clearTimeout(timer); });
