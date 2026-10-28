/* Device-local presentation only. No sockets, configuration writes, or native effects. */
(() => {
  'use strict';
  /* Generative themes: each one is a live WebGL scene (theme-scenes.js) that reacts to touch, typing and playback. */
  const backgrounds={
    aurora:{light:'#eef5f7',dark:'#0b1220'},bloom:{light:'#f2f5eb',dark:'#0e1e19'},
    resonance:{light:'#f6efe3',dark:'#130f1c'},constellation:{light:'#eef1fa',dark:'#070b16'},
    ink:{light:'#fafaf8',dark:'#101215'},
  };
  const registry = Object.freeze(Object.fromEntries([
    ['aurora','Aurora','Ribbons of light that swirl where you touch.','dark','#34e0b4','#0b1220'],
    ['bloom','Bloom','Every tap and keystroke grows a flower.','light','#f0728f','#f2f5eb'],
    ['resonance','Resonance','Sound-etched patterns that tune to your pointer.','dark','#ffb454','#130f1c'],
    ['constellation','Constellation','A drifting star network that links to your finger.','dark','#6a9bff','#070b16'],
    ['ink','Ink','Paper, precise lines, and uncompromising clarity.','light','#171b22','#fafaf8'],
  ].map(([id,label,description,appearance,accent,surface])=>[id,Object.freeze({id,label,description,appearance,accent,surface,backgrounds:Object.freeze(backgrounds[id]),stylesheet:`/themes/${id}.css`})])));
  const legacy = {
    cyber:['aurora','dark'],oled:['constellation','dark'],matrix:['bloom','dark'],nordic:['constellation','dark'],light:['aurora','light'],
    glass:['aurora','dark'],soft:['constellation','light'],clay:['bloom','light'],companion:['resonance','light'],
  };
  const read = key => {try{return window.localStorage.getItem(key);}catch(_){return null;}};
  const write = (key,value) => {try{window.localStorage.setItem(key,value);}catch(_){/* Private mode still permits a local theme. */}};
  const migrate = id => {
    if(Object.hasOwn(legacy,id))return {id:legacy[id][0],appearance:legacy[id][1]};
    const selected=Object.hasOwn(registry,id)?registry[id]:registry.aurora;
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
  let state={...migrate(read('touchhelm_theme')||read('phonepad_theme')||'aurora'),
    appearance:read('touchhelm_appearance')||migrate(read('touchhelm_theme')||'aurora').appearance,
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
    const original=assetURL(`./themes/${id}.css`),href=window.TouchHelmBrowserLink?.staticURL?.(original)||original;
    if(active.getAttribute('href')===href||active.href===href)return;
    ready=new Promise(resolve=>{
      active.onload=()=>{resolve(true);window.TouchHelmEffects?.synchronize();};
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
    const heading=node('h3','Choose your theme','th-picker-heading');
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
