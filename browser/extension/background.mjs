import {AppError,validateArgs,safeUrl,VERSION} from './shared.mjs';
import {pageOp} from './page-ops.mjs';
import {imageSize} from './image-size.mjs';
import {renderCursor} from './cursor-overlay.mjs';
import {CURSOR_THEME} from './cursor-theme.mjs';
import {cursorRuntime} from './character-runtime.mjs';
import {renderSharedCursor} from './shared-cursor-overlay.mjs';
import {createNetworkController} from './network.mjs';

let config={enabled:false,allowCreate:false,protectActive:true,port:17653,token:''};
let workspaces={},grants={},audit=[],clients=[],connected=false,lastError='',connectionId=null;
let epoch=0,loopRunning=false,reconnectTimer=null;const attached=new Set(),worlds=new Map(),locks=new Map(),canceled=new Set(),intentionalDetach=new Set(),screencastWaiters=new Map();
const network=createNetworkController({send:sendNetwork,
  active:tabId=>attached.has(tabId),
  authorize:(tabId,owner,mutating)=>guard(tabId,{owner,epoch,id:'network-event',deadline:Date.now()+5000},mutating),
  abort:async(tabId,e)=>{if(grants[tabId])grants[tabId].revoked=true;record('network-stopped',tabId,e.code||'error');await detach(tabId);}});
async function sendNetwork(tabId,method,params){
  if(!attached.has(tabId))throw new AppError('DEBUGGER_DETACHED','Network session detached; no command was retried.');
  let timer;
  try{return await Promise.race([chrome.debugger.sendCommand({tabId},method,params),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new AppError('CDP_TIMEOUT','Network command did not acknowledge; no command was retried.')),5000);})]);}
  finally{clearTimeout(timer);}
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const boot=(async()=>{
  await chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
  const c=await chrome.storage.local.get('config');if(c.config)config={...config,...c.config};
  if(!config.instanceId){config.instanceId=crypto.randomUUID();await chrome.storage.local.set({config});}
  const s=await chrome.storage.session.get(['workspaces','grants','audit']);workspaces=s.workspaces||{};grants=s.grants||{};audit=s.audit||[];
  // If Chrome killed the worker, adopt only debugger targets that are ALSO in our explicit grant ledger.
  try{const targets=await chrome.debugger.getTargets();for(const t of targets)if(t.attached && grants[t.tabId] && !grants[t.tabId].revoked){
    attached.add(t.tabId);
    // Memory-only routes cannot survive a worker restart. Release orphan pauses.
    try{await sendNetwork(t.tabId,'Fetch.disable',{});await sendNetwork(t.tabId,'Network.disable',{});}catch{await detach(t.tabId);}
  }}catch{}
  await chrome.alarms.create('bridge-reconnect',{periodInMinutes:0.5});await badge();
})();
function record(name,tabId,status) {audit.unshift({at:new Date().toISOString(),name,tabId:tabId??null,status});audit=audit.slice(0,120);void persist();}
async function persist(){await chrome.storage.session.set({workspaces,grants,audit});}
async function badge(){await chrome.action.setBadgeText({text:config.enabled?(connected?'ON':'…'):'OFF'});await chrome.action.setBadgeBackgroundColor({color:config.enabled?'#28adba':'#697080'});}
async function http(path,body,timeout=21000) {
  const r=await fetch(`http://127.0.0.1:${config.port}${path}`,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${config.token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(timeout),cache:'no-store'});
  const data=await r.json();if(!r.ok || data.error)throw new Error(data.error||`HTTP ${r.status}`);return data;
}
async function syncClients(next) {
  clients=next;
  const alive=new Set(next.map(c=>c.id));
  for(const [id,w] of Object.entries(workspaces))if(!alive.has(w.owner))await releaseWorkspace(id);
  await persist();
}
async function loop() {
  await boot;if(loopRunning || !config.token)return;loopRunning=true;
  try {
    const info=await http('/extension/connect',{extensionId:chrome.runtime.id,instanceId:config.instanceId,version:VERSION});
    connectionId=info.connectionId;await syncClients(info.sessions);connected=true;lastError='';await badge();
    while(config.token) {
      // The bounded poll returns at least every 15 seconds. Persisting connection status also renews MV3's idle timer.
      await chrome.storage.session.set({lastHeartbeat:Date.now()});
      const cid=connectionId;const batch=await http(`/extension/poll?connectionId=${encodeURIComponent(cid)}`);
      if(cid!==connectionId)break;
      for(const message of batch.messages||[]) {
        if(message.kind==='cancel') {canceled.add(message.id);setTimeout(()=>canceled.delete(message.id),60000);}
        else if(message.kind==='sessions')await syncClients(message.sessions);
        else if(message.kind==='command')void runCommand(message,cid);
      }
    }
  } catch(e) {lastError=String(e.message).slice(0,220);}
  finally {
    connected=false;connectionId=null;epoch++;loopRunning=false;await detachAll();await badge();
    clearTimeout(reconnectTimer);if(config.token)reconnectTimer=setTimeout(()=>void loop(),3000);
  }
}
function checkpoint(ctx) {
  if(!config.enabled)throw new AppError('PAUSED','User paused automation in the extension.');
  if(ctx && (ctx.epoch!==epoch || canceled.has(ctx.id) || Date.now()>ctx.deadline || !connected))throw new AppError('CANCELED','Operation stopped or its deadline expired.');
}
async function getWorkspace(id,owner) {
  const w=workspaces[id];if(!w || w.owner!==owner)throw new AppError('NOT_GRANTED','Workspace is not owned by this MCP session.');return w;
}
async function guard(tabId,ctx,mutating=true) {
  checkpoint(ctx);const g=grants[tabId];
  if(!g || g.owner!==ctx.owner || g.revoked)throw new AppError('NOT_GRANTED','This tab is not granted to this MCP session.');
  if(workspaces[g.workspaceId]?.paused)throw new AppError('WORKSPACE_PAUSED','User paused this workspace.');
  const tab=await chrome.tabs.get(tabId);safeUrl(tab.pendingUrl || tab.url || 'about:blank');
  if(tab.incognito)throw new AppError('INCOGNITO_BLOCKED','Incognito is not supported.');
  if(config.protectActive && tab.active && mutating)throw new AppError('HUMAN_ACTIVE_TAB','This tab is active. Ask the user to switch to a different tab; do not disable protection on their behalf.');
  checkpoint(ctx);return tab;
}
async function detach(tabId) {
  network.forget(tabId);
  worlds.delete(tabId);
  if(!attached.has(tabId))return;attached.delete(tabId);intentionalDetach.add(tabId);
  try{await chrome.debugger.detach({tabId});}catch{}finally{setTimeout(()=>intentionalDetach.delete(tabId),1000);}
}
async function detachAll(){await Promise.all([...attached].map(detach));}
async function releaseTab(tabId) {const g=grants[tabId];delete grants[tabId];await detach(Number(tabId));if(g?.restoreAutoDiscardable)await chrome.tabs.update(Number(tabId),{autoDiscardable:true}).catch(()=>{});await persist();}
async function releaseWorkspace(id) {for(const [tabId,g]of Object.entries(grants))if(g.workspaceId===id)await releaseTab(Number(tabId));delete workspaces[id];await persist();}
async function attach(tabId,ctx,mutating=true) {
  await guard(tabId,ctx,mutating);
  if(attached.has(tabId))return;
  let err;
  // Some hosts wedge the debugger channel when attaching to a just-created hidden tab.
  // The init commands below are idempotent, so detach-and-retry once before giving up.
  for(let attempt=0;attempt<2;attempt++){
    if(attempt)await sleep(700);
    checkpoint(ctx);
    let attachTimer,abandoned=false;
    const attachCall=chrome.debugger.attach({tabId},'1.3');
    // If attach resolves after we already gave up on it, undo the late attach instead of
    // leaving a zombie debugger session behind.
    attachCall.then(()=>{if(abandoned){attached.delete(tabId);intentionalDetach.add(tabId);chrome.debugger.detach({tabId}).catch(()=>{}).finally(()=>setTimeout(()=>intentionalDetach.delete(tabId),1000));}}).catch(()=>{});
    try{await Promise.race([attachCall,new Promise((_,reject)=>{attachTimer=setTimeout(()=>reject(new AppError('CDP_TIMEOUT','Debugger attach did not acknowledge.')),Math.max(1,Math.min(8000,ctx.deadline-Date.now())));})]);}
    catch(e){
      clearTimeout(attachTimer);err=e;
      if(e.code!=='CDP_TIMEOUT')throw new AppError('DEBUGGER_UNAVAILABLE',`Cannot attach (another debugger, restricted page or policy). ${e.message}`);
      abandoned=true;await detach(tabId);record('attach-retry',tabId,'attach-timeout');continue;
    }
    clearTimeout(attachTimer);attached.add(tabId);
    try {
      await raw(tabId,'Page.enable',{},ctx,mutating,{revokeOnTimeout:false});
      await raw(tabId,'Runtime.enable',{},ctx,mutating,{revokeOnTimeout:false});
      // Prevent the page from opening an OS file picker. Uploading files is intentionally not an API in v0.1.
      await raw(tabId,'Page.setInterceptFileChooserDialog',{enabled:true},ctx,mutating,{revokeOnTimeout:false});
      return;
    } catch(e){
      err=e;await detach(tabId);
      if(e.code!=='CDP_TIMEOUT')throw e;
      record('attach-retry',tabId,'retry');
    }
  }
  if(grants[tabId]){grants[tabId].revoked=true;await persist();}
  record('cdp-timeout',tabId,'revoked');
  throw err;
}
async function raw(tabId,method,params,ctx,mutating=true,opts) {
  await guard(tabId,ctx,mutating);
  // revokeOnTimeout=false is for commands that are idempotent or read-only: an unacknowledged
  // response leaves nothing uncertain, so the grant can survive a retry.
  const revokeOnTimeout=!opts||opts.revokeOnTimeout!==false;
  const capMs=opts&&opts.timeoutMs||12000;
  let timer;
  try {
    return await Promise.race([
      chrome.debugger.sendCommand({tabId},method,params),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(new AppError('CDP_TIMEOUT','Browser command did not acknowledge. Grant revoked; inspect the tab and explicitly re-grant it before retrying.')),Math.max(1,Math.min(capMs,ctx.deadline-Date.now())));})
    ]);
  } catch(e) {
    if(e.code==='CDP_TIMEOUT'){if(revokeOnTimeout&&grants[tabId])grants[tabId].revoked=true;await detach(tabId);record('cdp-timeout',tabId,revokeOnTimeout?'revoked':'timeout');}
    // Chrome does not emit onDetach for every explicit/late detach. A stale
    // attachment cache must never silently reconnect and replay an action.
    if(/debugger is not attached|not attached to (?:the )?tab/i.test(e.message)){
      if(grants[tabId])grants[tabId].revoked=true;
      attached.delete(tabId);worlds.delete(tabId);await persist();
      record('debugger-detached',tabId,'revoked');
      throw new AppError('DEBUGGER_DETACHED','Debugger disconnected. Grant revoked; inspect the tab before explicitly re-granting it. Input was not retried.');
    }
    throw e;
  } finally {clearTimeout(timer);}
}
async function page(tabId,op,args,ctx,mutating=true) {
  await attach(tabId,ctx,mutating);
  let contextId=worlds.get(tabId);
  if(!contextId) {
    const {frameTree}=await raw(tabId,'Page.getFrameTree',{},ctx,mutating);
    const world=await raw(tabId,'Page.createIsolatedWorld',{frameId:frameTree.frame.id,worldName:'tobkiri-tabs-isolated'},ctx,mutating);
    contextId=world.executionContextId;worlds.set(tabId,contextId);
  }
  const pack=ctx.cursor?.pack;
  const feedback=pack
    ? `(action,p)=>{(${renderCursor.toString()})('hide',p,${JSON.stringify(CURSOR_THEME)});return (${renderSharedCursor.toString()})(action,p,${JSON.stringify(pack)},globalThis.__tobkiriCharacterRuntime ??= (${cursorRuntime.toString()})());}`
    : `(action,p)=>{(${renderSharedCursor.toString()})('hide',p,null,null);return (${renderCursor.toString()})(action,p,${JSON.stringify(CURSOR_THEME)});}`;
  const result=await raw(tabId,'Runtime.evaluate',{expression:`(${pageOp.toString()})(${JSON.stringify(op)},${JSON.stringify(args||{})},${feedback})`,contextId,returnByValue:true,awaitPromise:true,timeout:4000},ctx,mutating);
  if(result.exceptionDetails)throw new AppError('PAGE_ERROR',result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result?.value;
}
async function tabInfo(tabId) {
  const t=await chrome.tabs.get(Number(tabId));const g=grants[tabId];return {tabId:t.id,workspaceId:g?.workspaceId,title:t.title,url:t.url,active:t.active,groupId:t.groupId,revoked:!!g?.revoked,discarded:t.discarded};
}
async function listTabs(owner,workspaceId) {
  const result=[];for(const [id,g]of Object.entries(grants))if(g.owner===owner&&(!workspaceId||g.workspaceId===workspaceId)){try{result.push(await tabInfo(id));}catch{delete grants[id];}}
  return result;
}
async function waitTabReady(tabId,ctx) {
  // Some hosts lazily start the renderer of a fresh background tab; attaching too early wedges
  // the debugger channel. Wait for the tab to report a non-loading, non-discarded state first.
  const until=Date.now()+5000;
  for(;;){
    checkpoint(ctx);
    const t=await chrome.tabs.get(tabId).catch(()=>null);
    if(!t)throw new AppError('TAB_GONE','Tab was closed.');
    if(!t.discarded&&t.status!=='loading')break;
    if(Date.now()>=until)break;
    await sleep(150);
  }
  await sleep(500);
}
async function newTab(owner,workspaceId,url,ctx) {
  checkpoint(ctx);
  if(!config.allowCreate)throw new AppError('CREATE_NOT_ALLOWED','User must enable new AI tabs in the extension.');
  const w=await getWorkspace(workspaceId,owner);
  if(w.paused)throw new AppError('WORKSPACE_PAUSED','User paused this workspace.');
  const tab=await chrome.tabs.create({windowId:w.windowId,url:'about:blank',active:false});
  // Record grant before navigating. Group ownership is a separate ledger, not inferred from membership.
  grants[tab.id]={owner,workspaceId,revoked:false,restoreAutoDiscardable:true};
  try {
    checkpoint(ctx);
    if(w.groupId!==null){try{await chrome.tabGroups.get(w.groupId);}catch{w.groupId=null;}}
    const grouping=w.groupId===null?{tabIds:[tab.id]}:{tabIds:[tab.id],groupId:w.groupId};
    w.groupId=await chrome.tabs.group(grouping);
    await chrome.tabGroups.update(w.groupId,{title:`🔎 ${w.name}`,color:w.color});
    await chrome.tabs.update(tab.id,{autoDiscardable:false});
    await persist();
    if(url!=='about:blank')await waitTabReady(tab.id,ctx);
  } catch(e) {await persist();throw new AppError('PARTIAL_TAB_CREATION',`${e.message} A background tab may remain; inspect browser_tabs before retrying.`);}
  if(url!=='about:blank'){
    // The tab is already created, grouped and granted — a failed first navigation is a
    // warning, not a partial creation. Return the handle (incl. revoked state) so the
    // caller can inspect and retry instead of losing track of a working tab.
    try{await navigate(tab.id,url,ctx,15000);}
    catch(e){return {...await tabInfo(tab.id),warning:`Initial navigation failed: ${e.message}`};}
  }
  return await tabInfo(tab.id);
}
async function navigate(tabId,url,ctx,timeoutMs=15000) {
  safeUrl(url);await attach(tabId,ctx);
  // A navigation can trigger page side effects. Never replay an unacknowledged one.
  const nav=await raw(tabId,'Page.navigate',{url},ctx);
  if(nav.errorText)throw new AppError('NAVIGATION_FAILED',nav.errorText);
  worlds.delete(tabId);const until=Date.now()+timeoutMs;
  while(Date.now()<until) {
    await guard(tabId,ctx);
    try {
      const {frameTree}=await raw(tabId,'Page.getFrameTree',{},ctx);
      if(!nav.loaderId || frameTree.frame.loaderId===nav.loaderId) {
        const r=await page(tabId,'ready',{},ctx);
        if(['interactive','complete'].includes(r.readyState))return await tabInfo(tabId);
      }
    } catch(e) {
      if(!/context|navigat|frame|document/i.test(e.message))throw e;worlds.delete(tabId);
    }
    await sleep(100);
  }
  throw new AppError('NAVIGATION_TIMEOUT','Navigation may have happened. Inspect the tab before retrying.');
}
async function point(tabId,a,ctx) {
  if(a.ref||a.selector)return await page(tabId,'point',a,ctx);
  const v=await page(tabId,'viewport',{},ctx);const x=a.x??v.width/2,y=a.y??v.height/2;
  if(x<0||y<0||x>=v.width||y>=v.height)throw new AppError('OUTSIDE_VIEWPORT','Coordinates must be inside the screenshot viewport in CSS pixels.');
  return {x,y};
}
// Some hosts silently drop trusted input on hidden tabs while still acknowledging the CDP
// command. Arm capture-phase listeners in the isolated world before dispatch, then verify
// delivery afterwards so callers never receive a false success.
async function expectInput(tabId,ctx,types,counts={}) {
  await page(tabId,'armInput',{types},ctx);
  return async()=>{
    await sleep(120);
    let probe;
    try{probe=await page(tabId,'inputProbe',{},ctx);}
    catch(e){
      if(!/context|navigat|frame|document/i.test(e.message))throw e;
      throw new AppError('INPUT_OUTCOME_UNKNOWN','Page context changed before delivery could be verified. The input may have applied; inspect the current page before retrying.');
    }
    if(!types.some(t=>probe?.seen?.[t]))throw new AppError('INPUT_NOT_APPLIED','Required input events were not observed in the page (some hosts drop or defer input on hidden tabs). Do not assume the action applied; verify page state before retrying. The grant is intact.');
    if(Object.entries(counts).some(([type,count])=>(probe?.seen?.[type]||0)<count))throw new AppError('INPUT_OUTCOME_UNKNOWN','Only part of the input gesture was observed. It may have affected the page or browser UI; inspect the current state before retrying. Input was not replayed.');
  };
}
// DOM delivery is an explicit choice, never a retry inferred from missing events.
async function domInput(tabId,op,args,ctx) {
  const r=await page(tabId,op,args,ctx);
  if(!r?.applied)throw new AppError('INPUT_NOT_APPLIED','DOM input was not applied. Inspect the page before retrying.');
  return r;
}
async function click(tabId,p,a,ctx) {
  if(a.inputRoute==='dom'){
    if((a.button&&a.button!=='left')||(a.clickCount&&a.clickCount!==1))throw new AppError('UNSUPPORTED_DOM_CLICK','DOM input supports one left click only.');
    const r=await domInput(tabId,'domClick',{x:p.x,y:p.y},ctx);
    return {trusted:false,via:'dom-click',tag:r.tag};
  }
  const button=a.button||'left',buttons={left:1,right:2,middle:4}[button];
  const clickEvent=button==='right'?'contextmenu':button==='middle'?'auxclick':'click';
  const count=a.clickCount||1;
  const verify=await expectInput(tabId,ctx,['mousedown','mouseup',clickEvent],{mousedown:count,mouseup:count,[clickEvent]:count});
  await page(tabId,'cursor',{action:'move',...p},ctx);
  await raw(tabId,'Input.dispatchMouseEvent',{type:'mouseMoved',...p,button:'none'},ctx);
  for(let n=1;n<=count;n++){
    await page(tabId,'cursor',{action:'down',...p},ctx);
    await raw(tabId,'Input.dispatchMouseEvent',{type:'mousePressed',...p,button,buttons,clickCount:n},ctx);
    try{await raw(tabId,'Input.dispatchMouseEvent',{type:'mouseReleased',...p,button,buttons:0,clickCount:n},ctx);}
    catch(e){await detach(tabId);throw e;}
  }
  try{await page(tabId,'cursor',{action:'move',...p},ctx);}catch{}
  await verify();
  try{await page(tabId,'mark',{x:p.x,y:p.y},ctx);}catch{}
  return {};
}
async function press(tabId,key,ctx,inputRoute) {
  const parts=key.split('+');let last=parts.pop();let modifiers=0;
  for(const p of parts){const n={Alt:1,Control:2,Ctrl:2,Meta:4,Cmd:4,Shift:8}[p];if(!n)throw new AppError('BAD_KEY','Unknown modifier.');modifiers|=n;}
  const table={Enter:['Enter',13,'\r'],Tab:['Tab',9,'\t'],Escape:['Escape',27],Backspace:['Backspace',8],Delete:['Delete',46],ArrowLeft:['ArrowLeft',37],ArrowUp:['ArrowUp',38],ArrowRight:['ArrowRight',39],ArrowDown:['ArrowDown',40],Home:['Home',36],End:['End',35],PageUp:['PageUp',33],PageDown:['PageDown',34],Space:['Space',32,' ']};
  const known=table[last];if(!known&&last.length!==1)throw new AppError('BAD_KEY','Unsupported page key.');
  if((modifiers&6) && !['a','c','v','x','z','y'].includes(last.toLowerCase()))throw new AppError('BROWSER_SHORTCUT_BLOCKED','Browser/OS shortcuts are not provided.');
  if((modifiers&6) && ['c','v','x'].includes(last.toLowerCase()))throw new AppError('CLIPBOARD_BLOCKED','Use browser_type, not the system clipboard.');
  const text=modifiers&7?undefined:(known?.[2]??(!known?last:undefined));
  const params={key:last==='Space'?' ':last,code:known?.[0]||( /[a-z]/i.test(last)?`Key${last.toUpperCase()}`:''),windowsVirtualKeyCode:known?.[1]||last.toUpperCase().charCodeAt(0),modifiers};
  if((modifiers&6)&&last.toLowerCase()==='a')params.commands=['selectAll'];
  if(inputRoute==='dom'){
    const r=await domInput(tabId,'domKey',{key:last,code:params.code,modifiers,text},ctx);
    return {trusted:false,via:'dom-key',inserted:r.inserted,submitted:r.submitted};
  }
  const verify=await expectInput(tabId,ctx,['keydown','keypress','keyup','beforeinput','input'],{keydown:1,keyup:1});
  await raw(tabId,'Input.dispatchKeyEvent',{...params,type:text?'keyDown':'rawKeyDown',...(text?{text,unmodifiedText:text}:{})},ctx);
  try{await raw(tabId,'Input.dispatchKeyEvent',{...params,type:'keyUp'},ctx);}catch(e){await detach(tabId);throw e;}
  await verify();return {};
}
async function dispatch(name,a,ctx) {
  const owner=ctx.owner;
  if(name==='browser_status')return {connected,version:VERSION,enabled:config.enabled,allowCreate:config.allowCreate,protectActive:config.protectActive,sessionId:owner,grantedTabs:(await listTabs(owner)).length,cursor:{renderer:ctx.cursor?.pack?'cursor-studio':'lucide',error:ctx.cursor?.error||null,coordinateSystem:'css_viewport_pixels',desktopProjection:false},limitations:['Main-world eval and raw CDP are exposed on granted tabs','No OS input/cookie export','Cross-origin iframe DOM and native dialogs are not supported','Page-initiated popups can still interrupt focus']};
  if(name==='browser_workspaces')return {workspaces:Object.entries(workspaces).filter(([,w])=>w.owner===owner).map(([workspaceId,w])=>({workspaceId,...w})),tabs:await listTabs(owner)};
  if(name==='browser_tabs'){if(a.workspaceId)await getWorkspace(a.workspaceId,owner);return {tabs:await listTabs(owner,a.workspaceId)};}
  if(name==='browser_workspace_release'){await getWorkspace(a.workspaceId,owner);await releaseWorkspace(a.workspaceId);return {released:true,tabsClosed:false};}
  if(name==='browser_tab_release'){if(grants[a.tabId]?.owner!==owner)throw new AppError('NOT_GRANTED','Tab not owned.');await releaseTab(a.tabId);return {released:true,tabClosed:false};}
  // Cleanup paths run without a deadline checkpoint so a timed-out command never leaves
  // an orphaned tab behind. Owner, pause and active-tab protection still apply; closing
  // a revoked tab cannot interact with page content, so the revocation check is waived.
  if(name==='browser_tab_close'){
    const g=grants[a.tabId];
    if(!g||g.owner!==owner)throw new AppError('NOT_GRANTED','This tab is not granted to this MCP session.');
    if(workspaces[g.workspaceId]?.paused)throw new AppError('WORKSPACE_PAUSED','User paused this workspace.');
    const tab=await chrome.tabs.get(a.tabId).catch(()=>{throw new AppError('TAB_GONE','Tab was already closed.');});
    if(config.protectActive&&tab.active)throw new AppError('HUMAN_ACTIVE_TAB','This tab is active. Ask the user to switch to a different tab; do not disable protection on their behalf.');
    await chrome.tabs.remove(a.tabId);await releaseTab(a.tabId);return {closed:true,wasRevoked:!!g.revoked};
  }
  checkpoint(ctx);
  if(name==='browser_tab_regrant'){
    // Restore a grant this session already held after an auto-revocation (e.g. CDP_TIMEOUT).
    // This is NOT granting an unrelated tab: owner, workspace ownership and pause are
    // re-checked, and the explicit call is the acknowledgment — not a blind retry.
    const g=grants[a.tabId];
    if(!g||g.owner!==owner||!workspaces[g.workspaceId]||workspaces[g.workspaceId].owner!==owner)throw new AppError('NOT_GRANTED','This tab is not granted to this MCP session.');
    if(workspaces[g.workspaceId].paused)throw new AppError('WORKSPACE_PAUSED','User paused this workspace.');
    const tab=await chrome.tabs.get(a.tabId).catch(()=>{throw new AppError('TAB_GONE','Tab was closed.');});
    safeUrl(tab.pendingUrl||tab.url||'about:blank');
    if(tab.incognito)throw new AppError('INCOGNITO_BLOCKED','Incognito is not supported.');
    if(g.revoked){g.revoked=false;await persist();record('tab-regrant',a.tabId,'ok');}
    return await tabInfo(a.tabId);
  }
  if(name==='browser_workspace_create') {
    if(!config.allowCreate)throw new AppError('CREATE_NOT_ALLOWED','User must enable new AI tabs.');
    const windows=await chrome.windows.getAll({windowTypes:['normal']});
    const win=windows.find(w=>w.focused&&!w.incognito)||windows.find(w=>!w.incognito);
    if(!win)throw new AppError('NO_WINDOW','Open a normal browser window first.');
    const workspaceId=crypto.randomUUID();workspaces[workspaceId]={owner,name:a.name,color:a.color||'cyan',windowId:win.id,groupId:null,paused:false};
    await persist();return {workspaceId,...await newTab(owner,workspaceId,a.url||'about:blank',ctx)};
  }
  if(name==='browser_workspace_update') {
    const w=await getWorkspace(a.workspaceId,owner);
    if(w.paused)throw new AppError('WORKSPACE_PAUSED','User paused workspace.');
    if(a.name!==undefined)w.name=a.name;if(a.color!==undefined)w.color=a.color;
    const update={title:`🔎 ${w.name}`,color:w.color};if(a.collapsed!==undefined)update.collapsed=a.collapsed;
    if(a.collapsed && config.protectActive && w.groupId!==null){for(const t of await chrome.tabs.query({groupId:w.groupId}))if(t.active)throw new AppError('HUMAN_ACTIVE_TAB','Cannot collapse a group containing the active tab.');}
    if(w.groupId!==null)await chrome.tabGroups.update(w.groupId,update);await persist();return {workspaceId:a.workspaceId,...w};
  }
  if(name==='browser_tab_open')return await newTab(owner,a.workspaceId,a.url,ctx);
  if(name==='browser_tab_navigate')return await navigate(a.tabId,a.url,ctx,a.timeoutMs);
  const readOnly=['browser_snapshot','browser_screenshot','browser_wait','browser_network_read','browser_network_body'].includes(name);
  await attach(a.tabId,ctx,!readOnly);
  if(name==='browser_network_start')return await network.start(a.tabId,owner,a);
  if(name==='browser_network_read')return network.read(a.tabId,owner,a);
  if(name==='browser_network_body')return await network.body(a.tabId,owner,a);
  if(name==='browser_network_routes')return await network.routes(a.tabId,owner,a);
  if(name==='browser_network_stop')return await network.stop(a.tabId,owner);
  if(name==='browser_snapshot')return await page(a.tabId,'snapshot',a,ctx,false);
  if(name==='browser_move'){
    const p=await point(a.tabId,a,ctx);
    const verify=await expectInput(a.tabId,ctx,['pointermove','mousemove']);
    await page(a.tabId,'cursor',{action:'move',...p},ctx);
    await raw(a.tabId,'Input.dispatchMouseEvent',{type:'mouseMoved',...p,button:'none'},ctx);
    await verify();return {moved:true,...p};
  }
  if(name==='browser_click'){const r=await click(a.tabId,await point(a.tabId,a,ctx),a,ctx);return {clicked:true,tabId:a.tabId,...r};}
  if(name==='browser_type'){
    const focused=await page(a.tabId,'focus',{...a,edit:true,replace:a.replace!==false},ctx);
    if(!a.text&&a.replace===false)return {inserted:true,characters:0};
    if(!a.text&&focused?.empty)return {inserted:true,characters:0,changed:false};
    if(a.inputRoute==='dom'){
      await domInput(a.tabId,'domType',{...a,text:a.text},ctx);
      return {inserted:true,characters:a.text.length,trusted:false,via:'dom-type'};
    }
    const verify=await expectInput(a.tabId,ctx,['beforeinput','input','textInput'],{input:1});
    if(a.text)await raw(a.tabId,'Input.insertText',{text:a.text},ctx);
    else await press(a.tabId,'Backspace',ctx);
    await verify();return {inserted:true,characters:a.text.length};
  }
  if(name==='browser_press'){if(a.ref||a.selector)await page(a.tabId,'focus',{...a,feedbackAction:'key'},ctx);const r=await press(a.tabId,a.key,ctx,a.inputRoute);return {pressed:true,...r};}
  if(name==='browser_scroll')return await page(a.tabId,'scroll',a,ctx);
  if(name==='browser_drag'){
    const v=await page(a.tabId,'viewport',{},ctx);if(a.points.some(p=>p.x>=v.width||p.y>=v.height))throw new AppError('OUTSIDE_VIEWPORT','Drag path exceeds viewport.');
    const verify=await expectInput(a.tabId,ctx,['pointerdown','mousedown','pointermove','mousemove','pointerup','mouseup'],{mousedown:1,mousemove:1,mouseup:1});
    const p=a.points[0];await page(a.tabId,'cursor',{action:'down',...p},ctx);
    await raw(a.tabId,'Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',buttons:1,clickCount:1},ctx);
    try{
      for(const p of a.points.slice(1)){await page(a.tabId,'cursor',{action:'drag',...p},ctx);await raw(a.tabId,'Input.dispatchMouseEvent',{type:'mouseMoved',...p,button:'left',buttons:1},ctx);await sleep((a.durationMs??300)/(a.points.length-1));}
      await raw(a.tabId,'Input.dispatchMouseEvent',{type:'mouseReleased',...a.points.at(-1),button:'left',buttons:0,clickCount:1},ctx);
    }catch(e){await detach(a.tabId);throw e;}
    try{await page(a.tabId,'cursor',{action:'move',...a.points.at(-1)},ctx);}catch{}
    await verify();return {dragged:true};
  }
  if(name==='browser_screenshot') {
    const format=a.format||'png';const params={format,fromSurface:true,captureBeyondViewport:!!a.fullPage};let clipped=false;
    const v=await page(a.tabId,'viewport',{},ctx,false);let width=v.width,height=v.height;
    if(a.fullPage){const m=await raw(a.tabId,'Page.getLayoutMetrics',{},ctx,false),size=m.cssContentSize||m.contentSize;width=Math.max(1,Math.min(Math.ceil(size.width),8192));height=Math.max(1,Math.min(Math.ceil(size.height),16384,Math.floor(16000000/width)));clipped=width<size.width||height<size.height;params.clip={x:0,y:0,width,height,scale:1};}
    else if(width*height>16000000)throw new AppError('IMAGE_TOO_LARGE','Viewport exceeds the screenshot size limit.');
    if(format==='jpeg')params.quality=85;
    // Hidden-tab captures are throttled on some hosts (Vivaldi): escalate to
    // captureBeyondViewport (forces off-screen compositing), then to a screencast
    // frame (the compositor must emit frames while a screencast runs).
    const screencastShot=async()=>{
      // Register the frame waiter BEFORE starting the cast so a fast first frame isn't missed;
      // the trailing catch keeps a late timeout rejection handled if we bail early.
      const frameP=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{screencastWaiters.delete(a.tabId);reject(new AppError('CDP_TIMEOUT','Screencast frame wait timed out.'));},Math.max(1,Math.min(10000,ctx.deadline-Date.now())));
        screencastWaiters.set(a.tabId,{resolve,timer});
      });
      frameP.catch(()=>{});
      try{
        await raw(a.tabId,'Page.startScreencast',{format,everyNthFrame:1,maxWidth:Math.min(width,8192),maxHeight:Math.min(height,8192)},ctx,false,{revokeOnTimeout:false});
        const f=await frameP;
        if(f.sessionId!==undefined)await chrome.debugger.sendCommand({tabId:a.tabId},'Page.screencastFrameAck',{sessionId:f.sessionId}).catch(()=>{});
        return {data:f.data};
      }finally{screencastWaiters.delete(a.tabId);await raw(a.tabId,'Page.stopScreencast',{},ctx,false,{revokeOnTimeout:false}).catch(()=>{});}
    };
    let shot;
    for(let attempt=0;attempt<3;attempt++){
      if(attempt){await sleep(800);checkpoint(ctx);await attach(a.tabId,ctx,false);}
      try {
        // Read-only capture: an unacknowledged reply leaves nothing uncertain, so keep the grant.
        if(attempt===2){
          shot=await screencastShot();
          width=v.width;height=v.height;if(a.fullPage)clipped=true;
        } else {
          const p=attempt===1?{...params,captureBeyondViewport:true,clip:a.fullPage?params.clip:{x:v.scrollX||0,y:v.scrollY||0,width,height,scale:1}}:params;
          // 4s cap per attempt: a host that answers capture does so in well under a
          // second, and the escalation chain must fit inside the command deadline.
          shot=await raw(a.tabId,'Page.captureScreenshot',p,ctx,false,{revokeOnTimeout:false,timeoutMs:4000});
        }
        break;
      } catch(e) {
        if(e.code==='CDP_TIMEOUT'&&attempt<2)continue;
        if(e.code!=='CDP_TIMEOUT')throw e;
        // Final fallback: the print pipeline rasterizes offscreen and does not need a
        // compositor surface — it works on hosts that never paint hidden tabs (Vivaldi).
        const pdf=await raw(a.tabId,'Page.printToPDF',{printBackground:true},ctx,false,{revokeOnTimeout:false,timeoutMs:15000}).catch(()=>null);
        if(pdf&&pdf.data&&pdf.data.length<30000000)return {tabId:a.tabId,via:'printToPDF',note:'Hidden-tab rasterization is unsupported on this host; captured the rendered page as PDF instead.',pdf:{data:pdf.data,mimeType:'application/pdf'},fullPage:true,clipped:false,viewport:v};
        throw new AppError('SCREENSHOT_UNAVAILABLE','This host did not acknowledge hidden-tab capture (capture, beyondViewport, screencast and printToPDF all failed); the grant is intact. Capture while the tab is foreground, or use browser_snapshot.');
      }
    }
    if(shot.data.length>22000000)throw new AppError('IMAGE_TOO_LARGE','Try JPEG or viewport-only.');
    const pixels=imageSize(shot.data,format);
    return {tabId:a.tabId,coordinateSystem:'Actions use CSS VIEWPORT pixels, not raw image pixels. For full-page images, also subtract current viewport scroll offsets.',width,height,imagePixels:pixels,viewport:v,cssPerImagePixel:{x:width/pixels.width,y:height/pixels.height},fullPage:!!a.fullPage,clipped,image:{data:shot.data,mimeType:`image/${format}`}};
  }
  if(name==='browser_wait'){const until=Date.now()+(a.timeoutMs||10000);while(Date.now()<until){const r=await page(a.tabId,'wait',a,ctx,false);if(r.matched)return {matched:true};await sleep(150);}throw new AppError('WAIT_TIMEOUT','Condition not met.');}
  if(name==='browser_select')return await page(a.tabId,'select',a,ctx);
  if(name==='browser_eval'){
    // Main-world evaluation: no contextId targets the page's default execution context.
    const result=await raw(a.tabId,'Runtime.evaluate',{expression:a.expression,returnByValue:true,awaitPromise:a.awaitPromise!==false,userGesture:true,timeout:8000},ctx);
    if(result.exceptionDetails)throw new AppError('PAGE_ERROR',result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    const r=result.result||{};return {type:r.type,subtype:r.subtype,className:r.className,value:r.value,unserializableValue:r.unserializableValue,description:r.description};
  }
  if(name==='browser_pdf'){
    await attach(a.tabId,ctx,false);
    // The print pipeline rasterizes offscreen — no compositor surface needed, so this
    // is the reliable capture path on hosts that never paint hidden tabs (Vivaldi).
    const r=await raw(a.tabId,'Page.printToPDF',{printBackground:a.printBackground!==false,landscape:!!a.landscape,scale:a.scale??1},ctx,false,{revokeOnTimeout:false,timeoutMs:20000});
    if(!r||!r.data)throw new AppError('PDF_UNAVAILABLE','Print pipeline returned no data.');
    if(r.data.length>30000000)throw new AppError('PDF_TOO_LARGE','Document exceeds the size limit (~22MB).');
    return {tabId:a.tabId,pdf:{data:r.data,mimeType:'application/pdf'}};
  }
  if(name==='browser_cdp')return await raw(a.tabId,a.method,a.params||{},ctx);
  if(name==='browser_check'){const s=await page(a.tabId,'checkState',a,ctx);if(s.type==='radio'&&!a.checked)throw new AppError('RADIO_UNCHECK','Select another radio button instead.');let r;if(s.checked!==a.checked)r=await click(a.tabId,await page(a.tabId,'point',a,ctx),{inputRoute:a.inputRoute},ctx);const after=await page(a.tabId,'checkState',a,ctx);if(after.checked!==a.checked)throw new AppError('CHECK_NOT_APPLIED','The page did not keep the requested state. Inspect the element; do not blindly repeat the click.');return {checked:after.checked,changed:s.checked!==a.checked,...r};}
  throw new AppError('UNKNOWN_TOOL','Not implemented.');
}
async function runCommand(message,cid) {
  const key=message.args?.tabId!==undefined?`tab:${message.args.tabId}`:'structure';
  const ctx={...message,epoch};
  const previous=locks.get(key)||Promise.resolve();
  const job=previous.catch(()=>{}).then(async()=>{
    try {
      validateArgs(message.name,message.args);
      if(!clients.some(c=>c.id===message.owner))throw new AppError('SESSION_EXPIRED','MCP session no longer exists.');
      const result=await dispatch(message.name,message.args,ctx);
      record(message.name,message.args.tabId,'ok');
      await http('/extension/result',{connectionId:cid,id:message.id,result});
    }catch(e){record(message.name,message.args?.tabId,e.code||'error');await http('/extension/result',{connectionId:cid,id:message.id,error:String(e.message).slice(0,1400)}).catch(()=>{});}
    finally{canceled.delete(message.id);}
  });locks.set(key,job);await job;if(locks.get(key)===job)locks.delete(key);
}
chrome.debugger.onDetach.addListener((source,reason)=>{
  network.forget(source.tabId);
  attached.delete(source.tabId);worlds.delete(source.tabId);
  if(!intentionalDetach.has(source.tabId) && grants[source.tabId] && reason==='canceled_by_user'){
    grants[source.tabId].revoked=true;record('debugger-detached',source.tabId,'revoked');void persist();
  }
});
chrome.debugger.onEvent.addListener((source,method,params)=>{
  void network.event(source,method,params).catch(e=>record('network-event',source.tabId,e.code||'error'));
  const tabId=source.tabId;
  if(method==='Page.frameNavigated' && !params.frame.parentId)worlds.delete(tabId);
  if(method==='Runtime.executionContextsCleared')worlds.delete(tabId);
  if(method==='Page.javascriptDialogOpening' && attached.has(tabId)){
    record('javascript-dialog',tabId,'dismissed');void chrome.debugger.sendCommand({tabId},'Page.handleJavaScriptDialog',{accept:false}).catch(()=>{});
  }
  if(method==='Page.fileChooserOpened')record('file-chooser',tabId,'blocked');
  if(method==='Page.screencastFrame'){
    const w=screencastWaiters.get(tabId);
    if(w){clearTimeout(w.timer);screencastWaiters.delete(tabId);w.resolve(params);}
  }
});
chrome.tabs.onActivated.addListener(({tabId})=>{
  // Detaching cancels interception before an active user tab continues to be used.
  if(config.protectActive && network.has(tabId))void detach(tabId);
});
chrome.tabGroups.onRemoved.addListener(group=>{for(const w of Object.values(workspaces))if(w.groupId===group.id)w.groupId=null;void persist();});
chrome.tabs.onRemoved.addListener(tabId=>{delete grants[tabId];attached.delete(tabId);worlds.delete(tabId);void persist();});
// Dev convenience: an unpacked extension's files can change on disk while a packed install's
// cannot, so a content-hash change means the sources were edited — reload once it stays stable
// across two alarm polls (~60s) to avoid reloading into a half-written file.
const devFiles=['manifest.json','background.mjs','network.mjs','page-ops.mjs','cursor-overlay.mjs','cursor-theme.mjs','character-runtime.mjs','shared-cursor-overlay.mjs','vendor/lucide/mouse-pointer-2.mjs','shared.mjs','popup.mjs','popup.html','popup.css'];
let devHash='',devPending='',devStable=0;
async function devHotReload() {
  try{
    const parts=[];
    for(const f of devFiles)parts.push(await (await fetch(chrome.runtime.getURL(f),{cache:'no-store'})).text());
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(parts.join('\n')));
    const h=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
    if(!devHash){devHash=h;return;}
    if(h===devHash){devPending='';devStable=0;return;}
    if(h!==devPending){devPending=h;devStable=0;return;}
    if(++devStable>=1){record('dev-reload',0,'ok');chrome.runtime.reload();}
  }catch{}
}
chrome.alarms.onAlarm.addListener(()=>{void devHotReload();void loop();});
chrome.runtime.onStartup.addListener(()=>void loop());
chrome.runtime.onInstalled.addListener(()=>void loop());
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(sender.id!==chrome.runtime.id || sender.url?.split('?')[0]!==chrome.runtime.getURL('popup.html')){respond({error:'Only the extension popup may change grants/settings.'});return false;}
  (async()=>{
    await boot;
    if(message.type==='status')return {version:VERSION,config:{enabled:config.enabled,allowCreate:config.allowCreate,protectActive:config.protectActive,paired:!!config.token},connected,lastError,clients,workspaces:Object.entries(workspaces).map(([id,w])=>({id,...w})),tabs:await Promise.all(Object.keys(grants).map(id=>tabInfo(id).catch(()=>null))).then(a=>a.filter(Boolean)),audit};
    if(message.type==='pair'){
      const m=/^tbt1\.(\d{4,5})\.([a-f0-9]{64})$/.exec(message.code?.trim()||'');
      if(!m||+m[1]<1024||+m[1]>65535)throw new Error('Invalid pairing code. Run npm run setup.');
      if(loopRunning)throw new Error('Disconnect before changing the pairing code.');
      config={...config,port:+m[1],token:m[2],enabled:true,allowCreate:!!message.allowCreate};
      await chrome.storage.local.set({config});void loop();return {ok:true};
    }
    if(message.type==='settings'){
      for(const k of ['enabled','allowCreate','protectActive'])if(typeof message[k]==='boolean')config[k]=message[k];
      epoch++;if(!config.enabled)await detachAll();await chrome.storage.local.set({config});await badge();return {ok:true};
    }
    if(message.type==='disconnect'){
      config.enabled=false;config.token='';epoch++;await detachAll();for(const id of Object.keys(workspaces))await releaseWorkspace(id);
      await chrome.storage.local.set({config});await badge();return {ok:true};
    }
    if(message.type==='workspace-pause'){
      const w=workspaces[message.workspaceId];if(!w)throw new Error('Workspace missing.');w.paused=!w.paused;epoch++;
      if(w.paused)for(const [id,g]of Object.entries(grants))if(g.workspaceId===message.workspaceId)await detach(Number(id));
      await persist();return {ok:true};
    }
    if(message.type==='workspace-release'){epoch++;await releaseWorkspace(message.workspaceId);return {ok:true};}
    if(message.type==='dev-reload'){setTimeout(()=>chrome.runtime.reload(),150);return {ok:true};}
    if(message.type==='grant-current'){
      const client=clients.find(c=>c.id===message.owner);if(!client)throw new Error('Start an MCP client first.');
      const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(!tab)throw new Error('No active tab.');safeUrl(tab.url);if(tab.incognito)throw new Error('Incognito blocked.');
      if(grants[tab.id])await releaseTab(tab.id);
      const id=crypto.randomUUID();workspaces[id]={owner:client.id,name:'Shared tab',color:'yellow',windowId:tab.windowId,groupId:null,paused:false};grants[tab.id]={owner:client.id,workspaceId:id,revoked:false};
      // Do not move/re-group a user's existing tab without a separate instruction.
      await persist();record('manual-grant',tab.id,'ok');return {ok:true};
    }
    throw new Error('Unknown popup request.');
  })().then(result=>respond({result}),e=>respond({error:e.message}));return true;
});
void devHotReload();void loop();
