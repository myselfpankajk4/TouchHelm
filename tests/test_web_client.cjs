/* Browser regressions with only network boundaries mocked. No real PC input.
 * Run: node tests/test_web_client.cjs
 * PLAYWRIGHT_MODULE / CHROMIUM_EXECUTABLE can select an existing installation.
 */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const artifactDir = path.join(__dirname, 'artifacts');
const captureScreenshots = process.argv.includes('--visual');
const behaviorOnly = process.argv.includes('--behavior-only');
const nameFilter = process.argv.find(arg => arg.startsWith('--filter='))?.slice('--filter='.length);
const serverConfig = {
  theme: 'nordic', mouse_sensitivity: 2.1, mouse_acceleration: 1.6,
  scroll_speed: 1.8, invert_scroll: true, laser_color: 'blue',
  volume: 37, muted: false, brightness: 62, auth_required: false,
};
const posts = [];
const desktopState = {presentation: {available:true,active:true,app:'PowerPoint',title:'Quarterly review',slide:3,total:12,slide_title:'Results'},
  media:{available:true,app:'Music',title:'Morning light',artist:'Test artist',status:'Playing',position:65,duration:240,
    sessions:[{id:'player-one',available:true,app:'Music',title:'Morning light',artist:'Test artist',status:'Playing',position:65,duration:240},
      {id:'player-two',available:true,app:'Video',title:'Design talk',status:'Paused',position:12,duration:600}]}};
const catalog = {sessions:desktopState.media.sessions,items:[{id:'track-one',title:'Morning light',kind:'queue'}],playlist_supported:true,playlist_message:'Selectable player queue'};
const apps = [{id:'app-editor',name:'Code Editor',running:true,launches:8},{id:'app-music',name:'Music',running:false,launches:3},{id:'app-notes',name:'Notes',running:false,launches:0}];
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.webp':'image/webp', '.png':'image/png' };
const server = http.createServer((req, res) => {
  const name = new URL(req.url, 'http://127.0.0.1').pathname;
  if (name === '/api/info') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    return res.end(JSON.stringify(serverConfig));
  }
  if (name === '/api/version') { res.writeHead(200, {'Content-Type':'application/json','Cache-Control':'no-store'}); return res.end(JSON.stringify({build:'test-build'})); }
  if (name === '/api/config') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      posts.push(JSON.parse(body || '{}'));
      res.writeHead(200, {'Content-Type': 'application/json'});
      res.end('{}');
    });
    return;
  }
  let relative = `web${name === '/' ? '/index.html' : name}`;
  if(name.startsWith('/preview/desktop/')){
    const file=name.slice('/preview/desktop/'.length)||'index.html';
    relative=['index.html','desktop.js','desktop.css','aircontrol.js','aircontrol.css'].includes(file)?`gui/web/${file}`:`web/${file}`;
  }
  const filename = path.resolve(root, relative);
  if (![path.join(root,'web'),path.join(root,'gui','web')].some(folder=>filename.startsWith(folder+path.sep))) {
    res.writeHead(403); return res.end();
  }
  try {
    const raw = fs.readFileSync(filename);
    const body = ['.html','.js','.css','.json','.svg'].includes(path.extname(filename)) ? raw.toString('utf8').replaceAll('__TOUCHHELM_BUILD__', 'test-build').replaceAll('__DESKTOP_TOKEN__','preview-disabled').replaceAll('__DESKTOP_ASSET_BASE__','/preview/desktop/') : raw;
    res.writeHead(200, {'Content-Type': types[path.extname(filename)] || 'application/octet-stream'});
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
});

// The socket double exposes controllable transport events and records wire packets.
function installSocketDouble({config,state,catalog,apps}) {
  window.__sockets = [];
  window.__packets = [];
  class Socket {
    static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
    constructor(url) {
      this.url = url; this.readyState = Socket.CONNECTING;
      window.__sockets.push(this);
      queueMicrotask(() => {
        if (window.__offline) { this.readyState = Socket.CLOSED; return; }
        this.readyState = Socket.OPEN;
        this.onopen?.({target: this});
      });
    }
    send(raw) {
      if (this.readyState !== Socket.OPEN) throw new Error('Socket is closed');
      const packet = JSON.parse(raw);
      window.__packets.push(packet);
      if (packet.type === 'auth') queueMicrotask(() => {
        const success = !window.__expectedPin || packet.pin === window.__expectedPin;
        this.onmessage?.({data: JSON.stringify(success
          ? {type: 'auth_res', success: true, config, ...config}
          : {type: 'auth_res', success: false, message: 'Invalid PIN'})});
      });
      const responses = {get_desktop_state:{type:'desktop_state',...(window.__stateOverride||state)},get_apps:{type:'apps_sync',apps:window.__appsOverride||apps},get_media_library:{type:'media_library',...catalog}};
      if (responses[packet.type]) queueMicrotask(() => this.onmessage?.({data:JSON.stringify(responses[packet.type])}));
      if (['launch_app','play_media','presentation','media'].includes(packet.type)) queueMicrotask(() => this.onmessage?.({data:JSON.stringify({type:'command_result',command:packet.type,success:true,message:'Done'})}));
    }
    close() { this.readyState = Socket.CLOSED; }
  }
  window.WebSocket = Socket;
}

let browser, origin;
async function fixture(viewport = {width: 390, height: 844}) {
  const context = await browser.newContext({viewport, hasTouch: true, serviceWorkers: 'block'});
  await context.addInitScript(installSocketDouble, {config:serverConfig,state:desktopState,catalog,apps});
  const page = await context.newPage();
  page.setDefaultTimeout(3000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin, {waitUntil: 'networkidle'});
  assert.deepEqual(errors, [], 'client loads without uncaught browser errors');
  await page.waitForFunction(() => window.touchhelm && window.__sockets.length);
  await page.evaluate(() => window.__packets.length = 0);
  return {page, context, errors};
}
async function typingView(page) {
  const view = await page.locator('#typeInput').evaluate(el => el.closest('.view').id);
  await page.locator(`.nav-tab[data-view="${view}"]`).click();
  await page.locator('#typeInput').focus();
  await page.locator('#chkRealtimeTyping').check();
  await page.evaluate(() => window.__packets.length = 0);
}

const tests = [];
test('v2 Return writes a local newline and Ctrl Enter explicitly sends a buffered draft', async page => {
  await typingView(page);
  await page.locator('#chkRealtimeTyping').uncheck();
  await page.locator('#typeInput').fill('first');
  await page.locator('#typeInput').press('Enter');
  await page.locator('#typeInput').press('a');
  assert.equal(await page.locator('#typeInput').inputValue(), 'first\na');
  assert.deepEqual(await packets(page), []);
  await page.locator('#typeInput').press('Control+Enter');
  assert.deepEqual(await packets(page), [{type:'text',text:'first\na',newline_mode:'shift_enter'}]);
});

test('v2 first pad contact dismisses the composer and preserves its draft without PC input', async page => {
  await typingView(page);
  await page.locator('#chkRealtimeTyping').uncheck();
  await page.locator('#typeInput').fill('unsent\nsecond line');
  await page.evaluate(() => window.__packets.length=0);
  const box=await page.locator('#touchSurface').boundingBox();
  await page.touchscreen.tap(box.x+30,box.y+30);
  assert.equal(await page.locator('#typingDock').evaluate(el=>el.classList.contains('expanded')),false);
  assert.equal(await page.locator('#typeInput').inputValue(),'unsent\nsecond line');
  assert.deepEqual(await page.evaluate(()=>window.__packets.filter(p=>['move','click','double_click','mousedown','scroll'].includes(p.type))),[]);
});

test('v2 Presenter prioritizes the laser above secondary controls and timer', async page => {
  await page.locator('#tabPresenter').click();
  const laser=await page.locator('#laserSurface').boundingBox();
  const tools=await page.locator('.slide-tools-row').boundingBox();
  const timer=await page.locator('.timer-details').boundingBox();
  assert.ok(laser.y<tools.y && laser.y<timer.y);
  assert.ok(laser.height>=280);
});

test('v2 media action follows real state and hides unsupported queues', async page => {
  await page.locator('#tabMedia').click();
  await page.evaluate(()=>window.touchhelm.controls.renderDesktopState({media:{available:true,status:'Playing',title:'Track',capabilities:{pause:true,play:true}}}));
  assert.match(await page.locator('#btnMediaPlay').innerText(),/Pause/);
  await page.evaluate(()=>window.touchhelm.controls.renderDesktopState({media:{available:true,status:'Paused',title:'Track',capabilities:{pause:true,play:true}}}));
  assert.match(await page.locator('#btnMediaPlay').innerText(),/^Play$/);
  await page.evaluate(()=>window.touchhelm.controls.renderMediaLibrary({playlist_supported:false,items:[{id:'local:x',title:'Not a queue',kind:'local'}],sessions:[]}));
  assert.equal(await page.locator('#mediaQueueSection').isVisible(),false);
});
test('v2 media seek clamps to provider bounds and renders supplied supplementary metadata', async page => {
  await page.locator('#tabMedia').click();
  await page.evaluate(()=>{window.touchhelm.controls.renderDesktopState({media:{available:true,session_id:'player-one',status:'Paused',title:'Track',position:14,duration:180,min_seek:10,max_seek:150,playback_rate:1,genre:['Jazz'],track:2,album_tracks:9,capabilities:{seek:true,play:true}}});window.__packets.length=0;});
  assert.match(await page.locator('#mediaDetails').textContent(),/Jazz.*Track 2 of 9/);
  await page.locator('#btnSeekBack').click();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='media'&&p.action==='seek'&&p.value===10)));
  await page.waitForFunction(()=>!window.touchhelm.experience.pending);
  await page.evaluate(()=>{window.touchhelm.experience.renderMedia({available:true,status:'Paused',position:14,min_seek:10,max_seek:150,capabilities:{seek:true}});window.touchhelm.experience.mediaAction('seek',999);});
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='media'&&p.action==='seek'&&p.value===150)));
});
test('v2 app hold and cancelled scrolling never also launch, and overflow remains keyboard accessible', async page => {
  await page.locator('#tabApps').click();const app=page.locator('[data-app-id="app-editor"]');
  await app.dispatchEvent('pointerdown',{pointerId:6,button:0,clientX:40,clientY:140});await page.waitForTimeout(550);
  assert.equal(await page.locator('#appActionsModal').isVisible(),true);
  await app.dispatchEvent('pointerup',{pointerId:6});await app.dispatchEvent('click',{detail:1});
  assert.equal(await page.evaluate(()=>window.__packets.filter(p=>p.type==='launch_app').length),0);
  await page.keyboard.press('Escape');
  await app.dispatchEvent('pointerdown',{pointerId:7,button:0,clientX:40,clientY:140});
  await app.dispatchEvent('pointermove',{pointerId:7,clientX:40,clientY:170});await app.dispatchEvent('pointerup',{pointerId:7});await app.dispatchEvent('click',{detail:1});
  assert.equal(await page.evaluate(()=>window.__packets.filter(p=>p.type==='launch_app').length),0);
  const more=page.locator('.app-more').first();await more.focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('#appActionsModal').isVisible(),true);
});
test('v2 optional pinch is locked to zoom and never scrolls or clicks',async page=>{
  await page.evaluate(()=>{window.touchhelm.pinchZoom=true;window.__packets.length=0;});
  await touch(page,'touchstart',[{x:100,y:200},{x:200,y:200}]);
  await touch(page,'touchmove',[{x:75,y:200},{x:225,y:200}]);
  await touch(page,'touchmove',[{x:75,y:240},{x:225,y:240}]);await touch(page,'touchend',[]);
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='zoom')));
  assert.deepEqual(await page.evaluate(()=>window.__packets.filter(p=>['scroll','click','move'].includes(p.type))),[]);
});
test('v2 disappeared selected player stays unavailable instead of targeting another session',async page=>{
  await page.locator('#tabMedia').click();await page.locator('#mediaSessionSelect').selectOption('player-two');
  await page.evaluate(()=>window.touchhelm.controls.renderMediaLibrary({sessions:[],items:[],playlist_supported:false}));
  assert.equal(await page.locator('#mediaSessionSelect').inputValue(),'player-two');
  assert.match(await page.locator('#mediaTitle').textContent(),/unavailable/i);assert.equal(await page.locator('#btnMediaPlay').isDisabled(),true);
});
test('v2 unknown hardware readback never displays an invented percentage',async page=>{
  await page.locator('#tabMedia').click();
  await page.evaluate(()=>{window.touchhelm.onVolumeSync(null,null);window.touchhelm.onBrightnessSync(null);});
  assert.match(await page.locator('#lblVolLevel').textContent(),/unknown|unavailable/i);
  assert.match(await page.locator('#lblBrightLevel').textContent(),/unknown|unavailable/i);
  assert.equal(await page.locator('#sliderVol').isDisabled(),true);assert.equal(await page.locator('#sliderBright').isDisabled(),true);
});
test('v2 certificate download uses authenticated headers and handoff preserves theme preferences',async page=>{
  await page.route('**/api/pairing',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({enabled:true,fingerprint_sha256:'fixture fingerprint',https_port:8766})}));
  await page.route('**/api/pairing/certificate',route=>route.fulfill({contentType:'application/pkix-cert',body:'Public fixture certificate'}));
  await page.route('**/api/pairing/handoff',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.evaluate(()=>{window.touchhelm.authPin='5678';window.touchhelm.typeInput.value='keep\nthis';});
  await page.locator('#btnSettings').click();await page.locator('#btnSecurePairing').click();
  const request=page.waitForRequest('**/api/pairing/certificate');await page.getByRole('button',{name:'Download local public certificate',exact:true}).click();
  assert.equal((await request).headers()['x-touchhelm-pin'],'5678');
  const handoff=page.waitForRequest('**/api/pairing/handoff');await page.getByRole('button',{name:'Continue with local HTTPS',exact:true}).click();const data=(await handoff).postDataJSON();
  assert.equal(data.draft,'keep\nthis');assert.equal(data.preferences.theme,'glass');assert.ok(data.preferences.appearance&&data.preferences.motion&&data.preferences.contrast);assert.equal(data.preferences.pin_code,undefined);
  assert.equal(await page.locator('#typeInput').inputValue(),'keep\nthis');
});
test('living Presenter navigation never overlaps monitor controls at narrow sizes',async page=>{
  for(const width of [320,360,390]) {
    await page.setViewportSize({width,height:568});await page.locator('#tabPresenter').click();
    const layout=await page.evaluate(()=>{const button=document.getElementById('btnSlideNext').getBoundingClientRect(),nav=document.querySelector('.slide-nav-grid').getBoundingClientRect(),monitor=document.querySelector('.display-choice').getBoundingClientRect();return {buttonBottom:button.bottom,navBottom:nav.bottom,monitorTop:monitor.top};});
    assert.ok(layout.buttonBottom<=layout.navBottom+1,'navigation contains its buttons');
    assert.ok(layout.buttonBottom<=layout.monitorTop,'monitor dropdown does not overlap navigation');
  }
});
test('living Media seek advances without a supplied rate and unchanged snapshots do not rewind it',async page=>{
  await page.locator('#tabMedia').click();
  const media={available:true,session_id:'clock-test',title:'Clock test',status:'Playing',position:240,duration:900,min_seek:0,max_seek:900,updated_at:100,capabilities:{seek:true}};
  await page.evaluate(media=>{const e=window.touchhelm.experience;window.__mediaTime=0;e.playbackClock.now=()=>window.__mediaTime;e.playbackClock.anchor=null;e.renderMedia(media);window.__mediaTime=1500;e.tickMedia();},media);
  assert.ok(Number(await page.locator('#mediaSeek').inputValue())>=241,'seek advances at effective1x');
  await page.evaluate(media=>{window.touchhelm.experience.renderMedia({...media});window.touchhelm.experience.tickMedia();},media);
  assert.ok(Number(await page.locator('#mediaSeek').inputValue())>=241,'snapshot does not rewind');
});
test('living Live typing defaults on, remembers explicit opt-out, and does not replay a restored draft',async(page,context)=>{
  assert.equal(await page.locator('#chkRealtimeTyping').isChecked(),true);
  await page.locator('#typeInput').focus();await page.locator('#chkRealtimeTyping').uncheck();await page.reload();
  assert.equal(await page.locator('#chkRealtimeTyping').isChecked(),false);
  await page.evaluate(()=>{localStorage.removeItem('touchhelm_live_typing');sessionStorage.setItem(`touchhelm_resume:${location.host}`,JSON.stringify({savedAt:Date.now(),draft:'saved draft',baseline:'saved draft',live:true}));});
  await page.reload();await page.waitForFunction(()=>window.touchhelm?.isConnected);
  assert.equal(await page.locator('#typeInput').inputValue(),'saved draft');
  assert.equal(await page.evaluate(()=>window.__packets.some(p=>p.type==='text')),false);
});
test('living Close window is limited to verified choices and reports a request rather than success',async page=>{
  await page.locator('#tabApps').click();
  await page.evaluate(()=>window.touchhelm.experience.drawApps([{id:'multi',name:'Editor',running:true,windows:[{id:'first',title:'One'},{id:'second',title:'Unsaved document'}]}],''));
  await page.locator('.app-more').click();await page.locator('#btnCloseAppWindow').click();
  assert.equal(await page.evaluate(()=>window.__packets.some(p=>p.type==='app_action'&&p.action==='close')),false);
  await page.locator('#appWindowChoices button').last().click();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='app_action'&&p.action==='close'&&p.window_id==='second')));
  assert.match(await page.locator('#appActionDetails').textContent(),/requested|waiting/i);
});

test('living offline live edits wait for explicit Send after reconnection',async page=>{
  await typingView(page);await page.locator('#typeInput').fill('hi');
  await page.evaluate(()=>{const c=touchhelm;c.ws.onclose();clearTimeout(c.reconnectTimer);});
  await page.locator('#typeInput').fill('hi there');
  await page.evaluate(()=>{touchhelm.connect();});await page.waitForFunction(()=>touchhelm.isConnected);
  await page.evaluate(()=>window.__packets.length=0);
  await page.locator('#typeInput').press('End');await page.locator('#typeInput').press('!');
  assert.deepEqual(await packets(page),[],'offline draft must not replay on the next edit');
  await page.locator('#btnSendText').click();
  assert.ok((await packets(page)).some(p=>p.type==='text'&&p.text===' there!'));
});

test('living scrub cancellation sends nothing and rejected seeking restores actual time',async page=>{
  await page.locator('#tabMedia').click();
  await page.evaluate(()=>{const e=touchhelm.experience,media={available:true,session_id:'scrub',title:'Scrub',status:'Paused',position:30,duration:300,min_seek:0,max_seek:300,capabilities:{seek:true}};window.__stateOverride={presentation:{available:false},media};e.renderMedia(media);const s=document.getElementById('mediaSeek');s.value=200;s.dispatchEvent(new Event('input'));e.tickMedia();});
  assert.equal(Number(await page.locator('#mediaSeek').inputValue()),200);
  await page.locator('#mediaSeek').dispatchEvent('pointercancel');
  assert.equal(Number(await page.locator('#mediaSeek').inputValue()),30);assert.deepEqual(await packets(page),[]);
  await page.evaluate(()=>{const s=document.getElementById('mediaSeek');s.value=200;s.dispatchEvent(new Event('input'));s.dispatchEvent(new Event('change'));});
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='media'&&p.action==='seek').length),1);
  assert.equal(await page.evaluate(()=>touchhelm.experience.pending),true);
  await page.evaluate(()=>touchhelm.experience.commandResult({command:'media',success:false,message:'Seek rejected'}));
  assert.equal(await page.evaluate(()=>touchhelm.experience.pending),false);
});

test('living real pad permits peripheral reactions while keeping labels and input intact',async page=>{
  await page.evaluate(async()=>{TouchHelmThemes.apply('companion',{effects:'rich',motion:'system'},false);await TouchHelmThemes.ready;});
  const result=await page.evaluate(()=>{const c=touchhelm,source=document.getElementById('touchSurface');TouchHelmEffects.synchronize();const accepted=TouchHelmEffects.react(source,{kind:'press',x:40,y:550});return {accepted,scenes:document.querySelectorAll('.th-effect-scene:not([hidden])').length,events:getComputedStyle(document.querySelector('.th-effects-stage')).pointerEvents};});
  assert.equal(result.accepted,true);assert.ok(result.scenes>0);assert.equal(result.events,'none');assert.deepEqual(await packets(page),[]);
});
test('living artwork decodes authenticated bytes, reuses valid art, and clears changed media',async page=>{
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jmk0AAAAASUVORK5CYII=','base64');let reads=0;
  await page.route('**/api/assets/good',route=>{reads++;assert.equal(route.request().headers()['x-touchhelm-pin'],'5678');return route.fulfill({status:200,contentType:'image/png',body:png});});
  await page.route('**/api/assets/broken',route=>route.fulfill({status:200,contentType:'image/png',body:'not a PNG'}));
  await page.locator('#tabMedia').click();
  const media={available:true,session_id:'art-test',title:'Supplied cover',status:'Paused',position:0,duration:60,artwork_id:'good',artwork_status:'available',capabilities:{}};
  await page.evaluate(media=>{window.touchhelm.authPin='5678';window.touchhelm.experience.renderMedia(media);},media);
  await page.waitForFunction(()=>document.getElementById('mediaArtwork').naturalWidth>0&&!document.getElementById('mediaArtwork').hidden);
  const src=await page.locator('#mediaArtwork').getAttribute('src');await page.evaluate(media=>window.touchhelm.experience.renderMedia({...media}),media);
  assert.equal(reads,1);assert.equal(await page.locator('#mediaArtwork').getAttribute('src'),src);
  await page.evaluate(media=>window.touchhelm.experience.renderMedia({...media,title:'Broken cover',artwork_id:'broken'}),media);
  await page.waitForFunction(()=>document.getElementById('mediaArtworkStatus').textContent==='Artwork could not be displayed');
  assert.equal(await page.locator('#mediaArtwork').isVisible(),false);
  await page.evaluate(media=>window.touchhelm.experience.renderMedia({...media,title:'No artwork',artwork_id:null,artwork_status:'not_provided'}),media);
  assert.match(await page.locator('#mediaArtworkStatus').textContent(),/has not supplied/);
  assert.equal(await page.locator('#mediaArtwork').getAttribute('src'),null);
});
test('living an absent catalog cannot falsely confirm a close',async page=>{
  await page.locator('#tabApps').click();
  await page.evaluate(()=>{
    const e=window.touchhelm.experience;
    e.pendingClose={appId:'unknown',windowId:'selected',finalCheck:true};
    e.drawApps([]);
  });
  assert.match(await page.locator('#appActionDetails').textContent(),/could not verify/i);
  await page.evaluate(()=>{
    const e=window.touchhelm.experience;
    e.pendingClose={appId:'known',windowId:'selected'};
    e.drawApps([{id:'known',name:'Scratch',windows:[]}]);
  });
  assert.match(await page.locator('#appActionDetails').textContent(),/Window closed/);
});

test('v2 preview board presents typing, held keys, missing artwork and action sheets without native transport',async page=>{
  const sockets=[];page.on('websocket',socket=>sockets.push(socket.url()));
  await page.goto(origin+'/preview.html',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>document.getElementById('previewPhone').contentWindow.touchhelm?.isConnected&&document.getElementById('previewDesktop').contentWindow.TouchHelmDesktopPreview);
  const phone=page.frameLocator('#previewPhone');
  await page.locator('#previewState').selectOption('held');
  assert.match(await phone.locator('#heldKeys').textContent(),/Ctrl.*Shift/);
  await page.locator('#previewState').selectOption('typing');
  assert.equal(await phone.locator('#typingDock').evaluate(el=>el.classList.contains('expanded')),true);
  assert.match(await phone.locator('#typeInput').inputValue(),/\n/);
  await page.locator('#previewState').selectOption('missing-artwork');assert.equal(await phone.locator('#mediaArtwork').isVisible(),false);
  await page.locator('#previewState').selectOption('menu');assert.equal(await phone.locator('#appActionsModal').isVisible(),true);
  await page.locator('#previewState').selectOption('ready');assert.equal(await phone.locator('#appActionsModal').isVisible(),false);
  assert.deepEqual(sockets,[],'preview transport never opens a real WebSocket');
});
async function openTheme(page) {
  if (!await page.locator('#settingsModal').isVisible()) await page.locator('#btnSettings').click();
  await page.locator('#btnTheme').click();
}
async function input(page, value, inputType = 'insertText', data = null, isComposing = false) {
  await page.locator('#typeInput').evaluate((el, event) => {
    el.value = event.value;
    el.dispatchEvent(new InputEvent('input', {bubbles: true, ...event}));
  }, {value, inputType, data, isComposing});
}
async function packets(page) {
  return page.evaluate(() => window.__packets.filter(p => p.type === 'text' || p.type === 'key'));
}
const graphemes = text => [...new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(text)].map(p => p.segment);
function remoteText(messages) {
  let text = '';
  for (const message of messages) {
    if (message.type === 'text') text += message.text;
    if (message.type === 'key' && message.key === 'backspace') text = graphemes(text).slice(0, -1).join('');
  }
  return text;
}
async function touch(page, type, points = [{x: 110, y: 190}]) {
  await page.locator('#touchSurface').evaluate((el, event) => {
    const touches = event.points.map((p, index) => new Touch({identifier: index + 1,
      target: el, clientX: p.x, clientY: p.y, pageX: p.x, pageY: p.y}));
    el.dispatchEvent(new TouchEvent(event.type, {bubbles: true, cancelable: true,
      touches, targetTouches: touches, changedTouches: touches}));
  }, {type, points});
}
async function tap(page) { await touch(page, 'touchstart'); await touch(page, 'touchend', []); }
function test(name, run, visual = false) { tests.push({name, run, visual}); }

async function disconnect(page) {
  await page.evaluate(() => {
    window.__offline = true;
    const ws = window.__sockets.at(-1); ws.readyState = 3; ws.onclose?.({});
  });
}
async function assertDialogFocus(page, id) {
  const dialog = page.locator(`#${id}`);
  assert.equal(await dialog.getAttribute('role'), 'dialog');
  assert.equal(await dialog.getAttribute('aria-modal'), 'true');
  assert.ok(await dialog.getAttribute('aria-labelledby'), 'dialog has an accessible heading');
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press(i < 6 ? 'Tab' : 'Shift+Tab');
    assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true,
      `${id} must contain keyboard focus`);
  }
}

test('navigation exposes selected tabs and keyboard theme choices are native controls', async page => {
  assert.equal(await page.locator('#statusPill').evaluate(el => el.tagName), 'BUTTON');
  const tabs = page.locator('.nav-tab');
  assert.equal(await tabs.count(), 6);
  for (let i = 0; i < 6; i++) {
    const tab = tabs.nth(i), view = await tab.getAttribute('data-view');
    assert.equal(await tab.getAttribute('role'), 'tab');
    assert.equal(await tab.getAttribute('aria-controls'), view);
    await tab.focus(); await page.keyboard.press('Enter');
    assert.equal(await tab.getAttribute('aria-selected'), 'true');
    assert.equal(await page.locator('.nav-tab[aria-selected="true"]').count(), 1);
    assert.ok(await page.locator(`#${view}`).isVisible());
  }
  await openTheme(page);
  const choice = page.locator('.th-theme-choice[data-theme-id="clay"]');
  assert.equal(await choice.evaluate(el => el.tagName), 'BUTTON');
  await choice.focus(); await page.keyboard.press('Space');
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'clay');
  assert.equal(await choice.getAttribute('aria-pressed'), 'true');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#themeModal').isVisible(), false);
  assert.equal(await page.locator('#btnTheme').evaluate(el => el === document.activeElement), true);
});

test('theme and settings dialogs contain focus, Escape closes, and focus returns to their trigger', async page => {
  for (const [trigger, dialog] of [['btnTheme', 'themeModal'], ['btnSettings', 'settingsModal']]) {
    if (trigger === 'btnTheme') await page.locator('#btnSettings').click();
    await page.locator(`#${trigger}`).focus(); await page.keyboard.press('Enter');
    assert.ok(await page.locator(`#${dialog}`).isVisible());
    await assertDialogFocus(page, dialog);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator(`#${dialog}`).isVisible(), false);
    assert.equal(await page.locator(`#${trigger}`).evaluate(el => el === document.activeElement), true);
    if (trigger === 'btnTheme') await page.keyboard.press('Escape');
  }
});

test('PIN dialog contains focus and remains required after Escape or backdrop interaction', async page => {
  await page.evaluate(() => {
    window.__expectedPin = '1234';
    window.__sockets.at(-1).onmessage({data: JSON.stringify({type: 'auth_required'})});
  });
  await assertDialogFocus(page, 'pinModal');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#pinModal').isVisible(), true);
  await page.locator('#pinModal').dispatchEvent('click');
  assert.equal(await page.locator('#pinModal').isVisible(), true);
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), false);
  await screenshot(page, 'pin-required');
});

test('Send and Clear restore typing focus for continued phone input', async page => {
  await typingView(page);
  await input(page, 'focus me', 'insertText', 'focus me');
  await page.locator('#btnSendText').click();
  assert.equal(await page.locator('#typeInput').evaluate(el => el === document.activeElement), true);
  await input(page, 'clear me', 'insertText', 'clear me');
  await page.locator('#btnClearText').click();
  assert.equal(await page.locator('#typeInput').inputValue(), '');
  assert.equal(await page.locator('#typeInput').evaluate(el => el === document.activeElement), true);
});

test('disconnected remote controls are disabled while drafts, local timer and navigation remain usable', async page => {
  await disconnect(page);
  for (const id of ['btnLeftClick', 'btnRightClick', 'btnMiddleClick', 'btnGyro',
    'btnKeyViewStart', 'btnSlideNext', 'btnSlidePrev', 'btnSlideStart', 'btnVolUp', 'btnVolMute',
    'btnMediaPlay', 'btnLockPc', 'sliderVol', 'sliderBright', 'sliderSensitivity',
    'sliderAccel', 'sliderScroll', 'chkInvertScroll']) {
    assert.ok(await page.locator(`#${id}`).isDisabled(), `${id} should reflect the disconnected state`);
  }
  for (const selector of ['.key-btn', '.macro-btn', '.num-btn']) {
    assert.equal(await page.locator(selector).evaluateAll(elements => elements.every(el => el.disabled)), true);
  }
  assert.equal(await page.locator('#typeInput').isDisabled(), false);
  assert.equal(await page.locator('#btnClearText').isDisabled(), false);
  await typingView(page);
  await input(page, 'local draft', 'insertText', 'local draft');
  assert.equal(await page.locator('#btnSendText').isDisabled(), false, 'Send can explain how to reconnect');
  await page.locator('#btnSendText').click();
  assert.equal(await page.locator('#typeInput').inputValue(), 'local draft');
  assert.ok(await page.locator('#uiFeedback').isVisible());
  assert.match(await page.locator('#uiFeedback').textContent(), /connect|offline/i);
  await screenshot(page, 'offline-trackpad');
  await page.locator('#typeInput').press('Enter');
  assert.equal(await page.locator('#typeInput').inputValue(), 'local draft\n');
  await page.locator('.nav-tab[data-view="viewPresenter"]').click();
  await page.locator('.timer-details summary').click();
  assert.equal(await page.locator('#btnTimerStart').isDisabled(), false);
  await page.locator('#btnTimerStart').click();
  assert.equal(await page.evaluate(() => window.touchhelm.timerRunning), true);
  await page.locator('#btnTimerStart').click();
  await page.locator('.nav-tab[data-view="viewTrackpad"]').click();
  await page.locator('#typeInput').focus();
  await page.locator('#btnClearText').click();
  assert.equal(await page.locator('#typeInput').inputValue(), '');
});

test('settings errors remain visible without falsely reporting a disconnected PC', async page => {
  const connectedLabel = await page.locator('#statusLabel').textContent();
  await page.route('**/api/config', route => route.fulfill({status: 403,
    contentType: 'application/json', body: JSON.stringify({error: 'Settings could not be saved'})}));
  await page.locator('#btnSettings').click();
  const response = page.waitForResponse(res => res.url().endsWith('/api/config'));
  await page.locator('#sliderSensitivity').evaluate(el => {
    el.value = '1.8'; el.dispatchEvent(new Event('input', {bubbles: true}));
  });
  await response;
  await page.waitForFunction(() => document.querySelector('#uiFeedback')?.textContent.trim());
  assert.ok(await page.locator('#uiFeedback').isVisible());
  assert.equal(await page.locator('#uiFeedback').getAttribute('role'), 'status');
  assert.equal(await page.locator('#uiFeedback').getAttribute('aria-live'), 'polite');
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), true);
  assert.equal(await page.locator('#statusLabel').textContent(), connectedLabel);
  await page.evaluate(() => window.touchhelm.clearFeedback('settings'));
  assert.equal(await page.locator('#uiFeedback').isVisible(), false);
  assert.ok(await page.locator('#settingsFeedback').isVisible());
  assert.match(await page.locator('#settingsFeedback').textContent(), /Pointer speed/);
  await screenshot(page, 'settings-error');
});

test('host form handles Enter and invalid PC addresses give an actionable visible error', async page => {
  await page.locator('#btnSettings').click();
  assert.equal(await page.locator('#settingHost').evaluate(el => el.closest('form')?.id), 'hostForm');
  const initialHost = await page.evaluate(() => window.touchhelm.host);
  await page.locator('#settingHost').fill('http://');
  await page.locator('#settingHost').press('Enter');
  assert.equal(await page.locator('#settingsModal').isVisible(), true);
  assert.equal(await page.evaluate(() => window.touchhelm.host), initialHost);
  assert.ok(await page.locator('#uiFeedback').isVisible());
  assert.match(await page.locator('#uiFeedback').textContent(), /address|host|PC/i);
  await page.locator('#settingHost').fill(new URL(origin).host);
  await page.locator('#settingHost').press('Enter');
  await page.waitForFunction(() => window.__sockets.length === 2 && window.touchhelm.isConnected);
  assert.equal(await page.locator('#settingsModal').isVisible(), false);
});

test('one Windows Start button, located in keyboard; typing controls located in trackpad', async page => {
  const controls = await page.locator('button').evaluateAll(buttons => buttons.filter(button =>
    button.dataset.shortcut === 'start' ||
    /Windows Start Menu/.test(button.title)).map(button => ({id: button.id, view: button.closest('.view')?.id})));
  assert.deepEqual(controls, [{id: 'btnKeyViewStart', view: 'viewKeyboard'}]);
  for (const id of ['typeInput', 'btnSendText', 'btnClearText', 'chkRealtimeTyping']) {
    assert.equal(await page.locator(`#${id}`).count(), 1);
    assert.equal(await page.locator(`#${id}`).evaluate(el => el.closest('.view').id), 'viewTrackpad');
  }
  await page.locator('.nav-tab[data-view="viewKeyboard"]').click();
  await page.locator('#btnKeyViewStart').click();
  const starts = await page.evaluate(() => window.__packets.filter(p => p.type === 'shortcut' && p.name === 'start'));
  assert.equal(starts.length, 1, 'one action per Start button click');
});

test('live typing sends null-data paste and replaces selected or autocorrected suffix', async page => {
  await typingView(page);
  await input(page, 'hello world', 'insertFromPaste');
  assert.equal(remoteText(await packets(page)), 'hello world');
  await input(page, 'hello friend', 'insertReplacementText', 'friend');
  assert.equal(remoteText(await packets(page)), 'hello friend');
  await input(page, 'hey friend', 'insertReplacementText', 'hey');
  assert.equal(remoteText(await packets(page)), 'hey friend');
  await input(page, 'hey ', 'deleteContentBackward');
  assert.equal(remoteText(await packets(page)), 'hey ');
});

test('live typing deletes a whole emoji grapheme, not UTF-16 code units', async page => {
  await typingView(page);
  await input(page, 'a👨‍👩‍👧‍👦b', 'insertFromPaste');
  await input(page, 'ab', 'deleteContentBackward');
  assert.equal(remoteText(await packets(page)), 'ab');
  assert.equal((await packets(page)).filter(p => p.key === 'backspace').length, 2);
});

test('composition remains local until compositionend', async page => {
  await typingView(page);
  await page.locator('#typeInput').dispatchEvent('compositionstart');
  await input(page, 'に', 'insertCompositionText', 'に', true);
  await input(page, '日本', 'insertCompositionText', '日本', true);
  assert.deepEqual(await packets(page), []);
  await page.locator('#typeInput').dispatchEvent('compositionend', {data: '日本'});
  assert.equal(remoteText(await packets(page)), '日本');
  await input(page, '日本', 'insertText', '日本');
  assert.equal(remoteText(await packets(page)), '日本', 'final input does not duplicate composition');
});

test('buffered draft syncs once when live is enabled; Clear resets only local baseline', async page => {
  await typingView(page);
  await page.locator('#chkRealtimeTyping').uncheck();
  await input(page, 'draft', 'insertFromPaste');
  assert.deepEqual(await packets(page), []);
  await page.locator('#chkRealtimeTyping').check();
  assert.equal(remoteText(await packets(page)), 'draft');
  await input(page, 'draft!', 'insertText', '!');
  assert.equal(remoteText(await packets(page)), 'draft!');
  await page.locator('#btnClearText').click();
  assert.equal(await page.locator('#typeInput').inputValue(), '');
  assert.equal(remoteText(await packets(page)), 'draft!');
  await input(page, 'next', 'insertText', 'next');
  assert.equal(remoteText(await packets(page)), 'draft!next');
});

test('live Send emits Enter once and resets draft; buffered Send emits text once', async page => {
  await typingView(page);
  await input(page, 'live', 'insertText', 'live');
  await page.locator('#btnSendText').click();
  assert.equal(await page.locator('#typeInput').inputValue(), '');
  assert.deepEqual(await packets(page), [{type: 'text', text: 'live'}, {type: 'key', key: 'enter'}]);
  await page.locator('#chkRealtimeTyping').uncheck();
  await input(page, 'buffer', 'insertFromPaste');
  await page.locator('#typeInput').press('Control+Enter');
  assert.deepEqual((await packets(page)).slice(2), [{type: 'text', text: 'buffer'}]);
  assert.equal(await page.locator('#typeInput').inputValue(), '');
});

test('live off and on preserves the sent baseline; buffered edits update that draft once', async page => {
  await typingView(page);
  await input(page, 'already', 'insertText', 'already');
  await page.locator('#chkRealtimeTyping').uncheck();
  await page.locator('#chkRealtimeTyping').check();
  assert.deepEqual(await packets(page), [{type: 'text', text: 'already'}], 'mode toggle must not duplicate sent text');
  await page.locator('#chkRealtimeTyping').uncheck();
  await input(page, 'already edited', 'insertText', ' edited');
  assert.equal(remoteText(await packets(page)), 'already', 'buffered edits wait for Send');
  await page.locator('#btnSendText').click();
  assert.equal(remoteText(await packets(page)), 'already edited');
  assert.equal((await packets(page)).filter(packet => packet.key === 'enter').length, 0);
  assert.equal(await page.locator('#typeInput').inputValue(), '');
});

test('offline Send preserves drafts and Return still creates a local newline', async page => {
  await typingView(page);
  await disconnect(page);
  await input(page, 'keep me', 'insertText', 'keep me');
  await page.locator('#btnSendText').dispatchEvent('click');
  assert.equal(await page.locator('#typeInput').inputValue(), 'keep me');
  await page.locator('#typeInput').press('Enter');
  assert.equal(await page.locator('#typeInput').inputValue(), 'keep me\n');
  await page.locator('#chkRealtimeTyping').uncheck();
  await page.locator('#btnSendText').dispatchEvent('click');
  assert.equal(await page.locator('#typeInput').inputValue(), 'keep me\n');
  assert.deepEqual(await packets(page), []);
});

test('startup reads server settings without posting phone defaults', async page => {
  assert.deepEqual(posts, [], 'startup must not write /api/config');
  assert.equal(await page.evaluate(() => window.touchhelm.sensitivity), serverConfig.mouse_sensitivity);
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'glass', 'host settings do not replace the device theme');
});

test('stale socket callbacks cannot mark a newer socket offline or reconnect it', async page => {
  await page.evaluate(() => {
    const ws = window.__sockets[0];
    window.__oldCallbacks = {close: ws.onclose, error: ws.onerror, open: ws.onopen, message: ws.onmessage};
  });
  await page.locator('#statusPill').click();
  await page.waitForFunction(() => window.__sockets.length === 2 && window.touchhelm.isConnected);
  const connectedLabel = await page.locator('#statusLabel').textContent();
  await page.evaluate(() => {
    window.__oldCallbacks.close?.({}); window.__oldCallbacks.error?.({});
    window.__oldCallbacks.message?.({data: JSON.stringify({type: 'auth_res', success: false})});
  });
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), true);
  assert.equal(await page.locator('#statusLabel').textContent(), connectedLabel);
  await page.waitForTimeout(2700);
  assert.equal(await page.evaluate(() => window.__sockets.length), 2);
});

test('PIN challenge blocks input, rejects an invalid PIN, and connects after a valid PIN', async page => {
  assert.equal(await page.locator('#pinModal').isVisible(), false, 'closed PIN dialog must be hidden');
  await page.evaluate(() => {
    window.__expectedPin = '1234';
    window.__sockets.at(-1).onmessage({data: JSON.stringify({type: 'auth_required'})});
  });
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), false);
  assert.equal(await page.locator('#pinModal').isVisible(), true);
  await page.evaluate(() => window.__packets.length = 0);
  await page.locator('#btnRightClick').dispatchEvent('click');
  await input(page, 'unauthenticated draft', 'insertText', 'unauthenticated draft');
  assert.deepEqual(await page.evaluate(() => window.__packets), [], 'input stays blocked until authenticated');
  await page.locator('#pinInput').fill('9999');
  await page.locator('#pinForm button').click();
  await page.waitForFunction(() => document.querySelector('#pinError').textContent === 'Invalid PIN');
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), false);
  assert.equal(await page.locator('#pinModal').isVisible(), true);
  await page.locator('#pinInput').fill('1234');
  await page.locator('#pinInput').press('Enter');
  await page.waitForFunction(() => window.touchhelm.isConnected);
  assert.equal(await page.locator('#pinModal').isVisible(), false);
  const settingResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/config') && response.request().method() === 'POST');
  await page.locator('#sliderSensitivity').evaluate(el => {
    el.value = '1.9'; el.dispatchEvent(new Event('input', {bubbles: true}));
  });
  const response = await settingResponse;
  assert.equal(response.request().headers()['x-touchhelm-pin'], '1234');
  assert.deepEqual(posts, [{mouse_sensitivity: 1.9}]);
});

test('server config broadcasts update UI without writing settings back', async page => {
  await page.evaluate(() => window.__sockets.at(-1).onmessage({data: JSON.stringify({
    type: 'config_sync', config: {mouse_sensitivity: 1.7, theme: 'matrix', laser_color: 'green'},
  })}));
  assert.equal(await page.evaluate(() => window.touchhelm.sensitivity), 1.7);
  assert.equal(await page.locator('#sliderSensitivity').inputValue(), '1.7');
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'glass', 'another device cannot restyle this phone');
  assert.deepEqual(posts, []);
});

test('failed wake lock cannot leave an active button or a dummy playback loop', async page => {
  await page.locator('#btnSettings').click();
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'wakeLock', {configurable: true, value: {
      request: () => Promise.reject(new Error('Wake lock unavailable')),
    }});
    HTMLMediaElement.prototype.play = () => Promise.reject(new Error('Unsupported media'));
  });
  await page.locator('#btnWakeLock').click();
  await page.waitForTimeout(30);
  assert.equal(await page.evaluate(() => window.touchhelm.wakeLockRequested), false);
  assert.equal(await page.locator('video:not(#remoteVideo)').count(), 0, 'failed wake lock must not create dummy media');
  assert.equal(await page.locator('#remoteVideo').evaluate(video=>video.srcObject), null, 'Remote video remains inactive');
  assert.equal(await page.evaluate(() => document.querySelector('#btnWakeLock').style.color === 'var(--primary)'), false);
  assert.ok(await page.locator('#uiFeedback').isVisible(), 'touch users need visible capability feedback');
  assert.match(await page.locator('#uiFeedback').textContent(), /awake|wake|https|browser/i);
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), true);
});

test('unsupported fullscreen API is handled without a browser exception', async page => {
  await page.locator('#btnSettings').click();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.evaluate(() => Object.defineProperty(document.documentElement, 'requestFullscreen', {
    configurable: true, value: undefined,
  }));
  await page.locator('#btnFullscreen').click();
  await page.waitForTimeout(30);
  assert.deepEqual(errors, []);
  assert.ok(await page.locator('#uiFeedback').isVisible(), 'fullscreen failure needs visible feedback');
  assert.match(await page.locator('#uiFeedback').textContent(), /fullscreen|browser/i);
  assert.equal(await page.evaluate(() => window.touchhelm.isConnected), true);
});

test('double tap produces exactly two effective clicks', async page => {
  await tap(page); await page.waitForTimeout(40); await tap(page);
  const clicks = await page.evaluate(() => window.__packets.filter(p => p.type === 'click' || p.type === 'double_click'));
  assert.equal(clicks.reduce((count, p) => count + (p.type === 'double_click' ? 2 : 1), 0), 2,
    JSON.stringify(clicks));
});

test('view change, blur and cancelled gestures clear drag timers and pressed buttons', async page => {
  await touch(page, 'touchstart');
  await page.locator('.nav-tab[data-view="viewKeyboard"]').click();
  await page.waitForTimeout(390);
  assert.equal(await page.evaluate(() => window.touchhelm.isDragging), false);
  assert.equal(await page.evaluate(() => window.__packets.some(p => p.type === 'mousedown')), false);
  await page.locator('.nav-tab[data-view="viewTrackpad"]').click();
  await touch(page, 'touchstart'); await page.waitForTimeout(390);
  assert.equal(await page.evaluate(() => window.touchhelm.isDragging), true);
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  assert.equal(await page.evaluate(() => window.touchhelm.isDragging), false);
  await touch(page, 'touchcancel', []);
  await page.evaluate(() => window.__packets.length = 0);
  await tap(page);
  assert.equal(await page.evaluate(() => window.__packets.filter(p => p.type === 'click').length), 1);
});

test('native chords, nested numpad, timer reset, current context and catalogs work together', async page => {
  await page.locator('.nav-tab[data-view="viewKeyboard"]').click();
  for (const key of ['lctrl','lshift','a']) await page.locator(`.native-key[data-key="${key}"]`).tap();
  assert.deepEqual(await page.evaluate(() => window.__packets.filter(p=>['keydown','keyup'].includes(p.type))), [
    {type:'keydown',key:'lctrl'},{type:'keydown',key:'lshift'},{type:'keydown',key:'a'},
    {type:'keyup',key:'a'},{type:'keyup',key:'lctrl'},{type:'keyup',key:'lshift'}]);
  await page.locator('#keyboardModeNumpad').click();
  await page.locator('.native-key[data-key="numpadenter"]').tap();
  await page.locator('.nav-tab[data-view="viewPresenter"]').click();
  assert.equal(await page.locator('#presentationTitle').textContent(),'Quarterly review');
  assert.equal(await page.locator('#presentationSlide').textContent(),'Slide 3 of 12');
  await page.locator('.timer-details summary').click();
  await page.locator('#btnTimerStart').click(); await page.locator('#btnTimerReset').click();
  await page.locator('#btnSlideNext').click();
  assert.equal(await page.evaluate(()=>window.touchhelm.timerRunning),false);
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='presentation' && p.action==='next')));
  await page.locator('.nav-tab[data-view="viewMedia"]').click();
  await page.locator('#mediaSessionSelect').selectOption('player-two');
  assert.equal(await page.locator('#mediaTitle').textContent(),'Design talk');
  await page.locator('#btnMediaPlay').click();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='media' && p.session_id==='player-two')));
  await page.locator('[data-item-id="track-one"]').click();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='play_media' && p.item_id==='track-one')));
  await page.locator('.nav-tab[data-view="viewApps"]').click();
  await page.locator('#appSearch').fill('notes');
  assert.equal(await page.locator('#appsList .app-item').count(),1);
  assert.equal(await page.locator('#appsList .app-more').count(),1);
  await page.locator('#appsList .app-item').click();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='launch_app' && p.app_id==='app-notes')));
});

test('restored app mark and control icons remain visible through action-state changes', async page => {
  assert.ok(await page.locator('.brand-logo').evaluate(el=>el.complete && el.naturalWidth>0));
  for (const view of ['Trackpad','Presenter','Media','Keyboard','Apps']) {
    await page.locator(`.nav-tab[data-view="view${view}"]`).click();
    assert.ok(await page.locator('.brand-logo').isVisible());
    const unresolved=await page.locator(`#view${view} svg use`).evaluateAll(uses=>uses.map(use=>use.getAttribute('href')).filter(ref=>!document.querySelector(ref)));
    assert.deepEqual(unresolved,[], `${view} icons resolve locally`);
    assert.ok(await page.locator(`#view${view} .ui-icon`).count()>0);
  }
  await typingView(page);
  assert.equal(await page.locator('#btnSendText use').getAttribute('href'),'#th-icon-enter');
  await page.locator('#chkRealtimeTyping').uncheck();
  assert.equal(await page.locator('#btnSendText use').getAttribute('href'),'#th-icon-send');
  await page.locator('.nav-tab[data-view="viewPresenter"]').click();
  await page.locator('.timer-details summary').click();
  await page.locator('#btnTimerStart').click();
  assert.equal(await page.locator('#btnTimerStart use').getAttribute('href'),'#th-icon-pause');
  await page.locator('#btnTimerReset').click();
  assert.equal(await page.locator('#btnTimerStart use').getAttribute('href'),'#th-icon-play');
});

test('server update reloads the latest UI and restores an unsent draft', async page => {
  await typingView(page); await page.locator('#chkRealtimeTyping').uncheck();
  await input(page,'saved across update','insertText','saved across update');
  await page.route('**/api/version', route=>route.fulfill({contentType:'application/json',body:JSON.stringify({build:'next-build'})}));
  await page.route('**/?build=next-build', route=>route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'web/index.html'),'utf8').replaceAll('__TOUCHHELM_BUILD__','next-build')}));
  await page.evaluate(()=>{ window.touchhelm.checkServerVersion(); });
  await page.waitForURL('**/?build=next-build');
  await page.waitForFunction(()=>window.touchhelm?.buildId==='next-build');
  assert.equal(await page.locator('#typeInput').inputValue(),'saved across update');
  assert.equal(await page.locator('#chkRealtimeTyping').isChecked(),false);
  assert.deepEqual(await packets(page),[], 'restoring draft never sends PC text');
});

test('keyboard disclosures visibly expand and expose advanced native keys', async page => {
  await page.locator('.nav-tab[data-view="viewKeyboard"]').click();
  const group=page.locator('details.keyboard-group').filter({has:page.locator('summary', {hasText:'Advanced keys'})});
  const summary=group.locator('summary');
  const closed=await summary.evaluate(el=>({content:getComputedStyle(el,'::after').content,transform:getComputedStyle(el,'::after').transform}));
  assert.notEqual(closed.content,'none', 'disclosure has a visible cue');
  await summary.click();
  assert.equal(await group.getAttribute('open'),'');
  assert.notEqual(await summary.evaluate(el=>getComputedStyle(el,'::after').transform),closed.transform);
  await group.locator('[data-key="f24"]').tap();
  assert.ok(await page.evaluate(()=>window.__packets.some(p=>p.type==='keydown' && p.key==='f24')));
  await screenshot(page,'keyboard-disclosure-open');
});

for (const [width, height] of [[360, 640], [390, 844], [844, 390], [320, 568], [390, 420]]) {
  test(`trackpad layout stays usable at ${width}x${height}`, async (page, context) => {
    await page.setViewportSize({width, height});
    await page.locator('.nav-tab[data-view="viewTrackpad"]').click();
    if (captureScreenshots) {
      fs.mkdirSync(artifactDir, {recursive: true});
      await page.screenshot({path: path.join(artifactDir, `trackpad-${width}x${height}.png`), animations: 'disabled'});
    }
    const layout = await page.evaluate(() => {
      const selectors = ['.top-bar', '.bottom-nav', '#btnSettings', '#typeInput', '#touchSurface'];
      return {width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
        boxes: selectors.map(selector => {
          const el = document.querySelector(selector), rect = el.getBoundingClientRect();
          return {selector, x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom,
            width: rect.width, height: rect.height, visible: !!el.getClientRects().length};
        })};
    });
    assert.ok(layout.scrollWidth <= width, `horizontal overflow: ${JSON.stringify(layout)}`);
    assert.equal(await page.locator('#pinModal').isVisible(), false, 'closed PIN dialog must be hidden');
    for (const box of layout.boxes) {
      assert.ok(box.visible && box.width > 0 && box.height > 0, `${box.selector} hidden`);
      assert.ok(box.x >= -1 && box.right <= width + 1 && box.y >= -1 && box.bottom <= height + 1,
        `control outside viewport: ${JSON.stringify(box)}`);
    }
    const nav = layout.boxes.find(box => box.selector === '.bottom-nav');
    assert.ok(Math.abs(nav.bottom - height) <= 1, `navigation must stay at viewport bottom: ${JSON.stringify(nav)}`);
    for (const box of layout.boxes.filter(box => ['#typeInput', '#btnSendText', '#btnClearText', '#touchSurface'].includes(box.selector))) {
      assert.ok(box.bottom <= nav.y + 1, `navigation covers ${box.selector}: ${JSON.stringify({box, nav})}`);
    }
    await page.locator('#typeInput').focus();
    await settleVisual(page);
    for (const id of ['btnSendText','btnClearText','btnTypingDone']) {
      const box = await page.locator(`#${id}`).boundingBox();
      assert.ok(box && box.y >= 0 && box.y+box.height <= nav.y+1, `expanded typing control ${id} remains reachable`);
    }
    const pad = layout.boxes.find(box => box.selector === '#touchSurface');
    const controlBudget = height <= 560 ? 240 : 260; // Header, navigation, two 44px control rows and their spacing.
    assert.ok(pad.height >= height - controlBudget, `collapsed pad leaves only compact controls: ${pad.height}/${height}`);
    if (height >= 568) assert.ok(pad.height >= height * 0.50, 'normal portrait reserves most of screen for movement');
    await screenshot(page, `typing-${width}x${height}`);
    await page.locator('.nav-tab[data-view="viewKeyboard"]').click();
    await page.locator('#btnKeyViewStart').scrollIntoViewIfNeeded();
    assert.ok(await page.locator('#btnKeyViewStart').isVisible());
    if (captureScreenshots) await page.screenshot({path: path.join(artifactDir, `keyboard-${width}x${height}.png`), animations: 'disabled'});
  }, true);
}

const views = ['Trackpad', 'Presenter', 'Media', 'Keyboard', 'Apps', 'Remote'];
async function settleVisual(page) {
  await page.evaluate(async () => {
    await Promise.race([new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))),new Promise(resolve=>setTimeout(resolve,100))]);
    const finite = document.getAnimations().filter(animation =>
      animation.effect?.getComputedTiming().iterations !== Infinity);
    await Promise.race([Promise.all(finite.map(animation => animation.finished.catch(() => {}))),new Promise(resolve=>setTimeout(resolve,350))]);
  });
}
async function inspectUsability(page, label) {
  await settleVisual(page);
  return page.evaluate(label => {
    const issues = [];
    const rgba = value => {
      if(value.startsWith('color(')||value.startsWith('oklab(')||value.startsWith('oklch(')){
        const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle=value;ctx.fillRect(0,0,1,1);const pixel=ctx.getImageData(0,0,1,1).data;return [pixel[0],pixel[1],pixel[2],pixel[3]/255];
      }
      const parts = (value.match(/[\d.]+/g) || []).map(Number);
      return [parts[0] || 0, parts[1] || 0, parts[2] || 0, parts.length > 3 ? parts[3] : 1];
    };
    const blend = (front, back) => front.slice(0, 3).map((channel, i) => channel * front[3] + back[i] * (1 - front[3])).concat(1);
    const luminance = color => color.slice(0, 3).map(channel => {
      const c = channel / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    }).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
    const name = el => el.id || el.getAttribute('aria-label') || el.textContent.trim().replace(/\s+/g, ' ').slice(0, 60) || el.className;
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const modal = document.querySelector('.modal-backdrop.open');
    const scope = modal || document.querySelector('.view.active');
    const elements = [...scope.querySelectorAll('button,input[type="range"],input[type="checkbox"],.theme-option')];
    if (!modal) elements.push(...document.querySelectorAll('.top-bar button,.bottom-nav button'));
    for (const el of elements.filter(visible)) {
      let target = el;
      if (el.type === 'checkbox') {
        const candidates = [el, el.closest('label'),
          [...document.querySelectorAll('label')].find(label => label.htmlFor === el.id)].filter(Boolean);
        target = candidates.find(candidate => {
          const box = candidate.getBoundingClientRect(); return box.width >= 43.5 && box.height >= 43.5;
        }) || el;
      }
      const rect = target.getBoundingClientRect();
      if (rect.width < 43.5 || rect.height < 43.5) issues.push(`${label}: small touch target ${name(el)} ${rect.width.toFixed(1)}×${rect.height.toFixed(1)}`);
      if (rect.x < -1 || rect.right > innerWidth + 1) issues.push(`${label}: horizontal clipping ${name(el)} [${rect.x.toFixed(1)},${rect.right.toFixed(1)}]`);
    }
    const textSelectors = '.nav-label,.hint-item,.card-title,.timer-title,.laser-title,.setting-label,.setting-hint,.theme-meta strong,.theme-meta span,.toggle-label,.laser-hint,#typingHint,.status-label,.macro-btn,.native-key,.key-group-label,.context-status,.context-app,.catalog-text strong,.catalog-text span,.catalog-status,.console-page h1,.volume-level-label span,.brightness-level-label span';
    const texts = [...scope.querySelectorAll(textSelectors)];
    if (!modal) texts.push(...document.querySelectorAll('.nav-label,.status-label'));
    for (const el of texts.filter(visible)) {
      if (el.closest(':disabled') || !el.textContent.trim()) continue;
      const chain = [];
      let opacity = 1;
      for (let ancestor = el; ancestor; ancestor = ancestor.parentElement) {
        const style = getComputedStyle(ancestor);
        chain.push(rgba(style.backgroundColor));
        opacity *= Number(style.opacity);
      }
      let background = [255, 255, 255, 1];
      for (const layer of chain.reverse()) background = blend(layer, background);
      const style = getComputedStyle(el), color = rgba(style.color);
      color[3] *= opacity;
      const foreground = blend(color, background), a = luminance(foreground), b = luminance(background);
      const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      const size = parseFloat(style.fontSize), bold = Number(style.fontWeight) >= 700;
      const minimum = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
      if (ratio + 0.02 < minimum) issues.push(`${label}: contrast ${name(el)} ${ratio.toFixed(2)}:1 (needs ${minimum}:1)`);
    }
    const app = document.querySelector('#app').getBoundingClientRect();
    if (innerWidth >= 1100 && app.width > 1000) issues.push(`${label}: desktop remote stretches to ${app.width.toFixed(0)}px`);
    return issues;
  }, label);
}
async function screenshot(page, name) {
  if (!captureScreenshots) return;
  await settleVisual(page);
  fs.mkdirSync(artifactDir, {recursive: true});
  await page.screenshot({path: path.join(artifactDir, `${name}.png`), animations: 'disabled'});
}
for (const [width, height] of [[360, 640], [390, 844], [844, 390], [320, 568], [390, 420], [1440, 900]]) {
  test(`all remote views and dialogs have readable text and touch targets at ${width}x${height}`, async page => {
    await page.setViewportSize({width, height});
    const issues = [];
    for (const view of views) {
      await page.locator(`.nav-tab[data-view="view${view}"]`).click();
      await screenshot(page, `${view.toLowerCase()}-${width}x${height}`);
      issues.push(...await inspectUsability(page, `${width}x${height}/${view}`));
      if (view === 'Keyboard') {
        await page.locator('#keyboardModeNumpad').click();
        await screenshot(page, `numpad-${width}x${height}`);
        issues.push(...await inspectUsability(page, `${width}x${height}/Numpad`));
        await page.locator('#keyboardModeKeys').click();
      }
    }
    for (const [trigger, id] of [['btnTheme', 'themeModal'], ['btnSettings', 'settingsModal']]) {
      if (trigger === 'btnTheme') await openTheme(page); else await page.locator(`#${trigger}`).click();
      await screenshot(page, `${id}-${width}x${height}`);
      issues.push(...await inspectUsability(page, `${width}x${height}/${id}`));
      await page.keyboard.press('Escape');
      if (trigger === 'btnTheme') await page.keyboard.press('Escape');
    }
    assert.deepEqual(issues, [], 'responsive, contrast and touch target audit');
  }, true);
}

test('all seven themes keep control text readable on every remote view and settings dialog', async page => {
  const issues = [];
  for (const theme of ['bloom', 'resonance', 'companion', 'clay', 'glass', 'soft', 'ink']) {
    for(const appearance of ['light','dark']) {
    await openTheme(page);
    await page.locator(`.th-theme-choice[data-theme-id="${theme}"]`).click();
    await page.locator('#th-picker-appearance').selectOption(appearance);
    await page.evaluate(()=>window.TouchHelmThemes.ready);
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    for (const view of views) {
      await page.locator(`.nav-tab[data-view="view${view}"]`).click();
      if (view === 'Trackpad') await screenshot(page, `theme-${theme}-trackpad`);
      issues.push(...await inspectUsability(page, `${theme}/${appearance}/${view}`));
    }
    await page.locator('#btnSettings').click();
    await screenshot(page, `theme-${theme}-settings`);
    issues.push(...await inspectUsability(page, `${theme}/${appearance}/settings`));
    await page.keyboard.press('Escape');
    }
  }
  assert.deepEqual(issues, [], 'seven-theme accessibility audit');
}, true);

test('living visual matrix covers every theme, appearance, phone size and desktop panel',async(page,context)=>{
  const issues=[],themes=['bloom','companion','resonance','clay','glass','soft','ink'];
  await page.goto(origin+'/index.html?preview=1');
  await page.waitForFunction(()=>window.touchhelm?.isConnected&&window.TouchHelmEffects);
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmDesktopPreview);
  for(const theme of themes)for(const appearance of ['light','dark']){
    await page.bringToFront();
    await page.evaluate(async({theme,appearance})=>{TouchHelmThemes.apply(theme,{appearance,effects:'off',motion:'reduced'},false);await TouchHelmThemes.ready;},{theme,appearance});
    for(const [width,height]of [[320,568],[360,640],[390,844],[844,390],[390,420],[1440,900]]){
      await page.setViewportSize({width,height});
      for(const view of views){
        await page.locator(`#tab${view}`).click();issues.push(...await inspectUsability(page,`${theme}/${appearance}/${width}x${height}/${view}`));
        if(view==='Presenter'){
          const overlap=await page.evaluate(()=>{const n=document.querySelector('#btnSlideNext').getBoundingClientRect(),s=document.querySelector('#presentationDisplay').getBoundingClientRect();return n.bottom>s.top;});
          if(overlap)issues.push(`${theme}/${width}: Presenter monitor overlap`);
        }
        if(view==='Remote'){
          for(const state of ['remote_control','remote_view','remote_connecting','remote_paused','remote_unavailable']){
            await page.evaluate(state=>TouchHelmDemo.setState(state),state);
            issues.push(...await inspectUsability(page,`${theme}/${appearance}/${width}x${height}/${state}`));
            if(width===390&&height===844&&state==='remote_control')await screenshot(page,`remote-${theme}-${appearance}-control`);
          }
          await page.evaluate(()=>{touchhelm.remote.reset('stopped','Interface preview.');remoteCastGuide.hidden=false;});
          issues.push(...await inspectUsability(page,`${theme}/${appearance}/${width}x${height}/casting`));
          await page.evaluate(()=>remoteCastGuide.hidden=true);
        }
        if(width===390&&height===844)await screenshot(page,`living-${theme}-${appearance}-${view.toLowerCase()}`);
      }
    }
    await desktop.bringToFront();
    await desktop.evaluate(async({theme,appearance})=>{TouchHelmThemes.apply(theme,{appearance,effects:'off',motion:'reduced'},false);await TouchHelmThemes.ready;},{theme,appearance});
    for(const width of [820,1280]){
      await desktop.setViewportSize({width,height:820});
      for(const panel of ['pairing','devices','settings','diagnostics']){
        await desktop.locator(`[data-panel="${panel}"]`).click();
        const errors=await desktop.evaluate(()=>{const scope=document.querySelector('[data-page]:not([hidden])'),issues=[];if(document.documentElement.scrollWidth>innerWidth+1)issues.push('horizontal overflow');for(const b of scope.querySelectorAll('button,select,input:not([type=checkbox]):not([type=range])')){if(!b.getClientRects().length)continue;const r=b.getBoundingClientRect();if(r.width<43.5||r.height<43.5)issues.push(`small target ${b.id}: ${r.width}x${r.height}`);if(r.left<0||r.right>innerWidth+1)issues.push(`clipped ${b.id}`);}return issues;});
        issues.push(...errors.map(error=>`${theme}/${appearance}/desktop${width}/${panel}: ${error}`));
        if(width===1280&&panel==='pairing')await screenshot(desktop,`living-${theme}-${appearance}-desktop`);
      }
    }
    if(['bloom','companion','resonance','clay'].includes(theme)&&appearance==='dark'){
      await page.bringToFront();
      await page.setViewportSize({width:390,height:844});await page.locator('#tabTrackpad').click();
      await page.evaluate(()=>{TouchHelmThemes.apply(TouchHelmThemes.state.id,{effects:'rich',motion:'system'},false);TouchHelmEffects.reset();});
      await page.waitForFunction(()=>TouchHelmEffects.diagnostics.idle>0,{timeout:4000});
      await page.waitForTimeout(900);
      if(captureScreenshots){fs.mkdirSync(artifactDir,{recursive:true});await page.screenshot({path:path.join(artifactDir,`living-${theme}-idle.png`)});}
      await page.evaluate(()=>TouchHelmEffects.react(document.querySelector('#btnLeftClick'),{kind:'press'}));
      await page.waitForTimeout(170);
      if(captureScreenshots)await page.screenshot({path:path.join(artifactDir,`living-${theme}-touch.png`)});
    }
  }
  for(const state of ['seeking','closing','tailscale_ready','tailscale_permission','tailscale_reconnect']){
    await page.bringToFront();
    await page.evaluate(state=>TouchHelmDemo.setState(state),state);await desktop.evaluate(state=>TouchHelmDesktopPreview.setState(state),state);
    if(state.startsWith('tailscale_')){await desktop.bringToFront();await desktop.locator('[data-panel=pairing]').click();await screenshot(desktop,`living-${state}`);}
  }
  await desktop.close();assert.deepEqual(issues,[],'full living theme/layout matrix');
},true);

test('Remote keeps a browser-only casting guide and refuses insecure streaming',async page=>{
  await page.locator('#tabRemote').click();
  await page.locator('[data-remote-mode="control"]').click();
  assert.match(await page.locator('#remoteStatus').textContent(),/trusted HTTPS/i);
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='remote_start').length),0);
  await page.locator('#remoteCastOpen').click();
  assert.ok(await page.locator('#remoteCastGuide').isVisible());
  assert.match(await page.locator('#remoteCastGuide').textContent(),/Google Cast|Miracast/);
});

async function fakeRemote(page,mode='control'){
  await page.locator('#tabRemote').click();
  await page.evaluate(mode=>{
    const r=touchhelm.remote;r.session='fixture';r.revision='geometry1';r.mode=mode;r.state='live';r.geometry={width:1920,height:1080};r.serverState='live';r.render();
    Object.defineProperty(remoteVideo,'videoWidth',{get:()=>1920,configurable:true});Object.defineProperty(remoteVideo,'videoHeight',{get:()=>1080,configurable:true});
    __packets.length=0;
  },mode);
}

test('Remote cursor removes the SVG hidden attribute for measured live positions',async page=>{
  await fakeRemote(page);
  await page.evaluate(()=>touchhelm.remote.handle({type:'remote_cursor',session_id:'fixture',revision:'geometry1',visible:true,x:.5,y:.5}));
  assert.ok(await page.locator('#remoteCursor').isVisible());
  await page.evaluate(()=>touchhelm.remote.handle({type:'remote_cursor',session_id:'fixture',revision:'geometry1',visible:false}));
  assert.equal(await page.locator('#remoteCursor').isVisible(),false);
});

test('Media and Remote share pending audio state and rollback failures',async page=>{
  await fakeRemote(page);
  await page.evaluate(()=>{touchhelm.remote.audioConfirmed=false;touchhelm.remote.caps={audio:true};touchhelm.remote.render();});
  await page.locator('#tabMedia').click();
  await page.locator('#mediaPcAudio').check();
  assert.equal(await page.locator('#remoteAudio').isChecked(),true);
  assert.equal(await page.locator('#remoteAudio').isDisabled(),true);
  const request=await page.evaluate(()=>__packets.find(p=>p.type==='remote_config'));
  assert.equal(request.audio,true);assert.equal(request.session_id,'fixture');
  await page.evaluate(()=>touchhelm.remote.handle({type:'remote_result',success:false,request:'remote_config',message:'Audio device unavailable'}));
  assert.equal(await page.locator('#mediaPcAudio').isChecked(),false);
  assert.equal(await page.locator('#remoteAudio').isChecked(),false);
});

test('Hidden viewer stays connected on incoming packets when mobile stops decoding',async page=>{
  await fakeRemote(page);
  await page.locator('#tabMedia').click();
  await page.evaluate(async()=>{
    const r=touchhelm.remote;r.lastFrame=performance.now()-20000;r.previousFrames=0;r.previousVideoPackets=0;
    r.pc={connectionState:'connected',getStats:async()=>new Map([['video',{type:'inbound-rtp',kind:'video',framesDecoded:0,packetsReceived:40}]]),close(){}};
    await r.tick();
  });
  assert.equal(await page.evaluate(()=>touchhelm.remote.session),'fixture');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='remote_pause').length),0);
});

test('Remote fullscreen requests landscape and unlocks orientation on exit',async page=>{
  await fakeRemote(page);
  await page.evaluate(()=>{
    window.__rotations=[];
    Object.defineProperty(document,'fullscreenElement',{configurable:true,get:()=>window.__fullscreenNode||null});
    remoteStage.requestFullscreen=async()=>{window.__fullscreenNode=remoteStage;document.dispatchEvent(new Event('fullscreenchange'));};
    document.exitFullscreen=async()=>{window.__fullscreenNode=null;document.dispatchEvent(new Event('fullscreenchange'));};
    Object.defineProperty(screen.orientation,'lock',{configurable:true,value:async value=>__rotations.push(value)});
    Object.defineProperty(screen.orientation,'unlock',{configurable:true,value:()=>__rotations.push('unlock')});
  });
  await page.locator('#remoteFullscreen').click();
  assert.deepEqual(await page.evaluate(()=>__rotations),['landscape']);
  await page.evaluate(()=>touchhelm.remote.fullscreen());
  assert.deepEqual(await page.evaluate(()=>__rotations),['landscape','unlock']);
});

test('Phone Return twice remains a draft and uses safe PC line breaks',async page=>{
  await page.locator('#typeInput').focus();
  await input(page,'Two lines','insertText','Two lines');
  await page.locator('#typeInput').press('Enter');await page.locator('#typeInput').press('Enter');
  assert.equal(await page.locator('#typeInput').inputValue(),'Two lines\n\n');
  const packets=await page.evaluate(()=>__packets);
  assert.equal(packets.filter(p=>p.type==='key'&&p.key==='enter').length,0);
  assert.ok(packets.filter(p=>p.type==='text'&&p.text.includes('\n')).every(p=>p.newline_mode==='shift_enter'));
});

test('Existing seven themes generate bounded procedural reactions without background photos',async page=>{
  for(const theme of ['bloom','companion','resonance','clay','glass','soft','ink']){
    await page.evaluate(async theme=>{touchhelm.switchView('viewTrackpad');TouchHelmThemes.apply(theme,{appearance:'dark',effects:'rich',motion:'full'},false);await TouchHelmThemes.ready;TouchHelmEffects.reset();},theme);
    await page.waitForFunction(theme=>TouchHelmEffects.diagnostics.theme===theme,theme);
    assert.equal(await page.evaluate(()=>TouchHelmEffects.react(document.querySelector('#btnLeftClick'),{kind:'press'})),true);
    const info=await page.evaluate(()=>({count:document.querySelectorAll('.th-effect:not([hidden])').length,procedural:TouchHelmEffects.diagnostics.procedural,background:getComputedStyle(touchSurface,'::before').backgroundImage}));
    assert.ok(info.count>0&&info.count<=8);assert.equal(info.procedural,true);assert.equal(info.background.includes('.webp'),false);
  }
});

test('Remote view mode cannot send input and direct coordinates stay scoped',async page=>{
  await fakeRemote(page,'view');
  assert.equal(await page.evaluate(()=>touchhelm.remote.input({type:'key',key:'a'})),false);
  assert.ok(await page.locator('#remoteLeft').isDisabled());
  await page.evaluate(()=>{touchhelm.remote.mode='control';touchhelm.remote.render();remoteInteraction.value='direct';});
  const box=await page.locator('#remoteStage').boundingBox();
  await page.locator('#remoteStage').tap({position:{x:box.width/2,y:box.height/2}});
  const commands=await page.evaluate(()=>__packets.filter(p=>p.type==='remote_input'));
  assert.ok(commands.every(p=>p.session_id==='fixture'&&p.revision==='geometry1'));
  assert.equal(commands.at(-1).command.type,'click');
  assert.ok(Math.abs(commands[0].command.x-.5)<.02);
});

test('Remote text Return stays multiline and Stop releases drag and clears video',async page=>{
  await fakeRemote(page);
  await page.locator('#remoteTyping summary').click();
  await page.locator('#remoteText').fill('first');await page.locator('#remoteText').press('Enter');await page.locator('#remoteText').press('b');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.command?.type==='text').length),0);
  await page.locator('#remoteTextSend').click();
  assert.equal(await page.evaluate(()=>__packets.find(p=>p.command?.type==='text').command.text),'first\nb');
  await page.locator('#remoteDrag').click();await page.locator('#remoteStop').click();
  assert.equal(await page.evaluate(()=>touchhelm.remote.session),'');
  assert.equal(await page.evaluate(()=>remoteVideo.srcObject),null);
  assert.equal(await page.locator('#remoteDrag').getAttribute('aria-pressed'),'false');
});

test('Leaving Remote keeps the stream without transmitting its draft on return',async page=>{
  await fakeRemote(page);
  await page.locator('#remoteTyping summary').click();await page.locator('#remoteText').fill('private draft');
  await page.locator('#tabTrackpad').click();await page.locator('#tabRemote').click();
    assert.equal(await page.evaluate(()=>touchhelm.remote.session),'fixture');
    assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='remote_pause').length),0);
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.command?.type==='text').length),0);
  assert.equal(await page.locator('#remoteText').inputValue(),'private draft');
});

test('Remote restores its local draft without replay and honors Shift Enter preference',async page=>{
  await page.evaluate(()=>localStorage.setItem('touchhelm_remote_draft','saved\ndraft'));
  await page.reload();await page.waitForFunction(()=>touchhelm?.isConnected);
  assert.equal(await page.locator('#remoteText').inputValue(),'saved\ndraft');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.command?.type==='text'||p.type==='text').length),0);
  await fakeRemote(page);
  await page.evaluate(()=>{touchhelm.newlineMode='shift_enter';touchhelm.remote.input({type:'text',text:'a\nb'});});
  assert.equal(await page.evaluate(()=>__packets.find(p=>p.command?.type==='text').command.newline_mode),'shift_enter');
});

test('Wireless Display setup shows real progress, approval and completion states',async(page,context)=>{
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmDesktopPreview);
  await desktop.setViewportSize({width:820,height:820});
  await desktop.locator('[data-panel="settings"]').click();
  for(const [state,progress,message]of [['permission',null,'Approve the Windows administrator prompt.'],['installing',null,'Downloading optional feature…'],['installing',52,'Installing Wireless Display…'],['installed',100,'Wireless Display is installed.'],['permission_required',null,'Installation approval was cancelled.']]){
    await desktop.evaluate(({state,progress,message})=>TouchHelmDesktopPreview.setWirelessDisplayState({state,progress,message}),{state,progress,message});
    assert.equal(await desktop.locator('#wirelessDisplayStatus').textContent(),message);
    const active=['permission','installing'].includes(state);
    assert.equal(await desktop.locator('#wirelessDisplayProgress').isVisible(),active);
    if(active&&progress===null)assert.equal(await desktop.locator('#wirelessDisplayProgress').getAttribute('value'),null);
    if(active&&progress===52){await desktop.locator('#wirelessDisplayStatus').scrollIntoViewIfNeeded();await screenshot(desktop,'wireless-display-installing');}
    assert.equal(await desktop.locator('#installWirelessDisplay').isDisabled(),active||state==='installed');
  }
  await desktop.close();
});

test('Focused PC text updates the phone without echo and protects concurrent drafts',async page=>{
  await page.evaluate(()=>{
    touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r1',text:'Typed on PC',editable:true});
  });
  assert.equal(await page.locator('#typeInput').inputValue(),'Typed on PC');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='text'||p.type==='key'||p.action==='write').length),0);
  await page.locator('#typeInput').fill('Phone edit');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='text_sync'&&p.action==='write').at(-1).revision),'r1');
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:false,message:'PC text changed. Review the PC text.'}));
  assert.equal(await page.locator('#typeInput').inputValue(),'Phone edit');
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r2',text:'Concurrent PC edit',editable:true}));
  assert.equal(await page.locator('#typeInput').inputValue(),'Phone edit');
  await page.locator('#usePCText').click();
  assert.equal(await page.locator('#typeInput').inputValue(),'Concurrent PC edit');
});

test('Two-way typing coalesces edits, waits for acknowledgement and preserves IME',async page=>{
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r1',text:'',editable:true}));
  await page.locator('#typeInput').fill('a');await page.locator('#typeInput').fill('abc');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write').length),1);
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r2',text:'a',editable:true}));
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write').at(-1).text),'abc');
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r3',text:'abc',editable:true}));
  await page.locator('#typeInput').evaluate(el=>{el.dispatchEvent(new CompositionEvent('compositionstart'));el.value='abc\n\n🙂';el.dispatchEvent(new InputEvent('input',{isComposing:true}));});
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write').length),2);
  await page.locator('#typeInput').evaluate(el=>el.dispatchEvent(new CompositionEvent('compositionend')));
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write').at(-1).text),'abc\n\n🙂');
});

test('Desktop connection selection reveals an actionable setup guide beside the QR',async(page,context)=>{
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmDesktopPreview);
  await desktop.locator('#connectionMode').selectOption('tailscale');
  assert.equal(await desktop.locator('#connectionSetupGuide').getAttribute('data-mode'),'tailscale');
  assert.match(await desktop.locator('#connectionSetupGuide').innerText(),/same account/i);
  assert.match(await desktop.locator('#connectionSetupGuide').innerText(),/8443|private HTTPS/i);
  await desktop.locator('#connectionMode').selectOption('local_ca');
  assert.match(await desktop.locator('#connectionSetupGuide').innerText(),/CA certificate/);
  await desktop.close();
});

test('PC text snapshots cannot erase typing that happened during a read',async page=>{
  await page.evaluate(()=>{touchhelm.textSync.reset();touchhelm.textSync.poll();});
  await page.locator('#typeInput').fill('New phone edit');
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',request_id:touchhelm.textSync.pending.request_id,available:true,field_id:'field',revision:'before',text:'',editable:true}));
  assert.equal(await page.locator('#typeInput').inputValue(),'New phone edit');
  assert.equal(await page.evaluate(()=>touchhelm.textSync.field),null);
});

test('Buffered edits to a linked PC field send only after explicit Send',async page=>{
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r1',text:'PC draft',editable:true}));
  await page.locator('#typeInput').focus();
  await page.evaluate(()=>{touchhelm.textSync.pending=null;touchhelm.textSync.poll();});
  await page.locator('#chkRealtimeTyping').uncheck();await page.locator('#typeInput').fill('Buffered phone edit');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write'||p.type==='text'||p.type==='key').length),0);
  await page.locator('#btnSendText').click();
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',request_id:touchhelm.textSync.pending.request_id,available:true,field_id:'field',revision:'r1',text:'PC draft',editable:true}));
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write').at(-1).text),'Buffered phone edit');
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r2',text:'Buffered phone edit',editable:true}));
  assert.equal(await page.locator('#typeInput').inputValue(),'');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='key').length),0);
});

test('Losing a linked PC field preserves the draft and never backspaces another app',async page=>{
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r1',text:'PC draft',editable:true}));
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:false,message:'Focus changed'}));
  await page.locator('#typeInput').fill('New draft');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.type==='key'||p.type==='text'||p.action==='write').length),0);
  assert.equal(await page.locator('#typeInput').inputValue(),'New draft');
});

test('Buffered Send waiting on a read preserves its draft if the PC field changed',async page=>{
  await typingView(page);
  await page.evaluate(()=>{
    touchhelm.textSync.receive({type:'text_state',available:true,field_id:'field',revision:'r1',text:'PC draft',editable:true});
    touchhelm.textSync.pending=null;touchhelm.textSync.poll();
  });
  await page.locator('#chkRealtimeTyping').uncheck();await page.locator('#typeInput').fill('Keep this phone draft');
  await page.locator('#btnSendText').click();
  await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',request_id:touchhelm.textSync.pending.request_id,available:true,field_id:'other-field',revision:'r2',text:'Different PC text',editable:true}));
  assert.equal(await page.locator('#typeInput').inputValue(),'Keep this phone draft');
  assert.equal(await page.evaluate(()=>__packets.filter(p=>p.action==='write'||p.type==='text'||p.type==='key').length),0);
  assert.equal(await page.evaluate(()=>touchhelm.textSync.conflict),true);
});

test('Text sync and pairing guides visual inspection',async(page,context)=>{
  const issues=[],desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmDesktopPreview);
  for(const theme of ['bloom','companion','resonance','clay','glass','soft','ink'])for(const appearance of ['light','dark']){
    await page.bringToFront();
    await page.evaluate(async({theme,appearance})=>{TouchHelmThemes.apply(theme,{appearance,effects:'off'},false);await TouchHelmThemes.ready;},{theme,appearance});
    for(const [width,height]of [[320,568],[360,640],[390,844],[844,390],[390,420]]){
      await page.setViewportSize({width,height});await page.locator('#typeInput').focus();
      await page.evaluate(()=>touchhelm.textSync.receive({type:'text_state',available:true,field_id:'sample',revision:'r1',text:'Sample PC text\nContinued on the phone',editable:true}));
      issues.push(...await inspectUsability(page,`${theme}/${appearance}/${width}x${height}/sync`));
      if(theme==='glass'&&appearance==='dark'&&width===390&&height===844)await screenshot(page,'text-sync-phone');
    }
    await desktop.bringToFront();
    await desktop.evaluate(async({theme,appearance})=>{TouchHelmThemes.apply(theme,{appearance,effects:'off'},false);await TouchHelmThemes.ready;},{theme,appearance});
    for(const width of [820,1280])for(const mode of ['local_ca','tailscale']){
      await desktop.setViewportSize({width,height:900});await desktop.locator('#connectionMode').selectOption(mode);
      const errors=await desktop.evaluate(()=>{
        const errors=[];if(document.documentElement.scrollWidth>innerWidth+1)errors.push('horizontal overflow');
        for(const node of connectionSetupGuide.querySelectorAll('button,select,input')){
          if(!node.getClientRects().length)continue;const r=node.getBoundingClientRect();
          if(r.width<43.5||r.height<43.5)errors.push(`small target ${node.id}`);
          if(r.right>innerWidth+1)errors.push(`clipped ${node.id}`);
        }
        return errors;
      });issues.push(...errors.map(x=>`${theme}/${appearance}/desktop${width}/${mode}: ${x}`));
      if(theme==='glass'&&appearance==='dark'&&width===1280)await screenshot(desktop,`pairing-guide-${mode}`);
    }
  }
  await desktop.close();assert.deepEqual(issues,[]);
},true);

test('AirControl chooser opens dedicated modes without starting a camera',async(page,context)=>{
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.locator('#switchControlMode').click();
  assert.equal(await desktop.locator('[data-page="home"]').isVisible(),true);
  await desktop.locator('#chooseAir').click();
  assert.equal(await desktop.locator('[data-page="aircontrol"]').isVisible(),true);
  assert.equal(await desktop.locator('#airCameraBadge').textContent(),'Camera off');
  await desktop.locator('#switchControlMode').click();await desktop.locator('#choosePhone').click();
  assert.equal(await desktop.locator('[data-page="pairing"]').isVisible(),true);
  await desktop.close();
});

test('AirControl ownership keeps the phone connected and drafts local until explicit Send',async page=>{
  await typingView(page);
  await page.evaluate(()=>{
    const client=touchhelm;
    client.ws.onmessage({data:JSON.stringify({type:'input_owner',owner:'aircontrol'})});
    window.__packets.length=0;
  });
  await page.locator('#typeInput').fill('kept during AirControl');
  assert.equal(await page.evaluate(()=>touchhelm.isConnected),true);
  assert.equal(await page.evaluate(()=>touchhelm.liveTypingPaused),true);
  assert.equal(await page.evaluate(()=>touchhelm.send({type:'click',button:'left'})),false);
  assert.equal(await page.evaluate(()=>touchhelm.send({type:'remote_query'})),true);
  await page.evaluate(()=>touchhelm.ws.onmessage({data:JSON.stringify({type:'input_owner',owner:'phone'})}));
  await page.locator('#typeInput').press('!');
  assert.deepEqual(await page.evaluate(()=>__packets.filter(p=>['text','key','click'].includes(p.type)||p.type==='text_sync'&&p.action!=='read')),[]);
  assert.match(await page.locator('#typeInput').inputValue(),/kept during AirControl/);
});

test('AirControl practice, mapping validation and animated guide reflect explicit state',async(page,context)=>{
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.locator('[data-panel="aircontrol"]').click();
  await desktop.evaluate(()=>TouchHelmAir.setPreview('practicing'));
  assert.equal(await desktop.locator('#airEnable').isEnabled(),true);
  await desktop.locator('#airGuideSelect').selectOption('pinch_index');
  assert.equal(await desktop.locator('#airGuideArt').getAttribute('data-gesture'),'pinch_index');
  await desktop.locator('[data-air-tab="mappings"]').click();
  assert.equal(await desktop.locator('[data-air-gesture="closed_fist"]').isDisabled(),true);
  await desktop.locator('[data-air-gesture="thumb_up"]').selectOption('right_click');
  await desktop.locator('#airSaveMappings').click();
  assert.match(await desktop.locator('#airMappingError').innerText(),/only one|already|duplicate/i);
  await desktop.close();
});

test('AirControl practice makes PC input status clear and keeps Enable reachable',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:820,height:620});
  await desktop.goto(origin+'/preview/desktop/?preview=1');await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.locator('[data-panel="aircontrol"]').click();
  await desktop.evaluate(()=>{
    TouchHelmAir.setPreview('practicing');
    TouchHelmAir.render({...TouchHelmAir.state,pose_score:.57,pose_name:null,gesture:'',action:'none',
      tracking_sources:{hand:true,face:false,hand_enabled:true,face_enabled:false}});
  });
  assert.match(await desktop.locator('#airCameraBadge').innerText(),/practice.*only/i);
  assert.match(await desktop.locator('#airTrackingState').innerText(),/face.*off/i);
  assert.doesNotMatch(await desktop.locator('#airDetected').innerText(),/57%|pose score/i);
  await desktop.locator('[data-air-tab="practice"]').click();
  const box=await desktop.locator('#airEnable').boundingBox();
  assert.ok(box&&box.y>=0&&box.y+box.height<=620,'Enable stays reachable in the sticky session heading');
  await desktop.close();
});

test('AirControl calibration shows a live finger and keeps its next action beside the preview',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:1120,height:800});
  await desktop.goto(origin+'/preview/desktop/?preview=1');await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.locator('[data-panel="aircontrol"]').click();
  await desktop.evaluate(()=>{
    TouchHelmAir.profile.mode='hand';TouchHelmAir.setPreview('calibrating');
    const hand=Array.from({length:21},()=>[.5,.5]);hand[8]=[.63,.28];
    const state={...TouchHelmAir.state,tracking:true,hand_points:hand,
      tracking_sources:{hand:true,face:false,hand_enabled:true,face_enabled:false}};
    TouchHelmAir.render(state);TouchHelmAir.draw(state);
  });
  assert.equal(await desktop.locator('.air-camera-column #airCaptureTarget').count(),1);
  assert.match(await desktop.locator('#airCalibrationStep').innerText(),/1 of 1/);
  await desktop.locator('#airFineCalibration').check();
  assert.match(await desktop.locator('#airCalibrationStep').innerText(),/1 of 5/);
  const capture=await desktop.locator('#airCaptureTarget').boundingBox();
  assert.ok(capture&&capture.y>=0&&capture.y+capture.height<=800,'Capture is visible before the camera preview');
  assert.equal(await desktop.locator('#airTrackedPointer').isVisible(),true);
  assert.equal(await desktop.locator('#airTrackedPointer').evaluate(n=>n.style.left),'63%');
  assert.ok(Math.abs(await desktop.locator('#airTrackedPointer').evaluate(n=>parseFloat(n.style.top))-28)<.01);
  await screenshot(desktop,'aircontrol-calibration-live-finger');
  await desktop.locator('[data-air-tab="settings"]').click();
  await desktop.locator('#airShowLandmarks').uncheck();
  await desktop.evaluate(()=>TouchHelmAir.draw({...TouchHelmAir.state,hand_points:Array.from({length:21},()=>[.7,.4])}));
  assert.equal(await desktop.locator('#airTrackedPointer').isVisible(),true);
  await desktop.evaluate(()=>TouchHelmAir.render({...TouchHelmAir.state,tracking:false,tracking_sources:{hand:false,face:false,hand_enabled:true,face_enabled:false}}));
  assert.equal(await desktop.locator('#airTrackedPointer').isVisible(),false);
  await desktop.evaluate(()=>{
    TouchHelmAir.render({...TouchHelmAir.state,tracking:true,calibration_points:['center','top_left']});
    const original=TouchHelmAir.previewAction.bind(TouchHelmAir);
    TouchHelmAir.previewAction=(action,data)=>{window.__lastAirAction={action,data};return original(action,data);};
  });
  await desktop.locator('#airFineCalibration').uncheck();await desktop.locator('#airCaptureTarget').click();
  assert.deepEqual(await desktop.evaluate(()=>__lastAirAction.data),{target:'center',quick:true});
  await desktop.close();
});

test('AirControl Start camera is reachable in the header and stopped sessions cannot enable input',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:820,height:620});
  await desktop.goto(origin+'/preview/desktop/?preview=1');await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.evaluate(()=>{TouchHelmDesktop.showPanel('aircontrol');TouchHelmAir.setPreview('ready');});
  assert.equal(await desktop.locator('.air-session-actions #airStart').count(),1);
  const button=await desktop.locator('#airStart').boundingBox();assert.ok(button&&button.y>=0&&button.y+button.height<=620);
  assert.equal(await desktop.locator('#airEnable').isVisible(),false);
  await desktop.locator('#airStart').click();
  assert.equal(await desktop.locator('#airStart').isVisible(),false);assert.equal(await desktop.locator('#airStop').isVisible(),true);
  await desktop.locator('#airStop').click();assert.equal(await desktop.locator('#airEnable').isVisible(),false);
  await desktop.close();
});

test('AirControl personal face calibration exposes activation and applies a tested action without stopping camera',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:1120,height:800});await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.evaluate(()=>{TouchHelmDesktop.showPanel('aircontrol');TouchHelmAir.profile.mode='head';TouchHelmAir.setPreview('practicing');TouchHelmAir.tab('practice');});
  await desktop.evaluate(()=>TouchHelmAir.draw({...TouchHelmAir.state,tracking_sources:{face:true,hand:false,face_enabled:true,hand_enabled:false}}));
  assert.equal(await desktop.locator('#airTrackedPointer').isVisible(),true);
  assert.match(await desktop.locator('#airTrackedPointer').innerText(),/Head pointer/);
  await desktop.locator('#airExpressionNeutral').click();
  assert.match(await desktop.locator('#airExpressionResult').innerText(),/relaxed.*captured/i);
  await desktop.locator('#airExpressionSelect').selectOption('smile');
  await desktop.locator('#airExpressionPractice').click();
  await desktop.locator('#airExpressionAction').selectOption('left_click');await desktop.locator('#airExpressionAssign').click();
  assert.equal(await desktop.evaluate(()=>TouchHelmAir.state.profile.bindings.smile),'left_click');
  assert.equal(await desktop.evaluate(()=>TouchHelmAir.state.camera_active),true);
  assert.match(await desktop.locator('#airExpressionResult').innerText(),/threshold|practice/i);
  await screenshot(desktop,'aircontrol-personal-face-calibration');
  await desktop.close();
});

test('AirControl practice keeps calibration feedback visible and separates readiness guidance',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:820,height:620});
  await desktop.goto(origin+'/preview/desktop/?preview=1');await desktop.waitForFunction(()=>window.TouchHelmAir);
  await desktop.evaluate(()=>{
    TouchHelmDesktop.showPanel('aircontrol');TouchHelmAir.setPreview('practicing');
    TouchHelmAir.render({...TouchHelmAir.state,message:'Relaxed face captured. Hold your selected expression, then capture it.',practice_ready:false});
  });
  assert.match(await desktop.locator('#airMessage').innerText(),/Relaxed face captured/);
  assert.match(await desktop.locator('#airPracticeResult').textContent(),/Windows input is off/);
  await desktop.evaluate(()=>TouchHelmAir.render({...TouchHelmAir.state,message:'Personal expression threshold captured. Choose its action and test it in practice.',practice_ready:true,practice_frames:20,practice_actions:1}));
  assert.match(await desktop.locator('#airMessage').innerText(),/threshold captured/);
  assert.match(await desktop.locator('#airPracticeResult').textContent(),/Enable PC control/);
  await screenshot(desktop,'aircontrol-practice-feedback');await desktop.close();
});

test('AirControl Head is default and its action dock explains drag and releases it in practice',async(page,context)=>{
  const desktop=await context.newPage();await desktop.setViewportSize({width:1120,height:800});
  await desktop.goto(origin+'/preview/desktop/?preview=1');await desktop.waitForFunction(()=>window.TouchHelmAir);
  assert.equal(await desktop.evaluate(()=>TouchHelmAir.profile.mode),'head');
  await desktop.evaluate(()=>{TouchHelmDesktop.showPanel('aircontrol');TouchHelmAir.setPreview('practicing');});
  assert.equal(await desktop.locator('#airHeadActions').isVisible(),true);
  assert.equal(await desktop.locator('#airGuideArt').getAttribute('data-gesture'),'head');
  await desktop.locator('[data-air-dwell=right]').click();
  assert.equal(await desktop.locator('[data-air-dwell=right]').getAttribute('aria-pressed'),'true');
  await desktop.locator('[data-air-dwell=drag]').click();
  assert.match(await desktop.locator('#airDwellStatus').innerText(),/settle.*hold.*drop/i);
  await desktop.evaluate(()=>TouchHelmAir.render({...TouchHelmAir.state,dragging:true}));
  assert.match(await desktop.locator('#airDwellStatus').innerText(),/held/i);
  await desktop.locator('#airReleaseDrag').click();
  assert.equal(await desktop.evaluate(()=>TouchHelmAir.state.dragging),false);
  await screenshot(desktop,'aircontrol-head-actions');
  await desktop.locator('[data-air-mode=hand]').click();
  assert.equal(await desktop.locator('#airHeadActions').isVisible(),false);
  await desktop.close();
});

test('AirControl theme and desktop scaling visual matrix',async(page,context)=>{
  const desktop=await context.newPage();await desktop.goto(origin+'/preview/desktop/?preview=1');
  await desktop.waitForFunction(()=>window.TouchHelmAir);
  const issues=[];
  for(const theme of ['bloom','companion','resonance','clay','glass','soft','ink'])for(const appearance of ['light','dark']){
    await desktop.evaluate(async({theme,appearance})=>{TouchHelmThemes.apply(theme,{appearance,effects:'off',motion:'reduced'},false);await TouchHelmThemes.ready;},{theme,appearance});
    for(const [width,height]of [[820,620],[1120,800],[1440,900]]){
      await desktop.setViewportSize({width,height});
      for(const panel of ['home','aircontrol']){
        await desktop.evaluate(panel=>TouchHelmDesktop.showPanel(panel),panel);
        if(panel==='aircontrol')await desktop.evaluate(()=>TouchHelmAir.setPreview('practicing'));
        for(const tab of panel==='aircontrol'?['controls','mappings','practice','settings']:['home']){
          if(tab!=='home')await desktop.locator(`[data-air-tab=${tab}]`).click();
          const errors=await desktop.evaluate(()=>{
            const result=[],scope=document.querySelector('[data-page]:not([hidden])');
            if(document.documentElement.scrollWidth>innerWidth+1)result.push('horizontal page overflow');
            for(const node of scope.querySelectorAll('button,select,input:not([type=checkbox]):not([type=range])')){
              if(!node.getClientRects().length)continue;const r=node.getBoundingClientRect();
              if(r.width<43.5||r.height<43.5)result.push(`small target ${node.id}: ${r.width}x${r.height}`);
              if(r.left<0||r.right>innerWidth+1)result.push(`clipped ${node.id}`);
            }
            return result;
          });issues.push(...errors.map(x=>`${theme}/${appearance}/${width}/${tab}: ${x}`));
          if(theme==='glass'&&appearance==='dark'&&width===1120)await screenshot(desktop,'aircontrol-'+tab);
        }
      }
    }
  }
  await desktop.setViewportSize({width:1120,height:800});
  for(const state of ['setup_required','calibrating','practicing','active','paused','tracking_lost','unavailable']){
    await desktop.evaluate(state=>{TouchHelmDesktop.showPanel('aircontrol');TouchHelmAir.setPreview(state);TouchHelmAir.tab('controls');},state);
    await screenshot(desktop,'aircontrol-state-'+state);
  }
  await desktop.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await desktop.locator('.guide-tip').evaluate(el=>getComputedStyle(el).animationName),'none');
  await desktop.close();assert.deepEqual(issues,[]);
},true);

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  let failed = 0;
  const selectedTests = tests.filter(test => (!behaviorOnly || !test.visual)
    && (!nameFilter || new RegExp(nameFilter, 'i').test(test.name)));
  assert.ok(selectedTests.length, 'test filter must match at least one check');
  try {
    const executablePath = process.env.CHROMIUM_EXECUTABLE ||
      (fs.existsSync(chromium.executablePath()) ? chromium.executablePath() : 'C:/Program Files/Google/Chrome/Application/chrome.exe');
    browser = await chromium.launch({executablePath, headless: true});
    for (const {name, run} of selectedTests) {
      posts.length = 0;
      let context;
      try {
        const fixtureResult = await fixture(); context = fixtureResult.context;
        await run(fixtureResult.page, context);
        assert.deepEqual(fixtureResult.errors, [], 'no uncaught browser errors during interaction');
        console.log(`PASS ${name}`);
      } catch (error) {
        failed++; console.error(`FAIL ${name}\n  ${error.stack || error}`);
      } finally { await context?.close(); }
    }
    console.log(`${selectedTests.length - failed}/${selectedTests.length} passed; ${failed} failed`);
  } finally {
    await browser?.close(); await new Promise(resolve => server.close(resolve));
  }
  process.exitCode = failed ? 1 : 0;
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
