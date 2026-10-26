/* Synthetic host only. URL arrives on stdin and is never logged. */
const {chromium}=require('playwright'),fs=require('node:fs');
(async()=>{let raw='';for await(const chunk of process.stdin)raw+=chunk;const {url}=JSON.parse(raw);let browser;const report={};
 try{
  const executablePath=fs.existsSync(chromium.executablePath())?chromium.executablePath():'C:/Program Files/Google/Chrome/Application/chrome.exe';
  browser=await chromium.launch({executablePath,headless:true});const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];page.on('pageerror',error=>errors.push(error.name));
  await page.goto(url,{waitUntil:'networkidle',timeout:45000});await page.waitForFunction(()=>window.TouchHelmBrowserLink?.settled,null,{timeout:35000});
  report.gate_allowed=await page.evaluate(()=>TouchHelmBrowserLink.allowed);
  if(!report.gate_allowed){report.gate_error=await page.locator('.browser-link-gate p').innerText();throw Error('Gate failed');}
  report.secure_context=await page.evaluate(()=>isSecureContext);report.fragment_removed=new URL(page.url()).hash==='';
  await page.locator('#pinInput').fill('5678');await page.locator('#pinInput').press('Enter');await page.waitForFunction(()=>window.touchhelm?.isConnected,null,{timeout:15000});report.pin_connected=true;
  // Kill/reject every future network request in the browser. Only the existing
  // direct UDP/DTLS peer remains; settings and artwork must not use HTTP.
  let requests=0;await page.route('**/*',route=>{requests++;return route.abort();});
  report.data_channel_only=await page.evaluate(()=>touchhelm.ws===TouchHelmBrowserLink.transport&&TouchHelmBrowserLink.peer.getConfiguration().iceServers.length===0);
  report.local_settings=await page.evaluate(async()=>{const response=await TouchHelmBrowserLink.fetch('/api/config',{method:'POST',body:JSON.stringify({mouse_sensitivity:2.2})});return response.ok&&(await response.json()).success;});
  report.local_artwork=await page.evaluate(async()=>{const response=await TouchHelmBrowserLink.fetch('/api/assets/synthetic-art');return response.ok&&(await response.arrayBuffer()).byteLength>100000;});
  report.security_changes_denied=await page.evaluate(async()=>{const response=await TouchHelmBrowserLink.fetch('/api/config',{method:'POST',body:JSON.stringify({require_pin:false})});return response.status===400;});
  report.typed_packet_sent=await page.evaluate(()=>touchhelm.send({type:'text',text:'synthetic direct control'}));
  await page.evaluate(()=>TouchHelmThemes.apply('ink',{appearance:'light'},false));await page.waitForTimeout(1500);
  report.theme_after_relay_stops=await page.evaluate(()=>document.querySelector('#th-active-theme').href.startsWith('blob:'));
  report.no_http_requests=requests===0;report.no_script_errors=errors.length===0;
  await page.evaluate(()=>TouchHelmBrowserLink.transport.close());await page.waitForFunction(()=>!touchhelm.isConnected,null,{timeout:5000});
  report.no_relay_fallback=await page.evaluate(()=>!TouchHelmBrowserLink.allowed&&TouchHelmBrowserLink.transport.readyState===3);
 }catch(error){report.error_type=error.name;}finally{await browser?.close();}
 process.stdout.write(JSON.stringify(report));process.exitCode=Object.values(report).every(value=>value===true)&&report.local_artwork?0:1;
})();
