import test from 'node:test';
import assert from 'node:assert/strict';
import {createNetworkController,matchesUrl} from '../extension/network.mjs';
import {validateArgs} from '../extension/shared.mjs';

function fixture() {
  const calls=[],aborts=[],timers=new Set();let now=1000,allowed=true,fail=null;
  const n=createNetworkController({
    send:async(tabId,method,params)=>{calls.push({tabId,method,params});if(fail===method)throw Error('lost ACK');return method==='Network.getResponseBody'?{body:'{"ok":true}',base64Encoded:false}:{};},
    authorize:async()=>{if(!allowed)throw Error('permission lost');},
    abort:async(tabId,e)=>{aborts.push({tabId,error:e.message});n.forget(tabId);},
    clock:()=>now,schedule:fn=>{timers.add(fn);return fn;},unschedule:fn=>timers.delete(fn)
  });
  const event=(method,p,tabId=1)=>n.event({tabId},method,p);
  const request=(id,url='https://fixture.test/api')=>event('Network.requestWillBeSent',{requestId:id,type:'Fetch',request:{url,method:'GET',headers:{Authorization:'secret',Cookie:'session',Accept:'application/json'},postData:'private body'}});
  const pause=(id,url='https://fixture.test/api')=>event('Fetch.requestPaused',{requestId:id,networkId:'n-'+id,request:{url,method:'GET'}});
  return {n,calls,aborts,timers,event,request,pause,deny:()=>{allowed=false;},fail:m=>{fail=m;},advance:ms=>{now+=ms;}};
}
test('network schemas validate bounds and per-action fields before any command',()=>{
  for(const args of [
    {rules:[{urlPattern:'*',action:'block',body:'x'}]},
    {rules:[{urlPattern:'*',action:'modify'}]},
    {rules:[{urlPattern:'*',action:'modify',url:'file:///tmp/a'}]},
    {rules:[{urlPattern:'*',action:'fulfill',headers:[{name:'X',value:'a\r\nb'}]}]},
    {rules:[{urlPattern:'*',action:'modify',requestMethod:'GET\n'}]},
    {rules:[],leaseMs:300001}
  ])assert.throws(()=>validateArgs('browser_network_routes',{tabId:1,...args}));
  assert.throws(()=>validateArgs('browser_network_start',{tabId:1,maxEntries:2}));
  validateArgs('browser_network_routes',{tabId:1,rules:[{urlPattern:'https://fixture.test/*',action:'fulfill',status:200,body:'緑'}]});
});
test('URL patterns are glob matches with literal regex punctuation',()=>{
  assert.ok(matchesUrl('https://fixture.test/api?x=*','https://fixture.test/api?x=1'));
  assert.ok(!matchesUrl('https://fixture.test/api','https://fixtureXtest/api'));
});
test('capture isolates owner/tab, bounds logs and redacts headers',async()=>{
  const f=fixture();await f.n.start(1,'owner',{maxEntries:10});
  await assert.rejects(f.n.start(1,'owner'),/ALREADY_STARTED/);
  for(let i=0;i<12;i++)await f.request('r'+i);
  await f.request('private','https://private.test/'); // the fixture sends it to tab 1
  await f.event('Network.responseReceived',{requestId:'r11',response:{url:'https://fixture.test/api',status:200,headers:{'Set-Cookie':'secret'}}});
  const r=f.n.read(1,'owner',{limit:2});assert.equal(r.entries.length,2);assert.equal(r.dropped,4);
  assert.equal(r.entries[0].headers.Authorization,'[redacted]');assert.equal(r.entries[0].postData,undefined);
  const all=f.n.read(1,'owner',{limit:100});assert.equal(all.entries.at(-1).headers['Set-Cookie'],'[redacted]');
  assert.throws(()=>f.n.read(1,'other'),/NOT_STARTED/);assert.throws(()=>f.n.read(2,'owner'),/NOT_STARTED/);
  assert.equal(f.n.read(1,'owner',{afterSeq:r.nextSeq}).entries[0].seq,r.nextSeq+1);
});
test('body only reads retained, successfully finished IDs and enforces byte limits',async()=>{
  const f=fixture();await f.n.start(1,'owner');await f.request('r');
  await assert.rejects(f.n.body(1,'owner',{requestId:'other'}),/UNKNOWN/);
  await assert.rejects(f.n.body(1,'owner',{requestId:'r'}),/NOT_READY/);
  await f.event('Network.loadingFinished',{requestId:'r',encodedDataLength:5});
  assert.equal((await f.n.body(1,'owner',{requestId:'r'})).body,'{"ok":true}');
  await assert.rejects(f.n.body(1,'owner',{requestId:'r',maxBytes:2}),/TOO_LARGE/);
  await assert.rejects(f.n.body(1,'owner',{requestId:'r',maxBytes:6}),/TOO_LARGE/,'decoded body also checked');
});
test('automatic rules block, UTF-8 fulfill, modify and pass unmatched requests once',async()=>{
  const f=fixture();await f.n.start(1,'owner');
  await f.n.routes(1,'owner',{rules:[{urlPattern:'*/blocked',action:'block'},
    {urlPattern:'*/mock',action:'fulfill',status:201,headers:[{name:'Content-Type',value:'text/plain'}],body:'緑'},
    {urlPattern:'*/modified',action:'modify',url:'https://fixture.test/else',requestMethod:'POST',postData:'葵'}]});
  for(const tail of ['blocked','mock','modified','other'])await f.pause(tail,'https://fixture.test/'+tail);
  const c=f.calls.filter(c=>['Fetch.failRequest','Fetch.fulfillRequest','Fetch.continueRequest'].includes(c.method));
  assert.equal(c.length,4);assert.equal(c[0].params.errorReason,'BlockedByClient');
  assert.equal(Buffer.from(c[1].params.body,'base64').toString(),'緑');
  assert.equal(Buffer.from(c[2].params.postData,'base64').toString(),'葵');
  assert.equal(c[2].params.method,'POST');assert.deepEqual(c[3].params,{requestId:'other'});
});
test('first rule/method matching, leases, empty clear and explicit stop release interception',async()=>{
  const f=fixture();await f.n.start(1,'owner');
  await f.n.routes(1,'owner',{rules:[{urlPattern:'*',method:'POST',action:'block'},{urlPattern:'*',action:'fulfill',body:'first'},{urlPattern:'*',action:'block'}],leaseMs:1000});
  await f.pause('a');assert.equal(f.calls.at(-1).method,'Fetch.fulfillRequest');
  f.advance(1001);await f.pause('expired');assert.equal(f.calls.at(-1).method,'Fetch.continueRequest');
  await [...f.timers][0]();await new Promise(r=>setTimeout(r,0));assert.equal(f.n.read(1,'owner').rules,0);
  await f.n.routes(1,'owner',{rules:[]});await f.n.stop(1,'owner');
  assert.equal(f.calls.at(-1).method,'Network.disable');assert.equal(f.timers.size,0);assert.equal(f.n.has(1),false);
});
test('permission loss settles with continue then disables; orphan pauses never hang',async()=>{
  const f=fixture();await f.n.start(1,'owner');await f.n.routes(1,'owner',{rules:[{urlPattern:'*',action:'block'}]});
  f.deny();await f.pause('lost');
  assert.equal(f.calls.at(-2).method,'Fetch.continueRequest');assert.equal(f.calls.at(-1).method,'Fetch.disable');
  f.n.forget(1);await f.pause('orphan');assert.equal(f.calls.at(-1).method,'Fetch.continueRequest');
});
test('failed/uncertain interception detaches without a second settlement',async()=>{
  const f=fixture();await f.n.start(1,'owner');await f.n.routes(1,'owner',{rules:[{urlPattern:'*',action:'fulfill',body:'mock'}]});
  f.fail('Fetch.fulfillRequest');await f.pause('unknown');assert.equal(f.aborts.length,1);
  assert.equal(f.calls.filter(c=>c.params.requestId==='unknown').length,1);assert.equal(f.n.has(1),false);
});
test('capture permission loss and child sessions do not leak data',async()=>{
  const f=fixture();await f.n.start(1,'owner');
  await f.n.event({tabId:1,sessionId:'child'},'Network.requestWillBeSent',{requestId:'private'});
  assert.equal(f.n.read(1,'owner').entries.length,0);f.deny();await f.request('r');
  assert.equal(f.n.has(1),false);assert.equal(f.aborts.length,1);
});
test('release/clear racing an event guard cannot send a second settlement or revoke the grant',async()=>{
  for(const mode of ['release','clear']){
    let resolveGuard;const calls=[],aborts=[];
    const n=createNetworkController({send:async(t,m,p)=>{calls.push({m,p});},authorize:()=>new Promise(r=>{resolveGuard=r;}),abort:async()=>{aborts.push(true);}});
    await n.start(1,'owner');await n.routes(1,'owner',{rules:[{urlPattern:'*',action:'block'}]});
    const event=n.event({tabId:1},'Fetch.requestPaused',{requestId:'paused',request:{url:'https://fixture.test/',method:'GET'}});
    if(mode==='release')n.forget(1);else await n.routes(1,'owner',{rules:[]});
    resolveGuard();await event;
    assert.equal(calls.filter(c=>c.p.requestId==='paused').length,0);assert.equal(aborts.length,0);
    n.forget(1);
  }
});
test('metadata guard latency preserves request/finish ordering and leaves Fetch settlement independent',async()=>{
  let firstGuard;let checks=0;const calls=[];
  const n=createNetworkController({send:async(t,m,p)=>{calls.push({m,p});return {body:'ok',base64Encoded:false};},
    authorize:async()=>{if(++checks===1)await new Promise(r=>{firstGuard=r;});},abort:async()=>{}});
  await n.start(1,'owner');
  const request=n.event({tabId:1},'Network.requestWillBeSent',{requestId:'r',request:{url:'https://fixture.test/',method:'GET'}});
  const finish=n.event({tabId:1},'Network.loadingFinished',{requestId:'r',encodedDataLength:2});
  await new Promise(r=>setTimeout(r,0));
  await n.event({tabId:1},'Fetch.requestPaused',{requestId:'paused',request:{url:'https://fixture.test/',method:'GET'}});
  assert.equal(calls.at(-1).m,'Fetch.continueRequest');
  firstGuard();await Promise.all([request,finish]);
  assert.deepEqual(n.read(1,'owner').entries.filter(e=>e.kind!=='route').map(e=>e.kind),['request','finished']);
  assert.equal((await n.body(1,'owner',{requestId:'r'})).body,'ok');n.forget(1);
});
test('an old permission rejection cannot revoke a newly started capture owner',async()=>{
  let rejectGuard;const aborts=[];
  const n=createNetworkController({send:async()=>({}),authorize:()=>new Promise((r,j)=>{rejectGuard=j;}),abort:async()=>{aborts.push(true);}});
  await n.start(1,'old');
  const event=n.event({tabId:1},'Network.loadingFinished',{requestId:'r',encodedDataLength:1});
  await new Promise(r=>setTimeout(r,0));n.forget(1);await n.start(1,'new');
  rejectGuard(Error('old owner released'));await event;
  assert.deepEqual(aborts,[]);assert.equal(n.read(1,'new').entries.length,0);n.forget(1);
});
