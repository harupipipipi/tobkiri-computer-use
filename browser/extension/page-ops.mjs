/** This function is serialized into a CDP ISOLATED world. No extension token or privileges enter the page. */
export function pageOp(op, a={}, renderFeedback=null) {
  const fail=(code,message)=>{throw new Error(`${code}: ${message}`);};
  // Rendering is best-effort and must not change the result of an input operation.
  const feedback=(action,p)=>{try{return renderFeedback?.(action,p);}catch{return {rendered:false};}};
  const store=globalThis.__tobkiri_tabs_refs ??= {refs:new Map(),generation:0};
  const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none';};
  const label=el=>(el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim() || el.labels?.[0]?.innerText || el.getAttribute('alt') || el.getAttribute('title') || el.getAttribute('placeholder') || el.innerText || el.getAttribute('name') || '').trim().slice(0,180);
  function target() {
    let el;
    if(a.ref) el=store.refs.get(a.ref);
    else if(a.selector) {let list;try{list=document.querySelectorAll(a.selector);}catch{fail('INVALID_SELECTOR','Invalid CSS selector.');}if(list.length!==1)fail('AMBIGUOUS_TARGET',`Selector matched ${list.length} elements; use a snapshot ref.`);el=list[0];}
    if(!el?.isConnected || el.ownerDocument!==document)fail('STALE_REF','Take a new snapshot, or use a unique selector.');
    return el;
  }
  function point(el) {
    if(!visible(el))fail('NOT_VISIBLE','Target is not visible.');
    if(el.disabled || el.getAttribute('aria-disabled')==='true')fail('DISABLED','Target is disabled.');
    el.scrollIntoView({block:'center',inline:'center',behavior:'instant'});
    const r=el.getBoundingClientRect();
    const left=Math.max(0,r.left),right=Math.min(innerWidth,r.right),top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);
    if(right<=left||bottom<=top)fail('OUTSIDE_VIEWPORT','Target has no visible point.');
    const x=(left+right)/2,y=(top+bottom)/2;
    let hit=document.elementFromPoint(x,y);
    for(let i=0;i<10&&hit?.shadowRoot;i++){const deeper=hit.shadowRoot.elementFromPoint(x,y);if(!deeper||deeper===hit)break;hit=deeper;}
    if(!hit || (hit!==el&&!el.contains(hit)))fail('OBSCURED','Target center is covered by another element.');
    return {x,y};
  }
  if(op==='ready')return {readyState:document.readyState,url:location.href};
  if(op==='viewport')return {width:innerWidth,height:innerHeight,scrollX,scrollY,devicePixelRatio};
  if(op==='snapshot') {
    store.refs.clear();store.generation++;
    const prefix=`r${store.generation}_${Math.random().toString(36).slice(2,9)}_`;
    const elements=[],roots=[document];let examined=0,capped=false;
    const max=Math.floor(a.maxElements||180);
    while(roots.length && elements.length<max && examined<30000) {
      const root=roots.shift();
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT);let el;
      while((el=walker.nextNode())) {
        if(++examined>30000){capped=true;break;}
        if(el.hasAttribute('data-tobkiri-cursor'))continue;
        if(el.shadowRoot)roots.push(el.shadowRoot);
        if(!el.matches('a[href],button,input,textarea,select,summary,[role="button"],[role="link"],[role="checkbox"],[role="radio"],[role="textbox"],[role="combobox"],[contenteditable="true"],[tabindex]') || !visible(el))continue;
        const ref=prefix+elements.length;store.refs.set(ref,el);
        const r=el.getBoundingClientRect();const sensitive=/password/i.test(el.type||'') || /password|one-time-code|cc-/i.test(el.autocomplete||'');
        const item={ref,tag:el.tagName.toLowerCase(),role:el.getAttribute('role')||undefined,name:label(el),type:el.type||undefined,disabled:!!el.disabled,inViewport:r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth,rect:{x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)}};
        if('value' in el && !sensitive && el.type!=='file') item.value=String(el.value).slice(0,200);
        if(sensitive)item.value='[REDACTED]';
        if('checked'in el)item.checked=el.checked;
        if(el.tagName==='SELECT')item.options=[...el.options].slice(0,50).map(o=>({value:o.value,label:o.label,selected:o.selected}));
        elements.push(item);if(elements.length>=max){capped=true;break;}
      }
    }
    const text=document.body?.innerText||'';
    return {untrustedContent:true,title:document.title,url:location.href,text:text.slice(0,a.maxTextChars||18000),textTruncated:text.length>(a.maxTextChars||18000),elements,elementsTruncated:capped,viewport:{width:innerWidth,height:innerHeight,scrollX,scrollY,devicePixelRatio},iframes:[...document.querySelectorAll('iframe')].slice(0,30).map(f=>({title:f.title,src:f.getAttribute('src'),note:'Iframe DOM is not exposed in v0.1; coordinates can target rendered content.'}))};
  }
  if(op==='point')return point(target());
  if(op==='checkState'){const el=target();if(!['checkbox','radio'].includes(el.type))fail('WRONG_ELEMENT','Target is not a checkbox/radio.');return {checked:el.checked,type:el.type};}
  if(op==='focus') {
    const el=target();const p=point(el);
    if(a.edit && !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el.isContentEditable))fail('NOT_EDITABLE','Target is not an editable control.');
    if(a.edit && (el.readOnly || ['file','checkbox','radio','button','submit','reset','image','range','color','date','time','datetime-local','month','week','hidden'].includes(el.type)))fail('NOT_EDITABLE','This input needs a specialized/manual interaction.');
    feedback(a.edit?'type':a.feedbackAction||'move',p);
    el.focus({preventScroll:true});
    if(a.replace) {
      if(typeof el.select==='function')el.select();
      else if(el.isContentEditable){const range=document.createRange();range.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(range);}
    }
    return {focused:true,empty:a.edit?('value'in el?el.value==='':el.textContent===''):undefined};
  }
  if(op==='select') {
    const el=target();if(!(el instanceof HTMLSelectElement))fail('WRONG_ELEMENT','Expected native select.');point(el);
    const option=[...el.options].find(o=>o.value===a.value);if(!option||option.disabled)fail('BAD_OPTION','Option missing or disabled.');
    feedback('click',point(el));
    el.value=a.value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return {value:el.value,syntheticEvents:true};
  }
  if(op==='scroll') {
    const dx=a.deltaX||0,dy=a.deltaY||0;
    let el;
    if(a.ref||a.selector)el=target();
    else {
      const x=a.x??innerWidth/2,y=a.y??innerHeight/2;
      if(x<0||y<0||x>=innerWidth||y>=innerHeight)fail('OUTSIDE_VIEWPORT','Scroll coordinates must be in the viewport.');
      el=document.elementFromPoint(x,y);
      for(let i=0;i<10&&el?.shadowRoot;i++){const next=el.shadowRoot.elementFromPoint(x,y);if(!next||next===el)break;el=next;}
    }
    const scrollAction=dy<0||(!dy&&dx<0)?'scroll_up':'scroll';
    if(a.ref||a.selector){const r=el.getBoundingClientRect();feedback(scrollAction,{x:(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2,y:(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2});}
    else feedback(scrollAction,{x:a.x??innerWidth/2,y:a.y??innerHeight/2});
    const root=document.scrollingElement;
    const canMove=(position,size,view,delta)=>delta<0?position>0:delta>0?position+view<size:false;
    while(el && el!==root) {
      const style=getComputedStyle(el);
      const yOk=/(auto|scroll|overlay)/.test(style.overflowY)&&canMove(el.scrollTop,el.scrollHeight,el.clientHeight,dy);
      const xOk=/(auto|scroll|overlay)/.test(style.overflowX)&&canMove(el.scrollLeft,el.scrollWidth,el.clientWidth,dx);
      if(yOk||xOk)break;
      el=el.parentElement||el.getRootNode()?.host;
    }
    el=el||root;if(!el)fail('NO_SCROLL_TARGET','No scrolling element.');
    const before={x:el.scrollLeft,y:el.scrollTop};el.scrollBy({left:dx,top:dy,behavior:'instant'});
    return {method:'dom-scroll',before,after:{x:el.scrollLeft,y:el.scrollTop},note:'Programmatic scrolling: no wheel event is dispatched.'};
  }
  if(op==='wait') {
    if(a.text!==undefined)return {matched:(document.body?.innerText||'').includes(a.text)};
    let el;try{el=document.querySelector(a.selector);}catch{fail('INVALID_SELECTOR','Invalid CSS selector.');}return {matched:!!el&&visible(el)};
  }
  // Trusted-input delivery probe: capture-phase listeners in this isolated world observe
  // CDP-dispatched events if (and only if) the host actually delivers them to the page.
  if(op==='armInput') {
    const prev=globalThis.__tbkInput;
    if(prev)for(const t of prev.types)document.removeEventListener(t,prev.h,true);
    const seen={};const h=e=>{if(e.isTrusted)seen[e.type]=1;};const types=a.types||[];
    for(const t of types)document.addEventListener(t,h,true);
    globalThis.__tbkInput={seen,h,types};
    return {armed:true};
  }
  if(op==='inputProbe')return {seen:globalThis.__tbkInput?.seen||{}};
  // The locally bundled Lucide cursor is injected as an explicit isolated-world callback.
  if(op==='cursor')return feedback(a.action,a)||{rendered:false};
  function mark(x,y){
    feedback('click',{x,y});
  }
  function flash(el){
    const r=el.getBoundingClientRect();if(!r.width&&!r.height)return;
    const host=document.documentElement||document.body;if(!host)return;
    const d=document.createElement('div');
    d.style.cssText=`position:fixed;left:${Math.round(r.left)-3}px;top:${Math.round(r.top)-3}px;width:${Math.round(r.width)+6}px;height:${Math.round(r.height)+6}px;border:2px solid #d2a8ff;border-radius:4px;z-index:2147483647;pointer-events:none;box-sizing:border-box;background:rgba(210,168,255,.14)`;
    host.appendChild(d);
    try{d.animate([{opacity:'1'},{opacity:'1',offset:.5},{opacity:'0'}],{duration:1800,easing:'ease-out'}).onfinish=()=>d.remove();}catch{setTimeout(()=>d.remove(),1900);}
  }
  if(op==='mark'){mark(a.x,a.y);return {marked:true};}
  // Explicit DOM input. These emit isTrusted:false events and cannot run browser default actions such as
  // focus traversal; callers must surface `trusted:false` rather than hiding the distinction.
  if(op==='domClick') {
    let hit=document.elementFromPoint(a.x,a.y);
    for(let i=0;i<10&&hit?.shadowRoot;i++){const next=hit.shadowRoot.elementFromPoint(a.x,a.y);if(!next||next===hit)break;hit=next;}
    if(!hit)return {applied:false};
    mark(a.x,a.y);flash(hit);
    const PE=globalThis.PointerEvent||MouseEvent;
    // Full pointer/mouse sequence with real coordinates, detail and pointer identity —
    // el.click() alone emits click with detail:0 and no coords, which delegated handlers
    // (e.g. React roots inspecting nativeEvent) can silently ignore.
    const base={bubbles:true,cancelable:true,composed:true,view:window,clientX:a.x,clientY:a.y,screenX:a.x,screenY:a.y,button:0,detail:1};
    const pe=t=>new PE(t,{...base,pointerId:1,pointerType:'mouse',isPrimary:true});
    const me=(t,extra)=>new MouseEvent(t,{...base,...extra});
    hit.dispatchEvent(pe('pointerover'));hit.dispatchEvent(me('mouseover'));
    hit.dispatchEvent(pe('pointermove'));hit.dispatchEvent(me('mousemove'));
    try{hit.focus?.({preventScroll:true});}catch{}
    hit.dispatchEvent(pe('pointerdown'));hit.dispatchEvent(me('mousedown',{buttons:1}));
    hit.dispatchEvent(pe('pointerup'));hit.dispatchEvent(me('mouseup',{buttons:0}));
    hit.dispatchEvent(me('click'));
    return {applied:true,tag:hit.tagName.toLowerCase()};
  }
  if(op==='domType') {
    const el=target();
    if(el.disabled||el.readOnly)fail('DISABLED','Target is disabled.');
    if(el instanceof HTMLInputElement||el instanceof HTMLTextAreaElement){
      let s,e;try{s=el.selectionStart??el.value.length;e=el.selectionEnd??s;}catch{s=e=el.value.length;}
      const proto=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
      const next=a.replace!==false?a.text:el.value.slice(0,s)+a.text+el.value.slice(e);
      if(setter)setter.call(el,next);else el.value=next;
      try{el.setSelectionRange(s+a.text.length,s+a.text.length);}catch{}
      el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:a.text}));
      flash(el);
      return {applied:true};
    }
    if(el.isContentEditable){
      if(a.replace!==false){const range=document.createRange();range.selectNodeContents(el);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);}
      let done=false;try{done=document.execCommand('insertText',false,a.text);}catch{}
      if(!done){
        const sel=getSelection();
        if(sel.rangeCount&&el.contains(sel.anchorNode)){const r=sel.getRangeAt(0);r.deleteContents();const n=document.createTextNode(a.text);r.insertNode(n);r.setStartAfter(n);r.collapse(true);sel.removeAllRanges();sel.addRange(r);}
        else el.append(a.text);
        el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:a.text}));
      }
      flash(el);
      return {applied:true};
    }
    fail('NOT_EDITABLE','Target is not editable.');
  }
  if(op==='domKey') {
    const el=document.activeElement&&document.activeElement!==document.body?document.activeElement:document.body;
    const init={key:a.key,code:a.code||'',bubbles:true,cancelable:true,composed:true,altKey:!!(a.modifiers&1),ctrlKey:!!(a.modifiers&2),metaKey:!!(a.modifiers&4),shiftKey:!!(a.modifiers&8)};
    const keydownOk=el.dispatchEvent(new KeyboardEvent('keydown',init));
    el.dispatchEvent(new KeyboardEvent('keyup',init));
    let inserted=false,submitted=false;
    const ed=el.closest?.('input,textarea,[contenteditable="true"]');
    if(keydownOk&&ed&&!ed.disabled&&!ed.readOnly){
      // Enter is handled before the generic text branch: it must newline in multi-line
      // fields or submit the owning form, never insert a stray '\r'.
      if(a.key==='Enter'){
        if(ed.isContentEditable||ed instanceof HTMLTextAreaElement){try{inserted=document.execCommand('insertText',false,'\n');}catch{}}
        else if(ed instanceof HTMLInputElement&&ed.form){ed.form.requestSubmit();submitted=true;}
      }
      else if(a.text){try{inserted=document.execCommand('insertText',false,a.text);}catch{}}
    }
    flash(el);
    return {applied:true,inserted,submitted};
  }
  fail('UNKNOWN_PAGE_OPERATION','Unsupported page operation.');
}
