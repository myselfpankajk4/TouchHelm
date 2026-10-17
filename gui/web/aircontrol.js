/* Owned desktop AirControl UI. Camera frames never use a LAN asset route. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),desktop=window.TouchHelmDesktop;
  if(!desktop)return;
  const labels={none:'No action',left_drag:'Left press / drag',left_click:'Left click',right_click:'Right click',double_click:'Double click',scroll:'Scroll',pause:'Pause',resume:'Resume',dictate:'Windows dictation',recenter:'Recenter',play_pause:'Play / pause',next_track:'Next track',previous_track:'Previous track',next_slide:'Next slide',previous_slide:'Previous slide',copy:'Copy',paste:'Paste',undo:'Undo',switch_app:'Switch app',keyboard:'Windows keyboard'};
  const gestures={pinch_index:'Thumb + index pinch',pinch_middle:'Thumb + middle pinch',two_fingers:'Two fingers',closed_fist:'Closed fist',open_palm:'Open palm',thumb_up:'Thumbs up',thumb_down:'Thumbs down',smile:'Deliberate smile',wink_left:'Left wink',wink_right:'Right wink',brows_up:'Raised eyebrows'};
  const guides={
    point:['Point with one finger','Keep your index finger extended and visible. Move inside your calibrated comfortable area to guide the pointer.'],
    pinch_index:['Pinch. Hold. Release.','Bring thumb and index together for 100 ms to press. Keep pinching while moving to drag. Separate your fingers to release.'],
    pinch_middle:['A deliberate right click','Bring thumb and middle finger together briefly. Keep the index pinch open so the inputs do not conflict.'],
    two_fingers:['Two fingers to scroll','Raise your index and middle fingers. Hold briefly, then move vertically. Lower your fingers to return to pointing.'],
    closed_fist:['Take a pause','Hold a closed fist for 600 ms. AirControl releases its mouse button and pauses PC input.'],
    open_palm:['Ready when you are','While paused, hold an open palm for 800 ms to resume. Keep the required hand or face steadily tracked.'],
    head:['Look around. Settle to click.','Calibrate your neutral head position. Move comfortably to point; stay within the target for the dwell ring to complete. Ordinary blinks are not clicks.'],
    smile:['A deliberate smile','In Head/Combined practice, relax your face, then hold a deliberate smile for 400 ms. Calibrate the observed expression before assigning an action.'],
    wink_left:['One eye, deliberately','Keep your right eye open and close only your left eye for 400 ms. Ordinary two-eye blinking never triggers this gesture. Practice and calibrate before use.'],
    wink_right:['A deliberate right wink','Keep your left eye open and close only your right eye for 400 ms. Practice and calibrate this expression before assigning an action.'],
    brows_up:['Raise. Hold. Relax.','Hold a neutral face first, then raise your eyebrows deliberately for 400 ms. Calibrate the observed expression in practice before assigning an action.']
  };
  function defaults(name='everyday',mode='hand'){
    const bindings={pinch_index:'left_drag',pinch_middle:'right_click',two_fingers:'scroll',closed_fist:'pause',open_palm:'resume',thumb_up:'none',thumb_down:'none',smile:'none',wink_left:'none',wink_right:'none',brows_up:'none'};
    if(name==='presenter')Object.assign(bindings,{thumb_up:'next_slide',thumb_down:'previous_slide'});
    if(name==='media')Object.assign(bindings,{thumb_up:'play_pause',thumb_down:'next_track'});
    return {version:1,name,mode,hand:'auto',camera_id:'0',monitor_id:'',mirror:true,landmarks:true,auto_dictation:true,sensitivity:1,smoothing:.45,pinch_close:.25,pinch_open:.4,dwell_ms:900,hold_ms:400,cooldown_ms:700,head_range:18,dwell:true,expressions_calibrated:false,calibrated_expressions:[],bindings,calibration:{hand_bounds:[.15,.15,.85,.85],head_neutral:[0,0]}};
  }
  class AirPanel {
    constructor(){
      this.profile=defaults();this.state={state:'setup_required',camera_active:false,owns_input:false,profile:this.profile,setup:{state:'setup_required',ready:false,message:'Prepare the isolated camera runtime. Your phone controls keep working.'},voice:{message:'Select a PC text field, then use Dictate.'}};
      this.dirty=false;this.busy=false;this.frameBusy=false;this.cameras=[];this.guidePinned=false;this.lastPreview='';this.lastSeq=-1;this.error='';
      this.mappingRows();this.loadProfile(this.profile);this.bind();
      if(desktop.state?.aircontrol)this.render(desktop.state.aircontrol);else this.render(this.state);
      window.addEventListener('touchhelm:desktop-state',event=>{if(event.detail.aircontrol)this.render(event.detail.aircontrol);});
      window.addEventListener('touchhelm:desktop-panel',event=>{
        document.body.classList.toggle('air-panel-hidden',event.detail!=='aircontrol');
        if(event.detail==='aircontrol'&&!this.discovered){this.discovered=true;this.refreshDevices();}
      });
      this.frameTimer=setInterval(()=>this.pollFrame(),100);
      document.body.classList.add('air-panel-hidden');
    }
    mappingRows(){
      const rows=Object.entries(gestures).map(([key,name])=>{
        const row=document.createElement('div');row.className='air-map-row';
        const label=document.createElement('label');label.htmlFor='airMap_'+key;label.textContent=name;
        const note=document.createElement('small');note.textContent=['closed_fist','open_palm'].includes(key)?'Reserved escape control':['smile','wink_left','wink_right','brows_up'].includes(key)?'Requires expression practice':'Choose an action';label.append(note);
        const select=document.createElement('select');select.id='airMap_'+key;select.dataset.airGesture=key;
        select.disabled=['closed_fist','open_palm'].includes(key);
        for(const [value,text]of Object.entries(labels)){
          if(value==='left_drag'&&!key.startsWith('pinch_')||value==='scroll'&&key!=='two_fingers'||value==='pause'&&key!=='closed_fist'||value==='resume'&&key!=='open_palm')continue;
          const option=new Option(text,value);select.append(option);
        }
        select.addEventListener('change',()=>{this.dirty=true;});row.append(label,select);return row;
      });$('airMappingRows').replaceChildren(...rows);
    }
    bind(){
      $('switchControlMode').addEventListener('click',()=>desktop.showPanel('home'));
      $('chooseAir').addEventListener('click',()=>desktop.showPanel('aircontrol'));
      $('choosePhone').addEventListener('click',async()=>{if(this.state.camera_active||this.state.owns_input){if(!await this.call('stop'))return;}desktop.showPanel('pairing');});
      document.querySelector('[data-panel="pairing"]').addEventListener('click',async event=>{
        if(!this.state.camera_active&&!this.state.owns_input)return;
        event.preventDefault();event.stopImmediatePropagation();if(await this.call('stop'))desktop.showPanel('pairing');
      },true);
      $('airInstall').addEventListener('click',()=>this.call('setup'));
      $('airCancelInstall').addEventListener('click',()=>this.call('cancel_setup'));
      $('airRefreshCameras').addEventListener('click',()=>this.refreshDevices());
      $('airPrivacy').addEventListener('click',()=>this.call('privacy'));
      $('airStart').addEventListener('click',()=>this.start());
      $('airStop').addEventListener('click',()=>this.call('stop'));
      $('airPause').addEventListener('click',()=>this.call(this.state.state==='active'?'pause':'resume'));
      $('airRecenter').addEventListener('click',()=>this.call('recenter'));
      $('airDictate').addEventListener('click',()=>this.call('dictate'));
      $('airVoiceAccess').addEventListener('click',()=>this.call('voice_access'));
      $('airCaptureTarget').addEventListener('click',()=>this.call('calibrate',{target:this.nextTarget()}));
      $('airRestartCalibration').addEventListener('click',()=>this.start());
      $('airEnable').addEventListener('click',()=>this.call('enable'));
      $('airPractice').addEventListener('click',()=>this.tab('practice'));
      $('airReturnPractice').addEventListener('click',()=>this.call('practice'));
      $('airExpressionPractice').addEventListener('click',()=>this.call('expression_calibrate'));
      $('airGuideSelect').addEventListener('change',()=>{this.guidePinned=true;this.guide($('airGuideSelect').value);});
      for(const button of document.querySelectorAll('[data-air-mode]'))button.addEventListener('click',async()=>{
        if(this.busy)return;const mode=button.dataset.airMode;
        this.profile.mode=mode;this.dirty=true;this.loadMode(mode);this.guide(mode==='hand'?'point':'head');
        if(this.state.camera_active)await this.start();
      });
      for(const button of document.querySelectorAll('[data-air-tab]')){
        button.addEventListener('click',()=>this.tab(button.dataset.airTab));
        button.addEventListener('keydown',event=>{
          const tabs=[...document.querySelectorAll('[data-air-tab]')];let index=tabs.indexOf(button);
          if(event.key==='ArrowRight')index=(index+1)%tabs.length;else if(event.key==='ArrowLeft')index=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=tabs.length-1;else return;
          event.preventDefault();tabs[index].click();tabs[index].focus();
        });
      }
      for(const node of document.querySelectorAll('[data-air-content=settings] input,[data-air-content=settings] select'))node.addEventListener('input',()=>{this.dirty=true;this.rangeLabels();});
      $('airCamera').addEventListener('change',()=>{this.dirty=true;});$('airMonitor').addEventListener('change',()=>{this.dirty=true;});
      $('airProfile').addEventListener('change',()=>{
        const name=$('airProfile').value,value=this.state.profiles?.[name]||{...this.profile,name,bindings:defaults(name).bindings};
        this.loadProfile(value);this.dirty=true;
      });
      for(const id of ['airSaveMappings','airSaveSettings'])$(id).addEventListener('click',()=>this.save());
      $('airResetMappings').addEventListener('click',()=>{this.loadProfile({...this.capture(),bindings:defaults($('airProfile').value).bindings});this.dirty=true;});
      $('airResetSettings').addEventListener('click',()=>{this.loadProfile(defaults('everyday',this.profile.mode));this.dirty=true;});
    }
    rangeLabels(){
      $('airSensitivityValue').textContent=Number($('airSensitivity').value).toFixed(1)+'×';
      $('airSmoothingValue').textContent=Math.round(Number($('airSmoothing').value)*100)+'%';
    }
    loadMode(mode){
      for(const button of document.querySelectorAll('[data-air-mode]'))button.setAttribute('aria-pressed',String(button.dataset.airMode===mode));
      $('airCalibrationHelp').textContent=mode==='hand'?'Hold your index finger at each comfortable target and capture it. Keep the hand still briefly before each capture.':'Look straight ahead and capture your neutral head position. Then move through the practice desk; Combined also requires your hand in view.';
    }
    loadProfile(profile){
      this.profile=structuredClone(profile);this.loadMode(profile.mode);$('airProfile').value=profile.name;
      const fields={hand:'airHand',camera_id:'airCamera',monitor_id:'airMonitor',sensitivity:'airSensitivity',smoothing:'airSmoothing',dwell_ms:'airDwellMs',hold_ms:'airHoldMs',cooldown_ms:'airCooldownMs',pinch_close:'airPinchClose',pinch_open:'airPinchOpen',head_range:'airHeadRange',mirror:'airMirror',landmarks:'airShowLandmarks',dwell:'airDwell',auto_dictation:'airAutoDictation'};
      for(const [key,id]of Object.entries(fields)){if($(id).type==='checkbox')$(id).checked=profile[key];else $(id).value=profile[key];}
      for(const [key,value]of Object.entries(profile.bindings||{})){const node=$('airMap_'+key);if(node)node.value=value;}
      this.rangeLabels();this.dirty=false;
    }
    capture(){
      const profile=structuredClone(this.profile);profile.name=$('airProfile').value;
      for(const [key,id]of Object.entries({hand:'airHand',camera_id:'airCamera',monitor_id:'airMonitor'}))profile[key]=$(id).value;
      for(const [key,id]of Object.entries({sensitivity:'airSensitivity',smoothing:'airSmoothing',dwell_ms:'airDwellMs',hold_ms:'airHoldMs',cooldown_ms:'airCooldownMs',pinch_close:'airPinchClose',pinch_open:'airPinchOpen',head_range:'airHeadRange'}))profile[key]=Number($(id).value);
      for(const [key,id]of Object.entries({mirror:'airMirror',landmarks:'airShowLandmarks',dwell:'airDwell',auto_dictation:'airAutoDictation'}))profile[key]=$(id).checked;
      for(const key of Object.keys(gestures))profile.bindings[key]=$('airMap_'+key).value;
      return profile;
    }
    validate(profile){
      const assigned=Object.values(profile.bindings).filter(v=>!['none','pause','resume'].includes(v));
      if(new Set(assigned).size!==assigned.length)throw Error('Assign an action to only one gesture; this profile has duplicate actions.');
      if(profile.pinch_open<=profile.pinch_close+.05)throw Error('Pinch release must be at least 0.05 above the close threshold.');
      for(const key of ['smile','wink_left','wink_right','brows_up'])if(profile.bindings[key]!=='none'&&!profile.calibrated_expressions.includes(key))throw Error('Practice and calibrate '+gestures[key]+' before assigning its action.');
    }
    async save(){
      try{const profile=this.capture();this.validate(profile);$('airMappingError').hidden=true;await this.call('save',{profile});}
      catch(error){this.error=error.message;$('airMappingError').textContent=error.message;$('airMappingError').hidden=false;$('airMessage').textContent=error.message;}
    }
    async start(){
      try{const profile=this.capture();this.validate(profile);if(await this.call('start',{profile})){this.profile=profile;this.dirty=false;this.tab('controls');}}
      catch(error){this.error=error.message;$('airMessage').textContent=error.message;}
    }
    async call(action,data){
      if(this.busy)return false;this.error='';this.busy=true;this.render(this.state);
      try{
        const response=desktop.preview?this.previewAction(action,data):await desktop.invoke('aircontrol',action,data||{});
        if(!response?.success)throw Error(response?.error||'AirControl request was not completed.');
        if(response.aircontrol){
          const previous=this.state.state;
          if(['save','start','expression_calibrate'].includes(action))this.dirty=false;
          this.render(response.aircontrol);
          if(response.aircontrol.state==='practicing'&&(previous==='calibrating'||action==='practice')){
            this.tab('practice');$('airPracticeResult').scrollIntoView({block:'nearest'});
          }
          if(action==='enable'){this.tab('controls');document.querySelector('.desktop-content').scrollTop=0;}
        }
        return true;
      }catch(error){this.error=error.message;$('airMessage').textContent=error.message;return false;}
      finally{this.busy=false;this.render(this.state);}
    }
    tab(name){
      for(const node of document.querySelectorAll('[data-air-tab]')){const active=node.dataset.airTab===name;node.setAttribute('aria-selected',String(active));node.tabIndex=active?0:-1;}
      for(const node of document.querySelectorAll('[data-air-content]'))node.hidden=node.dataset.airContent!==name;
    }
    guide(name){const value=guides[name]||guides.point;$('airGuideTitle').textContent=value[0];$('airGuideDescription').textContent=value[1];$('airGuideArt').dataset.gesture=guides[name]?name:'point';$('airGuideSelect').value=guides[name]?name:'point';}
    nextTarget(){
      const targets=this.profile.mode==='hand'?['center','top_left','top_right','bottom_left','bottom_right']:['center'];
      return targets.find(t=>!(this.state.calibration_points||[]).includes(t))||'center';
    }
    async refreshDevices(){
      try{
        const camera=desktop.preview?{success:true,cameras:[{id:'0',name:'Sample PC webcam · preview'}],message:'Preview camera; no hardware is opened.'}:await desktop.invoke('aircontrol','cameras',{});
        if(!camera.success)throw Error(camera.error);
        this.cameras=camera.cameras||[];
        $('airCamera').replaceChildren(...this.cameras.map(c=>new Option(c.name,c.id)));
        if(!this.cameras.length)$('airCamera').append(new Option('No camera detected',''));
        if(this.cameras.some(c=>c.id===this.profile.camera_id))$('airCamera').value=this.profile.camera_id;
        $('airCameraMessage').textContent=camera.message||'Choose a connected camera.';
        const displays=desktop.preview?{displays:[{id:'preview',name:'Sample monitor'}]}:await desktop.invoke('aircontrol','displays',{});
        $('airMonitor').replaceChildren(new Option('Primary monitor',''),...(displays.displays||[]).map(d=>new Option(d.name||d.id,d.id)));
        $('airMonitor').value=this.profile.monitor_id;this.render(this.state);
      }catch(error){$('airCameraMessage').textContent=error.message;}
    }
    render(state){
      this.state=state||this.state;const s=this.state,setup=s.setup||{},active=!!s.camera_active;
      if(s.profile&&!this.dirty)this.loadProfile(s.profile);
      $('airState').textContent=s.state==='practicing'?'Practice · PC input off':s.state==='active'?'PC control on':String(s.state||'setup_required').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());$('airState').dataset.state=s.state;
      const practiceMessage=s.practice_ready?'Practice click recognized. Choose Enable PC control above to move the Windows cursor.':'Practice only: move the simulated cursor below and test a click. Your Windows cursor stays still until you enable PC control.';
      $('airMessage').textContent=this.error||(s.state==='practicing'?practiceMessage:s.message)||'Choose Start camera for calibration and practice.';
      $('homeAirStatus').textContent=active?'AirControl camera is running. Selecting Phone stops it; Switch mode alone leaves the session intact.':'The camera stays off until you choose Start camera.';
      $('airSetup').hidden=!!setup.ready;$('airSetupMessage').textContent=setup.message||'Prepare the isolated camera runtime.';
      const installing=setup.state==='installing';$('airSetupProgress').hidden=!installing;
      if(Number.isFinite(setup.progress))$('airSetupProgress').value=setup.progress;else $('airSetupProgress').removeAttribute('value');
      $('airInstall').disabled=this.busy||installing;$('airCancelInstall').hidden=!installing;
      $('airPause').disabled=this.busy||!s.owns_input;$('airPause').textContent=s.state==='active'?'Pause':'Resume';
      $('airStop').disabled=this.busy||!active;$('airStart').disabled=this.busy||!setup.ready||!this.cameras.length||active;
      $('airStart').textContent=active?'Camera running':'Start camera';$('airCamera').disabled=active;$('airRefreshCameras').disabled=active;
      $('airMonitor').disabled=active;$('airRecenter').disabled=this.busy||!active;
      $('airCaptureTarget').disabled=this.busy||!active||s.calibrated||!['calibrating','practicing'].includes(s.state)||!s.tracking;
      $('airRestartCalibration').disabled=this.busy||!active;$('airPractice').disabled=!s.calibrated;
      $('airEnable').disabled=this.busy||!s.practice_ready||!s.calibrated||s.owns_input;
      $('airEnable').hidden=!!s.owns_input;
      $('airReturnPractice').disabled=this.busy||!active||!s.calibrated;
      $('airCameraBadge').textContent=!active?'Camera off':s.state==='practicing'?'Practice cursor only':s.state==='active'?'Windows control on':s.owns_input?'PC input paused':'Calibration · PC input off';
      $('airCameraEmpty').hidden=active&&!!this.lastPreview;
      $('airCameraEmpty').querySelector('strong').textContent=active?'Waiting for the first frame…':'Your space, your controls';
      $('airCameraEmpty').querySelector('span').textContent=active?'Models are loading. Calibration and practice send no PC input.':'Choose your camera, then start calibration.';
      const sources=s.tracking_sources;
      $('airTrackingState').textContent=!active?'Camera off':sources?
        [(sources.hand_enabled?(sources.hand?'Hand tracked':'Show your hand'):'Hand tracking off'),
          sources.face_enabled?(sources.face?'Face tracked':'Show one face'):'Face tracking off in Hand mode'].join(' · '):
        s.profile?.mode==='hand'?(s.tracking?'Hand tracked':'Show your hand')+' · Face tracking off in Hand mode':s.tracking?'Tracking':'Finding your pose…';
      $('airDetected').textContent=s.gesture==='conflict'?'Conflicting gestures · release, then point again':
        gestures[s.gesture]?'Detected: '+gestures[s.gesture]+' · '+(s.action==='none'?'No action assigned':labels[s.action]||'No action'):
        s.tracking?'Pointer tracked · no click gesture':'No supported gesture detected';
      $('airFps').textContent=Number.isFinite(s.metrics?.fps)?s.metrics.fps+' fps':'— fps';
      $('airHoldFill').style.width=(Math.max(0,Math.min(1,s.progress||0))*100)+'%';
      if(!this.guidePinned&&guides[s.gesture])this.guide(s.gesture);
      $('airVoiceMessage').textContent=s.voice?.message||'Windows manages dictation and microphone setup.';
      $('airHotkeyStatus').textContent=s.hotkey||'Pause hotkey is registered after PC control starts.';
      const next=this.nextTarget();$('airCaptureTarget').textContent='Capture '+next.replaceAll('_',' ');
      $('airCalibrationStatus').textContent=s.calibrated?'Calibration complete. Practice a click, then enable PC control.':(s.calibration_points?.length||0)+' targets captured';
      const target=$('airCalibrationTarget');target.hidden=!active||s.state!=='calibrating';
      const position={center:[50,50],top_left:[22,22],top_right:[78,22],bottom_left:[22,78],bottom_right:[78,78]}[next];target.style.left=position[0]+'%';target.style.top=position[1]+'%';
      $('airPracticeResult').textContent=`${s.practice_frames>=15?'Pointer tracking ready':'Keep your hand or face steadily visible'} · ${s.practice_actions?'Practice click recognized':'Test a pinch click, or a head dwell click'}. ${s.practice_ready?'Ready: Enable PC control above.':'Windows input is off.'}`;
      if(s.point){$('airPracticePointer').style.left=s.point[0]*100+'%';$('airPracticePointer').style.top=s.point[1]*100+'%';}
      $('airPracticeAction').textContent=s.actions?.[0]||labels[s.action]||'Waiting for your first move';
      const expression=s.expression_practice||{};
      if(s.profile?.calibrated_expressions){this.profile.calibrated_expressions=[...s.profile.calibrated_expressions];this.profile.expressions_calibrated=!!s.profile.expressions_calibrated;}
      $('airExpressionResult').textContent=expression.neutral?'Neutral captured. Observed deliberate expressions: '+((expression.seen||[]).map(k=>gestures[k]).join(', ')||'none yet')+'. Calibrate to enable their mappings.':'Hold a neutral face in Head/Combined practice, then a deliberate expression for 400 ms.';
      $('airExpressionPractice').disabled=this.busy||s.state!=='practicing'||!expression.neutral||!expression.seen?.length;
      const metrics=s.metrics||{};$('airMetrics').textContent=`Tracked updates: ${metrics.fps??'unknown'} fps · median frame-to-input latency: ${metrics.median_latency_ms??'unknown'} ms · inference: ${metrics.inference_ms??'unknown'} ms · worker CPU: ${metrics.cpu_percent??'unknown'}% of total PC · worker memory: ${metrics.memory_mb??'unknown'} MB. These are measurements, not guaranteed performance.`;
      window.TouchHelmThemes?.setInteractionActive?.(active);
      if(!active){this.lastPreview='';$('airPreview').hidden=true;$('airPreview').removeAttribute('src');$('airLandmarks').getContext('2d').clearRect(0,0,640,480);}
    }
    async pollFrame(){
      if(this.frameBusy||document.hidden||!this.state.camera_active||document.querySelector('[data-page=aircontrol]').hidden||desktop.preview)return;
      this.frameBusy=true;
      try{const state=await desktop.invoke('get_aircontrol_frame');this.render(state);this.draw(state);}catch(error){$('airMessage').textContent='Camera preview unavailable: '+error.message;}
      finally{this.frameBusy=false;}
    }
    draw(state){
      if(state.preview&&state.preview!==this.lastPreview&&state.preview.length<=300000&&/^[A-Za-z0-9+/=]+$/.test(state.preview)){
        this.lastPreview=state.preview;$('airPreview').src='data:image/jpeg;base64,'+state.preview;$('airPreview').hidden=false;$('airCameraEmpty').hidden=true;
      }
      const canvas=$('airLandmarks'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,640,480);
      if(!$('airShowLandmarks').checked)return;
      ctx.strokeStyle='#7ff2df';ctx.fillStyle='#fff';ctx.lineWidth=2;
      const hand=state.hand_points||[],face=state.face_points||[];
      const point=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p.every(v=>v>=-1&&v<=2);
      for(const [a,b]of [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]])if(point(hand[a])&&point(hand[b])){ctx.beginPath();ctx.moveTo(hand[a][0]*640,hand[a][1]*480);ctx.lineTo(hand[b][0]*640,hand[b][1]*480);ctx.stroke();}
      for(const p of [...hand,...face].slice(0,40))if(point(p)){ctx.beginPath();ctx.arc(p[0]*640,p[1]*480,3,0,Math.PI*2);ctx.fill();}
    }
    previewAction(action,data={}){
      if(action==='start'){this.profile=data.profile||this.profile;this.setPreview('calibrating');}
      else if(action==='setup')this.setPreview('ready');
      else if(action==='cancel_setup')this.setPreview('setup_required');
      else if(action==='stop')this.setPreview('ready');
      else if(action==='pause')this.setPreview('paused');
      else if(action==='resume'||action==='enable')this.setPreview('active');
      else if(action==='calibrate')this.setPreview('practicing');
      else if(action==='practice')this.setPreview('practicing');
      else if(action==='save'){this.profile=data.profile;this.setPreview('ready');}
      else if(action==='dictate'||action==='voice_access')this.state.voice={message:'Interface preview: no Windows speech command was sent.'};
      return {success:true,aircontrol:this.state};
    }
    setPreview(name){
      if(!desktop.preview)return;
      const active=['calibrating','practicing','active','paused','tracking_lost'].includes(name);
      const calibrated=['practicing','active','paused','tracking_lost'].includes(name);
      this.render({state:name,profile:structuredClone(this.profile),message:'Interface preview · no camera or native input. '+name.replaceAll('_',' '),setup:{state:'ready',ready:name!=='setup_required',message:'Synthetic setup state; no installation is performed.'},camera_active:active,owns_input:['active','paused','tracking_lost'].includes(name),calibrated,calibration_points:calibrated?['center','top_left','top_right','bottom_left','bottom_right']:[],practice_ready:calibrated,practice_frames:calibrated?45:0,practice_actions:calibrated?2:0,point:[.57,.44],gesture:'pinch_index',action:'left_drag',progress:.65,tracking:active&&name!=='tracking_lost',metrics:{fps:27,median_latency_ms:null},voice:{message:'Preview: Windows manages microphone setup and dictation.'},expression_practice:{neutral:false,seen:[]}});
      if(!this.cameras.length){this.cameras=[{id:'0',name:'Sample PC webcam · preview'}];$('airCamera').replaceChildren(new Option(this.cameras[0].name,'0'));}
    }
  }
  window.TouchHelmAir=new AirPanel();
})();
