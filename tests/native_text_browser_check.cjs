/* Opt-in real browser -> WebSocket -> Windows UIA scratch-field integration. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
  const python=process.env.PYTHON_EXECUTABLE||path.resolve('.venv/Scripts/python.exe');
  const host=spawn(python,['tests/native_text_browser_host.py'],{cwd:path.resolve(__dirname,'..'),windowsHide:true,stdio:['ignore','pipe','pipe']});
  let origin,browser,page;
  try{
    const ready=await new Promise((resolve,reject)=>{
      let buffer='';const timer=setTimeout(()=>reject(new Error('Native browser host timed out')),25000);
      host.once('exit',code=>{clearTimeout(timer);reject(new Error('Host exited: '+code));});
      host.stdout.on('data',chunk=>{
        buffer+=chunk.toString();
        for(const line of buffer.split('\n')){
          try{const value=JSON.parse(line);if(value.origin){clearTimeout(timer);resolve(value);return;}}catch{}
        }
      });
      host.stderr.on('data',chunk=>process.stderr.write(chunk));
    });
    origin=ready.origin;
    const executablePath=fs.existsSync(chromium.executablePath())?chromium.executablePath():'C:/Program Files/Google/Chrome/Application/chrome.exe';
    browser=await chromium.launch({executablePath,headless:true});
    const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,serviceWorkers:'block'});
    page=await context.newPage();page.setDefaultTimeout(25000);
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(origin);
    await page.locator('#pinInput').fill('5678');
    await page.locator('#pinForm').evaluate(form=>form.requestSubmit());
    await page.waitForFunction(()=>touchhelm.isConnected);
    assert.equal(await page.locator('#typingDock').evaluate(el=>el.classList.contains('expanded')),false);
    const command=async name=>{const response=await page.request.post(origin+'/probe/'+name);assert.equal(response.ok(),true);return response.json();};
    if(!(await command('normal')).focus_owned){
      console.log('SKIP real native/browser text: Windows did not grant foreground focus to the owned scratch form.');
      return;
    }
    await page.waitForFunction(()=>typeInput.value==='Scratch PC text'&&typingDock.classList.contains('expanded'));
    assert.equal(await page.locator('#typeInput').evaluate(el=>document.activeElement===el),true);
    assert.equal(await page.locator('#usePCText').count(),0);
    await command('edit');
    await page.waitForFunction(()=>typeInput.value==='PC changed outside phone');
    await page.locator('#typeInput').fill('Phone edit\nSecond line 🙂');
    await page.waitForFunction(()=>touchhelm.liveTextValue==='Phone edit\nSecond line 🙂'&&!touchhelm.textSync.pending);
    // Force a stale revision: change PC text while the phone has polling paused.
    await page.evaluate(()=>clearInterval(touchhelm.textSync.timer));
    await command('edit');
    await page.locator('#typeInput').fill('Phone replacement');
    await page.waitForFunction(()=>touchhelm.textSync.needsRead);
    await page.evaluate(()=>touchhelm.textSync.poll());
    await page.waitForFunction(()=>typeInput.value==='PC changed outside phone'&&!touchhelm.textSync.needsRead);
    await page.locator('#typeInput').fill('PC changed outside phone!');
    await page.waitForFunction(()=>touchhelm.liveTextValue==='PC changed outside phone!'&&!touchhelm.textSync.pending);
    await page.locator('#btnTypingDone').click();
    await page.evaluate(()=>touchhelm.textSync.poll());
    await page.waitForFunction(()=>!touchhelm.textSync.pending);
    assert.equal(await page.locator('#typingDock').evaluate(el=>el.classList.contains('expanded')),false,'routine reads must not reopen a dismissed dock');
    await command('password');await page.evaluate(()=>touchhelm.textSync.poll());
    await page.waitForFunction(()=>!touchhelm.textSync.pending);
    await command('normal');await page.evaluate(()=>touchhelm.textSync.poll());
    await page.waitForFunction(()=>typingDock.classList.contains('expanded'));
    assert.deepEqual(errors,[]);
    console.log('PASS real native/browser text: auto-open, PC-to-phone, phone-to-PC, stale-write recovery, no relink button, focus re-entry');
  }catch(error){
    if(page&&origin){
      const diagnostic=await (await page.request.post(origin+'/probe/diagnostics')).json();
      if(diagnostic.form?.foreground===false){
        console.log('SKIP real native/browser text: Windows did not grant foreground focus to the owned scratch form.');
        return;
      }
      console.error(diagnostic);
    }
    if(page)console.error(await page.evaluate(()=>({connected:touchhelm.isConnected,owner:touchhelm.inputOwner,
      live:touchhelm.chkRealtimeTyping.checked,paused:touchhelm.liveTypingPaused,status:pcTextStatus.textContent,
      available:touchhelm.textSync.latest?.available,pending:touchhelm.textSync.pending?.action,
      characters:typeInput.value.length,dock:typingDock.className})).catch(()=>({page:'unavailable'})));
    throw error;
  }finally{
    await browser?.close();
    if(origin)await fetch(origin+'/probe/shutdown',{method:'POST'}).catch(()=>{});
    await new Promise(resolve=>{if(host.exitCode!==null)return resolve();const timer=setTimeout(()=>{host.kill();resolve();},7000);host.once('exit',()=>{clearTimeout(timer);resolve();});});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
