/* Real Windows capture -> real browser WebRTC. Input is mocked in the host.
 * The probe certificate is ignored only here; this does NOT verify trusted pairing.
 */
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const python=process.env.TOUCHHELM_PYTHON||'D:/Mouse/.venv/Scripts/python.exe';
const host=spawn(python,['-u','-m','tests.remote_transport_host'],{cwd:root,windowsHide:true});
let output='',errors='';host.stderr.on('data',v=>errors+=v);
const ready=new Promise((resolve,reject)=>{
 const timer=setTimeout(()=>reject(new Error('Probe host timeout: '+errors)),30000);
 host.stdout.on('data',v=>{output+=v;const row=output.split(/\r?\n/).find(v=>v.startsWith('{"probe_url"'));if(row){clearTimeout(timer);resolve(JSON.parse(row));}});
 host.on('exit',code=>{clearTimeout(timer);reject(new Error(`Host exited ${code}: ${errors}`));});
});
(async()=>{
 let browser,context,address;
 try{
  address=await ready;
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844},serviceWorkers:'block'});
  const page=await context.newPage(),pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
  await page.goto(address.probe_url);
  await page.waitForSelector('#pinInput', {state:'visible'}).catch(()=>{});
  await page.evaluate(()=>{touchhelm.authPin='5678';touchhelm.authenticate();});
  await page.waitForFunction(()=>touchhelm.isConnected);
  await page.evaluate(()=>touchhelm.ws.addEventListener('close',e=>console.error('MAIN WS CLOSED',e.code,e.reason)));
  page.on('console',m=>{if(m.text().startsWith('MAIN WS CLOSED'))console.error(m.text());});
  await page.locator('#tabRemote').click();
  await page.waitForFunction(()=>touchhelm.remote.caps?.enabled);
  await page.locator('[data-remote-mode="view"]').click();
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&document.getElementById('remoteVideo').videoWidth>0,null,{timeout:30000}).catch(async error=>{
    console.error('PROBE STATE',await page.evaluate(()=>JSON.stringify({state:touchhelm.remote.state,status:remoteStatus.textContent,session:!!touchhelm.remote.session,pc:touchhelm.remote.pc?.connectionState,ice:touchhelm.remote.pc?.iceConnectionState,caps:touchhelm.remote.caps,video:remoteVideo.videoWidth})));
    throw error;
  });
  await page.waitForTimeout(3000);
  const video=await page.evaluate(()=>({state:touchhelm.remote.state,width:remoteVideo.videoWidth,height:remoteVideo.videoHeight,stats:remoteStats.textContent,latency:remoteLatency.textContent}));
  assert.equal(video.state,'live');assert.ok(video.width>0&&video.height>0);console.log('REAL VIDEO',JSON.stringify(video));
  assert.ok(video.height>=1080,'default Clear delivers desktop detail');
  await page.locator('#remoteQuality').selectOption('detail');
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&remoteVideo.videoHeight===1440,null,{timeout:15000});
  console.log('DETAIL',await page.evaluate(()=>JSON.stringify({width:remoteVideo.videoWidth,height:remoteVideo.videoHeight,stats:remoteStats.textContent})));
  if(!process.argv.includes('--lifecycle')){
  await page.locator('#remoteAudio').evaluate(el=>{el.checked=true;el.dispatchEvent(new Event('change'));});
  await page.waitForTimeout(1500);
  console.log('AUDIO',await page.evaluate(()=>JSON.stringify({enabled:remoteAudio.checked,message:remoteStatus.textContent,audioTracks:remoteVideo.srcObject.getAudioTracks().length})));
  const receivedAudio=await page.evaluate(async()=>{
    const stats=await touchhelm.remote.pc.getStats();return [...stats.values()].filter(s=>s.type==='inbound-rtp'&&s.kind==='audio').reduce((n,s)=>n+(s.packetsReceived||0),0);
  });
  assert.ok(receivedAudio>0,'browser received Opus audio packets');console.log('AUDIO PACKETS',receivedAudio);
  }
  await page.locator('#remoteQuality').selectOption('saver');
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&remoteVideo.videoHeight<=540,null,{timeout:10000});
  await page.locator('#remoteMode').selectOption('control');
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&touchhelm.remote.mode==='control');
  await page.locator('#remoteLeft').click();
  if(!process.argv.includes('--stop-only')){
  await page.locator('#tabTrackpad').click();
  await page.waitForTimeout(1500);
  assert.equal(await page.evaluate(()=>touchhelm.isConnected),true,'main connection survives leaving Remote');
  assert.ok(await page.evaluate(()=>touchhelm.remote.session),'Remote stream survives tab switching');
  await page.locator('#tabRemote').click();
  }
  await page.locator('#remoteStop').click();
  await page.waitForTimeout(1500);
  for(let i=0;i<12;i++){
    await page.reload();await page.waitForFunction(()=>touchhelm.isConnected,null,{timeout:10000});
    assert.equal(await page.locator('#pinModal').getAttribute('class').then(v=>v?.includes('open')),false,'refresh keeps pairing without lockout');
  }
  console.log('PASS twelve authenticated refreshes without PIN lockout');
  await page.waitForFunction(()=>!touchhelm.remote.session);
  await page.waitForTimeout(2000);
  assert.equal(await page.evaluate(()=>touchhelm.isConnected),true,'Stop preserves main connection');
  await page.evaluate(()=>touchhelm.send({type:'ping',t:Date.now()}));
  await page.locator('#tabRemote').click();
  await page.locator('[data-remote-mode="view"]').click();
  await page.waitForFunction(()=>touchhelm.remote.state==='live',null,{timeout:30000});
  await page.locator('#remoteStop').click();
  assert.deepEqual(pageErrors,[]);console.log('PASS capture, WebRTC video, optional audio negotiation, quality change, mode change and stop; PC input mocked.');
 }finally{
  if(context&&address)await context.request.get(address.probe_url+'/shutdown',{headers:{'X-Probe-Token':address.token}}).catch(()=>{});
  await browser?.close();
  await new Promise(resolve=>{if(host.exitCode!==null)return resolve();host.once('exit',resolve);setTimeout(()=>{host.kill();resolve();},10000);});
 }
})().catch(e=>{console.error(e.stack,errors,output);host.kill();process.exitCode=1;});
