/* Real Chrome / real local HTTP; no internet, private files or PC capture. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
let input='';process.stdin.on('data',v=>input+=v);process.stdin.on('end',()=>main(JSON.parse(input)).catch(e=>{console.error(e.stack);process.exitCode=1;}));
async function main({url}){
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:393,height:850},serviceWorkers:'block',acceptDownloads:true});
 const page=await context.newPage(),errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));
 await context.route('**/*',route=>{const target=new URL(route.request().url());if(target.origin===new URL(url).origin)return route.continue();if(['data:','blob:'].includes(target.protocol))return route.continue();external.push(target.href);return route.abort();});
 try{
  await page.goto(url);assert.equal(await page.locator('#tabFiles').count(),1,'Files must be a first-class tab');
  await page.evaluate(()=>{touchhelm.authPin='5678';touchhelm.authenticate();});
  await page.waitForFunction(()=>touchhelm.isConnected&&touchhelm.files?.ready);
  assert.equal(await page.evaluate(()=>isSecureContext),false,'Test must use ordinary LAN HTTP');
  assert.equal(await page.locator('#btnGyro').isVisible(),false,'Local mode must hide Air Mouse');
  await page.evaluate(()=>TouchHelmThemes.apply('aurora',{appearance:'light',effects:'off'}));
  await page.locator('#tabFiles').click();await page.waitForSelector('.files-location');
  await page.locator('.files-location').filter({hasText:'Downloads'}).first().click();
  await page.waitForSelector('.files-entry');
  await page.waitForFunction(()=>[...document.querySelectorAll('#viewFiles img')].every(img=>img.complete));
  if(process.env.TOUCHHELM_FILES_A11Y==='1'){
   const AxeBuilder=require('@axe-core/playwright').default;
   const audit=await new AxeBuilder({page}).include('#viewFiles').analyze();
   require('node:fs').writeFileSync('build/files-a11y.json',JSON.stringify(audit.violations.map(item=>({id:item.id,impact:item.impact,description:item.description,nodes:item.nodes.map(node=>node.target)})),null,2));
   assert.deepEqual(audit.violations.map(item=>item.id),[]);
  }
  if(process.env.TOUCHHELM_FILES_THEME_MATRIX==='1'){
   const AxeBuilder=require('@axe-core/playwright').default,results=[];
   for(const theme of ['aurora','bloom','resonance','constellation','ink'])for(const appearance of ['light','dark']){
    await page.evaluate(async value=>{TouchHelmThemes.apply(value.theme,{appearance:value.appearance,effects:'off'});await TouchHelmThemes.ready;},{theme,appearance});
    const audit=await new AxeBuilder({page}).include('#viewFiles').analyze();results.push({theme,appearance,violations:audit.violations.map(item=>({id:item.id,nodes:item.nodes.map(node=>node.target)}))});
    await page.screenshot({path:`build/files-theme-${theme}-${appearance}.png`});
   }
   require('node:fs').writeFileSync('build/files-theme-a11y.json',JSON.stringify(results,null,2));assert.deepEqual(results.flatMap(item=>item.violations),[]);
   await page.evaluate(async()=>{TouchHelmThemes.apply('aurora',{appearance:'light',effects:'off'});await TouchHelmThemes.ready;});
  }
  await page.screenshot({path:'build/files-393-light.png'});
  const retainedFocus=await page.evaluate(()=>{
   const files=touchhelm.files;const fixture={id:'a'.repeat(24),name:'Focus test.bin',size:1000,sent:0,direction:'send',state:'sending',destination:'Downloads'};
   files.transfers.push(fixture);files.drawTransfers();filesTransfers.querySelector('details').open=true;const action=document.querySelector('[aria-label="Cancel Focus test.bin"]');action.focus();fixture.sent=200;files.drawTransfers();
   const retained=document.activeElement===action;files.transfers.pop();files.drawTransfers();filesTransfers.querySelector('details').open=false;return retained;
  });assert.equal(retainedFocus,true,'A progress update must preserve keyboard focus on Cancel');
  const queuedReceive=await page.evaluate(()=>{
   const files=touchhelm.files,entries=files.entries.filter(entry=>!entry.directory).slice(0,2),before=files.transfers.length,click=HTMLAnchorElement.prototype.click;
   HTMLAnchorElement.prototype.click=()=>{};
   try{for(const entry of entries)files.receive(entry);const added=files.transfers.slice(before);const counts={receiving:added.filter(item=>item.state==='receiving').length,queued:added.filter(item=>item.state==='queued').length};for(const item of added)item.state='cancelled';files.transfers.splice(before);files.receiveQueue=[];files.downloadActive=null;files.drawTransfers();return counts;}finally{HTMLAnchorElement.prototype.click=click;}
  });assert.deepEqual(queuedReceive,{receiving:1,queued:1},'Receive should queue files instead of flooding native downloads');
  assert.equal(await page.locator('#filesEntries').getByText('Travel guide.pdf',{exact:true}).count(),1);
  const row=name=>page.locator('.files-entry').filter({has:page.getByText(name,{exact:true})});
  await page.locator('#filesSearch').fill('Travel');await page.waitForFunction(()=>touchhelm.files.entries.length===1);
  await page.locator('#filesSearch').fill('');await page.waitForFunction(()=>touchhelm.files.entries.length>=4);
  await row('Weekend.mp4').locator('.files-open-entry').click();await page.waitForFunction(()=>document.querySelector('#filesPreview video')?.readyState>=1);
  await page.evaluate(()=>document.querySelector('#filesPreview video').currentTime=1);
  await page.waitForFunction(()=>document.querySelector('#filesPreview video').currentTime>=1);
  {
   const opened=page.waitForEvent('popup');await page.locator('#filesOpenExternal').click();const videoTab=await opened;
   const mediaErrors=[];videoTab.on('console',message=>{if(message.type()==='error')mediaErrors.push(message.text());});
   await videoTab.waitForLoadState('domcontentloaded');
   await videoTab.waitForFunction(()=>document.querySelector('video')?.readyState>=2,null,{timeout:7000}).catch(error=>{console.error('TOP LEVEL MEDIA',mediaErrors);throw error;});
   await videoTab.evaluate(()=>{const video=document.querySelector('video');video.muted=true;return video.play();});
   await videoTab.waitForFunction(()=>document.querySelector('video').currentTime>0);await videoTab.close();
  }
  await page.screenshot({path:'build/files-video-preview.png'});await page.locator('#filesPreviewBack').click();await page.waitForSelector('#filesPreview',{state:'hidden'});
  {
   await page.setViewportSize({width:320,height:568});await page.evaluate(()=>viewFiles.scrollTop=viewFiles.scrollHeight);
   await row('Portrait.mp4').locator('.files-open-entry').click();await page.waitForFunction(()=>document.querySelector('#filesPreview video')?.readyState>=1);
   assert.equal(await page.evaluate(()=>viewFiles.scrollTop),0,'Opening a file must start its preview at the top');
   await page.evaluate(()=>{const video=document.querySelector('#filesPreview video');video.muted=true;return video.play();});await page.waitForFunction(()=>document.querySelector('#filesPreview video').currentTime>.1);await page.evaluate(()=>document.querySelector('#filesPreview video').pause());
   for(const [width,height] of [[393,850],[320,568],[844,390]]){
    await page.setViewportSize({width,height});
    const bounds=await page.evaluate(()=>{const video=document.querySelector('#filesPreview video'),body=filesPreviewBody.getBoundingClientRect(),rect=video.getBoundingClientRect(),viewport=viewFiles.getBoundingClientRect();return {top:rect.top-body.top,bottom:body.bottom-rect.bottom,viewportTop:rect.top-viewport.top,viewportBottom:viewport.bottom-rect.bottom,fit:getComputedStyle(video).objectFit,controls:video.controls,width:rect.width,height:rect.height};});
    assert.ok(bounds.top>=-1&&bounds.bottom>=-1,`Portrait player and controls must fit their container: ${JSON.stringify(bounds)}`);assert.equal(bounds.fit,'contain');assert.equal(bounds.controls,true);
    assert.ok(bounds.viewportTop>=-1&&bounds.viewportBottom>=-1,`The full portrait player must be visible above the phone navigation: ${JSON.stringify(bounds)}`);
    await page.screenshot({path:`build/test10-portrait-${width}.png`});
   }
   await page.setViewportSize({width:393,height:850});await page.locator('#filesPreviewBack').click();
  }
  {
   await row('Voice memo.aac').locator('.files-open-entry').click();await page.waitForFunction(()=>document.querySelector('#filesPreview audio')?.readyState>=2);
   assert.equal(await page.locator('#filesOpenExternal').isVisible(),true);
   await page.evaluate(()=>{const audio=document.querySelector('#filesPreview audio');audio.muted=true;return audio.play();});await page.waitForFunction(()=>document.querySelector('#filesPreview audio').currentTime>0);
   const opened=page.waitForEvent('popup');await page.locator('#filesOpenExternal').click();const audioTab=await opened;
   await audioTab.waitForFunction(()=>document.querySelector('video,audio')?.readyState>=2);
   await audioTab.evaluate(()=>{const audio=document.querySelector('video,audio');audio.muted=true;return audio.play();});await audioTab.waitForFunction(()=>document.querySelector('video,audio').currentTime>0);await audioTab.close();
   await page.locator('#filesPreviewBack').click();
  }
  await row('Evening mix.mp3').locator('.files-open-entry').click();await page.waitForFunction(()=>document.querySelector('#filesPreview audio')?.readyState>=1);
  await page.locator('#filesPreviewBack').click();await page.waitForSelector('#filesPreview',{state:'hidden'});
  await row('Travel guide.pdf').locator('.files-open-entry').click();
  assert.equal(await page.locator('#filesPreview iframe').count(),0);
  const pdfLink=page.locator('#filesOpenExternal');assert.equal(await pdfLink.innerText(),'Open PDF in Chrome');
  const pdfResponse=await context.request.get(new URL(await pdfLink.getAttribute('href'),url).href);
  assert.equal(pdfResponse.status(),200);assert.match(pdfResponse.headers()['content-type'],/application\/pdf/);assert.ok((await pdfResponse.body()).subarray(0,5).equals(Buffer.from('%PDF-')));
  await page.locator('#filesPreviewBack').click();await page.waitForSelector('#filesPreview',{state:'hidden'});
  const payload=Buffer.alloc(2560000);for(let i=0;i<payload.length;i++)payload[i]=i%256;
  for(let attempt=0;attempt<2;attempt++){
   await page.locator('#filesPicker').setInputFiles({name:'phone file.bin',mimeType:'application/octet-stream',buffer:payload});
   await page.waitForSelector('#filesDestination[open]');await page.waitForFunction(()=>!filesDestinationConfirm.disabled);await page.locator('#filesDestinationConfirm').click();
   await page.waitForFunction(n=>touchhelm.files.transfers.filter(t=>t.state==='complete').length===n,attempt+1,{timeout:20000});
  }
  await row('Travel guide.pdf').locator('input[type=checkbox]').check();assert.match(await page.locator('#filesReceive').innerText(),/1/);
  const downloaded=page.waitForEvent('download');await page.locator('#filesReceive').click();const download=await downloaded;assert.equal(await download.failure(),null);
  await page.locator('#filesNewFolder').click();await page.locator('#filesFolderName').fill('From my phone');await page.locator('#filesFolderForm [type=submit]').click();
  await page.waitForFunction(()=>touchhelm.files.folder?.name==='From my phone');assert.match(await page.locator('#filesStatus').innerText(),/empty/);
  await page.locator('#filesBreadcrumbs button').filter({hasText:'Downloads'}).click();await page.waitForSelector('.files-entry');
  await page.route('**/api/files/list?*',async route=>{
   const request=new URL(route.request().url());if(request.searchParams.get('id')!=='many-folders')return route.continue();
   const offset=Number(request.searchParams.get('offset')||0);const entries=Array.from({length:offset===0?200:5},(_,index)=>({id:`destination-${index+offset}`,name:`Folder ${String(index+offset).padStart(3,'0')}`,directory:true}));
   await route.fulfill({json:{id:'many-folders',name:'Many folders',writable:true,entries,breadcrumbs:[{id:'many-folders',name:'Many folders'}],has_more:offset===0,next_offset:offset+200}});
  });
  await page.locator('#filesPicker').setInputFiles({name:'chooser.bin',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});await page.waitForSelector('#filesDestination[open]');
  await page.evaluate(()=>touchhelm.files.destination('many-folders'));await page.waitForSelector('#filesDestinationMore:not([hidden])');await page.locator('#filesDestinationMore').click();
  await page.waitForSelector('#filesDestinationEntries button:has-text("Folder 204")');await page.locator('#filesDestinationClose').click();await page.unroute('**/api/files/list?*');
  // Cancellation after an allocated upload and while a chunk is in flight.
  await page.route('**/api/files/uploads/*',async route=>{if(route.request().method()==='PUT')await new Promise(resolve=>setTimeout(resolve,600));return route.continue().catch(()=>{});});
  await page.locator('#filesPicker').setInputFiles({name:'cancel me.bin',mimeType:'application/octet-stream',buffer:payload});await page.waitForFunction(()=>!filesDestinationConfirm.disabled);await page.locator('#filesDestinationConfirm').click();
  await page.waitForFunction(()=>touchhelm.files.transfers.some(t=>t.name==='cancel me.bin'&&t.upload));
  assert.ok((await page.locator('#filesTransfers').boundingBox()).height<=72,'Only the mini progress strip should show by default');
  assert.equal(await page.locator('#filesTransfers .files-transfer:visible').count(),0);
  await page.screenshot({path:'build/files-transfer-progress.png'});
  await page.locator('#filesTransferSummary').click();
  await page.getByRole('button',{name:'Cancel cancel me.bin',exact:true}).click();await page.waitForFunction(()=>touchhelm.files.transfers.some(t=>t.name==='cancel me.bin'&&t.state==='cancelled'));
  await page.unroute('**/api/files/uploads/*');
  for(const width of [320,980]){await page.setViewportSize({width,height:850});await page.screenshot({path:`build/files-${width}-light.png`});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  await page.setViewportSize({width:393,height:850});await page.evaluate(()=>TouchHelmThemes.apply('aurora',{appearance:'dark',effects:'off'}));await page.screenshot({path:'build/files-393-dark.png'});
  await page.locator('#tabRemote').click();await page.waitForFunction(()=>touchhelm.remote.caps?.local);
  await page.locator('[data-remote-mode=view]').click();await page.waitForFunction(()=>touchhelm.remote.state==='live'&&remoteVideo.videoWidth>0,null,{timeout:30000}).catch(async error=>{console.error('GENERATED MEDIA STATE',await page.evaluate(()=>({state:touchhelm.remote.state,status:remoteStatus.textContent,connection:touchhelm.remote.pc?.connectionState})));throw error;});
  await page.locator('#remoteStop').click();await page.waitForFunction(()=>!touchhelm.remote.session);
  await page.locator('#tabMedia').click();await page.locator('#mediaPcAudio').check();
  await page.waitForFunction(()=>touchhelm.remote.state==='live'&&touchhelm.remote.mode==='audio',null,{timeout:30000});
  await page.waitForFunction(async()=>{const pc=touchhelm.remote.pc;if(!pc||remoteVideo.muted||remoteVideo.paused)return false;const stats=await pc.getStats();return [...stats.values()].some(row=>row.type==='inbound-rtp'&&row.kind==='audio'&&row.packetsReceived>0&&row.totalAudioEnergy>0);},null,{timeout:15000});
  await page.evaluate(()=>touchhelm.remote.stop());
  await page.waitForFunction(()=>!touchhelm.remote.session);
  await page.evaluate(()=>touchhelm.send({type:'text',text:'synthetic local file control'}));
  await page.waitForTimeout(100);
 }finally{await context.close();await browser.close();}
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log(JSON.stringify({files_tab:true,local_http:true,no_external_requests:true,search:true,video_seek:true,chrome_video_playback:true,portrait_player_bounds:true,aac_inline_and_chrome:true,compact_transfers:true,mp3_metadata:true,pdf_preview:true,uploads_duplicate:true,download:true,new_folder:true,destination_pagination:true,cancel:true,responsive:true,screen:true,audio_only:true}));
}
