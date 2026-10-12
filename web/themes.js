/* Device-local presentation only. No sockets, configuration writes, or native effects. */
(() => {
  'use strict';
  const backgrounds={
    bloom:{light:'#f2f5eb',dark:'#0e1e19'},resonance:{light:'#f7efe1',dark:'#211921'},
    companion:{light:'#f2f0fb',dark:'#211b30'},clay:{light:'#f6ece7',dark:'#292025'},
    glass:{light:'#eaf4f8',dark:'#0b1929'},soft:{light:'#eef3f6',dark:'#1b2631'},ink:{light:'#fafaf8',dark:'#101215'},
  };
  const registry = Object.freeze(Object.fromEntries([
    ['bloom','Bloom','A flowering woodland, alive with quiet light.','light','#27634f','#f1f4e9'],
    ['resonance','Resonance','Vinyl, warm metal, and the rhythm of a record.','dark','#efb767','#231b24'],
    ['companion','Companion','A friendly presence in pearl and violet.','light','#6553a5','#efedf8'],
    ['clay','Clay','Sculpted controls with a soft, tactile finish.','light','#984137','#f5e9e4'],
    ['glass','Glass','Clear layers, deep blue, and refracted light.','dark','#8cdef4','#0b1929'],
    ['soft','Soft','Quiet blue surfaces and carefully measured space.','light','#355e86','#eaf0f5'],
    ['ink','Ink','Paper, precise lines, and uncompromising clarity.','light','#171b22','#fafaf8'],
  ].map(([id,label,description,appearance,accent,surface])=>[id,Object.freeze({id,label,description,appearance,accent,surface,backgrounds:Object.freeze(backgrounds[id]),stylesheet:`/themes/${id}.css`})])));
  const legacy = {cyber:['glass','dark'],oled:['glass','dark'],matrix:['bloom','dark'],nordic:['soft','dark'],light:['clay','light']};
  const read = key => {try{return window.localStorage.getItem(key);}catch(_){return null;}};
  const write = (key,value) => {try{window.localStorage.setItem(key,value);}catch(_){/* Private mode still permits a local theme. */}};
  const migrate = id => {
    if(Object.hasOwn(legacy,id))return {id:legacy[id][0],appearance:legacy[id][1]};
    const selected=Object.hasOwn(registry,id)?registry[id]:registry.glass;
    return {id:selected.id,appearance:selected.appearance};
  };
  const queries = {
    dark:window.matchMedia('(prefers-color-scheme: dark)'),
    reduced:window.matchMedia('(prefers-reduced-motion: reduce)'),
    contrast:window.matchMedia('(prefers-contrast: more)'),
  };
  const source = new URL(document.currentScript?.src || '/themes.js',window.location.href);
  const version=source.searchParams.get('v');
  const assetURL=relative=>{const url=new URL(relative,source);if(version)url.searchParams.set('v',version);return url.pathname+url.search;};
  const root=document.documentElement,pickers=new Set();
  let interactionActive=false;
  let state={...migrate(read('touchhelm_theme')||read('phonepad_theme')||'glass'),
    appearance:read('touchhelm_appearance')||migrate(read('touchhelm_theme')||'glass').appearance,
    effects:read('touchhelm_effects')||'rich',motion:read('touchhelm_motion')||'system',contrast:read('touchhelm_contrast')||'system'};
  let ready=Promise.resolve();
  const option=(value,values,fallback)=>values.includes(value)?value:fallback;
  function synchronize(){
    root.dataset.appearance=state.appearance==='system'?(queries.dark.matches?'dark':'light'):state.appearance;
    root.dataset.motion=queries.reduced.matches||state.motion==='reduced'?'reduced':'full';
    root.dataset.effects=state.effects==='off'?'off':root.dataset.motion==='reduced'?'calm':state.effects;
    root.dataset.contrast=state.contrast==='increased'||state.contrast==='system'&&queries.contrast.matches?'increased':'standard';
    root.dataset.themePaused=String(interactionActive||document.hidden||root.classList.contains('interaction-active'));
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta)meta.setAttribute('content',registry[state.id].backgrounds[root.dataset.appearance]);
    for(const refresh of pickers)refresh();
    window.TouchHelmEffects?.synchronize();
  }
  function loadStyles(id){
    let base=document.getElementById('th-themes-base');
    if(!base){base=document.createElement('link');base.id='th-themes-base';base.rel='stylesheet';base.href=assetURL('./themes.css');document.head.appendChild(base);}
    let active=document.getElementById('th-active-theme');
    if(!active){active=document.createElement('link');active.id='th-active-theme';active.rel='stylesheet';document.head.appendChild(active);}
    const href=assetURL(`./themes/${id}.css`);
    if(active.getAttribute('href')===href||active.href===href)return;
    ready=new Promise(resolve=>{
      active.onload=()=>resolve(true);
      active.onerror=()=>{
        resolve(false);
        if(id!=='ink')apply('ink',state,false);
        root.dataset.themeAssetError='true';
      };
    });
    root.dataset.themeAssetError='false';active.href=href;
  }
  function apply(id,preferences={},persist=true){
    const migrated=migrate(id),incoming={...state,...preferences};
    if(Object.hasOwn(legacy,id)&&!Object.hasOwn(preferences,'appearance'))incoming.appearance=migrated.appearance;
    state={id:migrated.id,
      appearance:option(incoming.appearance,['light','dark','system'],migrated.appearance),
      effects:option(incoming.effects,['rich','calm','off'],'rich'),
      motion:option(incoming.motion,['full','reduced','system'],'system'),
      contrast:option(incoming.contrast,['standard','increased','system'],'system')};
    root.dataset.theme=state.id;loadStyles(state.id);synchronize();
    if(persist)for(const [key,value] of Object.entries(state))write(`touchhelm_${key==='id'?'theme':key}`,value);
    return {...state};
  }
  const node=(tag,text,classes)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(classes)n.className=classes;return n;};
  function mountPicker(container,onSelect){
    if(!container)return ()=>{};
    const choices=node('div',null,'th-theme-choices'),buttons=[];
    const heading=node('h3','Choose your material','th-picker-heading');
    const choose=(id,prefs)=>{const selected=apply(id,prefs);onSelect?.(selected.id,{appearance:selected.appearance,motion:selected.motion,contrast:selected.contrast,effects:selected.effects});};
    for(const theme of Object.values(registry)){
      const button=node('button',null,'th-theme-choice');button.type='button';button.dataset.themeId=theme.id;
      button.setAttribute('aria-pressed','false');
      const swatch=node('span',null,'th-theme-swatch');swatch.setAttribute('aria-hidden','true');
      swatch.style.backgroundColor=theme.surface;swatch.style.color=theme.accent;
      const shape=node('span',null,`th-swatch-shape th-swatch-${theme.id}`);swatch.appendChild(shape);
      const copy=node('span',null,'th-theme-copy');copy.append(node('strong',theme.label),node('span',theme.description));
      button.append(swatch,copy);button.addEventListener('click',()=>choose(theme.id,{}));buttons.push(button);choices.appendChild(button);
    }
    const settings=node('div',null,'th-theme-preferences'),selects={};
    for(const [key,label,values] of [
      ['appearance','Appearance',[['system','Follow device'],['light','Light'],['dark','Dark']]],
      ['effects','Living effects',[['rich','Rich'],['calm','Calm'],['off','Off']]],
      ['contrast','Contrast',[['system','Follow device'],['standard','Standard'],['increased','Increased']]],
    ]){
      const field=node('label',null,'th-theme-preference');const select=node('select');select.id=`th-picker-${key}`;
      field.setAttribute('for',select.id);field.appendChild(node('span',label));
      for(const [value,text]of values){const item=node('option',text);item.value=value;select.appendChild(item);}
      select.addEventListener('change',()=>choose(state.id,{[key]:select.value,...(key==='effects'?{motion:'system'}:{})}));field.appendChild(select);settings.appendChild(field);selects[key]=select;
    }
    container.replaceChildren(heading,choices,settings);
    const refresh=()=>{for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.themeId===state.id));for(const[key,select]of Object.entries(selects))select.value=state[key];};
    pickers.add(refresh);refresh();return ()=>pickers.delete(refresh);
  }
  function updateContext(context={}){
    for(const key of ['connected','playing'])if(typeof context[key]==='boolean')root.dataset[key]=String(context[key]);
    synchronize();
  }
  function setInteractionActive(active){interactionActive=!!active;synchronize();}
  for(const query of Object.values(queries))query.addEventListener?.('change',synchronize);
  document.addEventListener('visibilitychange',synchronize);
  if(window.MutationObserver)new window.MutationObserver(synchronize).observe(root,{attributes:true,attributeFilter:['class']});
  window.TouchHelmThemes=Object.freeze({registry,migrate,apply,mountPicker,updateContext,setInteractionActive,
    get state(){return {...state};},get ready(){return ready;}});
  apply(state.id,state,false);
})();
