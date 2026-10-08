import assert from 'node:assert/strict';

// Production MCP -> installed MV3 extension -> exact background tab. No direct
// Playwright page mutation is used to implement the behavior being tested.
export async function verifyNetwork({client,tabId,social,screenshot,pass}) {
  const args={tabId},tool=(name,a={})=>client.tool('tobkiri_tabs_'+name,{...args,...a});
  const evaluate=async expression=>(await tool('eval',{expression})).value;
  const fetchJson=path=>evaluate(`fetch(${JSON.stringify(path)}).then(r=>r.json())`);
  await evaluate(`(()=>{document.querySelector('h1').textContent='DOMを書き換えました';document.querySelector('h1').style.color='#9a4e38';document.querySelector('h1').dataset.tobkiriDemo='changed';return document.querySelector('h1').outerHTML;})()`);
  assert.equal(await evaluate(`document.querySelector('h1').dataset.tobkiriDemo`),'changed');
  await screenshot('dom-modified.png');
  pass('Main-world eval changed heading text/style/attribute in the inactive SNS tab');

  await tool('network_start',{includePostData:true});
  assert.deepEqual(await fetchJson('/api/state?captured=1'),social.getState());
  let logs,request;
  for(let i=0;i<50;i++){
    logs=await tool('network_read');
    request=logs.entries.find(e=>e.kind==='request'&&e.url.endsWith('?captured=1'));
    if(request&&logs.entries.some(e=>e.kind==='finished'&&e.requestId===request.requestId))break;
    await new Promise(r=>setTimeout(r,50));
  }
  assert.ok(request);assert.ok(logs.entries.some(e=>e.kind==='response'&&e.requestId===request.requestId&&e.status===200));
  assert.deepEqual(JSON.parse((await tool('network_body',{requestId:request.requestId})).body),social.getState());
  pass('Network events captured URL/status/headers and retrieved the real JSON response body');

  const mocked=social.getState();mocked.viewer.name='通信差し替えデモ';
  mocked.posts[0].text='この投稿は、拡張が返した模擬レスポンスです。';
  const stateBefore=social.getState(),receiptCount=social.getRequests().length;
  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/state?mock*',action:'fulfill',status:200,
    headers:[{name:'Content-Type',value:'application/json; charset=utf-8'}],body:JSON.stringify(mocked)}]});
  const got=await evaluate(`(async()=>{state=await fetch('/api/state?mock=1').then(r=>r.json());render();return state;})()`);
  assert.deepEqual(got,mocked);assert.deepEqual(social.getState(),stateBefore);
  assert.equal(social.getRequests().length,receiptCount,'Mock response never reached the server');
  await screenshot('network-mocked.png');
  pass('UTF-8 mock response changed the rendered SNS without changing server data or sending the request');

  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/state?blocked*',action:'block'}]});
  const beforeBlock=social.getRequests().length;
  assert.equal(await evaluate(`fetch('/api/state?blocked=1').then(()=>false,()=>true)`),true);
  assert.equal(social.getRequests().length,beforeBlock);
  pass('Blocked request rejected in the page and never reached the server');

  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/state?rewrite*',action:'modify',
    url:social.base+'/api/state?arrived=1',headers:[{name:'X-Tobkiri-Test',value:'modified'}]}]});
  assert.deepEqual(await fetchJson('/api/state?rewrite=1'),stateBefore);
  assert.ok(social.getRequests().some(r=>r.path==='/api/state?arrived=1'&&r.testHeader==='modified'));
  assert.ok(!social.getRequests().some(r=>r.path==='/api/state?rewrite=1'));
  pass('Request URL and headers were rewritten once, verified by the server receipt');

  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/follow/aoi?body*',method:'POST',action:'modify',requestMethod:'PUT',postData:JSON.stringify({enabled:true})}]});
  const bodyResult=await evaluate(`fetch('/api/follow/aoi?body=1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false})}).then(r=>r.json())`);
  assert.deepEqual(bodyResult,stateBefore);
  const receipt=social.getRequests().find(r=>r.path==='/api/follow/aoi?body=1');
  assert.equal(receipt.method,'PUT');assert.deepEqual(receipt.body,{enabled:true});
  assert.deepEqual(social.getState(),stateBefore,'Idempotent rewritten request did not change the saved follows');
  pass('HTTP method and UTF-8 request body rewriting verified at the fictional server');

  // Narrow matching passes other URLs; simultaneous pauses cannot wait on the
  // per-tab tool lock held by an awaitPromise Runtime.evaluate.
  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/state?concurrent=*',method:'POST',action:'block'}]});
  const concurrent=await evaluate(`Promise.all(Array.from({length:6},(_,i)=>fetch('/api/state?concurrent='+i).then(r=>r.json()))).then(rows=>rows.length)`);
  assert.equal(concurrent,6);
  assert.equal((await tool('network_read')).entries.filter(e=>e.kind==='route'&&e.url.startsWith(social.base+'/api/state?concurrent=')&&e.action==='continue').length,6);
  await tool('network_routes',{rules:[{urlPattern:social.base+'/api/state?lease*',action:'fulfill',body:JSON.stringify(mocked)}],leaseMs:1000});
  assert.equal((await fetchJson('/api/state?lease=1')).viewer.name,mocked.viewer.name);
  for(let i=0;i<50;i++){if((await tool('network_read')).rules===0)break;await new Promise(r=>setTimeout(r,50));}
  assert.equal((await tool('network_read')).rules,0);
  assert.deepEqual(await fetchJson('/api/state?lease=2'),stateBefore);
  pass('Concurrent requests complete; route lease expires and normal responses resume');

  await tool('network_routes',{rules:[]});
  await tool('network_stop');
  assert.match((await client.tool('tobkiri_tabs_network_read',args,true)).error,/NETWORK_NOT_STARTED/);
  await evaluate(`(async()=>{state=await fetch('/api/state').then(r=>r.json());render();return true;})()`);
  assert.equal(await evaluate(`state.viewer.name`),stateBefore.viewer.name);
  pass('Explicit stop removes interception/logs and restores normal SNS data');
}
