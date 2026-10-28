const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const web=file=>path.join(__dirname,'../web',file);
const loadScenes=()=>{const sandbox={};sandbox.globalThis=sandbox;vm.runInNewContext(fs.readFileSync(web('theme-scenes.js'),'utf8'),sandbox);return sandbox.TouchHelmScenes;};
const IDS=['aurora','bloom','resonance','constellation'];

test('four generative scenes ship with light and dark fallback palettes',()=>{
  const scenes=loadScenes();
  assert.deepEqual([...scenes.ids],IDS);
  for(const id of IDS)for(const appearance of ['light','dark']){
    const palette=scenes.scenes[id].defaults[appearance];
    for(const key of ['bg','a','b','c'])assert.match(palette[key],/^#[0-9a-f]{6}$/i,`${id} ${appearance} ${key}`);
  }
});

test('scene fallback backgrounds match the theme stylesheets so the first frame never flashes',()=>{
  const scenes=loadScenes();
  for(const id of IDS){
    const css=fs.readFileSync(web(`themes/${id}.css`),'utf8');
    for(const appearance of ['light','dark']){
      const block=css.match(new RegExp(`\\[data-appearance="${appearance}"\\] \\{([^}]+)\\}`))[1];
      assert.equal(block.match(/--th-bg:\s*(#[0-9a-f]{6})/i)[1].toLowerCase(),scenes.scenes[id].defaults[appearance].bg.toLowerCase(),`${id} ${appearance}`);
      for(const key of ['a','b','c'])assert.match(block,new RegExp(`--th-gl-${key}:\\s*#[0-9a-f]{6}`,'i'),`${id} ${appearance} --th-gl-${key}`);
    }
  }
});

test('fragment sources are complete, sized to the device uniform budget and reject unknown scenes',()=>{
  const scenes=loadScenes();
  assert.deepEqual([4,31,32,63,64,256].map(scenes.stampCount),[4,4,8,8,12,12]);
  for(const id of IDS)for(const stamps of [4,8,12]){
    const source=scenes.fragmentSource(id,stamps);
    assert.ok(source.includes(`#define N ${stamps}`),`${id} stamp count`);
    assert.ok(!source.includes('__N__'));
    assert.match(source,/void main\s*\(/);
    assert.equal(source.split('{').length,source.split('}').length,`${id} balanced braces`);
  }
  assert.equal(scenes.fragmentSource('nope',4),null);
  assert.equal(scenes.fragmentSource('__proto__',4),null);
});

test('themes.js and the GL engine agree on which themes have a generative scene',()=>{
  const scenes=loadScenes(),themes=fs.readFileSync(web('themes.js'),'utf8');
  for(const id of scenes.ids)assert.ok(themes.includes(`${id}:`)||themes.includes(`'${id}'`),`${id} registered`);
});

test('the engine never reads typed text or touches the network',()=>{
  const engine=fs.readFileSync(web('theme-gl.js'),'utf8');
  assert.equal(/fetch\(|XMLHttpRequest|WebSocket|sendBeacon/.test(engine),false,'decoration must never touch the network');
  assert.equal(/\.value\b/.test(engine),false,'inputs and textareas are never read');
});

test('browser: every scene compiles, reacts, pauses and tears down cleanly',{skip:process.env.RUN_EFFECTS_DOM!=='1'},async()=>{
  const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'D:/Mouse/node_modules/playwright');
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
    await page.setContent('<html data-theme="aurora" data-appearance="dark" data-effects="rich" data-motion="full"><body><div class="touch-surface" style="position:absolute;left:15px;top:40px;width:360px;height:400px"></div><button class="native-key" style="position:absolute;left:30px;top:470px;width:90px;height:48px">Ctrl</button><textarea style="position:absolute;left:20px;top:550px">Private draft 9f7e</textarea></body></html>');
    await page.addStyleTag({path:web('themes.css')});await page.addStyleTag({path:web('theme-gl.css')});
    for(const id of IDS)await page.addStyleTag({content:fs.readFileSync(web(`themes/${id}.css`),'utf8').replace(/\[data-appearance/g,`[data-theme="${id}"][data-appearance`)});
    await page.addScriptTag({path:web('theme-scenes.js')});await page.addScriptTag({path:web('theme-gl.js')});
    await page.waitForFunction(()=>window.TouchHelmEffects&&document.documentElement.dataset.gl);
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.gl),'on','WebGL must be available for this check');
    for(const id of IDS)for(const appearance of ['dark','light']){
      await page.evaluate(({id,appearance})=>{const r=document.documentElement;r.dataset.theme=id;r.dataset.appearance=appearance;TouchHelmEffects.synchronize();},{id,appearance});
      await page.waitForFunction(id=>TouchHelmEffects.diagnostics.scene===id,id);
      assert.equal(await page.evaluate(()=>TouchHelmEffects.react(document.querySelector('button'),{kind:'key'})),true,`${id} ${appearance} reacts`);
      await page.waitForTimeout(120);
      assert.equal(await page.evaluate(()=>document.documentElement.dataset.gl),'on',`${id} ${appearance} keeps rendering`);
    }
    const text=await page.evaluate(()=>{document.querySelector('textarea').dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'x'}));return document.getElementById('th-gl').textContent;});
    assert.equal(text,'');
    await page.evaluate(()=>{document.documentElement.dataset.effects='off';TouchHelmEffects.synchronize();});
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.gl),'off');
    assert.equal(await page.evaluate(()=>TouchHelmEffects.diagnostics.scheduled),false);
    await page.evaluate(()=>{document.documentElement.dataset.effects='rich';document.documentElement.dataset.motion='reduced';TouchHelmEffects.synchronize();});
    assert.equal(await page.evaluate(()=>TouchHelmEffects.diagnostics.frozen),true,'reduced motion renders one frozen frame');
    await page.evaluate(()=>TouchHelmEffects.destroy());
    assert.equal(await page.locator('#th-gl').count(),0);
    assert.deepEqual(errors,[]);
  }finally{await browser.close();}
});
