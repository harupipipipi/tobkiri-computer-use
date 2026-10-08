import test from 'node:test';
import assert from 'node:assert/strict';
import {PassThrough} from 'node:stream';
import {once} from 'node:events';
import net from 'node:net';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {mkdtempSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {safeUrl,validateArgs,TOOLS} from '../extension/shared.mjs';
import {startBridge} from '../src/bridge.mjs';
import {request} from '../src/config.mjs';
import {imageSize} from '../extension/image-size.mjs';
import {runMcp} from '../src/mcp.mjs';
async function fixture(t) {
  const probe=net.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');const port=probe.address().port;await new Promise(r=>probe.close(r));
  const config={port,token:randomBytes(32).toString('hex')},bridge=await startBridge(config);t.after(()=>bridge.stop());return config;
}
async function pair(c){return await request(c,'/extension/connect',{extensionId:'a'.repeat(32),instanceId:'00000000-0000-0000-0000-000000000001'});}
async function register(c){return (await request(c,'/session/register',{name:'unit-test'})).sessionId;}
test('tool names are unique and schemas reject unknown fields',()=>{assert.equal(new Set(TOOLS.map(t=>t.name)).size,TOOLS.length);for(const t of TOOLS)assert.equal(t.inputSchema.additionalProperties,false);assert.throws(()=>validateArgs('browser_tabs',{all:true}));});
test('URL policy rejects browser internals, files, scripts and embedded credentials',()=>{for(const u of ['javascript:alert(1)','file:///etc/passwd','chrome://settings','data:text/html,test','https://a:b@example.org','https://chromewebstore.google.com/detail/a'])assert.throws(()=>safeUrl(u));assert.equal(safeUrl('https://example.org'),'https://example.org/');assert.equal(safeUrl('about:blank'),'about:blank');});
test('click must have exactly one target; coordinates bounded',()=>{assert.throws(()=>validateArgs('browser_click',{tabId:1}));assert.throws(()=>validateArgs('browser_click',{tabId:1,ref:'r1',x:1,y:2}));assert.throws(()=>validateArgs('browser_click',{tabId:1,x:1}));assert.throws(()=>validateArgs('browser_click',{tabId:1,x:-1,y:1}));assert.deepEqual(validateArgs('browser_click',{tabId:1,x:2,y:2}),{tabId:1,x:2,y:2});});
test('move requires one unambiguous target and valid CSS coordinates',()=>{
 for(const args of [{tabId:1},{tabId:1,x:1},{tabId:1,x:-1,y:0},{tabId:1,ref:'r1',selector:'button'},{tabId:1,selector:'button',x:0,y:0}])assert.throws(()=>validateArgs('browser_move',args));
 assert.deepEqual(validateArgs('browser_move',{tabId:1,x:0,y:0}),{tabId:1,x:0,y:0});
});
test('nested drag paths and timeouts are validated',()=>{assert.throws(()=>validateArgs('browser_drag',{tabId:1,points:[{x:0,y:0}]}));assert.throws(()=>validateArgs('browser_drag',{tabId:1,points:[{x:0,y:0},{x:2,y:3,evil:true}]}));assert.throws(()=>validateArgs('browser_wait',{tabId:1,text:'x',timeoutMs:99999}));assert.throws(()=>validateArgs('browser_wait',{tabId:1,text:'x',selector:'x'}));});
test('eval and cdp schemas bound their inputs',()=>{assert.throws(()=>validateArgs('browser_eval',{tabId:1}));assert.throws(()=>validateArgs('browser_eval',{tabId:1,expression:''}));assert.throws(()=>validateArgs('browser_eval',{tabId:1,expression:'1',extra:1}));assert.deepEqual(validateArgs('browser_eval',{tabId:1,expression:'1+1'}),{tabId:1,expression:'1+1'});assert.throws(()=>validateArgs('browser_cdp',{tabId:1}));assert.throws(()=>validateArgs('browser_cdp',{tabId:1,method:'Page.reload',params:'x'}));assert.deepEqual(validateArgs('browser_cdp',{tabId:1,method:'Page.reload'}),{tabId:1,method:'Page.reload'});assert.deepEqual(validateArgs('browser_cdp',{tabId:1,method:'Network.setCookie',params:{name:'a',value:'b',nested:{x:[1,2]}}}).params,{name:'a',value:'b',nested:{x:[1,2]}});});
test('loopback bridge authenticates and rejects web Origin / rebinding Host',async t=>{
 const c=await fixture(t),url=`http://127.0.0.1:${c.port}/status`;
 assert.equal((await fetch(url)).status,401);
 assert.equal((await fetch(url,{headers:{Authorization:`Bearer ${c.token}`,Origin:'https://evil.example'}})).status,403);
 const status=await new Promise((resolve,reject)=>{const r=http.get({host:'127.0.0.1',port:c.port,path:'/status',headers:{Host:'evil.example',Authorization:`Bearer ${c.token}`}},r=>{r.resume();resolve(r.statusCode);});r.on('error',reject);});assert.equal(status,403);
 assert.equal((await request(c,'/status')).product,'tobkiri-tabs');
});
test('extension Origin cannot access the internal RPC or admin API',async t=>{const c=await fixture(t);const r=await fetch(`http://127.0.0.1:${c.port}/shutdown`,{method:'POST',headers:{Authorization:`Bearer ${c.token}`,Origin:`chrome-extension://${'a'.repeat(32)}`,'Content-Type':'application/json'},body:'{}'});assert.equal(r.status,403);});
test('offline operations fail explicitly; status remains available',async t=>{const c=await fixture(t),sessionId=await register(c);assert.equal((await request(c,'/rpc',{sessionId,name:'browser_status',args:{}})).result.connected,false);await assert.rejects(request(c,'/rpc',{sessionId,name:'browser_workspace_create',args:{name:'test'}}),/EXTENSION_OFFLINE/);});
test('bridge routes commands by generated session owner and returns results',async t=>{
 const c=await fixture(t),sessionId=await register(c),{connectionId}=await pair(c);
 const call=request(c,'/rpc',{sessionId,name:'browser_tabs',args:{}});
 const {messages}=await request(c,`/extension/poll?connectionId=${connectionId}`);
 const command=messages.find(m=>m.kind==='command');assert.equal(command.owner,sessionId);assert.equal(command.name,'browser_tabs');assert.ok(command.deadline>Date.now());
 await request(c,'/extension/result',{connectionId,id:command.id,result:{tabs:[]}});assert.deepEqual((await call).result,{tabs:[]});
});
test('disconnected extension IDs cannot return results; another browser is rejected',async t=>{const c=await fixture(t);await pair(c);await assert.rejects(request(c,'/extension/connect',{extensionId:'b'.repeat(32),instanceId:'00000000-0000-0000-0000-000000000002'}),/Another browser/);await assert.rejects(request(c,'/extension/result',{connectionId:'wrong',id:'wrong',result:{}}),/expired/);});
test('session release revokes commands instead of replaying them',async t=>{const c=await fixture(t),sessionId=await register(c);await pair(c);const pending=request(c,'/rpc',{sessionId,name:'browser_tabs',args:{}}).catch(e=>e);await new Promise(r=>setTimeout(r,30));await request(c,'/session/release',{sessionId});assert.match((await pending).message,/session ended/);await assert.rejects(request(c,'/rpc',{sessionId,name:'browser_tabs',args:{}}),/expired/);});
test('MCP stdio initialization, negotiation, listing, parse errors and tool errors',async t=>{
 const c=await fixture(t),input=new PassThrough(),output=new PassThrough();const rows=[];let buf='';output.on('data',chunk=>{buf+=chunk;let n;while((n=buf.indexOf('\n'))>=0){rows.push(JSON.parse(buf.slice(0,n)));buf=buf.slice(n+1);}});
 const mcp=await runMcp(c,{input,output});t.after(()=>mcp.shutdown());
 const send=(method,params,id)=>input.write(JSON.stringify({jsonrpc:'2.0',...(id===undefined?{}:{id}),method,params})+'\n');
 async function response(id){for(let n=0;n<100;n++){const r=rows.find(r=>r.id===id);if(r)return r;await new Promise(r=>setTimeout(r,10));}throw new Error('No MCP response');}
 send('tools/list',{},0);assert.equal((await response(0)).error.code,-32000);
 send('initialize',{protocolVersion:'9999-01-01',capabilities:{},clientInfo:{name:'test',version:'1'}},1);assert.equal((await response(1)).result.protocolVersion,'2025-11-25');send('notifications/initialized');
 send('tools/list',{},2);assert.equal((await response(2)).result.tools.length,TOOLS.length);
 send('tools/call',{name:'browser_click',arguments:{tabId:1}},3);assert.equal((await response(3)).result.isError,true);
 send('tools/call',{name:'browser_status',arguments:{}},4);assert.equal(JSON.parse((await response(4)).result.content[0].text).connected,false);
 input.write('bad json\n');for(let n=0;n<50&&!rows.some(r=>r.error?.code===-32700);n++)await new Promise(r=>setTimeout(r,10));assert.ok(rows.some(r=>r.error?.code===-32700));
});

test('saveAs writes capture payloads under capturesDir and strips base64 from the reply',async t=>{
 const c=await fixture(t),sessionId=await register(c),{connectionId}=await pair(c);
 const capDir=mkdtempSync(join(tmpdir(),'tbt-cap-'));
 const input=new PassThrough(),output=new PassThrough();const rows=[];let buf='';output.on('data',chunk=>{buf+=chunk;let n;while((n=buf.indexOf('\n'))>=0){rows.push(JSON.parse(buf.slice(0,n)));buf=buf.slice(n+1);}});
 const mcp=await runMcp({...c,capturesDir:capDir},{input,output});t.after(()=>mcp.shutdown());
 const send=(method,params,id)=>input.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');
 async function response(id){for(let n=0;n<200;n++){const r=rows.find(r=>r.id===id);if(r)return r;await new Promise(r=>setTimeout(r,10));}throw new Error('No MCP response');}
 send('initialize',{protocolVersion:'2025-11-25',capabilities:{},clientInfo:{name:'test',version:'1'}},1);await response(1);send('notifications/initialized');
 send('tools/call',{name:'browser_pdf',arguments:{tabId:1,saveAs:'unit/x.pdf'}},10);
 let cmd;for(let n=0;n<100&&!cmd;n++){const {messages}=await request(c,`/extension/poll?connectionId=${connectionId}`);cmd=messages.find(m=>m.kind==='command');if(!cmd)await new Promise(r=>setTimeout(r,20));}
 assert.equal(cmd.name,'browser_pdf');
 await request(c,'/extension/result',{connectionId,id:cmd.id,result:{tabId:1,pdf:{data:Buffer.from('%PDF-1.4\n%%EOF\n').toString('base64'),mimeType:'application/pdf'}}});
 const r10=JSON.parse((await response(10)).result.content[0].text);
 assert.ok(r10.pdfSaved.path.startsWith(capDir));assert.equal(r10.pdfSaved.bytes>0,true);assert.equal(r10.pdf,undefined);
 assert.equal(readFileSync(join(capDir,'unit','x.pdf'),'utf8'),'%PDF-1.4\n%%EOF\n');
 send('tools/call',{name:'browser_pdf',arguments:{tabId:1,saveAs:'../evil.pdf'}},11);
 assert.equal((await response(11)).result.isError,true);
});

test('screenshot pixel dimensions are reported for Retina coordinate conversion',()=>{
 const b=Buffer.alloc(24);b.write('\x89PNG',0,'latin1');b.writeUInt32BE(2400,16);b.writeUInt32BE(1600,20);assert.deepEqual(imageSize(b.toString('base64'),'png'),{width:2400,height:1600});
 const jpeg=Buffer.from([255,216,255,192,0,11,8,3,32,4,176,1,1,17,0,255,217]);assert.deepEqual(imageSize(jpeg.toString('base64'),'jpeg'),{width:1200,height:800});
 assert.throws(()=>imageSize('','png'));
});
