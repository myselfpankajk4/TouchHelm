/* Isolated desktop browser-link regressions. No native app, tunnel or PC input.
 * Run: node --test tests/desktop_browser_link.test.cjs
 */
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');let server,browser,origin;
const qr='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="224" height="224"><rect width="224" height="224" fill="white"/><path d="M24 24h56v56H24zm120 0h56v56h-56zM24 144h56v56H24zm80-40h24v24h-24zm40 40h56v56h-56z" fill="black"/></svg>');
before(async()=>{
 server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname;const file=name==='/'?'index.html':name.slice(1);const desktop=['index.html','desktop.js','desktop.css','aircontrol.js','aircontrol.css','aircontrol-view.js'];const folder=desktop.includes(file)?path.join(root,'gui/web'):path.join(root,'web');const target=path.resolve(folder,file);if(!target.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}try{const raw=fs.readFileSync(target);const ext=path.extname(target);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'})[ext]||'application/octet-stream');res.end(['.html','.js','.css','.svg'].includes(ext)?raw.toString().replaceAll('__DESKTOP_TOKEN__','synthetic-desktop-token').replaceAll('__DESKTOP_ASSET_BASE__','/'):raw);}catch{res.writeHead(404);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 const executablePath=process.env.CHROMIUM_EXECUTABLE||(fs.existsSync(chromium.executablePath())?chromium.executablePath():'C:/Program Files/Google/Chrome/Application/chrome.exe');browser=await chromium.launch({executablePath,headless:true});
});
after(async()=>{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));});
async function fixture(options={}){
 const context=await browser.newContext({viewport:{width:1040,height:760},permissions:['clipboard-read','clipboard-write']});const page=await context.newPage();page.setDefaultTimeout(2500);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(({options,qr})=>{
  window.__calls=[];window.__failRead=false;window.__held=!!options.hold;window.__releaseInitial=()=>{window.__held=false;window.__resume?.();};
  window.__hostState={config:{mouse_sensitivity:1.3,mouse_acceleration:1.25,scroll_speed:1,invert_scroll:false,require_pin:true,remote_enabled:false,laser_color:'blue'},pin_code:'2468',devices:[],activity:[],pairing:{http_url:'http://192.0.2.10:8765/',qr_http:qr,secure_ready:false,browser_link:{state:'stopped',ready:false,origin:null,pairing_url:null,message:'Start a browser link when you are ready.',expires_in:0}},preferences:{theme:'glass',appearance:'dark',effects:'off',...(options.mode?{connection_mode:options.mode}:{})},diagnostics:{engine:'Synthetic WebView2 fixture',build:'test-build'}};
  window.pywebview={api:new Proxy({}, {get:(_,method)=>async(token,...args)=>{
   window.__calls.push({method,args});if(method==='get_state'){if(window.__held)await new Promise(resolve=>window.__resume=resolve);if(window.__failRead)throw Error('Synthetic host unavailable');return structuredClone(window.__hostState);}
   if(method==='save_settings'){window.__hostState.config={...window.__hostState.config,...args[0]};return {success:true,config:structuredClone(window.__hostState.config),pin_code:window.__hostState.pin_code};}
   if(method==='request_browser_link'){const active=args[0];window.__hostState.pairing.browser_link={state:active?'preparing':'stopped',ready:false,pairing_url:null,origin:null,message:active?'Preparing your browser link…':'Browser link stopped.',expires_in:0};return {success:true,pairing:structuredClone(window.__hostState.pairing),browser_link:structuredClone(window.__hostState.pairing.browser_link)};}
   if(method==='rotate_browser_link'){window.__hostState.pairing.browser_link.pairing_url='https://example.invalid/#browser-link=NEW-SYNTHETIC-TOKEN';window.__hostState.pairing.browser_link_url=window.__hostState.pairing.browser_link.pairing_url;return {success:true,pairing:structuredClone(window.__hostState.pairing)};}
   if(method==='generate_password'){window.__hostState.pin_code='1357';window.__hostState.config.require_pin=true;return {success:true,password:'1357',config:structuredClone(window.__hostState.config)};}
   return {success:true};
  }})};
 },{options,qr});
 await page.goto(origin,{waitUntil:'networkidle'});await page.waitForFunction(()=>window.TouchHelmDesktop);await page.evaluate(()=>TouchHelmDesktop.showPanel('pairing'));if(!options.hold)await page.waitForFunction(()=>TouchHelmDesktop.state?.config);
 return {page,context,errors,close:async()=>{assert.deepEqual(errors,[]);await context.close();}};
}
async function refresh(page){await page.evaluate(()=>TouchHelmDesktop.refresh());}
async function ready(page){await page.evaluate(qr=>{const p=window.__hostState.pairing;p.browser_link={state:'ready',ready:true,origin:'https://example.invalid',pairing_url:'https://example.invalid/#browser-link=SYNTHETIC-TOKEN',message:'Scan the QR, then enter your PIN.',expires_in:1799};p.browser_link_url=p.browser_link.pairing_url;p.qr_browser_link=qr;},qr);await refresh(page);}

test('capture synthetic desktop pairing states when requested',async t=>{
 if(!process.env.TOUCHHELM_CAPTURE_DIR){t.skip('Optional visual evidence');return;}
 fs.mkdirSync(process.env.TOUCHHELM_CAPTURE_DIR,{recursive:true});const f=await fixture();try{
 await f.page.screenshot({path:path.join(process.env.TOUCHHELM_CAPTURE_DIR,'pairing-stopped.png')});await ready(f.page);
 await f.page.screenshot({path:path.join(process.env.TOUCHHELM_CAPTURE_DIR,'pairing-ready.png')});await f.page.setViewportSize({width:820,height:620});
 await f.page.screenshot({path:path.join(process.env.TOUCHHELM_CAPTURE_DIR,'pairing-minimum.png')});
 await f.page.setViewportSize({width:410,height:620});await f.page.screenshot({path:path.join(process.env.TOUCHHELM_CAPTURE_DIR,'pairing-reflow.png')});
 }finally{await f.close();}
});

test('fresh profiles offer browser-only HTTPS without automatically starting it; saved HTTP stays selected',async()=>{
 const f=await fixture();try{assert.equal(await f.page.locator('#connectionMode').inputValue(),'browser_link');assert.equal(await f.page.locator('#browserLinkStart').isVisible(),true);assert.equal(await f.page.evaluate(()=>__calls.some(c=>c.method==='request_browser_link')),false);assert.match(await f.page.locator('#browserLinkNotice').innerText(),/Cloudflare/);}finally{await f.close();}
 const saved=await fixture({mode:'http'});try{assert.equal(await saved.page.locator('#connectionMode').inputValue(),'http');}finally{await saved.close();}
});
test('browser link start is explicit, busy state prevents duplicates, ready QR keeps the one-use fragment, and Stop is explicit',async()=>{
 const f=await fixture();try{await f.page.locator('#browserLinkStart').click();assert.equal(await f.page.locator('#browserLinkStart').isDisabled(),true);assert.deepEqual(await f.page.evaluate(()=>__calls.filter(c=>c.method==='request_browser_link').map(c=>c.args)),[[true]]);await ready(f.page);assert.match(await f.page.locator('#phoneURL').inputValue(),/#browser-link=SYNTHETIC-TOKEN$/);assert.equal(await f.page.locator('#pairingQR').isVisible(),true);assert.match(await f.page.locator('#browserLinkExpiry').innerText(),/29:59/);await f.page.locator('#browserLinkRotate').click();assert.match(await f.page.locator('#phoneURL').inputValue(),/NEW-SYNTHETIC-TOKEN/);await f.page.locator('#browserLinkStop').click();assert.equal(await f.page.locator('#pairingQR').isVisible(),false);assert.equal(await f.page.evaluate(()=>__calls.filter(c=>c.method==='save_settings').length),0);}finally{await f.close();}
});
test('loading and failed host reads hide stale pairing data, disable actions and expose a working Retry',async()=>{
 const f=await fixture({hold:true});try{assert.equal(await f.page.locator('#connectionMode').isDisabled(),true);assert.equal(await f.page.locator('#copyURL').isDisabled(),true);await f.page.evaluate(()=>__releaseInitial());await f.page.waitForFunction(()=>TouchHelmDesktop.state?.config);await ready(f.page);await f.page.evaluate(()=>__failRead=true);await refresh(f.page);assert.equal(await f.page.locator('#pairingQR').isVisible(),false);assert.equal(await f.page.locator('#phoneURL').inputValue(),'');assert.equal(await f.page.locator('#copyURL').isDisabled(),true);assert.match(await f.page.locator('#deviceStatus').innerText(),/unavailable/i);await f.page.evaluate(()=>__failRead=false);await f.page.locator('#retryDesktop').click();await f.page.waitForFunction(()=>!document.getElementById('copyURL').disabled);}finally{await f.close();}
});
test('copy feedback stays beside the address and browser-link errors remain visible without a fake ready URL',async()=>{
 const f=await fixture();try{await ready(f.page);await f.page.locator('#copyURL').click();await f.page.waitForFunction(()=>document.getElementById('copyStatus').textContent.includes('copied'));assert.match(await f.page.locator('#copyStatus').innerText(),/copied/i);assert.equal(await f.page.locator('#feedback').isVisible(),false);await f.page.evaluate(()=>{__hostState.pairing.browser_link={state:'error',ready:false,pairing_url:null,origin:null,message:'Connection failed. Try again.',expires_in:0};});await refresh(f.page);assert.equal(await f.page.locator('#phoneURL').inputValue(),'');assert.equal(await f.page.locator('#browserLinkStart').isEnabled(),true);assert.match(await f.page.locator('#browserLinkStatus').innerText(),/failed/i);}finally{await f.close();}
});
test('screen/audio access requires a separate explicit action using the existing partial settings save',async()=>{
 const f=await fixture();try{await ready(f.page);await f.page.locator('#pairingRemoteHelp summary').click();assert.equal(await f.page.locator('#enablePairingRemote').isVisible(),true);assert.equal(await f.page.evaluate(()=>__calls.some(c=>c.method==='save_settings')),false);await f.page.locator('#enablePairingRemote').click();assert.deepEqual(await f.page.evaluate(()=>__calls.filter(c=>c.method==='save_settings').map(c=>c.args)),[[{remote_enabled:true}]]);assert.match(await f.page.locator('#pairingRemoteStatus').innerText(),/enabled/i);}finally{await f.close();}
});
test('dirty settings expose a sticky save bar, keep drafts across polling, and clarify immediate PIN generation',async()=>{
 const f=await fixture();try{await f.page.evaluate(()=>TouchHelmDesktop.showPanel('settings'));await f.page.locator('#sensitivity').fill('2.5');assert.equal(await f.page.locator('#settingsSaveBar').getAttribute('data-dirty'),'true');assert.match(await f.page.locator('#generatePassword').innerText(),/save/i);await refresh(f.page);assert.equal(await f.page.locator('#sensitivity').inputValue(),'2.5');await f.page.locator('#saveSettings').click();assert.equal(await f.page.locator('#settingsSaveBar').getAttribute('data-dirty'),'false');}finally{await f.close();}
});
test('unchanged diagnostics keep their nodes and empty devices offer pairing rather than a loading claim',async()=>{
 const f=await fixture();try{await f.page.evaluate(()=>{window.__diagnosticNode=document.querySelector('#diagnostics dd');});await refresh(f.page);assert.equal(await f.page.evaluate(()=>__diagnosticNode===document.querySelector('#diagnostics dd')),true);await f.page.evaluate(()=>TouchHelmDesktop.showPanel('devices'));assert.match(await f.page.locator('#deviceStatus').innerText(),/No phone/i);await f.page.locator('#pairEmptyDevices').click();assert.equal(await f.page.locator('[data-page=pairing]').isVisible(),true);}finally{await f.close();}
});
test('ready browser pairing preserves targets and reflows at minimum, reference and 200 percent equivalent widths',async()=>{
 const f=await fixture();try{await ready(f.page);for(const size of [{width:820,height:620},{width:1040,height:760},{width:410,height:620}]){await f.page.setViewportSize(size);const issues=await f.page.evaluate(()=>{const r=[];if(document.documentElement.scrollWidth>innerWidth+1)r.push('page overflow');for(const n of document.querySelectorAll('[data-page=pairing] button,[data-page=pairing] select')){if(!n.checkVisibility())continue;const b=n.getBoundingClientRect();if(b.width<43.5||b.height<43.5)r.push('small '+n.id);if(b.left<0||b.right>innerWidth+1)r.push('clipped '+n.id);}return r;});assert.deepEqual(issues,[],JSON.stringify(size));if(size.width>=820)for(const id of ['pairingQR','phoneURL','pinCode']){const b=await f.page.locator('#'+id).boundingBox();assert.ok(b&&b.y>=0&&b.y+b.height<=size.height,id+' above fold');}}}finally{await f.close();}
});

