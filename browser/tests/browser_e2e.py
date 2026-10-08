"""Real, headed Chromium + unpacked MV3 extension + stdio MCP integration.
Test-only dependency: Python 3.11+, playwright and a Chromium executable.
Example: DISPLAY=:99 python tests/browser_e2e.py --chromium /usr/bin/chromium
All browser/config data lives in a temporary directory; no real user profile.
"""
from __future__ import annotations
import argparse, asyncio, base64, contextlib, functools, http.server, json, os, pathlib, secrets, shutil, socket, tempfile, threading, time
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]

class MCP:
    def __init__(self,proc): self.proc=proc;self.counter=0;self.pending={};self.reader=asyncio.create_task(self.read())
    async def read(self):
        while line:=await self.proc.stdout.readline():
            data=json.loads(line)
            future=self.pending.pop(data.get('id'),None)
            if future and not future.done(): future.set_result(data)
    async def rpc(self,method,params=None):
        self.counter+=1;i=self.counter;future=asyncio.get_running_loop().create_future();self.pending[i]=future
        self.proc.stdin.write((json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params or {}})+'\n').encode());await self.proc.stdin.drain()
        result=await asyncio.wait_for(future,45)
        if 'error'in result: raise AssertionError(result['error'])
        return result['result']
    async def initialize(self):
        r=await self.rpc('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'browser-e2e','version':'1'}})
        assert r['protocolVersion']=='2025-11-25'
        self.proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');await self.proc.stdin.drain()
    async def tool(self,name,allow_error=False,**args):
        r=await self.rpc('tools/call',{'name':name,'arguments':args})
        if r.get('isError'):
            if allow_error:return r
            raise AssertionError(f'{name}: {r["content"][0]["text"]}')
        if any(c['type']=='image' for c in r['content']):return r
        return json.loads(r['content'][0]['text'])
    async def close(self):
        self.proc.stdin.close()
        try:await asyncio.wait_for(self.proc.wait(),4)
        except asyncio.TimeoutError:self.proc.kill();await self.proc.wait()
        self.reader.cancel()

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path.startswith('/human'):
            html='''<!doctype html><meta charset="utf-8"><title>Human foreground — untouched</title><style>body{background:#182439;color:#e5f0fd;font:22px sans-serif;padding:50px}textarea{display:block;width:600px;height:180px;font:20px sans-serif;padding:20px}h1{font-size:48px}</style><h1>The front tab is mine.</h1><p>The AI is working in other tabs. This text area must keep focus.</p><textarea id="human" placeholder="Human typing here"></textarea>'''
            b=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        else:super().do_GET()

async def main(chromium: str, output: pathlib.Path):
    output.mkdir(parents=True,exist_ok=True);checks=[]
    # Do not disable/bypass enterprise policy to run this test.
    for policy in pathlib.Path('/etc/chromium/policies/managed').glob('*.json'):
        with contextlib.suppress(ValueError, OSError):
            rules=json.loads(policy.read_text())
            if '*' in rules.get('ExtensionInstallBlocklist',[]) and not rules.get('ExtensionInstallAllowlist'):
                report={'version':'0.1.0','status':'environment-blocked','passed':0,'failed':0,'skipped':1,'reason':'Managed Chromium policy blocks all extension installations. The policy was not modified. Run this test in an extension-enabled local browser.'}
                (output/'browser-e2e-report.json').write_text(json.dumps(report,indent=2)+'\n')
                print('BLOCKED: Chromium enterprise policy prohibits extension installation.',flush=True)
                return 77
    def passed(name,details=None):checks.append({'name':name,'passed':True,**({'details':details}if details is not None else {})});print('PASS',name,flush=True)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'tests')));threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
    with tempfile.TemporaryDirectory(prefix='tobkiri-tabs-test-') as tmp:
        tmp=pathlib.Path(tmp)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        token=secrets.token_hex(32);config=tmp/'config.json';config.write_text(json.dumps({'version':1,'port':port,'token':token}));os.chmod(config,0o600)
        bridge=await asyncio.create_subprocess_exec('node',str(ROOT/'src/cli.mjs'),'bridge','--config',str(config),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
        await asyncio.sleep(.4)
        p1=await asyncio.create_subprocess_exec('node',str(ROOT/'src/cli.mjs'),'mcp','--config',str(config),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        m=MCP(p1);await m.initialize();other=None
        try:
          async with async_playwright() as pw:
            ctx=await pw.chromium.launch_persistent_context(str(tmp/'profile'),executable_path=chromium,headless=False,timeout=15000,ignore_default_args=['--disable-extensions'],viewport={'width':1200,'height':800},args=['--no-sandbox','--disable-dev-shm-usage',f'--disable-extensions-except={ROOT/"extension"}',f'--load-extension={ROOT/"extension"}'])
            try:
              worker=ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker',timeout=15000)
              extension_id=worker.url.split('/')[2]
              popup=await ctx.new_page();await popup.goto(f'chrome-extension://{extension_id}/popup.html')
              await popup.locator('#pair-code').fill(f'tbt1.{port}.{token}');await popup.locator('#pair-create').check();await popup.locator('#pair').click()
              for _ in range(100):
                status=await m.tool('browser_status')
                if status.get('connected'):break
                await asyncio.sleep(.1)
              assert status['connected'] and status['enabled'] and status['allowCreate'],status
              passed('Pairing via actual extension UI and MCP stdio connection')
              human=await ctx.new_page();await human.goto(base+'/human');await human.bring_to_front();await human.locator('#human').click()
              human_id=await worker.evaluate('async()=>{const [t]=await chrome.tabs.query({active:true,lastFocusedWindow:true});return t.id}')
              await worker.evaluate('()=>{globalThis.__testActivations=[];chrome.tabs.onActivated.addListener(e=>__testActivations.push(e.tabId));}')
              w=await m.tool('browser_workspace_create',name='PR1322 · Background',color='cyan',url=base+'/fixture.html');tid=w['tabId'];wid=w['workspaceId']
              assert not w['active'];assert w['groupId']>=0
              agent=next(p for p in ctx.pages if p.url.startswith(base+'/fixture.html'))
              passed('Background tab creation, navigation and colored native tab group')
              snap=await m.tool('browser_snapshot',tabId=tid)
              assert 'AI works here' in snap['text'];assert 'NOT-FOR-SNAPSHOT' not in json.dumps(snap)
              passed('Background DOM snapshot with refs and password redaction')
              ref=next(x['ref']for x in snap['elements']if x.get('name')=='Background click')
              # The foreground user types while the MCP makes independent background mutations.
              human_text='Human stays focused while AI types.'
              await asyncio.gather(human.keyboard.type(human_text,delay=25),m.tool('browser_type',tabId=tid,selector='#entry',text='Built by Tobkiri Tabs'))
              await m.tool('browser_click',tabId=tid,ref=ref)
              assert await agent.locator('#entry').input_value()=='Built by Tobkiri Tabs'
              assert await agent.locator('#count').inner_text()=='1'
              assert await human.locator('#human').input_value()==human_text
              assert await human.evaluate('document.activeElement.id')=='human'
              assert await worker.evaluate('()=>__testActivations')==[]
              passed('Simultaneous human foreground typing and AI background click/type; ZERO activation events')
              logs=await agent.evaluate('eventLog');assert all(x['trusted']for x in logs if x['kind']in ['input','click'])
              passed('CDP input and click events have isTrusted=true')
              shot=await m.tool('browser_screenshot',tabId=tid)
              img=next(c for c in shot['content'] if c['type']=='image');(output/'background-tab.png').write_bytes(base64.b64decode(img['data']))
              assert await worker.evaluate('()=>__testActivations')==[]
              passed('Screenshot returned as MCP image without activating target tab')
              snap=await m.tool('browser_snapshot',tabId=tid)
              stale=await m.tool('browser_click',tabId=tid,ref=ref,allow_error=True);assert stale.get('isError') and 'STALE_REF'in stale['content'][0]['text']
              shadowref=next(x['ref']for x in snap['elements']if x.get('name')=='Shadow click');await m.tool('browser_click',tabId=tid,ref=shadowref)
              assert await agent.locator('#echo').inner_text()=='Shadow clicked'
              passed('Stale ref rejection and open Shadow DOM interaction')
              await m.tool('browser_check',tabId=tid,selector='#check',checked=True);assert await agent.locator('#check').is_checked()
              c=await m.tool('browser_check',tabId=tid,selector='#check',checked=True);assert c['changed'] is False
              await m.tool('browser_select',tabId=tid,selector='#mode',value='background');assert await agent.locator('#mode').input_value()=='background'
              passed('Idempotent checkbox and native select actions')
              await m.tool('browser_type',tabId=tid,selector='#submit-entry',text='local form')
              await m.tool('browser_press',tabId=tid,selector='#submit-entry',key='Enter')
              await m.tool('browser_wait',tabId=tid,text='Submitted locally',timeoutMs=3000)
              passed('Page-level Enter key and bounded text wait')
              # offscreen element is scrolled into view without bringing its browser tab forward
              await m.tool('browser_click',tabId=tid,selector='#bottom');assert await agent.locator('#bottom-status').inner_text()=='Clicked at bottom'
              before=await agent.evaluate('scrollY');await m.tool('browser_scroll',tabId=tid,deltaY=-350,x=800,y=350);await asyncio.sleep(.25);assert await agent.evaluate('scrollY')<before
              assert await worker.evaluate('()=>__testActivations')==[]
              passed('Offscreen element click and background DOM scrolling')
              full=await m.tool('browser_screenshot',tabId=tid,fullPage=True,format='jpeg');meta=json.loads(full['content'][0]['text']);assert meta['height']>800
              (output/'full-page.jpg').write_bytes(base64.b64decode(next(c for c in full['content']if c['type']=='image')['data']))
              passed('Full-page screenshot without changing front tab')
              # A second MCP process must have a separate ownership ledger.
              p2=await asyncio.create_subprocess_exec('node',str(ROOT/'src/cli.mjs'),'mcp','--name','Second agent','--config',str(config),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
              other=MCP(p2);await other.initialize()
              assert (await other.tool('browser_tabs'))['tabs']==[]
              denied=await other.tool('browser_click',tabId=tid,selector='#increment',allow_error=True);assert 'NOT_GRANTED'in denied['content'][0]['text']
              w2=await other.tool('browser_workspace_create',name='Arena · Research',color='yellow',url=base+'/fixture.html?second=1')
              assert {t['tabId']for t in (await m.tool('browser_tabs'))['tabs']}=={tid}
              passed('Two MCP sessions: separate groups and cross-session access denied')
              unowned=await m.tool('browser_snapshot',tabId=human_id,allow_error=True);assert 'NOT_GRANTED'in unowned['content'][0]['text']
              badurl=await m.tool('browser_tab_navigate',tabId=tid,url='chrome://settings',allow_error=True);assert badurl.get('isError')
              passed('Unshared human tab and restricted navigation rejected')
              # Human takes over the AI tab. Mutations must stop, not switch it away.
              await agent.bring_to_front();active_err=await m.tool('browser_click',tabId=tid,selector='#increment',allow_error=True)
              assert 'HUMAN_ACTIVE_TAB'in active_err['content'][0]['text'];assert await agent.locator('#count').inner_text()=='1'
              await human.bring_to_front();await human.locator('#human').click()
              passed('Human takeover blocks mutations of the active tab')
              await m.tool('browser_workspace_update',workspaceId=wid,name='PR1322 · Done',color='green',collapsed=True)
              group=await worker.evaluate('(id)=>chrome.tabGroups.get(id)',w['groupId']);assert group['collapsed'] and group['title']=='🔎 PR1322 · Done'
              passed('Workspace rename, recolor and collapse')
              # Pause is a real user popup action; it must not be remotely bypassable.
              await popup.locator('#toggle').click();paused=await m.tool('browser_click',tabId=tid,selector='#increment',allow_error=True);assert 'PAUSED'in paused['content'][0]['text']
              await popup.locator('#toggle').click();await human.bring_to_front()
              passed('Global pause from popup prevents further actions')
              await m.tool('browser_workspace_update',workspaceId=wid,color='cyan',collapsed=False)
              await popup.set_viewport_size({'width':430,'height':1000});await popup.screenshot(path=str(output/'extension-popup.png'),full_page=True)
              # Cancellation from Chrome's own debugger banner must not be automatically overridden.
              await m.tool('browser_snapshot',tabId=tid)
              await worker.evaluate('(tabId)=>chrome.debugger.detach({tabId})',tid)
              await asyncio.sleep(.1)
              revoked=await m.tool('browser_snapshot',tabId=tid,allow_error=True);assert 'NOT_GRANTED'in revoked['content'][0]['text']
              passed('Debugger cancellation revokes grant instead of silently reattaching')
              await other.tool('browser_tab_close',tabId=w2['tabId']);assert (await other.tool('browser_tabs'))['tabs']==[]
              await m.tool('browser_workspace_release',workspaceId=wid);assert (await m.tool('browser_tabs'))['tabs']==[]
              assert not agent.is_closed()
              passed('Owned-tab close and workspace release leave unrelated/human tabs intact')
              report={'version':'0.1.0','browser':ctx.browser.version if ctx.browser else 'Chromium','platform':os.uname().sysname if hasattr(os,'uname')else os.name,'headed':True,'transport':'stdio MCP -> loopback HTTP -> MV3 chrome.debugger','checks':checks,'passed':len(checks),'failed':0,'note':'Fresh isolated test profile and local test fixture only. Not tested against a real user profile, macOS/Windows UI, arbitrary external sites or a production MCP host.'}
              (output/'browser-e2e-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            finally:await ctx.close()
        finally:
          if other:await other.close()
          await m.close();bridge.terminate()
          try:await asyncio.wait_for(bridge.wait(),4)
          except asyncio.TimeoutError:bridge.kill();await bridge.wait()
          server.shutdown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--chromium',default=shutil.which('chromium') or 'chromium');p.add_argument('--output',type=pathlib.Path,default=ROOT/'test-results');a=p.parse_args()
    raise SystemExit(asyncio.run(main(a.chromium,a.output)) or 0)
