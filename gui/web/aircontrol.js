/* Owned desktop AirControl UI. Camera frames never use a LAN asset route. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),desktop=window.TouchHelmDesktop;
  const setText=(id,value)=>{if($(id).textContent!==String(value))$(id).textContent=value;};
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
  function defaults(name='everyday',mode='head'){
    const bindings={pinch_index:'left_drag',pinch_middle:'right_click',two_fingers:'scroll',closed_fist:'pause',open_palm:'resume',thumb_up:'none',thumb_down:'none',smile:'none',wink_left:'none',wink_right:'none',brows_up:'none'};
    if(name==='presenter')Object.assign(bindings,{thumb_up:'next_slide',thumb_down:'previous_slide'});
    if(name==='media')Object.assign(bindings,{thumb_up:'play_pause',thumb_down:'next_track'});
    return {version:1,name,mode,hand:'auto',camera_id:'0',monitor_id:'',mirror:true,landmarks:true,auto_dictation:true,sensitivity:1,smoothing:mode==='head'?.6:.45,pinch_close:.25,pinch_open:.4,dwell_ms:900,hold_ms:400,cooldown_ms:700,head_range:18,head_stability:8,hand_stability:6,dwell_radius:22,dwell:true,expressions_calibrated:false,calibrated_expressions:[],expression_thresholds:{},bindings,calibration:{hand_bounds:[.15,.15,.85,.85],head_neutral:[0,0]}};
  }
  class AirPanel {
    constructor(){
      this.profile=defaults();this.state={state:'setup_required',camera_active:false,owns_input:false,profile:this.profile,setup:{state:'setup_required',ready:false,message:'Prepare the isolated camera runtime. Your phone controls keep working.'},voice:{message:'Select a PC text field, then use Dictate.'}};
      this.dirty=false;this.busy=false;this.frameBusy=false;this.cameras=[];this.guidePinned=false;this.lastPreview='';this.lastSeq=-1;this.error='';
      this.mountWorkspace();
      $('airEnable').before($('airStart'));
      this.mappingRows();this.loadProfile(this.profile);this.bind();this.guide(this.profile.mode==='hand'?'point':'head');
      if(desktop.state?.aircontrol)this.render(desktop.state.aircontrol);else this.render(this.state);
      window.addEventListener('touchhelm:desktop-state',event=>{if(event.detail.aircontrol)this.render(event.detail.aircontrol);});
      window.addEventListener('touchhelm:desktop-panel',event=>{
        document.body.classList.toggle('air-panel-hidden',event.detail!=='aircontrol');
        if(event.detail==='aircontrol'&&!this.discovered){this.discovered=true;this.refreshDevices();}
      });
      this.frameTimer=setInterval(()=>this.pollFrame(),100);
      document.body.classList.add('air-panel-hidden');
    }
    mountWorkspace(){
      const panel=document.querySelector('[data-page=aircontrol]'),coach=$('airCoach'),workspace=panel.querySelector('.air-workspace');
      const progress=document.createElement('div');progress.className='air-progress-row';$('airWorkflow').before(progress);progress.append($('airWorkflow'),$('airSetupSummary'));
      panel.querySelector('.air-heading>div').append($('airModeSummary'));
      panel.dataset.airCurrentTab='controls';this.currentTab='controls';this.viewportRevision=0;
      workspace.before(panel.querySelector('.air-tabs'));
      coach.prepend($('airCalibrationControls'));
      const guide=document.createElement('details');guide.id='airGuideDisclosure';
      const summary=document.createElement('summary');summary.textContent='Gesture help';guide.append(summary);
      for(const id of ['airGuideTitle','airGuideArt','airGuideDescription'])guide.append($(id));
      guide.append($('airGuideSelect').parentElement);coach.append(guide);
      coach.insertBefore($('airHeadActions'),guide);
      const scroll=document.createElement('div');scroll.className='air-scroll-controls';
      scroll.innerHTML='<button id="airScroll" class="secondary-button">Scroll</button><button id="airScrollUp" class="secondary-button" hidden>Scroll up</button><button id="airScrollDown" class="secondary-button" hidden>Scroll down</button><button id="airScrollDone" class="secondary-button" hidden>Return to pointer</button>';
      $('airHeadActions').append(scroll);
      const exercises=document.createElement('div');exercises.id='airExerciseControls';exercises.className='air-exercise-controls';
      exercises.innerHTML='<h2>Practice a task</h2><label for="airExercise">Exercise</label><select id="airExercise"><option value="click">Click three targets</option><option value="drag">Drag to a destination</option><option value="scroll">Scroll to a marker</option><option value="free">Free practice</option></select><button id="airExerciseStart" class="secondary-button">Start exercise</button><div class="button-row"><button id="airExerciseReset" class="quiet-button">Reset exercise</button><button id="airExercisePause" class="quiet-button">Pause exercise</button></div><p id="airExerciseResult" role="status"></p><span id="airExerciseTime" class="muted" aria-live="off"></span>';
      coach.insertBefore(exercises,$('airHeadActions'));
      $('airStage').append($('airPracticeScreen'));
      const settings=panel.querySelector('[data-air-content=settings]');settings.prepend(panel.querySelector('.air-expression-setup'));
      const setup=document.createElement('details');setup.id='airSetupChoices';setup.open=true;
      setup.innerHTML='<summary>Camera, monitor and control mode</summary>';
      setup.append(panel.querySelector('.air-mode-row'),panel.querySelector('.air-selectors'),$('airCameraMessage'));
      workspace.after(setup);panel.querySelector('[data-air-content=controls]').append($('airSetup'));
      panel.querySelector('.air-session-actions').append($('airInstall'),$('airCancelInstall'));
      for(const tab of panel.querySelectorAll('[data-air-tab]')){
        tab.id='air-tab-'+tab.dataset.airTab;tab.setAttribute('aria-controls','air-panel-'+tab.dataset.airTab);
        const content=panel.querySelector(`[data-air-content=${tab.dataset.airTab}]`);
        content.id='air-panel-'+tab.dataset.airTab;content.setAttribute('aria-labelledby',tab.id);content.tabIndex=0;
      }
      this.viewportObserver=new ResizeObserver(()=>this.queueViewport());this.viewportObserver.observe($('airStage'));
    }
    queueViewport(){
      if(this.viewportQueued)return;this.viewportQueued=true;
      requestAnimationFrame(async()=>{
        this.viewportQueued=false;const r=$('airStage').getBoundingClientRect();
        const width=Math.round(r.width),height=Math.round(r.height);
        if(width<160||height<160||width>8192||height>8192)return;
        const key=width+'x'+height;if(key===this.viewportKey)return;
        this.viewportKey=key;this.lastViewport={width,height};const revision=++this.viewportRevision;
        this.viewportPending=revision;
        this.renderPractice(this.state);
        try{
          if(!desktop.preview){
            const result=await desktop.invoke('aircontrol','practice_viewport',{width,height,revision});
            if(!result.success)throw Error(result.error);
            if(revision!==this.viewportPending)return;
            const p=result.aircontrol?.practice,ack=p?.viewport_revision;
            if(!Number.isSafeInteger(ack)||ack<0||ack>=2147483647||!Array.isArray(p.viewport))throw Error('Practice area acknowledgement is unavailable.');
            this.viewportRevision=Math.max(this.viewportRevision,ack);
            if(ack!==revision||ack<this.state.practice?.viewport_revision||p.viewport[0]!==width||p.viewport[1]!==height){
              this.viewportKey='';this.queueViewport();return;
            }
            this.viewportPending=0;this.render(result.aircontrol);
          }
          else if(revision===this.viewportRevision){this.viewportPending=0;this.renderPractice(this.state);}
        }catch(error){if(revision!==this.viewportPending)return;this.viewportKey='';this.error='Practice area could not update: '+error.message;setText('airMessage',this.error);}
      });
    }
    practiceViewportReady(s=this.state){
      const p=s.practice,v=this.lastViewport;
      return desktop.preview||!this.viewportPending&&!!v&&p?.viewport?.[0]===v.width&&p.viewport[1]===v.height&&p.viewport_revision===this.viewportRevision;
    }
    mappingRows(){
      const rows=Object.entries(gestures).map(([key,name])=>{
        const row=document.createElement('div');row.className='air-map-row';
        const label=document.createElement('label');label.htmlFor='airMap_'+key;label.textContent=name;
        const note=document.createElement('small');note.textContent=['closed_fist','open_palm'].includes(key)?'Reserved escape control':['smile','wink_left','wink_right','brows_up'].includes(key)?'Requires expression practice':'Choose an action';label.append(note);
        const select=document.createElement('select');select.id='airMap_'+key;select.dataset.airGesture=key;
        select.disabled=['closed_fist','open_palm'].includes(key);
        for(const [value,text]of Object.entries(labels)){
          if(value==='left_drag'&&!['pinch_index','pinch_middle','smile','wink_left','wink_right','brows_up'].includes(key)||value==='scroll'&&key!=='two_fingers'||value==='pause'&&key!=='closed_fist'||value==='resume'&&key!=='open_palm')continue;
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
      $('airCaptureTarget').addEventListener('click',()=>{const quick=this.profile.mode==='hand'&&!$('airFineCalibration').checked;this.call('calibrate',{target:quick?'center':this.nextTarget(),quick});});
      $('airFineCalibration').addEventListener('change',()=>this.render(this.state));
      $('airRestartCalibration').addEventListener('click',()=>this.start());
      $('airEnable').addEventListener('click',()=>this.call('enable'));
      for(const button of document.querySelectorAll('[data-air-dwell]'))button.addEventListener('click',()=>this.call('dwell_'+button.dataset.airDwell));
      $('airReleaseDrag').addEventListener('click',()=>this.call('release_drag'));
      $('airChangeSetup').addEventListener('click',async()=>{if(this.state.camera_active&&!await this.call('stop'))return;$('airSetupChoices').open=true;$('airSetupChoices').scrollIntoView({block:'nearest'});});
      for(const [id,action]of [['airScroll','head_scroll'],['airScrollUp','scroll_up'],['airScrollDown','scroll_down'],['airScrollDone','scroll_done']])$(id).addEventListener('click',()=>this.call(action));
      $('airExerciseStart').addEventListener('click',async()=>{if(this.viewportPending)return;if(await this.call('practice_start',{name:$('airExercise').value}))this.tab('practice');});
      $('airExerciseReset').addEventListener('click',()=>this.call('practice_reset'));
      $('airExercisePause').addEventListener('click',()=>this.call(this.state.practice?.status==='paused'?'practice_resume':'practice_pause'));
      $('airResetMeasurements').addEventListener('click',()=>this.call('reset_measurements'));
      $('airExportReport').addEventListener('click',()=>this.exportReport());
      $('airPractice').addEventListener('click',()=>this.tab('practice'));
      $('airReturnPractice').addEventListener('click',()=>this.call('practice'));
      $('airExpressionNeutral').addEventListener('click',()=>this.call('expression_sample',{phase:'neutral'}));
      $('airExpressionPractice').addEventListener('click',()=>this.call('expression_sample',{phase:'gesture',gesture:$('airExpressionSelect').value}));
      $('airExpressionAssign').addEventListener('click',()=>this.call('expression_bind',{gesture:$('airExpressionSelect').value,action:$('airExpressionAction').value}));
      $('airExpressionSelect').addEventListener('change',()=>{this.guide($('airExpressionSelect').value);this.render(this.state);});
      $('airGuideSelect').addEventListener('change',()=>{this.guidePinned=true;this.guide($('airGuideSelect').value);});
      for(const button of document.querySelectorAll('[data-air-mode]'))button.addEventListener('click',async()=>{
        if(this.busy)return;const mode=button.dataset.airMode;
        this.profile.mode=mode;this.dirty=true;this.loadMode(mode);this.guide(mode==='hand'?'point':'head');
        this.render(this.state);
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
      $('airCalibrationHelp').textContent=mode==='hand'?'Hold your index finger comfortably near the middle and use Quick setup. Five-target fine tuning is available beside the preview.':'Look straight ahead and capture your neutral head position. Then move through the practice desk; Combined also requires your hand in view.';
    }
    loadProfile(profile){
      this.profile=structuredClone(profile);this.loadMode(profile.mode);$('airProfile').value=profile.name;
      const fields={hand:'airHand',camera_id:'airCamera',monitor_id:'airMonitor',sensitivity:'airSensitivity',smoothing:'airSmoothing',dwell_ms:'airDwellMs',hold_ms:'airHoldMs',cooldown_ms:'airCooldownMs',pinch_close:'airPinchClose',pinch_open:'airPinchOpen',head_range:'airHeadRange',mirror:'airMirror',landmarks:'airShowLandmarks',dwell:'airDwell',auto_dictation:'airAutoDictation'};
      for(const [key,id]of Object.entries(fields)){if($(id).type==='checkbox')$(id).checked=profile[key];else $(id).value=profile[key];}
      $('airHeadStability').value=profile.head_stability??8;$('airHandStability').value=profile.hand_stability??6;$('airDwellRadius').value=profile.dwell_radius??22;
      for(const [key,value]of Object.entries(profile.bindings||{})){const node=$('airMap_'+key);if(node)node.value=value;}
      this.rangeLabels();this.dirty=false;
    }
    capture(){
      const profile=structuredClone(this.profile);profile.name=$('airProfile').value;
      for(const [key,id]of Object.entries({hand:'airHand',camera_id:'airCamera',monitor_id:'airMonitor'}))profile[key]=$(id).value;
      for(const [key,id]of Object.entries({sensitivity:'airSensitivity',smoothing:'airSmoothing',dwell_ms:'airDwellMs',hold_ms:'airHoldMs',cooldown_ms:'airCooldownMs',pinch_close:'airPinchClose',pinch_open:'airPinchOpen',head_range:'airHeadRange'}))profile[key]=Number($(id).value);
      for(const [key,id]of Object.entries({mirror:'airMirror',landmarks:'airShowLandmarks',dwell:'airDwell',auto_dictation:'airAutoDictation'}))profile[key]=$(id).checked;
      for(const key of Object.keys(gestures))profile.bindings[key]=$('airMap_'+key).value;
      profile.head_stability=Number($('airHeadStability').value);profile.hand_stability=Number($('airHandStability').value);profile.dwell_radius=Number($('airDwellRadius').value);
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
      catch(error){this.error=error.message;$('airMappingError').textContent=error.message;$('airMappingError').hidden=false;setText('airMessage',error.message);}
    }
    async start(){
      try{const profile=this.capture();this.validate(profile);if(await this.call('start',{profile})){this.profile=profile;this.dirty=false;this.tab('controls');}}
      catch(error){this.error=error.message;setText('airMessage',error.message);}
    }
    async call(action,data){
      if(['practice_start','practice_reset','practice_resume'].includes(action)){
        if(!this.practiceViewportReady())return false;
        data={...data,viewport_revision:this.state.practice?.viewport_revision};
      }
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
      }catch(error){this.error=error.message;setText('airMessage',error.message);return false;}
      finally{this.busy=false;this.render(this.state);}
    }
    tab(name){
      for(const node of document.querySelectorAll('[data-air-tab]')){const active=node.dataset.airTab===name;node.setAttribute('aria-selected',String(active));node.tabIndex=active?0:-1;}
      for(const node of document.querySelectorAll('[data-air-content]'))node.hidden=node.dataset.airContent!==name;
      this.currentTab=name;document.querySelector('[data-page=aircontrol]').dataset.airCurrentTab=name;
      this.renderPractice(this.state);
      $('airPracticeScreen').hidden=name!=='practice';$('airExerciseControls').hidden=name!=='practice';
      if(['settings','mappings','diagnostics'].includes(name))document.querySelector(`[data-air-content=${name}]`).scrollIntoView({block:'start'});
      else document.querySelector('.desktop-content').scrollTop=0;
      this.queueViewport();
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
      if(Number.isSafeInteger(s.practice?.viewport_revision)&&s.practice.viewport_revision>=0)this.viewportRevision=Math.max(this.viewportRevision,s.practice.viewport_revision);
      const view=window.TouchHelmAirView.derive(s,this.profile);this.view=view;
      if(s.profile&&!this.dirty)this.loadProfile(s.profile);
      setText('airState',s.state==='practicing'?'Practice · PC input off':s.state==='active'?'PC control on':String(s.state||'setup_required').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()));$('airState').dataset.state=s.state;
      const practiceMessage=s.practice_ready?'Practice click recognized. Choose Enable PC control above to move the Windows cursor.':'Practice only: move the simulated cursor below and test a click. Your Windows cursor stays still until you enable PC control.';
      setText('airMessage',this.error||s.message||(s.state==='practicing'?practiceMessage:'Choose Start camera for calibration and practice.'));
      $('airReadiness').textContent=view.instruction;$('airModeSummary').textContent=view.modeSummary;
      $('airSetupChoices').hidden=active;$('airChangeSetup').hidden=!active;
      $('airWorkflow').hidden=s.owns_input;
      const steps=['camera','calibrate','practice','enable'];
      for(const item of document.querySelectorAll('[data-air-step]')){
        const current=item.dataset.airStep===view.step;item.toggleAttribute('data-current',current);
        if(current)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
        item.dataset.complete=String(steps.indexOf(item.dataset.airStep)<steps.indexOf(view.step));
      }
      $('homeAirStatus').textContent=active?'AirControl camera is running. Selecting Phone stops it; Switch mode alone leaves the session intact.':'The camera stays off until you choose Start camera.';
      $('airSetup').hidden=!!setup.ready;$('airSetupMessage').textContent=setup.message||'Prepare the isolated camera runtime.';
      const installing=setup.state==='installing';$('airSetupProgress').hidden=!installing;
      if(Number.isFinite(setup.progress))$('airSetupProgress').value=setup.progress;else $('airSetupProgress').removeAttribute('value');
      $('airInstall').disabled=this.busy||installing;$('airCancelInstall').hidden=!installing;
      $('airInstall').hidden=!!setup.ready;
      $('airPause').disabled=this.busy||!s.owns_input;$('airPause').textContent=s.state==='active'?'Pause':'Resume';
      $('airPause').hidden=!s.owns_input;
      $('airStop').disabled=this.busy||!active;$('airStart').disabled=this.busy||!setup.ready||!this.cameras.length||active;
      $('airStart').hidden=active||!setup.ready;$('airStop').hidden=!active;
      $('airStart').textContent=active?'Camera running':'Start camera';$('airCamera').disabled=active;$('airRefreshCameras').disabled=active;
      $('airMonitor').disabled=active;$('airRecenter').disabled=this.busy||!active;
      $('airCaptureTarget').disabled=this.busy||!active||s.calibrated||!['calibrating','practicing'].includes(s.state)||!(s.calibration_ready??s.tracking);
      $('airRestartCalibration').disabled=this.busy||!active;$('airPractice').disabled=!s.calibrated;
      $('airEnable').disabled=this.busy||!active||!(s.activation?.ready??s.practice_ready)||!s.calibrated||s.owns_input;
      $('airEnable').hidden=!active||!!s.owns_input||!s.calibrated;
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
      if(active&&!s.tracking){
        const detail=s.tracking_details||{};
        const reason=detail.processing_delayed?'Processing is over 250 ms behind. Reduce other CPU load, then resume with stable tracking.':
          sources?.hand_enabled&&!sources.hand?detail.hand:sources?.face_enabled&&!sources.face?detail.face:'';
        if(reason)$('airDetected').textContent=reason;
      }
      $('airFps').textContent=Number.isFinite(s.metrics?.fps)?s.metrics.fps+' fps':'— fps';
      $('airHoldFill').style.width=(Math.max(0,Math.min(1,s.progress||0))*100)+'%';
      if(!this.guidePinned&&guides[s.gesture])this.guide(s.gesture);
      $('airVoiceMessage').textContent=s.voice?.message||'Windows manages dictation and microphone setup.';
      $('airHotkeyStatus').textContent=s.hotkey||'Pause hotkey is registered after PC control starts.';
      const quick=s.profile?.mode==='hand'&&!$('airFineCalibration').checked;
      const next=quick?'center':this.nextTarget();$('airCaptureTarget').textContent=quick?'Use this center':'Capture '+next.replaceAll('_',' ');
      const calibrating=active&&s.state==='calibrating';
      $('airCalibrationControls').hidden=!calibrating;
      $('airFineCalibration').parentElement.hidden=s.profile?.mode!=='hand';
      $('airCalibrationStep').textContent='Calibration · '+(quick?1:((s.calibration_points?.length||0)+1))+' of '+(s.profile?.mode==='hand'&&!quick?5:1);
      $('airCalibrationHint').textContent=s.profile?.mode==='hand'?
        (s.tracking?(quick?'Hold your finger comfortably near the middle. Use this center to start practice.':'Move the finger marker toward the '+next.replaceAll('_',' ')+' target, hold still, then capture.'):'Show your whole hand with your index finger extended. A live finger pointer appears when tracked.'):
        (s.tracking?'Look straight ahead, hold your head still, then capture your neutral position.':'Keep one face clearly visible and look toward the camera.');
      if(!active||!s.tracking)$('airTrackedPointer').hidden=true;
      $('airCalibrationStatus').textContent=s.calibrated?'Calibration complete. Practice a click, then enable PC control.':(s.calibration_points?.length||0)+' targets captured';
      const target=$('airCalibrationTarget');target.hidden=!active||s.state!=='calibrating';
      const position={center:[50,50],top_left:[22,22],top_right:[78,22],bottom_left:[22,78],bottom_right:[78,78]}[next];target.style.left=position[0]+'%';target.style.top=position[1]+'%';
      $('airPracticeResult').textContent=`${s.practice_frames>=15?'Pointer tracking ready':'Keep your hand or face steadily visible'} · ${s.practice_actions?'Practice click recognized':'Test a pinch click, or a head dwell click'}. ${s.practice_ready?'Ready: Enable PC control above.':'Windows input is off.'}`;
      if(s.point)this.glidePointer(s.point);else this.glide=null;
      $('airPracticePointer').hidden=!active||!s.point;
      $('airPracticePointer').dataset.dragging=String(!!s.dragging);
      $('airPracticePointer').style.setProperty('--dwell-progress',Math.round((s.progress||0)*360)+'deg');
      const head=s.profile?.mode==='head',selection=s.dwell_action||'left_click';
      $('airHeadActions').hidden=!head||!active||!s.calibrated;
      $('airScroll').hidden=!!s.head_scroll;
      for(const id of ['airScrollUp','airScrollDown','airScrollDone'])$(id).hidden=!s.head_scroll;
      for(const id of ['airScroll','airScrollUp','airScrollDown','airScrollDone'])$(id).disabled=this.busy||!['active','practicing'].includes(s.state);
      for(const button of document.querySelectorAll('[data-air-dwell]')){
        const action={left:'left_click',double:'double_click',right:'right_click',drag:'drag'}[button.dataset.airDwell];
        button.setAttribute('aria-pressed',String(action===selection));button.disabled=this.busy||!['active','practicing'].includes(s.state);
      }
      $('airReleaseDrag').disabled=this.busy||!s.dragging;$('airReleaseDrag').hidden=!s.dragging;
      $('airDwellStatus').textContent=s.dragging?'Drag held. Move to the destination, then settle to drop. Release drag also lets go immediately.':selection==='drag'?'Drag: settle to hold, move to the destination, then settle to drop.':
        'Settle to '+(labels[selection]||'Left click').toLowerCase()+'. Move away before clicking again. Right and double-click return to Left click.';
      $('airDwellProgress').value=Math.max(0,Math.min(1,s.progress||0));
      $('airDwellProgress').setAttribute('aria-valuetext',Math.round((s.progress||0)*100)+'% of dwell hold');
      setText('airPracticeAction',s.actions?.[0]||labels[s.action]||'Waiting for your first move');
      const expression=s.expression_practice||{};
      if(s.profile?.calibrated_expressions){this.profile.calibrated_expressions=[...s.profile.calibrated_expressions];this.profile.expressions_calibrated=!!s.profile.expressions_calibrated;this.profile.expression_thresholds=structuredClone(s.profile.expression_thresholds||{});}
      const selected=$('airExpressionSelect').value,limits=s.profile?.expression_thresholds?.[selected];
      const faceReady=active&&s.state==='practicing'&&s.profile?.mode!=='hand'&&(sources?sources.face:s.tracking);
      $('airExpressionNeutral').disabled=this.busy||!faceReady;
      $('airExpressionPractice').disabled=this.busy||!faceReady||!expression.measured_neutral;
      $('airExpressionAssign').disabled=this.busy||!faceReady||!s.profile?.calibrated_expressions?.includes(selected);
      for(const meter of document.querySelectorAll('[data-air-expression]')){
        const value=expression.values?.[meter.dataset.airExpression];meter.value=Number.isFinite(value)?value:0;
        meter.setAttribute('aria-valuetext',Number.isFinite(value)?Math.round(value*100)+'% activation':'Unavailable');
      }
      setText('airExpressionResult',this.error||(!faceReady?'Use Head & Face or Combined practice with your face clearly tracked.':
        limits?'Personal threshold '+Math.round(limits.on*100)+'% activation. Test '+gestures[selected]+' in practice before enabling PC control.':
        expression.measured_neutral?'Relaxed face captured. Hold '+gestures[selected]+' for one second, then Capture expression.':'Hold a relaxed face for one second, then capture it.'));
      const metrics=s.metrics||{};$('airMetrics').textContent=`Tracked updates: ${metrics.fps??'unknown'} fps · median frame-to-input latency: ${metrics.median_latency_ms??'unknown'} ms · inference: ${metrics.inference_ms??'unknown'} ms · frame age: ${metrics.frame_age_ms??'unknown'} ms · captured: ${metrics.capture_fps??'unknown'} fps · rejected stale/invalid observations: ${metrics.rejected_observations??0} · worker CPU: ${metrics.cpu_percent??'unknown'}% of total PC · worker memory: ${metrics.memory_mb??'unknown'} MB. These are measurements, not guaranteed performance.`;
      window.TouchHelmThemes?.setInteractionActive?.(active);
      this.renderPractice(s);
      this.renderDiagnostics(s.metrics||{});
      if(!active){this.lastPreview='';$('airPreview').hidden=true;$('airPreview').removeAttribute('src');$('airLandmarks').getContext('2d').clearRect(0,0,640,480);}
    }
    renderPractice(s){
      const p=s.practice||{name:'free',status:'idle',targets:[]},key=JSON.stringify([p.name,p.targets,p.target_index]);
      const viewportReady=this.practiceViewportReady(s);
      $('airTaskTargets').hidden=!viewportReady;$('airPracticeDock').hidden=!viewportReady;
      $('airHeadActions').hidden=s.profile?.mode!=='head'||!s.camera_active||!s.calibrated||(this.currentTab==='practice'&&p.name!=='free');
      if(key!==this.targetKey){
        this.targetKey=key;$('airTaskTargets').replaceChildren();
        for(const [i,t]of (p.targets||[]).entries()){
          const target=document.createElement('div');target.className='air-task-target'+(i===(p.name==='drag'?0:p.target_index)?' is-current':'');
          target.style.cssText=`left:${t.x*100}%;top:${t.y*100}%;width:${t.width*100}%;height:${t.height*100}%;`;
          target.textContent=p.name==='drag'?(i?'Drop here':'Hold here'):String(i+1);$('airTaskTargets').append(target);
        }
      }
      $('airPracticeScreen').hidden=this.currentTab!=='practice';$('airExerciseControls').hidden=this.currentTab!=='practice';
      $('airPracticeDocument').hidden=p.name!=='scroll';$('airPracticeDocument').style.setProperty('--document-position',p.document_position||0);
      $('airTaskPrompt').textContent=!viewportReady?'Updating the practice area. Exercises wait for matching geometry.':p.status==='complete'?'Exercise complete. Reset to try again.':p.status==='paused'?'Exercise paused. Resume when ready.':p.name==='click'?'Settle on the highlighted target, then click.':p.name==='drag'?'Hold the source, move to the destination, then release.':p.name==='scroll'?'Scroll down until you reach the destination.':'Move freely. Settle to click, or use a pinch.';
      setText('airExerciseResult',p.name==='free'?'Free practice. Windows input stays off until Enable.':`${p.successes||0} completed, ${p.misses||0} missed. ${p.status==='complete'?'Exercise complete.':''}`);
      $('airExerciseTime').textContent=p.name==='free'?'':'Elapsed '+Math.round((p.elapsed_ms||0)/1000)+' seconds';
      $('airExerciseStart').disabled=this.busy||!s.camera_active||!s.calibrated||!viewportReady;
      $('airExerciseReset').disabled=this.busy||s.state!=='practicing'||p.name==='free'||!viewportReady;
      $('airExercisePause').disabled=this.busy||s.state!=='practicing'||!['running','paused'].includes(p.status)||(p.status==='paused'&&!viewportReady);
      $('airExercisePause').textContent=p.status==='paused'?'Resume exercise':'Pause exercise';
      const regions=s.scroll_regions||[],dockKey=JSON.stringify(regions);
      if(dockKey!==this.dockKey){this.dockKey=dockKey;$('airPracticeDock').replaceChildren();for(const r of regions){
        const button=document.createElement('button');button.type='button';button.textContent=r.label;button.dataset.action=r.action;
        button.style.cssText=`left:${r.rect[0]*100}%;top:${r.rect[1]*100}%;width:${(r.rect[2]-r.rect[0])*100}%;height:${(r.rect[3]-r.rect[1])*100}%;`;
        button.addEventListener('click',()=>this.call(r.action==='pause'?'practice_pause':r.action));$('airPracticeDock').append(button);
      }}
    }
    renderDiagnostics(metrics){
      const fields=[['capture_fps','Camera delivery','fps'],['observation_fps','Accepted observations','fps'],['inference_ms','Inference','ms'],
        ['frame_age_ms','Frame age','ms'],['median_latency_ms','Median frame-to-input','ms'],['p95_latency_ms','P95 frame-to-input','ms'],
        ['latency_sample_count','Latency samples','/ 600 maximum'],['tracking_interruptions','Tracking interruptions',''],
        ['cpu_percent','Worker CPU','% of this PC'],['memory_mb','Worker memory','MB'],['duration_seconds','Measurement duration','seconds']];
      const key=JSON.stringify(metrics);
      if(key!==this.diagnosticKey){this.diagnosticKey=key;const list=document.createElement('dl');list.className='air-diagnostics-grid';
        for(const [name,label,unit]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;
          dd.textContent=Number.isFinite(metrics[name])?metrics[name]+' '+unit:'Not measured';list.append(dt,dd);}
        $('airDiagnostics').replaceChildren(list);
      }
      $('airExportReport').disabled=this.busy;$('airResetMeasurements').disabled=this.busy;
    }
    async exportReport(){
      if(this.busy)return;this.busy=true;this.render(this.state);
      try{
        const result=desktop.preview?{success:true,report:{version:1,build:'',mode:this.profile.mode,display_size:[],duration_seconds:0,metrics:{latency_sample_count:0,median_latency_ms:null,p95_latency_ms:null},exercises:[]}}:await desktop.invoke('aircontrol','export_report',{});
        if(!result.success||!result.report)throw Error(result.error||'The session report is unavailable.');
        const url=URL.createObjectURL(new Blob([JSON.stringify(result.report,null,2)],{type:'application/json'})),link=document.createElement('a');
        link.href=url;link.download='touchhelm-aircontrol-report.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(error){this.error='Report could not export: '+error.message;setText('airMessage',this.error);}
      finally{this.busy=false;this.render(this.state);}
    }
    glidePointer(point){
      // Camera frames arrive at 10-15 Hz; ease the drawn cursor between them so a steady pointer does not visibly step.
      const node=$('airPracticePointer'),g=this.glide||(this.glide={x:point[0],y:point[1],tx:point[0],ty:point[1],last:0,raf:0});
      const jump=Math.hypot(point[0]-g.tx,point[1]-g.ty)>.35,still=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      g.tx=point[0];g.ty=point[1];
      const place=()=>{node.style.left=g.x*100+'%';node.style.top=g.y*100+'%';};
      if(jump||still||typeof requestAnimationFrame!=='function'||node.hidden){g.x=g.tx;g.y=g.ty;place();return;}
      if(g.raf)return;
      const tick=now=>{
        const dt=Math.min(.1,Math.max(0,(now-(g.last||now))/1000));g.last=now;
        const k=1-Math.exp(-dt/.045);g.x+=(g.tx-g.x)*k;g.y+=(g.ty-g.y)*k;
        const settled=Math.hypot(g.tx-g.x,g.ty-g.y)<.0002;if(settled){g.x=g.tx;g.y=g.ty;}
        place();g.raf=settled?0:requestAnimationFrame(tick);if(settled)g.last=0;
      };
      g.raf=requestAnimationFrame(tick);
    }
    async pollFrame(){
      if(this.frameBusy||document.hidden||!this.state.camera_active||document.querySelector('[data-page=aircontrol]').hidden||desktop.preview)return;
      this.frameBusy=true;
      try{const state=await desktop.invoke('get_aircontrol_frame');this.render(state);this.draw(state);}catch(error){setText('airMessage','Camera preview unavailable: '+error.message);}
      finally{this.frameBusy=false;}
    }
    draw(state){
      if(state.preview&&state.preview!==this.lastPreview&&state.preview.length<=300000&&/^[A-Za-z0-9+/=]+$/.test(state.preview)){
        this.lastPreview=state.preview;$('airPreview').src='data:image/jpeg;base64,'+state.preview;$('airPreview').hidden=false;$('airCameraEmpty').hidden=true;
      }
      const canvas=$('airLandmarks'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,640,480);
      const hand=state.hand_points||[],face=state.face_points||[];
      const point=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p.every(v=>v>=-1&&v<=2);
      const pointer=$('airTrackedPointer'),head=state.profile?.mode!=='hand',tip=head?state.point:hand[8];
      pointer.querySelector('small').textContent=head?'Head pointer':'Your finger';
      pointer.hidden=!state.camera_active||!state.tracking||!((head?state.tracking_sources?.face:state.tracking_sources?.hand)??true)||!point(tip);
      if(!pointer.hidden){pointer.style.left=Math.max(0,Math.min(1,tip[0]))*100+'%';pointer.style.top=Math.max(0,Math.min(1,tip[1]))*100+'%';}
      if(!$('airShowLandmarks').checked)return;
      ctx.strokeStyle='#7ff2df';ctx.fillStyle='#fff';ctx.lineWidth=2;
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
      else if(action==='expression_sample'){
        if(data.phase==='neutral')this.state.expression_practice={...this.state.expression_practice,neutral:true,measured_neutral:true,values:{smile:.1,wink_left:.1,wink_right:.1,brows_up:.1}};
        else {const gesture=data.gesture;this.state.profile.calibrated_expressions=[...new Set([...this.state.profile.calibrated_expressions,gesture])];this.state.profile.expressions_calibrated=true;this.state.profile.expression_thresholds={...this.state.profile.expression_thresholds,[gesture]:{on:.35,off:.2}};this.state.expression_practice.values[gesture]=.6;}
      }
      else if(action==='expression_bind')this.state.profile.bindings[data.gesture]=data.action;
      else if(action==='practice')this.setPreview('practicing');
      else if(action==='head_scroll'){this.state.head_scroll=true;this.state.scroll_regions=[];}
      else if(action==='scroll_done'){this.state.head_scroll=false;this.state.scroll_regions=[];}
      else if(action==='practice_start'){
        this.setPreview('practicing');const name=data.name;
        const w=64/(this.lastViewport?.width||640),h=64/(this.lastViewport?.height||480),centers=name==='click'?[[.25,.5],[.75,.5],[.5,.25]]:name==='drag'?[[.25,.5],[.75,.5]]:[];
        this.state.practice={name,status:name==='free'?'idle':'running',targets:centers.map(([x,y])=>({x:x-w/2,y:y-h/2,width:w,height:h})),target_index:0,successes:0,misses:0,elapsed_ms:0,document_position:0};
        if(this.profile.mode==='head'&&name==='drag')this.state.dwell_action='drag';
        if(this.profile.mode==='head'&&name==='scroll')this.state.head_scroll=true;
      }
      else if(action==='practice_pause')this.state.practice={...this.state.practice,status:'paused'};
      else if(action==='practice_resume')this.state.practice={...this.state.practice,status:'running'};
      else if(action==='practice_reset')return this.previewAction('practice_start',{name:this.state.practice?.name||'click'});
      else if(action==='reset_measurements')this.state.metrics={...this.state.metrics,median_latency_ms:null,p95_latency_ms:null,latency_sample_count:0,tracking_interruptions:0,duration_seconds:0};
      else if(action.startsWith('dwell_')){this.state.dwell_action=action==='dwell_drag'&&this.state.dragging?'left_click':{left:'left_click',double:'double_click',right:'right_click',drag:'drag'}[action.slice(6)];this.state.dragging=false;}
      else if(action==='release_drag'){this.state.dragging=false;this.state.dwell_action='left_click';}
      else if(action==='save'){this.profile=data.profile;this.setPreview('ready');}
      else if(action==='dictate'||action==='voice_access')this.state.voice={message:'Interface preview: no Windows speech command was sent.'};
      return {success:true,aircontrol:this.state};
    }
    setPreview(name){
      if(!desktop.preview)return;
      const active=['calibrating','practicing','active','paused','tracking_lost'].includes(name);
      const head=this.profile.mode==='head';
      if(!this.guidePinned)this.guide(head?'head':'point');
      const calibrated=['practicing','active','paused','tracking_lost'].includes(name);
      this.render({state:name,profile:structuredClone(this.profile),message:'Interface preview · no camera or native input. '+name.replaceAll('_',' '),setup:{state:'ready',ready:name!=='setup_required',message:'Synthetic setup state; no installation is performed.'},camera_active:active,owns_input:['active','paused','tracking_lost'].includes(name),calibrated,calibration_points:calibrated?['center','top_left','top_right','bottom_left','bottom_right']:[],practice_ready:calibrated,practice_frames:calibrated?45:0,practice_actions:calibrated?2:0,point:[.57,.44],gesture:head?'':'pinch_index',action:head?'none':'left_drag',dwell_action:'left_click',dragging:false,progress:.65,tracking:active&&name!=='tracking_lost',metrics:{fps:27,median_latency_ms:null},voice:{message:'Preview: Windows manages microphone setup and dictation.'},expression_practice:{neutral:false,seen:[]}});
      if(!this.cameras.length){this.cameras=[{id:'0',name:'Sample PC webcam · preview'}];$('airCamera').replaceChildren(new Option(this.cameras[0].name,'0'));}
    }
  }
  window.TouchHelmAir=new AirPanel();
})();
