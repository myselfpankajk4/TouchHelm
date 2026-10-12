const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Node {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attrs={};this.events={};this.style={};this.textContent='';this.value='';this.hidden=false;}
  set innerHTML(_){throw Error('Use safe DOM construction');}
  setAttribute(k,v){this.attrs[k]=String(v); if(k==='id')this.id=String(v);}
  getAttribute(k){return this.attrs[k]??null;}
  appendChild(n){this.children.push(n);n.parentNode=this;return n;}
  append(...nodes){nodes.forEach(n=>this.appendChild(n));}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(n=>n!==this);}
  addEventListener(k,f){(this.events[k]??=[]).push(f);}
  removeEventListener(k,f){this.events[k]=(this.events[k]||[]).filter(v=>v!==f);}
  emit(k,event={}){(this.events[k]||[]).forEach(f=>f({target:this,...event}));}
}
function setup(saved={},blockedStorage=false){
  const root=new Node('html'),head=new Node('head'),body=new Node('body');
  const all=()=>[root,head,body,...[head,body].flatMap(function flat(n){return n.children.flatMap(c=>[c,...flat(c)]);})];
  const doc={documentElement:root,head,body,hidden:false,currentScript:{src:'http://localhost/themes.js?v=test-build'},events:{},
    createElement:t=>new Node(t),getElementById:id=>all().find(n=>n.id===id)||null,
    querySelector:q=>q.includes('theme-color')?null:null,
    addEventListener(k,f){(this.events[k]??=[]).push(f);}};
  const storage=new Map(Object.entries(saved));
  const media=new Map();
  const win={document:doc,location:{href:'http://localhost/'},localStorage:{getItem:k=>{if(blockedStorage)throw Error('blocked');return storage.get(k)??null;},setItem:(k,v)=>{if(blockedStorage)throw Error('blocked');storage.set(k,String(v));}},
    matchMedia(q){if(!media.has(q))media.set(q,{matches:false,events:[],addEventListener(k,f){this.events.push(f);}});return media.get(q);},
    MutationObserver:class{constructor(f){win.mutate=f;}observe(){}},addEventListener(){}};
  root.classList={contains:n=>root.classes?.includes(n)||false};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/themes.js'),'utf8'),{window:win,document:doc,URL,Promise,console,localStorage:win.localStorage});
  return {themes:win.TouchHelmThemes,root,head,body,storage,media,doc,win};
}
test('registry contains exactly seven complete locally bundled theme families',()=>{
  const {themes}=setup();
  assert.deepEqual(Object.keys(themes.registry),['bloom','resonance','companion','clay','glass','soft','ink']);
  for(const theme of Object.values(themes.registry)){
    assert.ok(theme.label&&theme.description);
    assert.match(theme.stylesheet,/^\/themes\/[a-z]+\.css$/);
  }
});
test('legacy palettes migrate with their correct appearance',()=>{
  const {themes}=setup();
  for(const [old,id,appearance] of [['cyber','glass','dark'],['oled','glass','dark'],['matrix','bloom','dark'],['nordic','soft','dark'],['light','clay','light']]){
    assert.deepEqual(JSON.parse(JSON.stringify(themes.migrate(old))),{id,appearance});
  }
});
test('unknown IDs cannot resolve inherited object names or stylesheet paths',()=>{
  const {themes}=setup();
  for(const id of ['constructor','__proto__','toString','../../private'])assert.equal(themes.migrate(id).id,'glass');
});
test('apply loads only the active family and stores preferences per device',()=>{
  const {themes,root,head,storage}=setup();
  themes.apply('bloom',{appearance:'dark',motion:'reduced',contrast:'increased'});
  themes.apply('ink',{appearance:'light'});
  const links=head.children.filter(n=>n.tagName==='LINK');
  assert.equal(links.length,2);
  assert.equal(links.filter(n=>n.id==='th-active-theme').length,1);
  assert.match(links.find(n=>n.id==='th-active-theme').href,/\/themes\/ink\.css\?v=test-build/);
  assert.equal(root.dataset.theme,'ink');
  assert.equal(root.dataset.appearance,'light');
  assert.equal(storage.get('touchhelm_theme'),'ink');
  assert.equal(storage.get('touchhelm_appearance'),'light');
});
test('nonpersistent previews do not overwrite saved preferences',()=>{
  const {themes,storage}=setup({touchhelm_theme:'soft',touchhelm_appearance:'dark'});
  themes.apply('companion',{appearance:'light'},false);
  assert.equal(storage.get('touchhelm_theme'),'soft');
  assert.equal(storage.get('touchhelm_appearance'),'dark');
});
test('system appearance and motion respond to changed accessibility preferences',()=>{
  const {themes,root,media}=setup();
  themes.apply('resonance',{appearance:'system',motion:'system',contrast:'system'},false);
  for(const query of ['(prefers-color-scheme: dark)','(prefers-reduced-motion: reduce)','(prefers-contrast: more)']){
    const item=media.get(query); item.matches=true; item.events.forEach(fn=>fn());
  }
  assert.equal(root.dataset.appearance,'dark');
  assert.equal(root.dataset.motion,'reduced');
  assert.equal(root.dataset.contrast,'increased');
});
test('motion pauses during interaction and while hidden without changing playback truth',()=>{
  const {themes,root,doc,win}=setup();
  themes.updateContext({connected:true,playing:true});
  themes.setInteractionActive(true);
  assert.equal(root.dataset.themePaused,'true');
  themes.setInteractionActive(false); assert.equal(root.dataset.themePaused,'false');
  doc.hidden=true; doc.events.visibilitychange.forEach(fn=>fn());
  assert.equal(root.dataset.themePaused,'true');
  doc.hidden=false;root.classes=['interaction-active'];win.mutate();
  assert.equal(root.dataset.themePaused,'true');
  assert.equal(root.dataset.playing,'true');
});
test('picker creates semantic choices and reports appearance settings safely',()=>{
  const {themes,body}=setup();const chosen=[];
  themes.mountPicker(body,(...args)=>chosen.push(args));
  const flatten=n=>[n,...n.children.flatMap(flatten)];
  const nodes=flatten(body),choices=nodes.filter(n=>n.dataset.themeId);
  assert.equal(choices.length,7);assert.ok(choices.every(n=>n.tagName==='BUTTON'));
  choices.find(n=>n.dataset.themeId==='clay').emit('click');
  assert.equal(chosen.at(-1)[0],'clay');
  const appearance=nodes.find(n=>n.id==='th-picker-appearance');
  assert.equal(appearance.tagName,'SELECT');appearance.value='dark';appearance.emit('change');
  assert.equal(chosen.at(-1)[1].appearance,'dark');
});
test('invalid stored settings normalize and blocked storage never prevents switching',()=>{
  const {themes,root}=setup({touchhelm_theme:'not-a-theme',touchhelm_appearance:'bad',touchhelm_motion:'bad'});
  assert.equal(themes.state.id,'glass');
  assert.equal(themes.apply('unknown',{},false).id,'glass');
  assert.ok(['light','dark'].includes(root.dataset.appearance));
  const blocked=setup({},true);
  assert.equal(blocked.themes.apply('bloom',{appearance:'light'}).id,'bloom');
});

test('a failed material stylesheet falls back to Ink without changing the saved choice',()=>{
  const {themes,root,head,storage}=setup();
  themes.apply('bloom',{appearance:'light'});
  head.children.find(n=>n.id==='th-active-theme').onerror();
  assert.equal(root.dataset.theme,'ink');
  assert.equal(storage.get('touchhelm_theme'),'bloom');
  assert.equal(head.children.filter(n=>n.id==='th-active-theme').length,1);
});

test('every material supplies readable light and dark text and primary controls',()=>{
  const {themes}=setup();
  const ratio=(a,b)=>{
    const luminance=hex=>{let digits=hex.slice(1);if(digits.length===3)digits=[...digits].map(n=>n+n).join('');const rgb=digits.match(/../g).map(n=>parseInt(n,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
    const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
  };
  const failures=[];
  for(const id of ['bloom','resonance','companion','clay','glass','soft','ink']){
    const css=fs.readFileSync(path.join(__dirname,`../web/themes/${id}.css`),'utf8');
    for(const appearance of ['light','dark']){
      const section=css.match(new RegExp(`\\[data-appearance="${appearance}"\\] \\{([^}]+)\\}`))[1];
      const tokens=Object.fromEntries([...section.matchAll(/--th-([\w-]+):\s*(#[a-fA-F0-9]{3,6})/g)].map(m=>[m[1],m[2]]));
      assert.equal(themes.registry[id].backgrounds?.[appearance],tokens.bg,`${id} browser theme-color palette`);
      for(const surface of ['bg','panel','surface']){
        if(ratio(tokens.text,tokens[surface])<4.5)failures.push(`${id} ${appearance} text/${surface}`);
        if(ratio(tokens.muted,tokens[surface])<4.5)failures.push(`${id} ${appearance} muted/${surface}`);
      }
      if(ratio(tokens['on-accent'],tokens.accent)<4.5)failures.push(`${id} ${appearance} primary text`);
      if(ratio(tokens.border,tokens.panel)<3)failures.push(`${id} ${appearance} graphical border`);
    }
  }
  assert.deepEqual(failures,[]);
});

// Optional bounded visual batch. The server is GET-only; preview=1 replaces the
// phone transport, and desktop HTML comes from its pure synthetic renderer.
if(process.argv.includes('--visual'))runVisualBatch().catch(error=>{console.error(error);process.exitCode=1;});
async function runVisualBatch(){
  const http=require('node:http');
  const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'D:/Mouse/node_modules/playwright');
  const root=path.resolve(__dirname,'..'),out=path.join(root,'assets/theme/review');
  const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png','.json':'application/json'};
  const server=http.createServer((req,res)=>{
    if(req.method!=='GET'){res.writeHead(405);return res.end();}
    const pathname=new URL(req.url,'http://127.0.0.1').pathname;
    let file;
    if(pathname==='/preview/desktop/'||pathname==='/preview/desktop/index.html')file=path.join(out,'desktop-fixture.html');
    else if(pathname.startsWith('/preview/desktop/')){const relative=pathname.slice('/preview/desktop/'.length);file=path.join(root,['desktop.css','desktop.js'].includes(relative)?'gui/web':'web',relative);}
    else file=path.join(root,'web',pathname==='/'?'index.html':pathname.slice(1));
    const allowed=[path.join(root,'web')+path.sep,path.join(root,'gui/web')+path.sep,path.join(out,'desktop-fixture.html')];
    if(!allowed.some(prefix=>file.startsWith(prefix))||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end();}
    let bytes=fs.readFileSync(file);
    if(['.html','.js','.css'].includes(path.extname(file)))bytes=Buffer.from(bytes.toString().replaceAll('__TOUCHHELM_BUILD__','theme-review'));
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(bytes);
  });
  let browser;
  try{
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const url=`http://127.0.0.1:${server.address().port}`;
    browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
    const context=await browser.newContext({serviceWorkers:'block'});
    const phone=await context.newPage(),desktop=await context.newPage(),board=await context.newPage();
    const errors=[],results=[];let screenshots=0;
    const capture=async(page,name)=>{await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});screenshots++;};
    for(const page of [phone,desktop,board]){
      page.on('pageerror',error=>errors.push(error.message));
      await page.route('**/*',route=>{const u=new URL(route.request().url());return u.hostname==='127.0.0.1'||['data:','blob:'].includes(u.protocol)?route.continue():route.abort();});
    }
    await phone.setViewportSize({width:390,height:844});await desktop.setViewportSize({width:1040,height:760});await board.setViewportSize({width:1480,height:1150});
    await phone.goto(url+'/index.html?preview=1');await desktop.goto(url+'/preview/desktop/?preview=1');
    await phone.waitForFunction(()=>window.touchhelm?.isConnected&&window.TouchHelmDemo&&window.TouchHelmThemes);
    await desktop.waitForFunction(()=>window.TouchHelmDesktopPreview&&document.getElementById('pairingQR').src.startsWith('data:'));
    const defaults={bloom:'light',resonance:'dark',companion:'light',clay:'light',glass:'dark',soft:'light',ink:'light'};
    for(const [theme,appearance]of Object.entries(defaults)){
      for(const page of [phone,desktop])await page.evaluate(async({theme,appearance})=>{window.TouchHelmThemes.apply(theme,{appearance,motion:'reduced',contrast:'standard'},false);await window.TouchHelmThemes.ready;await document.fonts.ready;},{theme,appearance});
      for(const tab of ['Trackpad','Presenter','Media','Keyboard','Apps']){
        await phone.evaluate(tab=>{window.TouchHelmDemo.setState('ready');document.getElementById('tab'+tab).click();},tab);await phone.waitForTimeout(100);
        const details=await phone.evaluate(()=>{
          const active=document.querySelector('.view.active');
          const buttons=[...active.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width&&getComputedStyle(b).display!=='none');
          return {theme:document.documentElement.dataset.theme,view:active.id,overflow:document.documentElement.scrollWidth>innerWidth,
            small:buttons.filter(b=>{const r=b.getBoundingClientRect();return r.width<43.9||r.height<43.9;}).map(b=>({id:b.id,text:b.textContent.trim().slice(0,35),w:b.getBoundingClientRect().width,h:b.getBoundingClientRect().height}))};
        });results.push({theme,appearance,tab,...details});await capture(phone,`${theme}-${tab.toLowerCase()}`);
      }
      for(const panel of ['pairing','devices','settings','diagnostics']){
        await desktop.locator(`.desktop-nav button[data-panel="${panel}"]`).click();await capture(desktop,`${theme}-desktop-${panel}`);
        results.push({theme,panel,desktop:true,overflow:await desktop.evaluate(()=>document.documentElement.scrollWidth>innerWidth),qr:panel==='pairing'?await desktop.locator('#pairingQR').evaluate(n=>n.naturalWidth>0):undefined});
      }
      const opposite=appearance==='light'?'dark':'light';
      await phone.evaluate(async({theme,appearance})=>{window.TouchHelmThemes.apply(theme,{appearance,motion:'reduced',contrast:'standard'},false);await window.TouchHelmThemes.ready;document.getElementById('tabTrackpad').click();},{theme,appearance:opposite});
      await capture(phone,`${theme}-opposite`);
    }
    for(const theme of ['ink','bloom']){
      await phone.setViewportSize({width:350,height:640});await phone.evaluate(async theme=>{window.TouchHelmThemes.apply(theme,{appearance:'light',motion:'reduced',contrast:'increased'},false);await window.TouchHelmThemes.ready;document.getElementById('tabTrackpad').click();},theme);
      await capture(phone,`${theme}-350-contrast`);results.push({theme,viewport:'350',overflow:await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
    }
    await board.goto(url+'/preview.html');await board.waitForFunction(()=>document.getElementById('previewStatus').textContent.includes('Both local'));await board.waitForTimeout(100);await capture(board,'preview-board');
    fs.writeFileSync(path.join(out,'findings.json'),JSON.stringify({errors,results},null,2));
    console.log(JSON.stringify({screenshots,errors,issues:results.filter(r=>r.overflow||r.small?.length||r.qr===false)},null,2));
  }finally{
    await browser?.close();await new Promise(resolve=>server.close(resolve));
  }
}
