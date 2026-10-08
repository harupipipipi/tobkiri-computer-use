const $=id=>document.getElementById(id);let state=null,busy=false;
async function send(message){const r=await chrome.runtime.sendMessage(message);if(r.error)throw new Error(r.error);return r.result;}
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function notify(message){$('message').textContent=message;$('message').hidden=!message;}
async function act(fn){if(busy)return;busy=true;try{notify('');await fn();await refresh();}catch(e){notify(e.message);}finally{busy=false;}}
async function refresh(){
  const s=await send({type:'status'});state=s;
  $('ver').textContent=s.version||'';
  $('dot').className='dot '+(s.connected?(s.config.enabled?'online':'paused'):'');
  $('connection-label').textContent=s.connected?(s.config.enabled?'接続中・バックグラウンドで待機':'一時停止中'):'ブリッジ未接続';
  $('connection-detail').textContent=s.connected?`${s.clients.length} MCPクライアント · ${s.tabs.length} 許可済みタブ`:(s.lastError || 'ペアリングコードでローカル接続');
  $('toggle').disabled=!s.config.paired;$('toggle').textContent=s.config.enabled?'一時停止':'再開';$('toggle').className=s.config.enabled?'primary':'danger';
  $('protect').checked=s.config.protectActive;$('allow-create').checked=s.config.allowCreate;
  if(s.config.paired){$('pairing').open=false;$('pair-code').value='';}else $('pairing').open=true;
  const current=$('client').value;$('client').replaceChildren();
  if(!s.clients.length)$('client').append(node('option','MCPクライアント未接続'));
  for(const c of s.clients){const o=node('option',c.name);o.value=c.id;$('client').append(o);}
  if(s.clients.some(c=>c.id===current))$('client').value=current;
  $('grant').disabled=!s.clients.length||!s.connected;
  $('workspace-count').textContent=`${s.workspaces.length} WORKSPACES`;
  const list=$('workspace-list');list.replaceChildren();
  if(!s.workspaces.length){const empty=node('div',undefined,'empty');empty.append(node('strong','AIの作業場所は、まだ空です。'),node('span','MCPからワークスペースを作るか、今のタブを渡してください。'));list.append(empty);}
  for(const w of s.workspaces){
    const card=node('div',undefined,'workspace'),heading=node('div',undefined,'workspace-title'),pill=node('span',`🔎 ${w.name}`,'pill');pill.dataset.color=w.color;
    const tabs=s.tabs.filter(t=>t.workspaceId===w.id);heading.append(pill,node('small',w.paused?'PAUSED':`${tabs.length} TABS`));card.append(heading);
    const rows=node('div',undefined,'tabs');
    for(const t of tabs){const row=node('div',undefined,'tab-line');row.append(node('span','▤'),node('span',t.title||'about:blank','title'));if(t.revoked)row.append(node('span','再許可が必要','tag human'));else if(t.active)row.append(node('span','人間優先','tag human'));else row.append(node('span','BACKGROUND','tag'));rows.append(row);}
    card.append(rows);const actions=node('div',undefined,'workspace-actions');
    const pause=node('button',w.paused?'再開':'一時停止');pause.onclick=()=>act(()=>send({type:'workspace-pause',workspaceId:w.id}));
    const release=node('button','人間に返す');release.onclick=()=>act(()=>send({type:'workspace-release',workspaceId:w.id}));actions.append(pause,release);card.append(actions);list.append(card);
  }
  $('audit').replaceChildren();for(const l of s.audit.slice(0,12)){const row=node('div',undefined,'log-row');row.append(node('span',l.at.slice(11,19)),node('span',l.name.replace('browser_',''),'action'),node('span',l.status,l.status==='ok'?'ok':''));$('audit').append(row);}
}
$('pair').onclick=()=>act(async()=>{await send({type:'pair',code:$('pair-code').value,allowCreate:$('pair-create').checked});await new Promise(r=>setTimeout(r,350));});
$('toggle').onclick=()=>act(()=>send({type:'settings',enabled:!state.config.enabled}));
$('protect').onchange=()=>act(()=>send({type:'settings',protectActive:$('protect').checked}));
$('allow-create').onchange=()=>act(()=>send({type:'settings',allowCreate:$('allow-create').checked}));
$('grant').onclick=()=>act(()=>send({type:'grant-current',owner:$('client').value}));
$('reload').onclick=()=>act(async()=>{await send({type:'dev-reload'});notify('再読み込みしました');});
$('disconnect').onclick=()=>act(()=>send({type:'disconnect'}));
void refresh().catch(e=>notify(e.message));setInterval(()=>{if(!busy)void refresh().catch(()=>{});},1500);
