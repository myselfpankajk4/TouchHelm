/* Capability-driven UI; native mutations only cross the authenticated client. */
(() => {
  const id=name=>document.getElementById(name);
  const clock=n=>Number.isFinite(n)?`${Math.floor(Math.max(0,n)/60)}:${String(Math.floor(Math.max(0,n)%60)).padStart(2,'0')}`:'—';
  const finite=n=>typeof n==='number'&&Number.isFinite(n);
  const stored=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
  const save=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));}catch{}};
  class TouchHelmExperience {
    constructor(client) {
      this.client=client;this.controls=client.controls;this.assetUrls=new Map();this.assetRequests=new Map();this.assetGeneration=0;this.pending=false;
      this.playbackClock=new window.TouchHelmMediaClock();
      this.haptics=new window.TouchHelmHaptics(client);client.vibrate=pattern=>this.haptics.pulse(pattern);
      this.client.newlineMode=stored('touchhelm_newline_mode','shift_enter');if(!['enter','shift_enter'].includes(this.client.newlineMode))this.client.newlineMode='shift_enter';
      if(id('newlineMode')) {id('newlineMode').value=this.client.newlineMode;id('newlineMode').addEventListener('change',e=>{client.newlineMode=e.target.value;save('touchhelm_newline_mode',client.newlineMode);});}
      this.client.pinchZoom=stored('touchhelm_pinch',false);
      id('chkPinchZoom').checked=this.client.pinchZoom;
      id('chkPinchZoom').addEventListener('change',e=>{client.pinchZoom=e.target.checked;save('touchhelm_pinch',client.pinchZoom);});
      id('btnTestHaptics').addEventListener('click',()=>{this.haptics.test();id('hapticsStatus').textContent=this.haptics.description();});
      id('secureCapabilities').textContent='Everything connects over local Wi-Fi. To keep using the remote longer, adjust your phone’s screen timeout.';
      if(window.TouchHelmThemes){const picker=id('themePicker')||document.querySelector('.theme-grid');if(picker)window.TouchHelmThemes.mountPicker(picker,(theme)=>{client.currentTheme=theme;this.cacheTheme();client.vibrate(22);});}
      if(window.isSecureContext)navigator.serviceWorker?.ready.then(()=>this.cacheTheme()).catch(()=>{});
      this.bindMedia();this.bindPresentation();this.bindApps();this.bindChords();
      this.controls?.drawApps();
      this.playbackFrame=setInterval(()=>this.tickMedia(),500);
      const stop=()=>{this.cancelAppHolds();this.cancelCloseChecks();this.haptics.cancel();this.clearPending();window.TouchHelmThemes?.setInteractionActive(false);};
      window.addEventListener('blur',()=>this.cancelAppHolds());
      document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('pagehide',()=>{stop();client.releaseDragLock();client.stopLaser();clearInterval(this.playbackFrame);this.clearAssets();});
    }
    text(name,value){if(id(name))id(name).textContent=value??'';}
    send(message){return this.client.send(message);}
    api(path){return `${this.client.httpBase()}${path}`;}
    cancelAppHolds(){for(const cancel of this.appHolds||[])cancel();this.appHolds?.clear();}
    cacheTheme(){window.TouchHelmThemes?.ready.then(()=>{const link=id('th-active-theme');if(!link)return;const url=new URL(link.href,location.href);const paths=[url.pathname+url.search];navigator.serviceWorker?.controller?.postMessage({type:'cache_theme',paths});});}
    async image(element,assetId){
      if(!element)return false;
      if(assetId&&element.dataset.assetId===assetId&&element.dataset.decoded==='true'&&!element.hidden)return true;
      element.dataset.assetId=assetId||'';element.dataset.decoded='false';element.hidden=true;
      if(!assetId){element.removeAttribute('src');return false;}
      const generation=this.assetGeneration;
      try{
        let url=this.assetUrls.get(assetId);
        if(!url){let request=this.assetRequests.get(assetId);if(!request){request=(async()=>{const response=await fetch(this.api(`/api/assets/${encodeURIComponent(assetId)}`),{headers:{'X-TouchHelm-Pin':this.client.authPin||''},cache:'no-store'});if(!response.ok)throw Error('Artwork unavailable');const blob=await response.blob();if(blob.size>4*1024*1024||!blob.type.startsWith('image/')||generation!==this.assetGeneration)throw Error('Invalid artwork');const value=URL.createObjectURL(blob);if(this.assetUrls.size>=160){const [key,old]=this.assetUrls.entries().next().value;URL.revokeObjectURL(old);this.assetUrls.delete(key);}this.assetUrls.set(assetId,value);return value;})();this.assetRequests.set(assetId,request);}url=await request;}
        if(generation===this.assetGeneration&&element.dataset.assetId===assetId){
          element.src=url;await element.decode();
          if(generation!==this.assetGeneration||element.dataset.assetId!==assetId)return false;
          element.dataset.decoded='true';element.hidden=false;return true;
        }
      }catch{if(element.dataset.assetId===assetId){element.hidden=true;element.dataset.decoded='false';}return false;}
      finally{this.assetRequests.delete(assetId);}
      return false;
    }
    clearAssets(){this.assetGeneration++;for(const url of this.assetUrls.values())URL.revokeObjectURL(url);this.assetUrls.clear();this.assetRequests.clear();document.querySelectorAll('img[data-asset-id]').forEach(image=>{image.hidden=true;image.removeAttribute('src');});}
    bindMedia(){
      id('mediaSeek')?.addEventListener('input',()=>{this.seeking=true;this.text('seekPreview',clock(Number(id('mediaSeek').value)));});
      id('mediaSeek')?.addEventListener('change',()=>{this.seeking=false;this.mediaAction('seek',Number(id('mediaSeek').value));});
      const cancelSeek=()=>{if(this.seeking){this.seeking=false;this.text('seekPreview','');this.tickMedia();}};
      id('mediaSeek')?.addEventListener('pointercancel',cancelSeek);window.addEventListener('blur',cancelSeek);
      for(const [button,delta] of [['btnSeekBack',-10],['btnSeekForward',10]])id(button)?.addEventListener('click',()=>{const p=this.estimatedPosition();if(finite(p))this.mediaAction('seek',p+delta);});
      id('btnShuffle')?.addEventListener('click',()=>this.mediaAction('shuffle',!this.media?.shuffle));
      id('btnRepeat')?.addEventListener('click',()=>{const modes=['none','track','list'];this.mediaAction('repeat',modes[(modes.indexOf(String(this.media?.repeat||'none').toLowerCase())+1)%3]);});
      id('btnMediaStop')?.addEventListener('click',()=>this.mediaAction('stop'));
      id('mediaRate')?.addEventListener('change',e=>this.mediaAction('rate',Number(e.target.value)));
      id('mediaSessionSelect')?.addEventListener('change',()=>{this.clearPending();this.seeking=false;});
    }
    mediaAction(action,value){
      if(this.pending||!this.client.isConnected)return false;
      if(action==='seek')value=Math.max(this.media?.min_seek??0,Math.min(this.media?.max_seek??this.media?.duration??value,value));
      const packet={type:'media',action};if(value!==undefined)packet.value=value;
      if(!this.send(packet))return false;
      this.pending=true;
      if(action==='seek'){this.pendingSeek={value,requestedAt:performance.now(),session:this.media?.session_id||this.media?.id||'',sampledAt:this.media?.sampled_at};this.text('seekPreview',`Seeking to ${clock(value)}`);}
      this.text('mediaCommandStatus',action==='seek'?`Seeking to ${clock(value)}…`:'Waiting for the player…');this.renderMedia(this.media||{});
      this.pendingTimer=setTimeout(()=>{this.clearPending();this.text('mediaCommandStatus','The player did not confirm the request. Try again.');this.send({type:'get_desktop_state'});},5000);
      return true;
    }
    clearPending(){clearTimeout(this.pendingTimer);this.pending=false;this.pendingSeek=null;this.text('seekPreview','');if(this.media)this.renderMedia(this.media);}
    renderMedia(media){
      if(!this.playbackClock.update(media))return this.media;
      const pending=this.pendingSeek;
      const isNew=this.media!==media;
      this.media=media;
      if(pending){const session=media.session_id||media.id||'';
        if(media.available===false||session!==pending.session)this.clearPending();
        else if(isNew&&finite(media.position)&&Math.abs(media.position-pending.value)<=2+Math.max(0,(performance.now()-pending.requestedAt)/1000)*(media.playback_rate||1)){this.clearPending();this.text('mediaCommandStatus','');}}
      const caps=media.capabilities||{},connected=this.client.isConnected;
      const state=String(media.status||'').toLowerCase(),known=['playing','paused','stopped'].includes(state),unavailable=media.available===false;
      const play=id('btnMediaPlay');if(play)play.disabled=!connected||unavailable||this.pending||(known?!(state==='playing'?caps.pause??true:caps.play??true):caps.play_pause===false);
      for(const [button,cap]of[['btnMediaPrev','prev'],['btnMediaNext','next']])if(id(button))id(button).disabled=!connected||unavailable||this.pending||caps[cap]===false;
      this.renderArtwork(media);
      const canSeek=caps.seek===true&&finite(media.position)&&finite(media.min_seek)&&finite(media.max_seek)&&media.max_seek>media.min_seek;
      if(id('mediaSeekTools'))id('mediaSeekTools').hidden=!canSeek;
      if(canSeek){const seek=id('mediaSeek');seek.min=media.min_seek;seek.max=media.max_seek;seek.disabled=!connected||this.pending;if(!this.seeking)seek.value=this.estimatedPosition();for(const key of ['btnSeekBack','btnSeekForward'])id(key).disabled=!connected||this.pending;}
      for(const [element,cap]of[['btnShuffle','shuffle'],['btnRepeat','repeat'],['btnMediaStop','stop'],['rateLabel','rate']]){if(id(element))id(element).hidden=caps[cap]!==true;const control=element==='rateLabel'?id('mediaRate'):id(element);if(control)control.disabled=!connected||this.pending;}
      id('btnShuffle')?.setAttribute('aria-pressed',String(!!media.shuffle));this.text('btnRepeat',`Repeat: ${media.repeat||'none'}`);
      if(id('mediaRate')&&finite(media.playback_rate)){const select=id('mediaRate'),value=String(media.playback_rate);select.querySelector('option[data-provider]')?.remove();if(![...select.options].some(option=>option.value===value)){const option=document.createElement('option');option.value=value;option.textContent=`${value}×`;option.dataset.provider='true';select.append(option);}select.value=value;}
      const genres=media.genres||media.genre||[],track=media.track_number??media.track,tracks=media.album_track_count??media.album_tracks;
      const detail=[media.album_artist?`Album artist: ${media.album_artist}`:'',Array.isArray(genres)&&genres.length?`Genres: ${genres.join(', ')}`:'',track>0?`Track ${track}${tracks>0?` of ${tracks}`:''}`:'',media.subtitle||''].filter(Boolean);
      this.text('mediaDetails',detail.join(' · '));if(id('mediaOptions'))id('mediaOptions').hidden=!detail.length&&!['shuffle','repeat','rate','stop'].some(key=>caps[key]);
      this.tickMedia();return media;
    }
    estimatedPosition(){return this.playbackClock.position();}
    tickMedia(){if(document.hidden||!this.client.isConnected)return;const p=this.estimatedPosition(),duration=this.media?.duration;if(finite(p)){
      this.text('mediaPosition',clock(p));this.text('mediaDuration',clock(duration));
      const seek=id('mediaSeek');if(seek&&!this.seeking){seek.value=p;seek.setAttribute('aria-valuetext',`${clock(p)} of ${clock(duration)}`);}
      const progress=id('mediaProgress');if(progress){progress.hidden=!finite(duration)||duration<=0;if(!progress.hidden){progress.style.setProperty('--progress',`${Math.min(100,p/duration*100)}%`);progress.setAttribute('aria-label',`${clock(p)} of ${clock(duration)}`);}}
    }else{this.text('mediaPosition','—');this.text('mediaDuration',clock(duration));if(id('mediaProgress'))id('mediaProgress').hidden=true;}}
    renderArtwork(media){
      const image=id('mediaArtwork'),placeholder=id('mediaArtworkPlaceholder');if(!image)return;
      const asset=media.artwork_id,item=JSON.stringify([media.session_id||media.id||media.app,media.title,media.artist,media.album]);
      if(this.artworkItem!==item){this.artworkItem=item;image.dataset.assetId='';image.hidden=true;image.removeAttribute('src');}
      const caption=message=>{if(placeholder){placeholder.hidden=false;this.text('mediaArtworkStatus',message);}};
      if(!asset){this.image(image,null);caption(media.artwork_status==='read_error'?'Artwork could not be read':'This player has not supplied artwork');return;}
      if(image.dataset.assetId===asset&&image.dataset.decoded==='true'&&!image.hidden){if(placeholder)placeholder.hidden=true;return;}
      caption('Loading artwork…');
      this.image(image,asset).then(ready=>{if(this.artworkItem!==item||this.media?.artwork_id!==asset)return;if(ready){if(placeholder)placeholder.hidden=true;}else caption('Artwork could not be displayed');});
    }
    bindPresentation(){
      id('presentationDetails')?.addEventListener('toggle',()=>{if(id('presentationDetails').open){this.text('presentationDetailsStatus','Loading supported slide details…');this.send({type:'get_presentation_details'});}});
      id('slidePicker')?.addEventListener('change',e=>{const slide=Number(e.target.value);if(Number.isInteger(slide)&&slide>0)this.send({type:'presentation',action:'goto',slide});});
      id('presentationDisplay')?.addEventListener('change',e=>{this.client.presentationDisplay=e.target.value;});
      this.send({type:'get_displays'});
    }
    renderPresentation(presentation){this.presentation=presentation;this.client.autoPresentationDisplay=presentation.display?.id||'';if(id('presentationDetails')?.open&&presentation.slide!==this.detailsSlide){this.detailsSlide=presentation.slide;this.send({type:'get_presentation_details'});}}
    presentationDetails(details){
      this.text('presentationDetailsStatus',details.message|| (details.available?'Available presentation details':'These details are not exposed by this presentation app.'));
      for(const [key,prefix]of[['current','current'],['next','next']]){const slide=details[key]||{};this.image(id(`${prefix}SlidePreview`),slide.artwork_id);this.text(`${prefix}SlideCaption`,slide.title||`${prefix==='current'?'Current':'Next'} slide${slide.index?` · ${slide.index}`:''}`);}
      this.text('speakerNotes',details.notes||'No speaker notes available.');
      const picker=id('slidePicker');if(picker){picker.replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose a slide';picker.append(placeholder);for(const slide of details.slides||[]){const option=document.createElement('option');option.value=slide.index;option.textContent=`${slide.index} · ${slide.title||'Untitled slide'}`;picker.append(option);}picker.disabled=!this.client.isConnected||!details.capabilities?.goto;}
    }
    displays(data){const select=id('presentationDisplay');if(!select)return;select.replaceChildren();const auto=document.createElement('option');auto.value='';auto.textContent='Presentation display';select.append(auto);for(const display of data.displays||[]){const option=document.createElement('option');option.value=display.id;option.textContent=display.name||display.id;select.append(option);}select.value=this.client.presentationDisplay||'';}
    bindApps(){
      id('btnCloseAppActions')?.addEventListener('click',()=>this.client.closeModal(id('appActionsModal')));
      id('appActionsModal')?.addEventListener('click',e=>{if(e.target===id('appActionsModal'))this.client.closeModal(e.target);});
      id('btnOpenApp')?.addEventListener('click',()=>{if(this.selectedApp)this.send({type:'launch_app',app_id:this.selectedApp.id});});
      id('btnFocusApp')?.addEventListener('click',()=>this.focusApp());
      id('btnCloseAppWindow')?.addEventListener('click',()=>this.chooseAppWindow('close'));
      id('btnPinApp')?.addEventListener('click',()=>this.appAction(this.selectedApp?.pinned?'unpin':'pin'));
      id('btnAppDetails')?.addEventListener('click',()=>this.appAction('details'));
    }
    appAction(action,windowId){if(!this.selectedApp)return false;return this.send({type:'app_action',action,app_id:this.selectedApp.id,...(windowId?{window_id:windowId}:{})});}
    focusApp(){return this.chooseAppWindow('focus');}
    chooseAppWindow(action){
      const windows=this.selectedApp?.windows||[],list=id('appWindowChoices');list.replaceChildren();
      const choose=windowId=>{if(!this.appAction(action,windowId))return;if(action==='close'){
        this.cancelCloseChecks();this.pendingClose={appId:this.selectedApp.id,windowId};this.text('appActionDetails','Close requested. Waiting for the window; any save prompt appears on your PC.');this.syncAppActions();
        this.closeTimers=[1000,3000,5000].map(delay=>setTimeout(()=>{if(!this.pendingClose)return;if(delay===5000)this.pendingClose.finalCheck=true;this.send({type:'get_apps'});},delay));
        this.closeTimers.push(setTimeout(()=>{if(!this.pendingClose)return;this.cancelCloseChecks();this.text('appActionDetails','Close requested, but TouchHelm could not verify the window. Check your PC and refresh Apps.');this.syncAppActions();},7500));
      }};
      if(windows.length===1)return choose(windows[0].id);
      this.text('appActionDetails',windows.length?`Choose a window to ${action}.`:'No verified running window is available.');
      for(const entry of windows){const button=document.createElement('button');button.textContent=entry.title||'App window';button.addEventListener('click',()=>choose(entry.id));list.append(button);}
    }
    cancelCloseChecks(){for(const timer of this.closeTimers||[])clearTimeout(timer);this.closeTimers=[];this.pendingClose=null;}
    syncAppActions(){const hasWindows=!!this.selectedApp?.windows?.length;const close=id('btnCloseAppWindow');if(close){close.hidden=!hasWindows;close.disabled=!this.client.isConnected||!!this.pendingClose;}if(id('btnFocusApp'))id('btnFocusApp').disabled=!this.client.isConnected||!hasWindows;}
    openAppMenu(app,trigger){this.selectedApp=app;this.text('appActionsTitle',app.name);this.text('btnPinApp',app.pinned?'Unpin app':'Pin app');this.text('appActionDetails',`${app.running?'Running · ':''}${app.launches||0} opens with TouchHelm`);id('appWindowChoices').replaceChildren();this.syncAppActions();this.client.openModal(id('appActionsModal'),trigger);}
    drawApps(apps,query){
      const list=id('appsList');if(!list)return;this.cancelAppHolds();this.appHolds=new Set();list.replaceChildren();
      if(this.pendingClose){const pending=this.pendingClose,app=apps.find(value=>value.id===pending.appId),remains=app?.windows?.some(window=>window.id===pending.windowId);
        if(app&&Array.isArray(app.windows)&&!remains){this.cancelCloseChecks();this.text('appActionDetails','Window closed.');window.TouchHelmEffects?.react(id('appActionsTitle'),{kind:'success'});}
        else if(pending.finalCheck){this.cancelCloseChecks();this.text('appActionDetails',app?'Window is still open. Check your PC for a save prompt or close refusal.':'Close requested, but TouchHelm could not verify the window. Check your PC and refresh Apps.');}}
      if(this.selectedApp){this.selectedApp=apps.find(app=>app.id===this.selectedApp.id)||null;if(this.selectedApp)this.text('btnPinApp',this.selectedApp.pinned?'Unpin app':'Pin app');}
      this.syncAppActions();
      const filtered=apps.filter(app=>app.name.toLocaleLowerCase().includes(query));
      for(const app of filtered){
        const row=document.createElement('div');row.className='app-row';const button=document.createElement('button');button.className='catalog-item app-item';button.dataset.appId=app.id;button.disabled=!this.client.isConnected||this.controls.pendingApps.has(app.id);
        const mark=document.createElement('span');mark.className='app-monogram';mark.textContent=Array.from(app.name.trim())[0]||'A';mark.setAttribute('aria-hidden','true');
        const image=document.createElement('img');image.className='app-logo';image.alt='';image.hidden=true;image.addEventListener('load',()=>mark.hidden=true);image.addEventListener('error',()=>{image.hidden=true;mark.hidden=false;});this.image(image,app.icon_id);
        const text=document.createElement('span');text.className='catalog-text';const title=document.createElement('strong');title.textContent=app.name;const subtitle=document.createElement('span');subtitle.textContent=app.pinned?'Pinned':app.running?'Running':app.launches>0?`${app.launches} TouchHelm opens`:'Installed app';text.append(title,subtitle);button.append(mark,image,text);
        let timer=null,held=false,start=null;
        const cancel=()=>{clearTimeout(timer);start=null;held=true;};this.appHolds.add(cancel);
        button.addEventListener('pointerdown',e=>{if(button.disabled||e.button!==0)return;held=false;start={x:e.clientX,y:e.clientY};timer=setTimeout(()=>{held=true;this.client.vibrate(40);this.openAppMenu(app,button);},500);});
        button.addEventListener('pointermove',e=>{if(start&&Math.hypot(e.clientX-start.x,e.clientY-start.y)>8){clearTimeout(timer);start=null;held=true;}});
        button.addEventListener('pointerup',()=>{clearTimeout(timer);start=null;});
        for(const event of ['pointercancel','lostpointercapture','pointerleave'])button.addEventListener(event,cancel);
        button.addEventListener('contextmenu',e=>e.preventDefault());
        button.addEventListener('click',event=>{if(held&&event.detail!==0){held=false;return;}held=false;if(!button.disabled&&this.send({type:'launch_app',app_id:app.id})){this.controls.pendingApps.add(app.id);button.disabled=true;this.text('appsStatus',`Opening ${app.name}…`);}});
        const more=document.createElement('button');more.className='app-more';more.setAttribute('aria-label',`Actions for ${app.name}`);const glyph=this.controls.icon('apps');if(glyph)more.append(glyph);else more.textContent='Actions';more.disabled=!this.client.isConnected;more.addEventListener('click',()=>this.openAppMenu(app,more));row.append(button,more);list.append(row);
      }
      this.text('appsStatus',!this.client.isConnected?'Connect to your PC to launch apps.':filtered.length?`${filtered.length} apps`:query?'No apps match your search.':'No registered apps reported. Refresh to try again.');
    }
    bindChords(){
      const keys=['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z',...'0123456789','enter','space','tab','esc','backspace','delete','home','end','pageup','pagedown','left','right','up','down',...Array.from({length:24},(_,i)=>`f${i+1}`)];
      const saved=stored('touchhelm_chords',[]);this.favorites=Array.isArray(saved)?saved.filter(chord=>Array.isArray(chord)&&chord.length>0&&chord.length<=8&&chord.every(key=>keys.includes(key)||['lctrl','lshift','lalt','win'].includes(key))).slice(-12):[];
      const select=id('chordKey');for(const key of keys){const option=document.createElement('option');option.value=key;option.textContent=key.toUpperCase();select?.append(option);}
      const update=()=>{this.chord=[...document.querySelectorAll('#chordModifiers input:checked')].map(e=>e.value).concat(select?.value||'a');this.text('chordPreview',this.chord.map(key=>({lctrl:'Ctrl',lshift:'Shift',lalt:'Alt',win:'Win'})[key]||key.toUpperCase()).join(' + '));};
      id('chordModifiers')?.addEventListener('change',update);select?.addEventListener('change',update);update();
      id('btnSendChord')?.addEventListener('click',()=>this.sendChord(this.chord));
      id('btnSaveChord')?.addEventListener('click',()=>{if(!this.favorites.some(chord=>JSON.stringify(chord)===JSON.stringify(this.chord)))this.favorites.push([...this.chord]);this.favorites=this.favorites.slice(-12);save('touchhelm_chords',this.favorites);this.drawFavorites();});this.drawFavorites();
    }
    sendChord(keys){if(!this.client.isConnected)return false;this.controls.releaseKeys();return this.send({type:'hotkey',keys});}
    drawFavorites(){const list=id('chordFavorites');if(!list)return;list.replaceChildren();for(const keys of this.favorites.filter(keys=>Array.isArray(keys)&&keys.length<9)){const button=document.createElement('button');button.textContent=keys.map(key=>({lctrl:'Ctrl',lshift:'Shift',lalt:'Alt',win:'Win'})[key]||String(key).toUpperCase()).join(' + ');button.addEventListener('click',()=>this.sendChord(keys));list.append(button);}}
    commandResult(result){
      if(result.command==='media'){if(!result.success||!this.pendingSeek){this.clearPending();this.text('mediaCommandStatus',result.success?'':result.message||'Player request failed.');}this.send({type:'get_desktop_state'});}
      if(result.command==='app_action'&&result.action==='close'&&this.pendingClose&&!result.success){this.cancelCloseChecks();this.text('appActionDetails',result.message||'Windows could not request this close.');this.syncAppActions();}
      if(['app_action','launch_app'].includes(result.command)){if(result.details)this.text('appActionDetails',Object.entries(result.details).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join('\n'));if(!result.success)this.text('appActionDetails',result.message||'App action failed.');this.send({type:'get_apps'});}
    }
  }
  window.TouchHelmExperience=TouchHelmExperience;
})();
