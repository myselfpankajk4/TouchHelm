/* Owned desktop bridge, or an explicitly marked read-only interface preview. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), token = document.querySelector('meta[name="desktop-token"]')?.content;
  const preview = new URL(location.href).searchParams.get('preview') === '1' || !!window.__TOUCHHELM_DESKTOP_PREVIEW__;
  let state = null, busy = false, dirty = false, preferencesLoaded = false, deviceStamp = '', activityStamp = '', preferenceSave = Promise.resolve(), preferenceRevision = 0;
  const fixture = () => ({preview:true,config:{mouse_sensitivity:1.3,mouse_acceleration:1.25,scroll_speed:1,invert_scroll:false,require_pin:true,laser_color:'blue'},pin_code:'5678',devices:[{device:'Android phone',ip:'192.168.1.40',authenticated:true,ping:12},{device:'Tablet',ip:'192.168.1.41',authenticated:false,ping:0}],activity:['[10:40:12] Android phone: Connected','[10:40:15] Android phone: Pointer moved'],pairing:{http_url:'http://192.168.1.25:8765/',qr:null},preferences:{theme:'glass',appearance:'dark',motion:'system',contrast:'system'},diagnostics:{engine:'EdgeChromium / WebView2',python:'Preview',build:'Sample build',source:'Sample workspace',host:'192.168.1.25',http_port:8765}});
  let hostReady=false, diagnosticStamp='';
  function settingsDirty(value){dirty=value;$('settingsSaveBar').dataset.dirty=String(value);$('saveSettings').disabled=!hostReady||!value;}
  function availability(ready,loading=false){
    hostReady=ready;$('desktopConnectionNotice').hidden=ready;
    $('desktopConnectionMessage').textContent=loading?'Loading host controls…':'Desktop connection unavailable. Reconnect to refresh pairing details.';
    $('retryDesktop').hidden=ready||loading;
    for(const field of $('settingsForm').querySelectorAll('fieldset'))field.disabled=!ready;
    $('saveSettings').disabled=!ready||!dirty;
    if(!ready){$('phoneURL').value='';$('copyURL').disabled=$('openURL').disabled=true;$('pairingQR').hidden=true;$('pinCode').hidden=true;document.querySelector('.qr-wrap').classList.add('qr-placeholder');document.querySelector('.qr-wrap').dataset.placeholder=loading?'Loading your connection…':'Reconnect to refresh your QR code';$('enablePairingRemote').disabled=true;$('deviceStatus').textContent=loading?'Loading devices…':'Device status unavailable';$('noDevices').hidden=true;}
  }
  function message(text,kind='error'){$('feedback').textContent=text;$('feedback').dataset.kind=kind;$('feedback').hidden=!text;if(text)window.TouchHelmEffects?.react($('feedback'),{kind});}
  async function invoke(method,...args){
    if(preview){if(method==='get_state')return state||fixture();if(method==='save_settings'){state.config={...state.config,...args[0]};state.pin_code=args[0].pin_code;return {success:true,config:state.config};}if(method==='save_preferences')return {success:true};return {success:false,error:'Native commands are disabled in the interface preview.'};}
    const api=window.pywebview?.api;if(!api||typeof api[method]!=='function')throw new Error('The desktop connection is not ready. Restart TouchHelm if this continues.');
    return api[method](token,...args);
  }
  function showPanel(id){window.TouchHelmEffects?.reset?.();for(const panel of document.querySelectorAll('[data-page]'))panel.hidden=panel.dataset.page!==id;for(const button of document.querySelectorAll('[data-panel]')){if(button.dataset.panel===id)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}document.querySelector('.desktop-content').scrollTop=0;window.dispatchEvent(new CustomEvent('touchhelm:desktop-panel',{detail:id}));}
  window.TouchHelmDesktop={invoke,showPanel,preview,refresh:()=>poll(),get state(){return state;}};
  for(const button of document.querySelectorAll('[data-panel]'))button.addEventListener('click',()=>showPanel(button.dataset.panel));
  const fields={mouse_sensitivity:'sensitivity',mouse_acceleration:'acceleration',scroll_speed:'scrollSpeed',invert_scroll:'invertScroll',require_pin:'requirePIN',pin_code:'pinInput',laser_color:'laserColor',remote_enabled:'remoteEnabled',files_enabled:'filesEnabled'};
  function labels(){for(const[id,output,digits]of [['sensitivity','sensitivityValue',1],['acceleration','accelerationValue',2],['scrollSpeed','scrollSpeedValue',1]])$(output).textContent=`${Number($(id).value).toFixed(digits)}×`; $('pinInput').required=$('requirePIN').checked;$('pinInput').disabled=!$('requirePIN').checked;}
  $('settingsForm').addEventListener('input',()=>{settingsDirty(true);$('saveStatus').textContent='Unsaved changes';labels();});
  $('settingsForm').addEventListener('submit',async event=>{
    event.preventDefault();const settings={};for(const[key,id]of Object.entries(fields)){const node=$(id);settings[key]=node.type==='checkbox'?node.checked:node.type==='range'?Number(node.value):node.value;}
    if(!settings.require_pin)settings.pin_code=settings.pin_code||'';
    $('saveSettings').disabled=true;$('saveError').hidden=true;
    try{const result=await invoke('save_settings',settings);if(!result.success)throw new Error(result.error||'Settings were not saved.');dirty=false;state.config={...state.config,...result.config};state.pin_code=result.pin_code??settings.pin_code;$('saveStatus').textContent=result.warning?'Settings saved · phone update pending':'Settings saved';if(result.warning)message(result.warning);else window.TouchHelmEffects?.react($('saveSettings'),{kind:'success'});render(state);}
    catch(error){$('saveError').textContent=`Settings were not saved: ${error.message} Adjust these settings and retry.`;$('saveError').hidden=false;window.TouchHelmEffects?.react($('saveSettings'),{kind:'error'});}
    finally{settingsDirty(dirty);}
  });
  function render(next){
    if(!next?.config)return;
    availability(next.connection_state!=='disconnected'&&next.connection_state!=='loading',next.connection_state==='loading');
    const setup=next.wireless_display||{state:'unknown',progress:null,message:'First-time setup may take a few minutes. Install the Windows receiver here.'};
    $('wirelessDisplayStatus').textContent=setup.message;
    const installing=['checking','permission','installing'].includes(setup.state);
    $('wirelessDisplayProgress').hidden=!installing;
    if(Number.isFinite(setup.progress))$('wirelessDisplayProgress').value=setup.progress;else $('wirelessDisplayProgress').removeAttribute('value');
    $('installWirelessDisplay').disabled=installing||setup.state==='installed';
    $('installWirelessDisplay').textContent=setup.state==='installed'?'Installed':setup.state==='permission'?'Waiting for Windows approval…':setup.state==='installing'?'Installing…':'Install Wireless Display';
    const remote=next.remote||{state:'stopped'};
    $('desktopRemoteStatus').textContent=remote.device?`${remote.device} · ${remote.mode==='audio'?'Listen to PC audio':remote.mode==='control'?'Control PC':'View PC'} · ${remote.mode==='audio'?'No screen captured':remote.display?.name||remote.display?.id||'Monitor'} · ${remote.state} · Audio ${remote.audio?'on':'off'}`:remote.message||'No remote session.';
    $('desktopStopRemote').disabled=!remote.device;
    $('desktopRemoteBanner').hidden=!remote.device;
    $('desktopRemoteBannerText').textContent=$('desktopRemoteStatus').textContent;
    state=next;const offline=next.connection_state==='disconnected';$('hostStatus').textContent=offline?'Host disconnected':next.connection_state==='loading'?'Loading host…':'Host running';document.querySelector('.host-status').classList.toggle('offline',offline);
    $('previewBanner').hidden=!preview;
    const pairing=next.pairing||{},url=hostReady?pairing.http_url:null,qr=url?pairing.qr:null;
    $('pairingRemoteStatus').textContent=next.config.remote_enabled?'Screen and audio access enabled. Start a session from your phone.':'Screen and audio access is off.';$('enablePairingRemote').hidden=!!next.config.remote_enabled;$('enablePairingRemote').disabled=!hostReady;
    $('pairingRemoteHelp').querySelector('summary').textContent=next.config.remote_enabled?'Screen and audio access · On':'Screen and audio access · Off';
    $('pairingFilesHelp').querySelector('summary').textContent=next.config.files_enabled?'File access · On':'File access · Off';$('pairingFilesStatus').textContent=next.config.files_enabled?'File access enabled for PIN-paired local phones.':'File access is off. Enable it to browse and transfer files from your phone.';$('enablePairingFiles').hidden=!!next.config.files_enabled;$('enablePairingFiles').disabled=!hostReady;
    if($('phoneURL').value!==(url||''))$('copyStatus').textContent='';
    $('phoneURL').value=url||'';$('copyURL').disabled=!url;$('openURL').disabled=!url;
    $('pairingMode').textContent='HTTP · local network';
    $('pairingLead').textContent='Use the same Wi-Fi as this PC, then scan the code with your phone camera.';
    document.querySelector('.qr-wrap').dataset.placeholder='Reconnect to refresh your QR code';
    document.querySelector('.qr-wrap').classList.toggle('qr-placeholder',!qr);$('pairingQR').hidden=!qr;if(qr)$('pairingQR').src=qr;
    document.querySelector('.pairing-security h2').textContent=next.config.require_pin?'Your pairing PIN':'Connection security';$('pairingPINHelp').hidden=!next.config.require_pin;
    $('pinStatus').textContent=next.config.require_pin?'Enter this PIN on your phone to connect.':'Direct access: phones on this network can connect without a password.';$('pinCode').textContent=next.pin_code||'';$('pinCode').hidden=!next.config.require_pin||!hostReady;
    const devices=next.devices||[],stamp=JSON.stringify(devices);if(stamp!==deviceStamp){deviceStamp=stamp;$('devicesBody').replaceChildren(...devices.map(device=>{const row=document.createElement('tr');if(!device.authenticated)row.className='locked';for(const text of [device.device||'Unknown device',device.ip||'',device.authenticated?'Ready':'PIN required',device.authenticated&&Number(device.ping)>0?`${device.ping} ms`:'—']){const cell=document.createElement('td');cell.textContent=text;row.appendChild(cell);}return row;}));}$('deviceCount').textContent=`${devices.length} ${devices.length===1?'device':'devices'}`;$('noDevices').hidden=devices.length>0;
    const activity=(next.activity||[]).join('\n');if(activity!==activityStamp){activityStamp=activity;const log=$('activityLog'),bottom=log.scrollHeight-log.scrollTop-log.clientHeight<20;log.textContent=activity||'No activity yet.';if(bottom)log.scrollTop=log.scrollHeight;}
    if(!dirty){for(const[key,id]of Object.entries(fields)){const node=$(id),value=key==='pin_code'?next.pin_code||'':next.config[key];if(node.type==='checkbox')node.checked=!!value;else node.value=value??'';}labels();}
    $('deviceStatus').textContent=!hostReady?'Device status unavailable':devices.length?`${devices.length} ${devices.length===1?'phone':'devices'} connected`:'No phone connected yet.';$('noDevices').hidden=!hostReady||devices.length>0;
    const diag=JSON.stringify(next.diagnostics||{});if(diag!==diagnosticStamp){diagnosticStamp=diag;$('diagnostics').replaceChildren(...Object.entries(next.diagnostics||{}).flatMap(([key,value])=>{const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=key.replaceAll('_',' ').replace(/^./,char=>char.toUpperCase());detail.textContent=String(value);return [term,detail];}));}
    settingsDirty(dirty);
    if(!preferencesLoaded&&window.TouchHelmThemes){const prefs=next.preferences||{},selected=window.TouchHelmThemes.migrate(prefs.theme||'aurora');window.TouchHelmThemes.apply(selected.id,{appearance:prefs.appearance||selected.appearance,motion:prefs.motion||'system',contrast:prefs.contrast||'system',effects:prefs.effects||'rich'});preferencesLoaded=true;}
    window.TouchHelmThemes?.updateContext({connected:!offline,deviceCount:devices.length});
    window.dispatchEvent(new CustomEvent('touchhelm:desktop-state',{detail:next}));
  }
  async function poll(){if(busy||document.hidden)return;busy=true;try{render(await invoke('get_state'));}catch(error){availability(false);$('hostStatus').textContent='Desktop connection unavailable';document.querySelector('.host-status').classList.add('offline');}finally{busy=false;}}
  $('retryDesktop').addEventListener('click',poll);
  $('copyURL').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('phoneURL').value);$('copyStatus').textContent='Address copied. Open it on your phone.';}catch(_){$('phoneURL').focus();$('phoneURL').select();$('copyStatus').textContent='Press Ctrl+C to copy the selected address.';}});
  $('enablePairingRemote').addEventListener('click',async()=>{try{const result=await invoke('save_settings',{remote_enabled:true});if(!result.success)throw Error(result.error);state.config={...state.config,...result.config};await poll();}catch(error){$('pairingRemoteStatus').textContent=error.message;}});
  $('enablePairingFiles').addEventListener('click',async()=>{try{const result=await invoke('save_settings',{files_enabled:true});if(!result.success)throw Error(result.error);state.config={...state.config,...result.config};await poll();}catch(error){$('pairingFilesStatus').textContent=error.message;}});
  $('filesEnabled').addEventListener('change',()=>{if($('filesEnabled').checked)$('requirePIN').checked=true;labels();});
  $('openURL').addEventListener('click',async()=>{try{const result=await invoke('open_phone');if(result&&!result.success)message(result.error);}catch(error){message(error.message);}});
  $('minimize').addEventListener('click',async()=>{try{const result=await invoke('minimize');if(result?.success===false)message(result.error);}catch(error){message(error.message);}});
  function savePreferences(preferences){const revision=++preferenceRevision;preferenceSave=preferenceSave.then(async()=>{try{const result=await invoke('save_preferences',preferences);if(!result.success)throw new Error(result.error);if(revision===preferenceRevision)message('Desktop preferences saved.','success');}catch(error){if(revision===preferenceRevision)message(`Preferences were not saved: ${error.message}`);}});}
  $('desktopStopRemote').addEventListener('click',async()=>{try{const result=await invoke('stop_remote');if(!result.success)throw new Error(result.error);message('Remote stop requested.','success');await poll();}catch(error){message(error.message);}});
  $('desktopRemoteBannerStop').addEventListener('click',()=>$('desktopStopRemote').click());
  $('desktopCastingSettings').addEventListener('click',async()=>{try{const result=await invoke('open_casting_settings');if(!result.success)throw new Error(result.error);}catch(error){message(error.message);}});
  $('installWirelessDisplay').addEventListener('click',async()=>{try{const result=await invoke('install_wireless_display');if(!result.success)throw new Error(result.error);await poll();}catch(error){message(error.message);}});
  $('generatePassword').addEventListener('click',async()=>{try{const result=await invoke('generate_password');if(!result.success)throw new Error(result.error);state.pin_code=result.password;state.config={...state.config,...result.config};$('pinInput').value=result.password;$('requirePIN').checked=true;labels();message('New pairing password saved. Pair connected phones again.','success');await poll();}catch(error){message(error.message);}});
  $('remoteEnabled').addEventListener('change',()=>{if($('remoteEnabled').checked)$('requirePIN').checked=true;labels();});
  if(window.TouchHelmThemes)window.TouchHelmThemes.mountPicker($('themePicker'),(id,prefs)=>savePreferences({theme:id,...prefs}));
  availability(false,true);
  if(preview){window.TouchHelmDesktopPreview={setState(name){const value=window.__TOUCHHELM_DESKTOP_PREVIEW__||fixture();state=structuredClone(value);if(name.startsWith('remote_'))state.remote={device:['remote_control','remote_view','remote_connecting'].includes(name)?'Android phone · preview':null,mode:name==='remote_view'?'view':'control',state:name==='remote_connecting'?'connecting':name==='remote_paused'?'paused':name==='remote_unavailable'?'unavailable':'live',display:{name:'Sample monitor'},audio:false};if(name==='disconnected'){state.connection_state='disconnected';state.devices=[];}if(name==='loading'){state.connection_state='loading';state.devices=[];state.activity=['Loading device status…'];}if(name==='unavailable'){state.devices=[];state.activity=['Provider context unavailable. Native connection remains available.'];}render(state);}};window.addEventListener('touchhelm:preview-state',event=>window.TouchHelmDesktopPreview.setState(event.detail?.state||'ready'));window.TouchHelmDesktopPreview.setState('ready');}
  else{window.addEventListener('pywebviewready',poll);setInterval(poll,1000);if(window.pywebview?.api)poll();}
  if(preview){showPanel('pairing');window.TouchHelmDesktopPreview.setWirelessDisplayState=value=>{state=structuredClone(state||fixture());state.wireless_display=value;render(state);};}
})();
