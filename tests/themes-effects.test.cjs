const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const file=path.join(__dirname,'../web/theme-effects.js');
const runtime=()=>{assert.ok(fs.existsSync(file),'Shared living effects runtime must exist');return require(file);};
test('actor budget recycles six touch slots and permits only two idle actors',()=>{
  const {createDirector}=runtime();const d=createDirector();
  const idle=[d.acquire('idle',0),d.acquire('idle',0),d.acquire('idle',0)];
  assert.ok(idle[0]);assert.ok(idle[1]);assert.equal(idle[2],null);
  const touches=Array.from({length:100},(_,i)=>d.acquire('touch',i));
  assert.equal(d.snapshot().touch,6);assert.equal(d.snapshot().idle,2);
  assert.equal(new Set(touches.map(s=>s.id)).size,6);
  d.expire(10000);assert.equal(d.snapshot().touch,0);assert.equal(d.snapshot().idle,0);
});
test('interaction and scrolling suppress idle while local touch feedback remains available',()=>{
  const {createDirector}=runtime();const d=createDirector();d.acquire('idle',0);
  d.configure({active:true},50);assert.equal(d.snapshot().idle,0);assert.equal(d.acquire('idle',100),null);
  assert.ok(d.acquire('touch',100));d.configure({active:false},150);
  assert.equal(d.acquire('idle',900),null);assert.ok(d.acquire('idle',1400));
});
test('off and hidden clear actors; reduced motion has no idle spatial scene',()=>{
  const {createDirector}=runtime();const d=createDirector();d.acquire('touch',0);
  d.configure({hidden:true},10);assert.equal(d.snapshot().touch,0);assert.equal(d.acquire('touch',20),null);
  d.configure({hidden:false,reduced:true},30);assert.equal(d.acquire('idle',2000),null);
  assert.ok(d.acquire('touch',2000));assert.equal(d.snapshot().mode,'calm');
  d.configure({mode:'off'},2001);assert.equal(d.acquire('touch',2002),null);assert.equal(d.snapshot().touch,0);
});
test('frame admission caps continuous pointer work at thirty updates per second',()=>{
  const {createDirector}=runtime();const d=createDirector();let frames=0;
  for(let time=0;time<1000;time++)if(d.frame(time))frames++;
  assert.ok(frames<=30);assert.ok(frames>=28);
});

test('browser DOM lifecycle keeps effects inert, bounded, private and cancellable',{skip:process.env.RUN_EFFECTS_DOM!=='1'},async()=>{
  const {chromium}=require('D:/Mouse/node_modules/playwright');
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setContent('<html data-theme="bloom" data-effects="rich" data-motion="full"><body><div class="touch-surface" style="position:absolute;left:15px;top:40px;width:360px;height:400px"></div><button class="native-key" style="position:absolute;left:30px;top:470px;width:90px;height:48px">Ctrl</button><textarea style="position:absolute;left:20px;top:550px">Private draft 9f7e</textarea><div data-effects-protect style="position:absolute;left:250px;top:470px;width:90px;height:90px">QR</div></body></html>');
    await page.addStyleTag({path:path.join(__dirname,'../web/theme-effects.css')});
    await page.addScriptTag({path:file});
    await page.waitForFunction(()=>window.TouchHelmEffects.diagnostics.idle>0);
    const first=await page.evaluate(()=>({d:TouchHelmEffects.diagnostics,aria:document.querySelector('.th-effects-stage').getAttribute('aria-hidden'),events:getComputedStyle(document.querySelector('.th-effects-stage')).pointerEvents}));
    assert.ok(first.d.idle<=2);assert.equal(first.aria,'true');assert.equal(first.events,'none');
    await page.evaluate(()=>{const button=document.querySelector('button');for(let i=0;i<100;i++)TouchHelmEffects.react(button,{kind:'key'});});
    assert.equal(await page.locator('.th-effect:not([hidden])[data-kind="touch"]').count(),6);
    assert.equal(await page.locator('.th-effect').count(),8);
    const input=await page.evaluate(()=>{let calls=0;document.addEventListener('pointerdown',()=>calls++);const b=document.querySelector('button'),event=new PointerEvent('pointerdown',{bubbles:true,pointerId:4,cancelable:true});b.dispatchEvent(event);document.querySelector('textarea').dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'x'}));return {calls,prevented:event.defaultPrevented,d:TouchHelmEffects.diagnostics,text:document.querySelector('.th-effects-stage').textContent};});
    assert.equal(input.calls,1);assert.equal(input.prevented,false);assert.equal(input.d.idle,0);assert.equal(input.d.touch,6);assert.equal(input.text,'');
    await page.evaluate(()=>{document.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:4}));document.documentElement.dataset.effects='off';TouchHelmEffects.synchronize();});
    assert.equal(await page.locator('.th-effect:not([hidden])').count(),0);
    assert.equal(await page.evaluate(()=>TouchHelmEffects.diagnostics.scheduled),false);
    for(const theme of ['bloom','companion','resonance','clay']){
      await page.evaluate(theme=>{const r=document.documentElement;r.dataset.theme=theme;r.dataset.effects='rich';TouchHelmEffects.synchronize();TouchHelmEffects.react(document.querySelector('button'),{kind:'key'});},theme);
      assert.equal(await page.locator(`.th-effect-${theme}:not([hidden]) svg`).count(),1);
    }
    await page.evaluate(()=>{document.documentElement.dataset.motion='reduced';TouchHelmEffects.synchronize();});
    assert.equal(await page.evaluate(()=>TouchHelmEffects.diagnostics.mode),'calm');
    assert.equal(await page.locator('.th-effect:not([hidden])[data-kind="idle"]').count(),0);
    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
    assert.equal(await page.locator('.th-effect:not([hidden])').count(),0);assert.equal(await page.evaluate(()=>TouchHelmEffects.diagnostics.scheduled),false);
    await page.evaluate(()=>TouchHelmEffects.destroy());assert.equal(await page.locator('.th-effects-stage').count(),0);
    assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
});
