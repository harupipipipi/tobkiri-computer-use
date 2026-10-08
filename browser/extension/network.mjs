import {AppError} from './shared.mjs';

// Memory-only, exact-tab capture. Fetch pauses are settled in this worker, never
// left waiting for another MCP call. Rules expire even if the client disappears.
const privateHeaders = /^(authorization|proxy-authorization|cookie|set-cookie)$/i;
const text = (value, size=8192) => String(value ?? '').slice(0, size);
function headers(value) {
  return Object.fromEntries(Object.entries(value || {}).slice(0,100).map(([k,v]) =>
    [text(k,256), privateHeaders.test(k) ? '[redacted]' : text(v,1024)]));
}
export function matchesUrl(pattern, url) {
  return new RegExp('^' + pattern.split('*').map(p=>p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*') + '$').test(url);
}
function base64Utf8(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = ''; for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
export function createNetworkController({send,authorize,abort,active=()=>true,clock=Date.now,schedule=setTimeout,unschedule=clearTimeout}) {
  const sessions = new Map();
  function owned(tabId,owner) {
    const s=sessions.get(tabId);
    if(!s || s.owner!==owner)throw new AppError('NETWORK_NOT_STARTED','Start network capture on this granted tab first.');
    return s;
  }
  function entry(s,kind,params) {
    const item={seq:++s.seq,at:clock(),kind,...params};
    s.entries.push(item);s.bytes+=new TextEncoder().encode(JSON.stringify(item)).length;
    while(s.entries.length>s.maxEntries || s.bytes>2000000){s.bytes-=new TextEncoder().encode(JSON.stringify(s.entries.shift())).length;s.dropped++;}
    return item;
  }
  function forget(tabId) {
    const s=sessions.get(tabId);if(s)unschedule(s.timer);
    sessions.delete(tabId);
  }
  async function disableRoutes(tabId,s,reason) {
    unschedule(s.timer);s.rules=[];s.expiresAt=null;
    try {await send(tabId,'Fetch.disable',{});entry(s,'routes-stopped',{reason});}
    catch(e){if(sessions.get(tabId)===s && active(tabId)){entry(s,'interception-error',{error:text(e.message)});await abort(tabId,e);}throw e;}
  }
  async function start(tabId,owner,{maxEntries=200,includePostData=false}={}) {
    if(sessions.has(tabId))throw new AppError('NETWORK_ALREADY_STARTED','Read or stop the existing capture before starting a new one.');
    const s={owner,maxEntries,includePostData,entries:[],bytes:0,requests:new Map(),seq:0,dropped:0,rules:[],expiresAt:null,queue:Promise.resolve(),pending:0};
    sessions.set(tabId,s);
    try{await send(tabId,'Network.enable',{maxTotalBufferSize:4000000,maxResourceBufferSize:1000000,maxPostDataSize:4096});}
    catch(e){if(sessions.get(tabId)===s){await abort(tabId,e);forget(tabId);}throw e;}
    return {tabId,capturing:true,maxEntries,includePostData,scope:'root tab debugger session; child workers/OOPIF sessions are not attached'};
  }
  async function stop(tabId,owner) {
    const s=owned(tabId,owner);
    await disableRoutes(tabId,s,'explicit-stop');
    try{await send(tabId,'Network.disable',{});}catch(e){if(sessions.get(tabId)===s && active(tabId))await abort(tabId,e);throw e;}
    forget(tabId);return {tabId,stopped:true,logsCleared:true};
  }
  function read(tabId,owner,{afterSeq=0,limit=100}={}) {
    const s=owned(tabId,owner),entries=[];let bytes=0;
    for(const e of s.entries)if(e.seq>afterSeq){
      const size=new TextEncoder().encode(JSON.stringify(e)).length;
      if(entries.length>=limit || bytes+size>500000)break;
      entries.push(e);bytes+=size;
    }
    return {tabId,entries:structuredClone(entries),nextSeq:entries.at(-1)?.seq??afterSeq,latestSeq:s.seq,
      oldestSeq:s.entries[0]?.seq??null,dropped:s.dropped,hasMore:(entries.at(-1)?.seq??afterSeq)<s.seq,rules:s.rules.length,expiresAt:s.expiresAt};
  }
  async function body(tabId,owner,{requestId,maxBytes=64000}) {
    const s=owned(tabId,owner),r=s.requests.get(requestId);
    if(!r)throw new AppError('NETWORK_REQUEST_UNKNOWN','Request ID is not retained by this capture.');
    if(!r.finished)throw new AppError('NETWORK_BODY_NOT_READY','Request has not finished successfully.');
    if(r.bytes>maxBytes)throw new AppError('NETWORK_BODY_TOO_LARGE','Response exceeds maxBytes.');
    const result=await send(tabId,'Network.getResponseBody',{requestId});
    const bytes=result.base64Encoded?Math.floor(result.body.length*3/4)-(result.body.endsWith('==')?2:result.body.endsWith('=')?1:0):new TextEncoder().encode(result.body).length;
    if(bytes>maxBytes)throw new AppError('NETWORK_BODY_TOO_LARGE','Response exceeds maxBytes.');
    return {tabId,requestId,...result,bytes};
  }
  async function routes(tabId,owner,{rules,leaseMs=30000}) {
    const s=owned(tabId,owner);
    if(!rules.length){await disableRoutes(tabId,s,'explicit-clear');return {tabId,rules:0,expiresAt:null};}
    // Publish before enabling: a requestPaused event can precede the enable ACK.
    unschedule(s.timer);s.rules=structuredClone(rules);s.expiresAt=clock()+leaseMs;
    s.timer=schedule(()=>{if(sessions.get(tabId)===s)void disableRoutes(tabId,s,'lease-expired').catch(()=>{});},leaseMs);
    try{await send(tabId,'Fetch.enable',{patterns:rules.map(r=>({urlPattern:r.urlPattern,requestStage:'Request'}))});}
    catch(e){s.rules=[];unschedule(s.timer);if(sessions.get(tabId)===s && active(tabId))await abort(tabId,e);throw e;}
    return {tabId,rules:rules.length,expiresAt:s.expiresAt,stage:'Request'};
  }
  async function paused(tabId,p) {
    if(!active(tabId))return; // Detaching already releases its paused requests.
    const s=sessions.get(tabId);
    try {
      let rule;
      if(s && s.expiresAt>clock() && !p.responseStatusCode && !p.responseErrorReason) {
        try {await authorize(tabId,s.owner,true);}
        catch {
          if(!active(tabId) || sessions.get(tabId)!==s)return;
          await send(tabId,'Fetch.continueRequest',{requestId:p.requestId});await disableRoutes(tabId,s,'permission-changed');return;
        }
        // Re-check the lease/session after asynchronous guard checks.
        if(!active(tabId) || sessions.get(tabId)!==s)return;
        // Fetch.disable releases these requests; don't settle them a second time
        // if clear/expiry raced the asynchronous guard.
        if(s.expiresAt===null)return;
        if(sessions.get(tabId)===s && s.expiresAt>clock())
          rule=s.rules.find(r=>matchesUrl(r.urlPattern,p.request.url)&&(!r.method||r.method===p.request.method));
      }
      const params={requestId:p.requestId};let method='Fetch.continueRequest';
      if(rule?.action==='block'){method='Fetch.failRequest';params.errorReason='BlockedByClient';}
      if(rule?.action==='fulfill'){
        method='Fetch.fulfillRequest';params.responseCode=rule.status??200;
        params.responseHeaders=rule.headers||[];params.body=base64Utf8(rule.body??'');
      }
      if(rule?.action==='modify') {
        if(rule.url!==undefined)params.url=rule.url;
        if(rule.requestMethod!==undefined)params.method=rule.requestMethod;
        if(rule.headers!==undefined)params.headers=rule.headers;
        if(rule.postData!==undefined)params.postData=base64Utf8(rule.postData);
      }
      await send(tabId,method,params); // Exactly one settlement, never replay.
      if(sessions.get(tabId)===s && s)entry(s,'route',{requestId:p.networkId,fetchId:p.requestId,url:text(p.request.url),action:rule?.action||'continue'});
    } catch(e) {
      if(!active(tabId) || (s && sessions.get(tabId)!==s))return;
      if(s)entry(s,'interception-error',{error:text(e.message)});
      // Detach releases pending pauses. An uncertain block/fulfill is not retried.
      await abort(tabId,e);
    }
  }
  async function metadata(tabId,s,method,p) {
    try{await authorize(tabId,s.owner,false);}catch{if(sessions.get(tabId)===s && active(tabId))await abort(tabId,new AppError('NETWORK_PERMISSION_LOST','Capture permission changed.'));return;}
    if(sessions.get(tabId)!==s)return;
    const requestId=p.requestId;
    if(method==='Network.requestWillBeSent') {
      s.requests.delete(requestId);s.requests.set(requestId,{finished:false});
      if(s.requests.size>s.maxEntries)s.requests.delete(s.requests.keys().next().value);
      entry(s,'request',{requestId,...p.fields});
    } else if(method==='Network.responseReceived') {
      entry(s,'response',{requestId,...p.fields});
    } else if(method==='Network.loadingFinished') {
      const r=s.requests.get(requestId);if(r){r.finished=true;r.bytes=p.encodedDataLength;}
      entry(s,'finished',{requestId,encodedDataLength:p.encodedDataLength});
    } else if(method==='Network.loadingFailed') {
      entry(s,'failed',{requestId,errorText:text(p.errorText),blockedReason:p.blockedReason,canceled:!!p.canceled});
    }
  }
  async function event(source,method,p) {
    if(source.sessionId || source.tabId===undefined)return;
    const tabId=source.tabId;
    if(method==='Fetch.requestPaused'){await paused(tabId,p);return;}
    const s=sessions.get(tabId);if(!s || !['Network.requestWillBeSent','Network.responseReceived','Network.loadingFinished','Network.loadingFailed'].includes(method))return;
    // Order metadata despite asynchronous Chrome permission checks. Fetch events
    // bypass this queue so an awaitPromise evaluation cannot deadlock its fetches.
    if(s.pending>=500){s.dropped++;return;}
    let payload={requestId:p.requestId};
    if(method==='Network.requestWillBeSent') {
      payload.fields={url:text(p.request.url),method:p.request.method,type:p.type,
        headers:headers(p.request.headers),...(s.includePostData?{postData:text(p.request.postData,4096)}:{}),
        ...(p.redirectResponse?{redirectStatus:p.redirectResponse.status}: {})};
    } else if(method==='Network.responseReceived') {
      payload.fields={url:text(p.response.url),status:p.response.status,mimeType:text(p.response.mimeType,256),
        headers:headers(p.response.headers),fromDiskCache:!!p.response.fromDiskCache,fromServiceWorker:!!p.response.fromServiceWorker};
    } else payload={...payload,encodedDataLength:p.encodedDataLength,errorText:text(p.errorText),blockedReason:p.blockedReason,canceled:!!p.canceled};
    s.pending++;
    const job=s.queue.then(()=>sessions.get(tabId)===s?metadata(tabId,s,method,payload):undefined);
    s.queue=job.catch(()=>{});
    try{await job;}finally{s.pending--;}
  }
  return {start,stop,read,body,routes,event,forget,has:tabId=>sessions.has(tabId)};
}
