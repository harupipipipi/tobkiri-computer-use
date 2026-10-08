import http from 'node:http';
import {randomUUID} from 'node:crypto';
import {secureEqual} from './config.mjs';
import {VERSION, validateArgs} from '../extension/shared.mjs';
import {packReader} from './cursor-pack.mjs';
import {isAbsolute} from 'node:path';

const reply=(res,code,data)=>{ if (!res.writableEnded && !res.destroyed) { res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}); res.end(JSON.stringify(data)); } };
async function body(req, limit=256*1024) {
  if (!req.headers['content-type']?.startsWith('application/json')) throw new Error('Content-Type must be application/json.');
  let size=0; const chunks=[];
  for await(const chunk of req) { size+=chunk.length; if(size>limit) throw new Error('Request body too large.'); chunks.push(chunk); }
  const b=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if(!b || typeof b!=='object' || Array.isArray(b)) throw new Error('Object body required.'); return b;
}
export async function startBridge(config) {
  let readPack=packReader(config);
  const sessions=new Map(), pending=new Map(); let extension=null, closing=false;
  const clientList=()=>[...sessions.values()].map(({id,name})=>({id,name}));
  const connected=()=>extension && Date.now()-extension.lastSeen<45000;
  function enqueue(message) {
    if(!extension) return;
    if(extension.queue.length>=256) { disconnect('Extension queue overflow.'); return; }
    extension.queue.push(message); flush();
  }
  function flush() {
    if(extension?.poll && extension.queue.length) {
      const p=extension.poll; extension.poll=null; clearTimeout(p.timer);
      reply(p.res,200,{messages:extension.queue.splice(0,64)});
    }
  }
  function finish(id,error,result) {
    const p=pending.get(id); if(!p) return;
    pending.delete(id); clearTimeout(p.timer);
    reply(p.res,error?400:200,error?{error}:{result});
  }
  function cancel(id,reason='Canceled. An already dispatched browser event cannot be undone.') {
    if(!pending.has(id)) return;
    if(extension) extension.queue=extension.queue.filter(m=>m.id!==id);
    enqueue({kind:'cancel',id}); finish(id,reason);
  }
  function release(id) {
    sessions.delete(id);
    for(const [key,p] of pending) if(p.sessionId===id) cancel(key,'MCP session ended.');
    enqueue({kind:'sessions',sessions:clientList()});
  }
  function disconnect(reason) {
    if(extension?.poll) { clearTimeout(extension.poll.timer); reply(extension.poll.res,409,{error:reason}); }
    extension=null;
    for(const id of pending.keys()) finish(id,reason);
  }
  function checkExtension(id) {
    if(!extension || extension.id!==id) throw new Error('Extension connection expired; reconnect.');
    extension.lastSeen=Date.now(); return extension;
  }
  function checkSession(id) {
    const s=sessions.get(id); if(!s) throw new Error('MCP session expired; restart the MCP connection.');
    s.lastSeen=Date.now(); return s;
  }
  const server=http.createServer(async(req,res)=>{
    // Numeric Host blocks DNS rebinding. Ordinary web origins and preflights never receive CORS permission.
    const origin=req.headers.origin;
    if(req.headers.host!==`127.0.0.1:${config.port}` || (origin && !/^chrome-extension:\/\/[a-p]{32}$/.test(origin))) return reply(res,403,{error:'Forbidden origin or host.'});
    if(!secureEqual(req.headers.authorization || '',`Bearer ${config.token}`)) return reply(res,401,{error:'Authentication required.'});
    let url; try { url=new URL(req.url,`http://127.0.0.1:${config.port}`); } catch { return reply(res,400,{error:'Invalid URL.'}); }
    const path=url.pathname;
    // Extension contexts cannot call the internal MCP/session/admin endpoints.
    if(origin && !path.startsWith('/extension/')) return reply(res,403,{error:'Extension endpoint only.'});
    try {
      if(req.method==='GET' && path==='/status') return reply(res,200,{product:'tobkiri-tabs',version:VERSION,connected:Boolean(connected()),sessions:sessions.size});
      if(req.method==='POST' && path==='/cursor/configure') {
        // Trusted local launcher only, never an MCP/page/extension operation.
        const b=await body(req);
        if(typeof b.path!=='string'||!isAbsolute(b.path))throw new Error('Absolute cursor-pack path required.');
        readPack=packReader({...config,cursorPackPath:b.path});
        return reply(res,200,{ok:true});
      }
      if(req.method==='POST' && path==='/session/register') {
        const b=await body(req); if(sessions.size>=16) throw new Error('Too many MCP sessions.');
        const id=randomUUID(); sessions.set(id,{id,name:String(b.name || 'MCP client').slice(0,80),lastSeen:Date.now()});
        enqueue({kind:'sessions',sessions:clientList()}); return reply(res,200,{sessionId:id});
      }
      if(req.method==='POST' && path==='/session/ping') { const b=await body(req); checkSession(b.sessionId); return reply(res,200,{ok:true}); }
      if(req.method==='POST' && path==='/session/release') { const b=await body(req); release(b.sessionId); return reply(res,200,{ok:true}); }
      if(req.method==='POST' && path==='/extension/connect') {
        const b=await body(req);
        if(!/^[a-p]{32}$/.test(b.extensionId || '')) throw new Error('Invalid extension ID.');
        if(!/^[a-f0-9-]{36}$/.test(b.instanceId || '')) throw new Error('Invalid browser instance ID.');
        if(origin && origin!==`chrome-extension://${b.extensionId}`) throw new Error('Extension identity mismatch.');
        if(connected() && (extension.extensionId!==b.extensionId || extension.instanceId!==b.instanceId)) throw new Error('Another browser/extension is connected. Disconnect it first.');
        disconnect('Extension reconnected. In-flight operations were not replayed.');
        extension={id:randomUUID(),extensionId:b.extensionId,instanceId:b.instanceId,lastSeen:Date.now(),queue:[],poll:null};
        return reply(res,200,{connectionId:extension.id,sessions:clientList(),version:VERSION});
      }
      if(req.method==='GET' && path==='/extension/poll') {
        const e=checkExtension(url.searchParams.get('connectionId'));
        if(origin && origin!==`chrome-extension://${e.extensionId}`) throw new Error('Extension identity mismatch.');
        if(e.poll) throw new Error('Only one poll is allowed.');
        const timer=setTimeout(()=>{if(e.poll?.res===res) e.poll=null; reply(res,200,{messages:[]});},15000);
        e.poll={res,timer}; res.on('close',()=>{clearTimeout(timer); if(e.poll?.res===res)e.poll=null;});
        flush(); return;
      }
      if(req.method==='POST' && path==='/extension/result') {
        const b=await body(req,24*1024*1024); const e=checkExtension(b.connectionId);
        if(origin && origin!==`chrome-extension://${e.extensionId}`) throw new Error('Extension identity mismatch.');
        if(typeof b.id!=='string') throw new Error('Invalid result ID.');
        finish(b.id,b.error?String(b.error).slice(0,1500):null,b.result);
        return reply(res,200,{ok:true});
      }
      if(req.method==='POST' && path==='/rpc') {
        const b=await body(req); const session=checkSession(b.sessionId);
        validateArgs(b.name,b.args ?? {});
        if(!connected()) {
          if(b.name==='browser_status') return reply(res,200,{result:{connected:false,message:'Open the extension, paste your pairing code and connect.'}});
          throw new Error('EXTENSION_OFFLINE: Open the extension and connect. No browser action was sent.');
        }
        if(pending.size>=128 || [...pending.values()].filter(p=>p.sessionId===session.id).length>=32) throw new Error('Too many outstanding operations.');
        const id=randomUUID(); const duration=Math.min(35000,Math.max(25000,(b.args?.timeoutMs || 0)+4000));
        const timer=setTimeout(()=>cancel(id,'TIMEOUT: Outcome may be uncertain. Inspect the tab before retrying a click, submit or other non-idempotent action.'),duration);
        pending.set(id,{res,timer,sessionId:session.id});
        // Internal HTTP, not MCP Streamable HTTP: transport abort explicitly cancels this queued command.
        res.on('close',()=>{if(!res.writableEnded) cancel(id,'Client canceled the operation.');});
        const cursor=await readPack();
        if(!pending.has(id))return; // Canceled while reading presentation data.
        enqueue({kind:'command',id,owner:session.id,name:b.name,args:b.args ?? {},cursor,deadline:Date.now()+duration}); return;
      }
      if(req.method==='POST' && path==='/shutdown') {
        await body(req); reply(res,200,{ok:true}); setTimeout(()=>stop(),30); return;
      }
      reply(res,404,{error:'Unknown endpoint.'});
    } catch(error) { reply(res,400,{error:error.message || 'Request failed.'}); }
  });
  server.headersTimeout=10000; server.requestTimeout=40000; server.keepAliveTimeout=2000; server.maxConnections=160;
  const sweep=setInterval(()=>{
    for(const [id,s] of sessions) if(Date.now()-s.lastSeen>90000) release(id);
    if(extension && !connected()) disconnect('Extension heartbeat expired.');
  },15000); sweep.unref();
  async function stop() {
    if(closing)return; closing=true; clearInterval(sweep); disconnect('Bridge stopped.');
    server.closeAllConnections(); await new Promise(resolve=>server.close(resolve));
  }
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(config.port,'127.0.0.1',resolve);});
  return {server,stop};
}
