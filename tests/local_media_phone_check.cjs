/* Actual WebRTC media after public shutdown; generated tracks, never PC capture. */
const {chromium}=require('playwright'),fs=require('node:fs');
(async()=>{let raw='';for await(const chunk of process.stdin)raw+=chunk;const {url}=JSON.parse(raw),report={};let browser,page,stage='launch';
 try{
  const executablePath=fs.existsSync(chromium.executablePath())?chromium.executablePath():'C:/Program Files/Google/Chrome/Application/chrome.exe';
  browser=await chromium.launch({executablePath,headless:true});page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];page.on('pageerror',error=>errors.push(error.name));
  stage='pair';await page.goto(url,{waitUntil:'networkidle',timeout:45000});await page.waitForFunction(()=>window.TouchHelmBrowserLink?.settled,null,{timeout:35000});
  report.gate_allowed=await page.evaluate(()=>TouchHelmBrowserLink.allowed);if(!report.gate_allowed)throw Error('Pairing failed');
  await page.locator('#pinInput').fill('5678');await page.locator('#pinInput').press('Enter');await page.waitForFunction(()=>touchhelm.isConnected,null,{timeout:15000});
  let requests=0;const requestPaths=[];await page.route('**/*',route=>{requests++;requestPaths.push(new URL(route.request().url()).pathname);return route.abort();});
  report.secure_after_shutdown=await page.evaluate(()=>isSecureContext&&location.protocol==='https:');
  stage='capabilities';await page.waitForFunction(()=>touchhelm.remote.caps?.secure&&touchhelm.remote.caps?.enabled,null,{timeout:10000});report.secure_media_allowed=true;
  await page.locator('#tabRemote').click();stage='video';await page.locator('[data-remote-mode="view"]').click();
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&remoteVideo.videoWidth>0,null,{timeout:25000});report.video_after_shutdown=true;
  stage='video_audio';await page.locator('#remoteAudio').check();await page.waitForFunction(async()=>{if(!touchhelm.remote.audioConfirmed)return false;const stats=await touchhelm.remote.pc.getStats();return [...stats.values()].some(value=>value.type==='inbound-rtp'&&value.kind==='audio'&&value.packetsReceived>0);},null,{timeout:15000});report.audio_with_video_after_shutdown=true;
  stage='stop_screen';await page.locator('#remoteStop').click();await page.waitForFunction(()=>!touchhelm.remote.session);await page.waitForTimeout(700);
  await page.locator('#tabMedia').click();stage='audio_only';await page.locator('#mediaPcAudio').check();
  await page.waitForFunction(async()=>{const remote=touchhelm.remote,pc=remote.pc,session=remote.session;if(remote.mode!=='audio'||remote.state!=='live'||!remote.audioConfirmed||!pc||!session)return false;const stats=await pc.getStats();return remote.pc===pc&&remote.session===session&&remote.mode==='audio'&&!!remoteVideo.srcObject&&remoteVideo.srcObject.getVideoTracks().length===0&&[...stats.values()].some(value=>value.type==='inbound-rtp'&&value.kind==='audio'&&value.packetsReceived>0);},null,{timeout:25000});
  report.audio_only_after_shutdown=true;
  report.control_survives_media=await page.evaluate(()=>touchhelm.send({type:'text',text:'synthetic direct control'}));
  await page.evaluate(()=>touchhelm.remote.stop());report.no_http_requests=requests===0;if(requests)report.request_paths=requestPaths;report.no_script_errors=errors.length===0;
 }catch(error){report.error_type=error.name;report.error_message=String(error.message).replace(/https?:\/\/\S+/g,'[url]').slice(0,600);report.failure_stage=stage;if(page)report.media_state=await page.evaluate(()=>({connected:!!window.touchhelm?.isConnected,secure:isSecureContext,protocol:location.protocol,state:window.touchhelm?.remote?.state,message:document.getElementById('remoteStatus')?.textContent})).catch(()=>({}));}
 finally{await browser?.close();}
 process.stdout.write(JSON.stringify(report));process.exitCode=Object.values(report).every(value=>value===true)&&report.video_after_shutdown?0:1;
})();
