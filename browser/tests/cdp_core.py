"""Real headed Chromium, direct CDP, production isolated-world DOM code.
No Playwright focus emulation and no browser-policy changes. In-memory fixtures only.
This is NOT the installed-extension E2E test; use browser_e2e.py for that.
Test dependency: pip install websockets
"""
from __future__ import annotations
import argparse, asyncio, base64, json, os, pathlib, shutil, tempfile
import websockets
ROOT=pathlib.Path(__file__).resolve().parents[1]
class CDP:
 def __init__(self,ws):self.ws=ws;self.n=0;self.pending={};self.reader=asyncio.create_task(self.read())
 async def read(self):
  async for data in self.ws:
   m=json.loads(data);f=self.pending.pop(m.get('id'),None)
   if f and not f.done():f.set_result(m)
 async def send(self,method,params=None,session=None):
  self.n+=1;future=asyncio.get_running_loop().create_future();self.pending[self.n]=future
  m={'id':self.n,'method':method,'params':params or {}}
  if session:m['sessionId']=session
  await self.ws.send(json.dumps(m));r=await asyncio.wait_for(future,15)
  if 'error'in r:raise RuntimeError(str(r['error']))
  return r.get('result',{})
async def main(binary,output):
 output.mkdir(parents=True,exist_ok=True);checks=[]
 def passed(name):checks.append({'name':name,'passed':True});print('PASS',name,flush=True)
 source=(ROOT/'extension/page-ops.mjs').read_text().replace('export function pageOp','function pageOp')
 fixture=(ROOT/'tests/fixture.html').read_text()
 with tempfile.TemporaryDirectory(prefix='tobkiri-direct-cdp-',ignore_cleanup_errors=True)as tmp:
  proc=await asyncio.create_subprocess_exec(binary,'--no-sandbox','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',f'--user-data-dir={tmp}','about:blank',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
  try:
   active=pathlib.Path(tmp)/'DevToolsActivePort'
   for _ in range(100):
    if active.exists():break
    await asyncio.sleep(.1)
   port,endpoint=active.read_text().splitlines()[:2]
   async with websockets.connect(f'ws://127.0.0.1:{port}{endpoint}',max_size=32*1024*1024)as ws:
    cdp=CDP(ws);version=await cdp.send('Browser.getVersion')
    async def create(html,background):
     target=(await cdp.send('Target.createTarget',{'url':'about:blank','background':background}))['targetId']
     session=(await cdp.send('Target.attachToTarget',{'targetId':target,'flatten':True}))['sessionId']
     await cdp.send('Page.enable',session=session);await cdp.send('Runtime.enable',session=session)
     frame=(await cdp.send('Page.getFrameTree',session=session))['frameTree']['frame']['id']
     await cdp.send('Page.setDocumentContent',{'frameId':frame,'html':html},session)
     return target,session,frame
    human,h,frame_h=await create('<title>Human foreground</title><h1>Human foreground</h1><textarea id="human" style="width:500px;height:150px"></textarea>',False)
    agent,a,frame_a=await create(fixture,True)
    await cdp.send('Page.bringToFront',session=h)
    async def evaluate(expression,session=a,context_id=None):
     p={'expression':expression,'returnByValue':True,'awaitPromise':True,'timeout':4000}
     if context_id:p['contextId']=context_id
     r=await cdp.send('Runtime.evaluate',p,session)
     if 'exceptionDetails'in r:raise RuntimeError(r['exceptionDetails'].get('exception',{}).get('description',str(r['exceptionDetails'])))
     return r.get('result',{}).get('value')
    await evaluate('document.querySelector("#human").focus()',h)
    world=(await cdp.send('Page.createIsolatedWorld',{'frameId':frame_a,'worldName':'tobkiri-tabs-isolated'},a))['executionContextId']
    async def op(name,args=None):return await evaluate(f'(()=>{{{source};return pageOp({json.dumps(name)},{json.dumps(args or {})});}})()',a,world)
    async def click(point):
     await cdp.send('Input.dispatchMouseEvent',{'type':'mouseMoved',**point,'button':'none'},a)
     await cdp.send('Input.dispatchMouseEvent',{'type':'mousePressed',**point,'button':'left','buttons':1,'clickCount':1},a)
     await cdp.send('Input.dispatchMouseEvent',{'type':'mouseReleased',**point,'button':'left','buttons':0,'clickCount':1},a)
    async def front_unchanged():
     hv=await evaluate('document.visibilityState',h);av=await evaluate('document.visibilityState',a)
     assert hv=='visible'and av=='hidden',{'human':hv,'agent':av}
     assert await evaluate('document.activeElement.id',h)=='human'
    await front_unchanged();passed('Real foreground/hidden tabs: no focus emulation or background-throttling overrides')
    snap=await op('snapshot');assert 'AI works here' in snap['text'];assert 'NOT-FOR-SNAPSHOT' not in json.dumps(snap);passed('Production isolated-world snapshot and sensitive-input redaction')
    button_ref=next(e['ref']for e in snap['elements']if e.get('name')=='Background click')
    human_text='Human foreground typing stays here.'
    async def foreground_input():
     for char in human_text:
      await cdp.send('Input.insertText',{'text':char},h);await asyncio.sleep(.025)
    async def background_input():
     await op('focus',{'selector':'#entry','edit':True,'replace':True});await cdp.send('Input.insertText',{'text':'Built by Tobkiri Tabs'},a)
     await click(await op('point',{'ref':button_ref}))
    await asyncio.gather(foreground_input(),background_input())
    assert await evaluate('document.querySelector("#human").value',h)==human_text
    assert await evaluate('entry.value')=='Built by Tobkiri Tabs';assert await evaluate('count.textContent')=='1'
    await front_unchanged();passed('Concurrent foreground text input and hidden-tab typing/clicking; foreground focus retained')
    assert all(e['trusted']for e in await evaluate('eventLog'));passed('Input/click events are trusted browser events')
    shot=await cdp.send('Page.captureScreenshot',{'format':'png','fromSurface':True,'captureBeyondViewport':False},a);(output/'background-tab.png').write_bytes(base64.b64decode(shot['data']))
    await front_unchanged();passed('Hidden-tab screenshot without foreground activation')
    newer=await op('snapshot')
    try:await op('point',{'ref':button_ref});raise AssertionError('Stale ref accepted')
    except RuntimeError as e:assert 'STALE_REF'in str(e)
    shadow=next(e['ref']for e in newer['elements']if e.get('name')=='Shadow click');await click(await op('point',{'ref':shadow}));assert await evaluate('echo.textContent')=='Shadow clicked'
    passed('Stale-ref rejection and open-shadow-root interaction')
    check=await op('checkState',{'selector':'#check'});assert not check['checked'];await click(await op('point',{'selector':'#check'}));assert await evaluate('check.checked')
    await op('select',{'selector':'#mode','value':'background'});assert await evaluate('mode.value')=='background';passed('Checkbox state and native select operation')
    await op('focus',{'selector':'#entry','edit':True,'replace':True});await cdp.send('Input.insertText',{'text':''},a);assert await evaluate('entry.value')=='';passed('Empty text replacement clears input')
    await op('focus',{'selector':'#submit-entry','edit':True,'replace':True});await cdp.send('Input.insertText',{'text':'Local form only'},a)
    await cdp.send('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r','unmodifiedText':'\r'},a)
    await cdp.send('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13},a)
    assert (await op('wait',{'text':'Submitted locally'}))['matched'];passed('Page Enter key and production wait predicate')
    await click(await op('point',{'selector':'#bottom'}));assert await evaluate('document.querySelector("#bottom-status").textContent')=='Clicked at bottom'
    before=await evaluate('scrollY');scroll=await op('scroll',{'x':500,'y':300,'deltaY':-350});assert await evaluate('scrollY')<before;assert scroll['method']=='dom-scroll'
    await front_unchanged();passed('Offscreen element targeting and deterministic hidden-tab DOM scrolling')
    center=await op('point',{'selector':'#canvas'});path=[{'x':center['x']-100+i*25,'y':center['y']}for i in range(8)]
    await cdp.send('Input.dispatchMouseEvent',{'type':'mousePressed',**path[0],'button':'left','buttons':1,'clickCount':1},a)
    for point in path[1:]:await cdp.send('Input.dispatchMouseEvent',{'type':'mouseMoved',**point,'button':'left','buttons':1},a)
    await cdp.send('Input.dispatchMouseEvent',{'type':'mouseReleased',**path[-1],'button':'left','buttons':0,'clickCount':1},a)
    assert int(await evaluate('document.querySelector("#drag-count").textContent'))>0;await front_unchanged();passed('Coordinate dragging on a hidden tab without changing human focus')
    size=(await cdp.send('Page.getLayoutMetrics',session=a))['cssContentSize']
    shot=await cdp.send('Page.captureScreenshot',{'format':'jpeg','quality':85,'fromSurface':True,'captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}},a)
    (output/'full-page.jpg').write_bytes(base64.b64decode(shot['data']));await front_unchanged();passed('Full-page screenshot of background document')
    report={'version':'0.1.0','browser':version['product'],'platform':os.uname().sysname if hasattr(os,'uname')else os.name,'headed':True,'mode':'Direct CDP + production page-ops.mjs; NOT installed-extension E2E','policyModified':False,'focusEmulation':False,'navigation':'Allowed in-memory about:blank documents only','checks':checks,'passed':len(checks),'failed':0,'unverified':['Actual chrome.debugger extension transport','Extension installation and popup runtime under MV3','Navigation to real websites','macOS / Windows','Production MCP clients']}
    (output/'cdp-core-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    try:await cdp.send('Browser.close')
    except Exception:pass
  finally:
   if proc.returncode is None:proc.terminate()
   try:await asyncio.wait_for(proc.wait(),5)
   except asyncio.TimeoutError:proc.kill();await proc.wait()
   await asyncio.sleep(.5)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--chromium',default=shutil.which('chromium')or'chromium');p.add_argument('--output',type=pathlib.Path,default=ROOT/'test-results');a=p.parse_args();asyncio.run(main(a.chromium,a.output))
