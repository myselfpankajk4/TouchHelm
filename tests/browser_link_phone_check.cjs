/* Receives an ephemeral synthetic-host URL over stdin, never via logs/CLI. */
const {chromium}=require('playwright');const fs=require('node:fs');
(async()=>{
 let input='';for await(const chunk of process.stdin)input+=chunk;
 const {url}=JSON.parse(input);let browser;const report={};
 try{
  const executablePath=fs.existsSync(chromium.executablePath())?chromium.executablePath():'C:/Program Files/Google/Chrome/Application/chrome.exe';
  browser=await chromium.launch({executablePath,headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];page.on('pageerror',()=>errors.push(true));
  await page.goto(url,{waitUntil:'networkidle',timeout:45000});
  await page.waitForFunction(()=>window.TouchHelmBrowserLink?.settled,null,{timeout:20000});
  report.gate_allowed=await page.evaluate(()=>TouchHelmBrowserLink.allowed);
  report.fragment_removed=new URL(page.url()).hash==='';
  report.secure_context=await page.evaluate(()=>window.isSecureContext);
  await page.locator('#pinInput').fill('5678');await page.locator('#pinInput').press('Enter');
  await page.waitForFunction(()=>window.touchhelm?.isConnected,null,{timeout:15000});
  report.phone_connected=true;
  report.no_service_worker=await page.evaluate(async()=>!navigator.serviceWorker.controller&&(await navigator.serviceWorker.getRegistrations()).length===0);
  await page.reload({waitUntil:'networkidle'});await page.waitForFunction(()=>window.touchhelm?.isConnected,null,{timeout:15000});report.cookie_refresh_works=true;
  report.no_script_errors=errors.length===0;
 }catch(error){report.error_type=error.name;}finally{await browser?.close();}
 process.stdout.write(JSON.stringify(report));process.exitCode=Object.values(report).every(v=>v===true)&&report.phone_connected?0:1;
})();
