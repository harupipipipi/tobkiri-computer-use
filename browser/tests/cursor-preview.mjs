import {renderCursor} from '../extension/cursor-overlay.mjs';
import {CURSOR_THEME} from '../extension/cursor-theme.mjs';
import {pageOp} from '../extension/page-ops.mjs';

const $ = id => document.getElementById(id);
const feedback = (action,p) => renderCursor(action,p,$('hold').checked?{...CURSOR_THEME,idleMs:60000}:CURSOR_THEME);
const op = (name,args={}) => pageOp(name,args,feedback);
const center = () => { const r=$('target').getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; };
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
let clicks=0;
$('target').onclick=()=>{$('count').textContent=String(++clicks);};
$('move').onclick=()=>feedback('move',center());
$('click').onclick=()=>{const p=center();op('domClick',p);};
$('drag').onclick=async()=>{const r=$('stage').getBoundingClientRect();for(let i=0;i<=10;i++){feedback(i===10?'move':'drag',{x:r.x+35+i*(r.width-70)/10,y:r.y+r.height/2+45});await delay(55);}};
$('edge').onclick=async()=>{for(const p of [{x:0,y:0},{x:innerWidth-1,y:0},{x:innerWidth-1,y:innerHeight-1},{x:0,y:innerHeight-1}]){feedback('move',p);await delay(500);}};
$('contrast').onclick=()=>{$('stage').classList.toggle('dark');feedback('move',center());};
$('hide').onclick=()=>feedback('hide',{});
$('type').onclick=()=>op('focus',{selector:'#entry',edit:true});
$('scroll').onclick=()=>op('scroll',{selector:'#scroller',deltaY:100});
$('checks').onclick=async()=>{
  const lines=[];
  const assert=(ok,name)=>{if(!ok)throw new Error(name);lines.push(`PASS ${name}`);$('report').textContent=lines.join('\n');};
  const host=()=>document.querySelector('[data-tobkiri-cursor]');
  try {
    window.scrollTo({top:0,behavior:'instant'});
    const p=center();feedback('move',p);
    assert(!!host()?.shadowRoot.querySelector('svg path'),'Lucide SVG is present');
    const h=host(),holder=h.shadowRoot.firstElementChild,r=holder.getBoundingClientRect();
    assert(Math.abs(r.x-p.x)<.1&&Math.abs(r.y-p.y)<.1,'CSS viewport coordinates match the cursor hotspot');
    assert(document.elementFromPoint(p.x,p.y)===$('target'),'Cursor overlay does not intercept hit testing');
    feedback('down',p);assert(!h.shadowRoot.querySelector('div div').hidden,'Pressed state displays a ring');
    feedback('move',{x:p.x+20,y:p.y});assert(host()===h&&document.querySelectorAll('[data-tobkiri-cursor]').length===1,'Move reuses one overlay');
    assert(h.shadowRoot.querySelector('div div').hidden,'Move clears the pressed state');
    const style=document.createElement('style');style.textContent='[data-tobkiri-cursor]{display:none!important;pointer-events:auto!important;transform:scale(3)!important} svg{display:none!important}';document.head.append(style);
    try{assert(getComputedStyle(h).display==='block'&&getComputedStyle(h).pointerEvents==='none'&&getComputedStyle(h.shadowRoot.querySelector('svg')).display!=='none','Page CSS cannot hide or resize the cursor');}finally{style.remove();}
    op('domClick',p);assert(clicks>0,'Underlying target still receives a click');
    const internal=document.createElement('button');internal.textContent='INTERNAL_CURSOR';host().shadowRoot.append(internal);
    const snapshot=op('snapshot');internal.remove();assert(!snapshot.elements.some(e=>e.name==='INTERNAL_CURSOR'),'Cursor shadow subtree is excluded from snapshots');
    op('focus',{selector:'#entry',edit:true});assert(document.activeElement===$('entry'),'Typing feedback preserves input focus');
    op('focus',{selector:'#entry',edit:true,replace:true});op('domType',{selector:'#entry',text:''});assert($('entry').value==='','Empty DOM replacement clears the input');
    const result=op('scroll',{selector:'#scroller',deltaY:100});assert(result.after.y>result.before.y,'Container scroll works with cursor feedback');
    feedback('move',{x:0,y:0});assert(host().dataset.x==='0'&&host().dataset.y==='0','Top-left edge accepts zero coordinates');
    feedback('move',{x:innerWidth-1,y:innerHeight-1});assert(!!host(),'Bottom-right edge remains in the viewport');
    assert(host().shadowRoot.querySelector('svg').style.transform==='scale(-1, -1)','Edge glyph turns inward without moving its hotspot');
    feedback('move',{x:innerWidth,y:0});assert(!host(),'Out-of-viewport feedback is removed');
    renderCursor('click',{x:60,y:60},{...CURSOR_THEME,idleMs:40});await delay(80);assert(!host(),'Idle overlay is removed');
    $('report').textContent=`${lines.length} checks passed\n${lines.join('\n')}`;
    window.scrollTo({top:0,behavior:'instant'});feedback('click',center());
  } catch(error) { $('report').textContent=lines.join('\n')+`\nFAIL ${error.message}`; }
};
