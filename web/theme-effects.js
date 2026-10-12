/* A passive, device-local scene director. It never reads editable text or sends input. */
(function(global){
  'use strict';
  const FAMILIES=new Set(['bloom','companion','resonance','clay']);
  function createDirector(){
    const slots=Array.from({length:8},(_,id)=>({id,kind:id<2?'idle':'touch',until:0}));
    let state={mode:'rich',reduced:false,hidden:false,active:false},quietUntil=0,lastFrame=-Infinity;
    const mode=()=>state.mode==='off'?'off':state.reduced?'calm':state.mode;
    function expire(now){for(const slot of slots)if(slot.until<=now)slot.until=0;}
    function configure(next,now=0){
      const wasActive=state.active,wasMode=mode();state={...state,...next};
      if(wasActive&&!state.active)quietUntil=now+1100;
      for(const slot of slots)if(wasMode!==mode()||mode()==='off'||state.hidden||(slot.kind==='idle'&&(state.active||mode()!=='rich')))slot.until=0;
    }
    function acquire(kind,now,duration=kind==='idle'?6800:850){
      expire(now);if(state.hidden||mode()==='off'||kind==='idle'&&(mode()!=='rich'||state.active||now<quietUntil))return null;
      const candidates=slots.filter(s=>s.kind===kind);let slot=candidates.find(s=>s.until===0);
      if(!slot&&kind==='touch')slot=candidates.reduce((a,b)=>a.until<=b.until?a:b);
      if(!slot)return null;slot.until=now+duration;return slot;
    }
    return {configure,acquire,expire,clear(){for(const slot of slots)slot.until=0;},
      frame(now){if(now-lastFrame<1000/30)return false;lastFrame=now;return true;},
      snapshot(){return {mode:mode(),idle:slots.filter(s=>s.kind==='idle'&&s.until>0).length,touch:slots.filter(s=>s.kind==='touch'&&s.until>0).length,slots:slots.map(s=>({...s}))};}};
  }
  if(typeof module==='object'&&module.exports){module.exports={createDirector};return;}
  const doc=global.document;if(!doc||global.TouchHelmEffects)return;
  const root=doc.documentElement,director=createDirector(),NS='http://www.w3.org/2000/svg';
  const random=(min,max)=>min+Math.random()*(max-min),now=()=>performance.now();
  const stage=doc.createElement('div');stage.className='th-effects-stage';stage.setAttribute('aria-hidden','true');stage.inert=true;
  const nodes=Array.from({length:8},(_,id)=>{const n=doc.createElement('div');n.className='th-effect';n.hidden=true;n.dataset.slot=String(id);stage.append(n);return n;});
  const listeners=[],pointers=new Set();let timer=null,scrollTimer=null,nextScene=0,theme='',active=false,disposed=false;
  const sensitive='input,textarea,select,[contenteditable="true"],img,canvas,.qr-code,.qr-frame,.pairing-code,[data-effects-protect],#qrCode,#pairingQR,#pinModal';
  const controls='button,.native-key,[role="button"],summary';
  const listen=(target,event,fn,options={passive:true})=>{target.addEventListener(event,fn,options);listeners.push(()=>target.removeEventListener(event,fn,options));};
  const svgNode=(name,attrs={},parent)=>{const n=doc.createElementNS(NS,name);for(const [key,value]of Object.entries(attrs))n.setAttribute(key,String(value));if(parent)parent.append(n);return n;};
  const path=(parent,d,cls='th-stem',extra={})=>svgNode('path',{d,class:cls,...(cls==='th-stem'?{pathLength:1}:{}),...extra},parent);
  function flower(parent,x,y,size,variant){
    const group=svgNode('g',{transform:`translate(${x} ${y}) scale(${size})`,class:`th-flower th-flower-${variant%3}`},parent);
    const petals=variant%3===0?5:variant%3===1?8:6;
    for(let i=0;i<petals;i++)svgNode('ellipse',{cx:0,cy:-7,rx:variant%3===1?3:4.5,ry:7,transform:`rotate(${i*360/petals})`,class:'th-petal'},group);
    svgNode('circle',{r:3.5,class:'th-pollen'},group);
  }
  function bloom(svg,frame,w,h){
    const seed=Math.floor(random(0,3));
    if(frame){
      path(svg,`M 6 ${h-7} Q 2 ${h/2} 8 8 Q ${w/3} 1 ${w*.68} 5`);
      path(svg,`M ${w-7} 8 Q ${w+1} ${h/2} ${w-7} ${h-6} Q ${w*.65} ${h+1} ${w*.45} ${h-4}`);
      for(const [x,y,r]of[[8,10,-35],[6,h*.65,25],[w-7,h-10,135]])path(svg,'M0 0 C-9 -13 -14 -9 -10 0 C-6 4 -2 3 0 0','th-leaf',{transform:`translate(${x} ${y}) rotate(${r}) scale(.6)`});
      flower(svg,w-8,9,.4,seed);flower(svg,8,h-9,.35,seed+1);
    }else{
      path(svg,`M14 ${h} C38 ${h*.72} 9 ${h*.42} 44 9`);
      path(svg,`M26 ${h*.64} Q62 ${h*.60} 67 ${h*.28} M27 ${h*.46} Q7 ${h*.37} 9 ${h*.2}`);
      for(let i=0;i<8;i++){const y=h-12-i*(h-28)/8,x=24+Math.sin(i*1.5)*10;path(svg,'M0 0 C-20 -17 -26 -6 -17 3 C-9 8 -4 3 0 0','th-leaf',{transform:`translate(${x} ${y}) rotate(${i%2?185:0}) scale(${.55+random(0,.3)})`});}
      flower(svg,44,15,.8,seed);flower(svg,68,h*.28,.62,seed+1);flower(svg,9,h*.2,.48,seed+2);
      for(let i=0;i<3;i++)svgNode('ellipse',{cx:random(48,85),cy:random(50,h-10),rx:3,ry:6,class:'th-drifting-petal',transform:`rotate(${random(-30,40)} 60 80)`},svg);
    }
  }
  function companion(svg,frame,w,h,kind){
    if(frame){path(svg,`M3 14 V7 Q3 3 7 3 H17 M${w-17} 3 H${w-7} Q${w-3} 3 ${w-3} 7 V14 M3 ${h-14} V${h-7} Q3 ${h-3} 7 ${h-3} H17 M${w-17} ${h-3} H${w-7} Q${w-3} ${h-3} ${w-3} ${h-7} V${h-14}`,'th-circuit');return;}
    const g=svgNode('g',{transform:`translate(${w/2-36} ${h/2-33})`,class:'th-robot'},svg);
    path(g,'M36 10 V1 M31 1 H41','th-circuit');
    svgNode('rect',{x:3,y:28,width:8,height:18,rx:4,class:'th-shell'},g);svgNode('rect',{x:61,y:28,width:8,height:18,rx:4,class:'th-shell'},g);
    svgNode('rect',{x:8,y:10,width:56,height:50,rx:18,class:'th-shell'},g);
    svgNode('rect',{x:15,y:23,width:42,height:24,rx:10,class:'th-visor'},g);
    const eyes=svgNode('g',{class:'th-eyes'},g);
    for(const x of [27,45])svgNode('ellipse',{cx:x,cy:34,rx:3.4,ry:kind==='error'?2:5,class:'th-eye'},eyes);
    path(g,kind==='error'?'M30 53 Q36 48 42 53':root.dataset.connected==='true'?'M30 50 Q36 57 42 50':'M32 52 H40','th-mouth');
    svgNode('circle',{cx:57,cy:17,r:2.5,class:root.dataset.connected==='true'?'th-online':'th-offline'},g);
    svgNode('rect',{x:17,y:60,width:12,height:6,rx:3,class:'th-shell'},g);svgNode('rect',{x:43,y:60,width:12,height:6,rx:3,class:'th-shell'},g);
  }
  function resonance(svg,frame,w,h){
    if(frame){for(let i=0;i<3;i++)path(svg,`M4 ${3+i*2} Q${w/2} ${9-i} ${w-4} ${3+i*2}`,'th-string');path(svg,`M4 ${h-4} H${w-4}`,'th-string');return;}
    for(let i=0;i<4;i++)path(svg,`M${8+i*7} ${h-3} Q${12+i*7} ${h/2} ${8+i*7} 6`,'th-string');
    const g=svgNode('g',{class:'th-notes'},svg);
    for(const [x,y,tilt]of[[53,30,-9],[76,73,12],[50,113,-4]]){const n=svgNode('g',{transform:`translate(${x} ${y}) rotate(${tilt})`},g);svgNode('ellipse',{cx:0,cy:0,rx:6,ry:4,transform:'rotate(-20)',class:'th-note'},n);path(n,'M5 0 V-22 Q17 -20 11 -12','th-note-stem');}
    path(svg,`M40 ${h-8} Q58 ${h-22} 77 ${h-7}`,'th-string');
  }
  function clay(svg,frame,w,h){
    if(frame){path(svg,`M10 5 Q${w/2} 1 ${w-10} 5 M6 11 Q2 ${h/2} 6 ${h-10}`,'th-clay-highlight');path(svg,`M12 ${h-5} Q${w/2} ${h} ${w-10} ${h-5}`,'th-clay-impression');return;}
    path(svg,`M12 ${h-20} C-4 ${h-52} 7 ${h-77} 25 ${h-78} C49 ${h-90} 61 ${h-46} 45 ${h-19} C37 ${h-4} 21 ${h-4} 12 ${h-20} Z`,'th-clay-form');
    path(svg,`M49 ${h-19} C35 ${h-45} 66 ${h-61} 82 ${h-40} C95 ${h-18} 65 ${h-4} 49 ${h-19} Z`,'th-clay-form th-clay-small');
    path(svg,`M14 ${h-28} Q6 ${h-57} 24 ${h-65} M53 ${h-27} Q54 ${h-43} 70 ${h-36}`,'th-clay-highlight');
    path(svg,`M22 ${h-20} Q32 ${h-13} 41 ${h-26}`,'th-clay-impression');
  }
  const draw={bloom,companion,resonance,clay};
  function clearNode(n){for(const a of n.getAnimations())a.cancel();n.hidden=true;n.replaceChildren();}
  function reconcile(){const slots=director.snapshot().slots;for(const slot of slots)if(!slot.until&&!nodes[slot.id].hidden)clearNode(nodes[slot.id]);}
  const visible=el=>{const r=el.getBoundingClientRect();return r.width>20&&r.height>20&&r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth&&!el.closest('[hidden],dialog:not([open])');};
  function protectedTarget(el){return !el||el.closest(sensitive)||el.matches(':focus-visible')||el.disabled;}
  function allowedArea(box,host){
    if(box.x<5||box.y<5||box.x+box.w>innerWidth-5||box.y+box.h>innerHeight-5)return false;
    const exclusions=doc.querySelectorAll(`${sensitive},button,summary,h1,h2,h3,label,p,.trackpad-hints > *,.laser-contact,.laser-guides,.presenter-status`);
    for(const el of exclusions){if(el===host||!el.getClientRects().length)continue;const r=el.getBoundingClientRect();if(box.x<r.right+8&&box.x+box.w>r.left-8&&box.y<r.bottom+8&&box.y+box.h>r.top-8)return false;}
    return true;
  }
  function occupied(box){return nodes.some(n=>{if(n.hidden)return false;const r=n.getBoundingClientRect();return box.x<r.right+14&&box.x+box.w>r.left-14&&box.y<r.bottom+8&&box.y+box.h>r.top-8;});}
  function sceneRegion(){
    const hosts=[...doc.querySelectorAll('.touch-surface,.desktop-nav,[data-effects-region]')].filter(visible);
    for(const host of hosts.sort(()=>Math.random()-.5)){
      const r=host.getBoundingClientRect(),w=Math.min(98,r.width*.29),h=Math.min(150,r.height*.42);
      if(h<65)continue;
      const sides=Math.random()<.5?[false,true]:[true,false];
      for(const right of sides){const box={x:right?r.right-w-28:r.left+14,y:r.bottom-h-18,w,h};if(allowedArea({...box,w:w+14},host)&&!occupied(box))return {...box,frame:false,host};}
    }
    const options=[...doc.querySelectorAll('.native-key,.trackpad-btn,.desktop-nav button,.desktop-button,.tool-btn,.nav-tab')].filter(el=>visible(el)&&!protectedTarget(el));
    for(const host of options.sort(()=>Math.random()-.5)){const r=host.getBoundingClientRect(),box={x:r.left,y:r.top,w:r.width,h:r.height,frame:true,host};if(!occupied(box))return box;}return null;
  }
  function paint(slot,box,kind='idle'){
    const n=nodes[slot.id];clearNode(n);n.hidden=false;n.className=`th-effect th-effect-${theme} ${box.frame?'th-effect-frame':'th-effect-scene'} th-effect-${kind}`;n.dataset.kind=slot.kind;
    Object.assign(n.style,{left:`${box.x}px`,top:`${box.y}px`,width:`${box.w}px`,height:`${box.h}px`});
    const svg=svgNode('svg',{viewBox:`0 0 ${box.w} ${box.h}`,width:box.w,height:box.h,'aria-hidden':'true',focusable:'false'});n.append(svg);draw[theme](svg,box.frame,box.w,box.h,kind);
    const duration=Math.max(1,slot.until-now()),calm=director.snapshot().mode==='calm';
    let frames=[{opacity:0},{opacity:1,offset:.15},{opacity:1,offset:.7},{opacity:0}];
    if(!calm&&!box.frame){
      const movement=theme==='companion'?14:theme==='clay'?2:6;
      frames=frames.map((f,i)=>({...f,transform:`translate(${i===2?movement:0}px,${i===1?-3:0}px) rotate(${theme==='bloom'&&i===2?3:0}deg)`}));
    }
    n.animate(frames,{duration,easing:calm?'linear':`steps(${Math.max(1,Math.floor(duration/34))},end)`,fill:'forwards'});
    if(!calm&&theme==='companion'&&!box.frame){const eyes=svg.querySelector('.th-eyes');eyes.animate([{transform:'scaleY(1)'},{transform:'scaleY(.12)',offset:.46},{transform:'scaleY(1)',offset:.53},{transform:'scaleY(1)'}],{duration:210,delay:random(900,1800),iterations:1,easing:'steps(6,end)'});}
  }
  function schedule(){if(timer!==null)clearTimeout(timer);timer=null;if(disposed||doc.hidden||!FAMILIES.has(theme)||director.snapshot().mode==='off')return;const snap=director.snapshot();const ends=snap.slots.filter(s=>s.until).map(s=>s.until);const scene=active||snap.mode!=='rich'?Infinity:nextScene;const due=Math.min(scene,...ends);if(Number.isFinite(due))timer=setTimeout(tick,Math.max(34,due-now()));}
  function tick(){timer=null;director.expire(now());reconcile();if(!active&&director.snapshot().mode==='rich'&&now()>=nextScene){const box=sceneRegion();if(box){const slot=director.acquire('idle',now(),random(4600,7400));if(slot)paint(slot,box);}nextScene=now()+random(2200,4600);}schedule();}
  function synchronize(){
    if(disposed)return;const next=root.dataset.theme,changed=next!==theme;theme=next;
    active=pointers.size>0||!!scrollTimer||root.dataset.themePaused==='true';
    director.configure({mode:FAMILIES.has(theme)?root.dataset.effects||'rich':'off',reduced:root.dataset.motion==='reduced',hidden:doc.hidden,active},now());
    if(changed){director.clear();nextScene=now()+350;}
    reconcile();schedule();
  }
  function react(element,{kind='press',x,y}={}){
    if(!FAMILIES.has(theme)||protectedTarget(element)||!visible(element))return false;
    const rect=element.getBoundingClientRect(),frame=element.matches(controls);
    let box={x:rect.left,y:rect.top,w:rect.width,h:rect.height,frame,host:element};
    if(!frame){const w=Math.min(85,rect.width*.3),h=Math.min(115,rect.height*.35);box={x:rect.left+14,y:rect.bottom-h-14,w,h,frame:false,host:element};if(!allowedArea(box,element))return false;}
    const slot=director.acquire('touch',now(),director.snapshot().mode==='calm'?260:kind==='key'?500:950);if(!slot)return false;
    paint(slot,box,kind);
    if(Number.isFinite(x)&&Number.isFinite(y)){nodes[slot.id].style.setProperty('--th-petal-x',`${Math.max(-30,Math.min(30,x-box.x-box.w/2))}px`);nodes[slot.id].style.setProperty('--th-petal-y',`${Math.max(-30,Math.min(30,y-box.y-box.h/2))}px`);}
    schedule();return true;
  }
  function move(event){
    if(!director.frame(now())||director.snapshot().mode!=='rich'||doc.hidden)return;
    for(const n of nodes){if(n.hidden)continue;const eyes=n.querySelector('.th-eyes');if(eyes){const r=n.getBoundingClientRect();eyes.style.translate=`${Math.max(-3,Math.min(3,(event.clientX-r.x-r.width/2)/35))}px ${Math.max(-2,Math.min(2,(event.clientY-r.y-r.height/2)/45))}px`;}else if(theme==='bloom'){const r=n.getBoundingClientRect();n.style.setProperty('--th-bend',`${Math.max(-4,Math.min(4,(event.clientX-r.x-r.width/2)/30))}deg`);}}
  }
  function scroll(){if(scrollTimer)clearTimeout(scrollTimer);director.clear();reconcile();scrollTimer=setTimeout(()=>{scrollTimer=null;nextScene=now()+1200;synchronize();},180);synchronize();}
  function suspend(value){if(value)pointers.add('external');else pointers.delete('external');synchronize();}
  function reset(){director.clear();reconcile();nextScene=now()+1200;synchronize();}
  function destroy(){disposed=true;if(timer!==null)clearTimeout(timer);if(scrollTimer)clearTimeout(scrollTimer);listeners.forEach(fn=>fn());observer.disconnect();director.clear();nodes.forEach(clearNode);stage.remove();}
  doc.body.append(stage);
  listen(doc,'pointerdown',event=>{pointers.add(event.pointerId);synchronize();const el=event.target.closest(`${controls},.touch-surface,.laser-surface`);if(el)react(el,{kind:el.matches('.native-key')?'key':'press',x:event.clientX,y:event.clientY});});
  for(const event of ['pointerup','pointercancel','lostpointercapture'])listen(doc,event,e=>{pointers.delete(e.pointerId);nextScene=now()+1200;synchronize();});
  listen(doc,'pointermove',move);listen(doc,'scroll',scroll,{passive:true,capture:true});listen(global,'resize',scroll);
  listen(doc,'keydown',event=>{if(event.repeat||event.target.closest(sensitive))return;if(['Enter',' '].includes(event.key)&&event.target.matches(controls))react(event.target,{kind:'key'});});
  listen(doc,'visibilitychange',()=>{if(doc.hidden){pointers.clear();if(scrollTimer)clearTimeout(scrollTimer);scrollTimer=null;}nextScene=now()+1200;synchronize();});
  listen(global,'blur',()=>{pointers.clear();synchronize();});
  const observer=new MutationObserver(()=>{synchronize();});observer.observe(root,{attributes:true,attributeFilter:['data-theme','data-effects','data-motion','data-theme-paused']});
  global.TouchHelmEffects=Object.freeze({react,suspend,reset,synchronize,destroy,get diagnostics(){return {...director.snapshot(),scheduled:timer!==null,theme};}});
  synchronize();
})(typeof window==='undefined'?globalThis:window);
