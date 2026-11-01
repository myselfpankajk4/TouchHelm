/* Live desktop viewer. Decoration and input stay independent of video transport. */
(() => {
  'use strict';
  function mapPoint(g,x,y){
    if(![x,y,g.width,g.height].every(Number.isFinite)||!g.width||!g.height)return null;
    const fit=Math.min(g.box.width/g.width,g.box.height/g.height),w=g.width*fit*g.scale,h=g.height*fit*g.scale;
    const nx=(x-g.box.left-g.box.width/2-g.panX+w/2)/w,ny=(y-g.box.top-g.box.height/2-g.panY+h/2)/h;
    return nx>=0&&nx<=1&&ny>=0&&ny<=1?{x:nx,y:ny}:null;
  }
  const gestureChoice=(locked,ratio,travel)=>locked||(Math.abs(ratio-1)>.08?'zoom':Math.abs(travel)>10?'scroll':null);
  const validateQuality=q=>({clear:'balanced',balanced:'saver',saver:'saver'}[q]||'balanced');
  if(typeof module!=='undefined')module.exports={mapPoint,gestureChoice,validateQuality};
  if(typeof document==='undefined')return;
  const $=id=>document.getElementById(id);
  const inputs=new Set(['move','click','dblclick','mousedown','mouseup','scroll','key','keydown','keyup','text','hotkey','zoom']);
  class TouchHelmRemote {
    constructor(client){
      this.client=client;this.session='';this.revision='';this.state='stopped';this.mode='control';this.scale=1;this.panX=this.panY=0;
      this.points=new Map();this.video=$('remoteVideo');this.stage=$('remoteStage');this.selectedMode='control';this.previousFrames=0;
      this.audioRequested=false;this.audioConfirmed=false;this.audioPending=false;this.previousAudio=0;
      try{$('remoteText').value=(localStorage.getItem('touchhelm_remote_draft')||'').slice(0,10000);}catch{}
      try{const saved=localStorage.getItem('touchhelm_remote_quality');$('remoteQuality').value=['saver','balanced','clear','detail'].includes(saved)?saved:'clear';}catch{}
      $('remoteQuality').addEventListener('change',()=>{try{localStorage.setItem('touchhelm_remote_quality',$('remoteQuality').value);}catch{}});
      $('remoteText').addEventListener('input',()=>{try{localStorage.setItem('touchhelm_remote_draft',$('remoteText').value);}catch{}});
      for(const button of document.querySelectorAll('[data-remote-mode]'))button.addEventListener('click',()=>this.start(button.dataset.remoteMode));
      $('remoteStop').addEventListener('click',()=>this.stop());
      $('remoteResume').addEventListener('click',()=>this.start(this.selectedMode));
      $('remoteRefresh').addEventListener('click',()=>this.query());
      $('remoteCastOpen').addEventListener('click',()=>{$('remoteCastGuide').hidden=!$('remoteCastGuide').hidden;});
      $('remoteFit').addEventListener('click',()=>{this.scale=1;this.panX=this.panY=0;this.transform();});
      $('remoteActual').addEventListener('click',()=>{const r=this.stage.getBoundingClientRect();this.scale=Math.max(1,1/Math.min(r.width/(this.video.videoWidth||r.width),r.height/(this.video.videoHeight||r.height)));this.panX=this.panY=0;this.transform();});
      $('remoteFullscreen').addEventListener('click',()=>this.fullscreen());
      $('remoteFullscreenExit').addEventListener('click',()=>this.fullscreen());
      $('remoteFullscreenStop').addEventListener('click',()=>{if(document.fullscreenElement===this.stage)document.exitFullscreen().catch(()=>{});this.stop();});
      document.addEventListener('fullscreenchange',()=>{if(document.fullscreenElement!==this.stage&&this.orientationLocked){screen.orientation?.unlock?.();this.orientationLocked=false;}this.renderCursor();});
      window.addEventListener('resize',()=>this.renderCursor());
      for(const id of ['remoteMonitor','remoteQuality','remoteMode'])$(id).addEventListener('change',()=>this.configure());
      for(const id of ['remoteAudio','mediaPcAudio'])$(id).addEventListener('change',event=>this.setAudio(event.target.checked));
      for(const id of ['remoteUnmute','mediaPcAudioUnmute','remoteAudioOnlyUnmute'])$(id).addEventListener('click',()=>this.unmute());
      $('remoteAudioOnlyStop').addEventListener('click',()=>this.stop());
      $('remoteLeft').addEventListener('click',()=>this.input({type:'click',button:'left'}));
      $('remoteRight').addEventListener('click',()=>this.input({type:'click',button:'right'}));
      $('remoteDrag').addEventListener('click',()=>{this.drag=!this.drag;this.input({type:this.drag?'mousedown':'mouseup',button:'left'});$('remoteDrag').setAttribute('aria-pressed',String(this.drag));});
      $('remoteTextSend').addEventListener('click',()=>{if(this.input({type:'text',text:$('remoteText').value}))this.status('Text sent to the active PC application.');});
      $('remoteText').addEventListener('keydown',event=>{if(event.ctrlKey&&event.key==='Enter'&&!event.isComposing){event.preventDefault();$('remoteTextSend').click();}});
      $('remoteEnter').addEventListener('click',()=>this.input({type:'key',key:'enter'}));
      $('remoteRelease').addEventListener('click',()=>{this.client.controls?.releaseKeys();this.cancelGesture();});
      $('remoteChordSend').addEventListener('click',()=>{
        const aliases={ctrl:'lctrl',control:'lctrl',shift:'lshift',alt:'lalt'};
        const keys=$('remoteChord').value.toLowerCase().split('+').map(k=>aliases[k.trim()]||k.trim()).filter(Boolean);
        if(!keys.length||keys.length>16)return this.status('Enter a combination such as Ctrl+Shift+A.');
        this.input({type:'hotkey',keys});
      });
      // Reuse native press/release, repeat and modifier semantics, including the numpad.
      $('remoteTyping').addEventListener('toggle',()=>{
        if(!$('remoteTyping').open||this.keysBuilt)return;
        this.keysBuilt=true;
        const keys=[...this.client.controls?.keyButtons||[]];
        for(const original of keys)$('remoteKeys').append(this.client.controls.makeKey(original.dataset.key,original.textContent));
        this.render();
      });
      for(const type of ['pointerdown','pointermove','pointerup','pointercancel','lostpointercapture'])this.stage.addEventListener(type,event=>this.pointer(type,event));
      this.stage.addEventListener('wheel',event=>{if(this.state!=='live')return;event.preventDefault();if(event.ctrlKey){this.scale=Math.max(1,Math.min(6,this.scale*Math.exp(-event.deltaY/300)));this.transform();}else if(this.mode==='control')this.input({type:'scroll',dx:-event.deltaX/60,dy:-event.deltaY/60});},{passive:false});
      document.addEventListener('visibilitychange',()=>{if(document.hidden&&this.session)this.pause('Paused while the phone is in the background.');});
      window.addEventListener('blur',()=>this.cancelGesture());
      this.video.addEventListener('loadedmetadata',()=>this.transform());
      this.timer=setInterval(()=>this.tick(),1000);
      this.render();
    }
    status(text){this.lastMessage=text||'';$('remoteStatus').textContent=this.lastMessage;if(this.mode==='audio')$('mediaPcAudioStatus').textContent=this.lastMessage;}
    query(){this.client.send({type:'remote_query'});}
    onView(view){
      this.cancelGesture();this.client.controls?.releaseKeys();
      if(view==='viewRemote'){this.query();if(this.session&&this.mode!=='audio'){this.state='connecting';this.lastFrame=performance.now();this.render();}}
      // Navigation keeps media alive; phone backgrounding still pauses it.
      window.TouchHelmEffects?.suspend(view==='viewRemote'&&!!this.session);
    }
    connected(value){if(value){this.query();this.syncAudioControls();}else{this.restartMode=null;this.reset('disconnected','PC disconnected. Reconnect, then tap Resume.');}}
    async fullscreen(){
      try{
        if(document.fullscreenElement===this.stage){await document.exitFullscreen();return;}
        if(!this.stage.requestFullscreen)throw new Error('Fullscreen is unavailable in this browser.');
        await this.stage.requestFullscreen();
        try{if(!screen.orientation?.lock)throw new Error();await screen.orientation.lock('landscape');this.orientationLocked=true;$('remoteFullscreenHint').textContent='';}
        catch{this.status('Landscape lock is unavailable. Rotate your phone manually.');$('remoteFullscreenHint').textContent='Rotate your phone for landscape';}
        this.renderCursor();
      }catch(error){this.status(error.message||'Fullscreen could not start.');}
    }
    setAudio(enabled){
      if(this.audioPending)return this.syncAudioControls();
      if(enabled&&this.caps?.enabled===false){this.audioRequested=false;this.status('Screen and audio access is off on this PC. In desktop Pair your phone, open Screen and audio access → Enable.');this.syncAudioControls();return;}
      this.audioRequested=!!enabled;
      if(!enabled&&this.mode==='audio'&&this.session){this.stop();return;}
      if(!this.session){if(enabled){this.start('audio');this.audioPending=this.state==='connecting';}this.syncAudioControls();return;}
      this.audioPending=true;this.configure();
    }
    unmute(){
      if(!this.audioConfirmed)return;
      this.playMedia();
    }
    playMedia(){
      const session=this.session,attempt=this.playAttempt=(this.playAttempt||0)+1;
      this.video.muted=!this.audioConfirmed;
      this.video.play().then(()=>{if(this.session===session&&this.playAttempt===attempt)this.syncAudioControls();}).catch(error=>{
        if(this.session!==session||this.playAttempt!==attempt||error.name==='AbortError')return;
        if(this.audioConfirmed){this.video.muted=true;this.status('The browser blocked audio playback. Tap Unmute to hear PC audio.');this.syncAudioControls();}
      });
    }
    syncAudioControls(){
      const pending=this.audioPending||!!this.session&&this.state==='connecting';
      for(const id of ['remoteAudio','mediaPcAudio']){const el=$(id);el.checked=this.audioPending?this.audioRequested:this.audioConfirmed;el.disabled=pending||!this.client.isConnected||this.caps?.audio===false;}
      for(const id of ['remoteUnmute','mediaPcAudioUnmute','remoteAudioOnlyUnmute'])$(id).hidden=!this.audioConfirmed||!this.video.muted;
      $('mediaPcAudioStatus').textContent=pending?'Connecting PC audio…':this.audioConfirmed?this.video.muted?'PC audio ready · tap Unmute to hear it.':this.state==='live'?'Listening to PC audio on this phone.':'Audio stream waiting for playback…':this.state==='unavailable'?this.lastMessage||'PC audio unavailable.':this.caps?.audio===false?'PC audio provider unavailable on the host.':!this.client.isConnected?'Connect to your PC to listen.':'Audio off · listening alone does not capture or control the screen.';
      if(this.client.isConnected&&this.caps?.enabled===false)$('mediaPcAudioStatus').textContent='Screen and audio access is off on this PC. In desktop Pair your phone, open Screen and audio access → Enable.';
    }
    wrap(data){return this.session&&document.querySelector('#viewRemote.active')&&inputs.has(data.type)?{type:'remote_input',session_id:this.session,revision:this.revision,command:data}:data;}
    input(command){if(this.mode!=='control'||this.state!=='live')return false;if(command.type==='text'&&command.text?.includes('\n')&&this.client.newlineMode==='shift_enter')command={...command,newline_mode:'shift_enter'};return this.client.send({type:'remote_input',session_id:this.session,revision:this.revision,command});}
    start(mode){
      if(new URLSearchParams(location.search).get('preview')==='1'&&window.TouchHelmDemo)return window.TouchHelmDemo.setState(mode==='audio'?'remote_audio':mode==='control'?'remote_control':'remote_view');
      if(!this.client.isConnected)return this.status('Connect to your PC first.');
      if(!this.caps?.local&&!this.caps?.secure)return this.status('Connect directly to your PC on the same local Wi-Fi before starting Remote.');
      if(!window.RTCPeerConnection)return this.status('WebRTC is unavailable in this browser. Use current Android Chrome.');
      if(this.caps?.enabled===false)return this.status('Screen and audio access is off on this PC. Open TouchHelm on the PC → Pair your phone → Screen and audio access → Enable, then refresh access here.');
      if(this.session){
        if((this.mode==='audio')!==(mode==='audio')){this.restartMode=mode;this.restartAudio=this.audioConfirmed;this.client.send({type:'remote_stop',session_id:this.session});this.reset('stopped','Switching stream mode…');return;}
        return this.configure();
      }
      if(mode==='audio')this.audioRequested=true;
      this.selectedMode=mode;this.mode=mode;this.state='connecting';$('remoteMode').value=mode;this.status('Starting desktop stream…');this.render();
      this.client.send({type:'remote_start',mode,quality:$('remoteQuality').value,display_id:mode==='audio'?undefined:$('remoteMonitor').value||undefined,audio:this.audioRequested});
    }
    async connect(){
      const session=this.session;
      this.pc=new RTCPeerConnection({iceServers:[]});const pc=this.pc;
      if(this.mode!=='audio')pc.addTransceiver('video',{direction:'recvonly'});pc.addTransceiver('audio',{direction:'recvonly'});
      this.stream=new MediaStream();this.video.srcObject=this.stream;
      pc.ontrack=event=>{if(this.pc!==pc)return;this.stream.addTrack(event.track);this.playMedia();this.syncAudioControls();};
      pc.onconnectionstatechange=()=>{if(this.pc!==pc)return;if(['disconnected','failed'].includes(pc.connectionState)){this.state='reconnecting';this.status('Media connection interrupted. Waiting for a fresh frame…');this.render();}};
      try{
        await pc.setLocalDescription(await pc.createOffer());
        if(pc.iceGatheringState!=='complete')await new Promise((resolve,reject)=>{
          const timeout=setTimeout(()=>{pc.removeEventListener('icegatheringstatechange',ready);reject(new Error('WebRTC network setup timed out.'));},10000);
          const ready=()=>{if(pc.iceGatheringState==='complete'){clearTimeout(timeout);pc.removeEventListener('icegatheringstatechange',ready);resolve();}};
          pc.addEventListener('icegatheringstatechange',ready);
        });
        if(this.session===session&&this.pc===pc)this.client.send({type:'remote_offer',session_id:session,sdp:pc.localDescription.sdp});
      }catch(error){if(this.session===session){this.stop();this.status(error.message);}}
    }
    async handle(msg){
      if(msg.type==='remote_cursor'){
        if(msg.session_id!==this.session||msg.revision!==this.revision)return;
        this.cursor=msg;this.renderCursor();return;
      }
      if(msg.type==='remote_capabilities'){
        this.caps=msg;
        $('remoteCastStatus').textContent=msg.casting?.message||'Receiver compatibility: Unknown. Check desktop Settings.';
        const select=$('remoteMonitor'),old=select.value;select.replaceChildren();
        for(const display of [...msg.displays||[]].sort((a,b)=>Number(!!b.primary)-Number(!!a.primary))){const option=document.createElement('option');option.value=display.id;option.textContent=display.name||display.id;select.append(option);}
        if([...select.options].some(o=>o.value===old))select.value=old;
        if(!this.session)this.status(!msg.enabled?'Screen and audio access is off on this PC. In desktop Pair your phone, open Screen and audio access → Enable.':!msg.local&&!msg.secure?'Connect directly to the PC on the same local Wi-Fi.':msg.message||'Screen and audio access is ready on local Wi-Fi.');
        $('remoteAudio').disabled=!msg.audio;this.render();return;
      }
      if(msg.success===false){this.restartMode=null;this.audioPending=false;this.audioRequested=this.audioConfirmed;if(this.state==='connecting')this.state=this.session?this.serverState||'reconnecting':'unavailable';this.status(msg.message||'Remote request failed.');this.render();return;}
      if(msg.type==='remote_answer'){
        if(msg.session_id!==this.session||!this.pc)return;
        try{await this.pc.setRemoteDescription({type:'answer',sdp:msg.sdp});}catch(error){this.stop();this.status(`Media negotiation: ${error.message}`);}return;
      }
      if(msg.type!=='remote_state')return;
      if(!msg.session_id){
        if(msg.device){if(!this.session)this.status(`Remote is in use by ${msg.device}. Stop it on the desktop first.`);return;}
        this.reset(msg.state||'stopped',msg.message);
        if(msg.success&&msg.request==='remote_stop'&&this.restartMode){const mode=this.restartMode;this.restartMode=null;this.audioRequested=this.restartAudio;this.start(mode);}
        return;
      }
      if(this.session&&this.session!==msg.session_id)return;
      this.session=msg.session_id;this.revision=msg.revision;this.mode=msg.mode;this.serverState=msg.state;
      if(!this.pc){this.previousFrames=0;this.lastFrame=performance.now();this.connect();}
      this.state=msg.state==='live'?'connecting':msg.state;
      this.geometry=msg.display?.rect;$('remoteMode').value=msg.mode;$('remoteQuality').value=msg.quality;
      if(msg.display)$('remoteMonitor').value=msg.display.id;
      const hadAudio=this.audioConfirmed;this.audioConfirmed=!!msg.audio;
      if(msg.success){this.audioPending=false;this.audioRequested=this.audioConfirmed;}
      if(!msg.audio)this.video.muted=true;
      else if(!hadAudio||!this.video.muted)this.playMedia();
      this.status(msg.message);this.render();
    }
    configure(){
      if(!this.session)return;
      this.cancelGesture();this.client.controls?.releaseKeys();this.state='connecting';this.render();
      this.client.send({type:'remote_config',session_id:this.session,mode:this.mode==='audio'?'audio':$('remoteMode').value,display_id:this.mode==='audio'?undefined:$('remoteMonitor').value,quality:$('remoteQuality').value,audio:this.audioRequested});
    }
    stop(){this.restartMode=null;this.cancelGesture();this.client.controls?.releaseKeys();this.client.send({type:'remote_stop',session_id:this.session||undefined});this.reset('stopped','Remote stopped.');}
    pause(message){this.restartMode=null;this.cancelGesture();this.client.controls?.releaseKeys();this.client.send({type:'remote_pause',session_id:this.session||undefined});this.reset('paused',message);}
    reset(state,message){
      if(document.fullscreenElement===this.stage)document.exitFullscreen?.().catch(()=>{});
      this.cancelGesture();this.client.controls?.releaseKeys();this.session='';this.revision='';this.serverState='stopped';
      const pc=this.pc;this.pc=null;if(pc){pc.ontrack=pc.onconnectionstatechange=null;pc.close();}
      this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.video.srcObject=null;this.video.muted=true;this.previousAudio=0;
      this.cursor=null;$('remoteCursor').setAttribute('hidden','');
      this.audioConfirmed=false;this.audioRequested=false;this.audioPending=false;
      this.state=state;this.status(message||'Remote stopped.');this.render();
    }
    render(){
      const active=!!this.session||this.state==='connecting',audioOnly=active&&this.mode==='audio';$('remoteWelcome').hidden=active&&!audioOnly;$('remoteViewer').hidden=!active||audioOnly;$('remoteAudioOnly').hidden=!audioOnly;
      $('remoteResume').hidden=!['paused','disconnected'].includes(this.state);$('remoteState').textContent=this.state[0].toUpperCase()+this.state.slice(1);
      $('remoteStage').dataset.state=this.state;
      for(const id of ['remoteLeft','remoteRight','remoteDrag','remoteTextSend','remoteEnter','remoteChordSend','remoteRelease'])$(id).disabled=this.state!=='live'||this.mode!=='control';
      for(const button of $('remoteKeys').querySelectorAll('button'))button.disabled=this.state!=='live'||this.mode!=='control';
      $('remoteTyping').hidden=this.mode!=='control';window.TouchHelmEffects?.suspend(active&&!audioOnly&&!!document.querySelector('#viewRemote.active'));
      this.syncAudioControls();
      this.renderCursor();
    }
    transform(){this.video.style.transform=`translate(${this.panX}px,${this.panY}px) scale(${this.scale})`;this.renderCursor();}
    renderCursor(){
      const marker=$('remoteCursor'),c=this.cursor,visible=!!c?.visible&&this.state==='live';marker.toggleAttribute('hidden',!visible);if(!visible)return;
      const r=this.stage.getBoundingClientRect(),width=this.video.videoWidth||this.geometry?.width,height=this.video.videoHeight||this.geometry?.height;
      if(!width||!height)return;
      const fit=Math.min(r.width/width,r.height/height),w=width*fit*this.scale,h=height*fit*this.scale;
      marker.style.left=`${r.width/2+this.panX+(c.x-.5)*w}px`;marker.style.top=`${r.height/2+this.panY+(c.y-.5)*h}px`;
    }
    point(event){return mapPoint({box:this.stage.getBoundingClientRect(),width:this.video.videoWidth||this.geometry?.width,height:this.video.videoHeight||this.geometry?.height,scale:this.scale,panX:this.panX,panY:this.panY},event.clientX,event.clientY);}
    pointer(type,event){
      if(event.target.closest('button,input,select'))return;
      if(type==='pointercancel'||type==='lostpointercapture'){if(this.points.has(event.pointerId))this.cancelGesture();return;}
      if(this.state!=='live')return;
      if(type==='pointerdown'){
        if(event.button!=null&&event.button!==0)return;event.preventDefault();this.stage.setPointerCapture(event.pointerId);
        this.points.set(event.pointerId,{x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY});
        if(this.points.size===1){this.gesture=null;this.travel=0;this.started=performance.now();}
        if(this.points.size===2){const[a,b]=[...this.points.values()];this.gesture=null;this.multi=true;this.distance=Math.hypot(a.x-b.x,a.y-b.y)||1;this.center=(a.y+b.y)/2;this.centerX=(a.x+b.x)/2;this.baseScale=this.scale;}
        return;
      }
      const previous=this.points.get(event.pointerId);if(!previous)return;
      if(type==='pointermove'){
        const dx=event.clientX-previous.x,dy=event.clientY-previous.y;previous.x=event.clientX;previous.y=event.clientY;this.travel+=Math.hypot(dx,dy);
        if(this.points.size>=2){
          const[a,b]=[...this.points.values()],distance=Math.hypot(a.x-b.x,a.y-b.y),center=(a.y+b.y)/2,centerX=(a.x+b.x)/2,ratio=distance/this.distance;
          this.gesture=gestureChoice(this.gesture,ratio,Math.hypot(center-this.center,centerX-this.centerX));
          if(this.gesture==='zoom'){this.scale=Math.max(1,Math.min(6,this.baseScale*ratio));this.transform();}
          else if(this.gesture==='scroll'){if(this.mode==='control')this.input({type:'scroll',dy:(center-this.center)/20,dx:(centerX-this.centerX)/20});this.center=center;this.centerX=centerX;}
        }else if(!this.multi){
          if(this.mode==='view'||$('remoteInteraction').value==='pan'){this.panX+=dx;this.panY+=dy;this.transform();}
          else if($('remoteInteraction').value==='direct'){const point=this.point(event);if(point)this.input({type:'absolute',...point});}
          else this.input({type:'move',dx,dy});
        }
        return;
      }
      if(type==='pointerup'){
        if(!this.multi&&this.travel<8&&performance.now()-this.started<400&&this.mode==='control'&&$('remoteInteraction').value!=='pan'){
          if($('remoteInteraction').value==='direct'){const point=this.point(event);if(point){this.input({type:'absolute',...point});this.input({type:'click',button:'left'});}}
          else this.input({type:'click',button:'left'});
        }
        this.points.delete(event.pointerId);if(!this.points.size){this.multi=false;this.gesture=null;}
      }
    }
    cancelGesture(){
      this.points.clear();this.gesture=null;this.multi=false;
      if(this.drag)this.input({type:'mouseup',button:'left'});this.drag=false;$('remoteDrag').setAttribute('aria-pressed','false');
    }
    async tick(){
      const pc=this.pc;if(!pc||pc.connectionState==='closed'||document.hidden)return;
      try{
        const stats=await pc.getStats();if(pc!==this.pc)return;
        for(const stat of stats.values()){
          if(stat.type==='inbound-rtp'&&stat.kind==='audio'&&this.mode==='audio'){
            const count=stat.packetsReceived||0;
            if(count>this.previousAudio){this.lastFrame=performance.now();if(this.serverState==='live'&&this.state!=='live'){this.state='live';this.status('PC audio connected · screen capture off.');this.render();}}
            this.previousAudio=count;
          }
          if(stat.type==='inbound-rtp'&&stat.kind==='video'){
            const count=stat.framesDecoded||0,frames=count-this.previousFrames;this.previousFrames=count;
            const packets=stat.packetsReceived||0,received=packets>(this.previousVideoPackets||0);this.previousVideoPackets=packets;
            // Hidden video may stop decoding on mobile. Network receipt keeps
            // the off-tab stream alive; the visible viewer requires fresh frames.
            const offTab=!document.querySelector('#viewRemote.active');
            if(frames>0||offTab&&received){this.lastFrame=performance.now();if(this.serverState==='live'&&this.state!=='live'){this.state='live';this.status('Desktop stream connected.');this.render();}}
            $('remoteStats').textContent=`${Math.max(0,frames)} fps · ${stat.frameWidth||this.video.videoWidth} × ${stat.frameHeight||this.video.videoHeight}`;
            // Low capture FPS is not evidence of network congestion. Keep the
            // selected resolution; WebRTC adjusts bitrate using receiver feedback.
          }
          if(stat.type==='candidate-pair'&&stat.state==='succeeded'&&Number.isFinite(stat.currentRoundTripTime))$('remoteLatency').textContent=`${Math.round(stat.currentRoundTripTime*1000)} ms network RTT`;
        }
        const age=performance.now()-(this.lastFrame||0);
        if(age>5000&&this.state==='live'){this.state='reconnecting';this.status('No fresh video frames. Checking media connection…');this.render();}
        if(age>15000)this.pause('Media stopped updating. Check the connection and tap Resume.');
      }catch{}
    }
  }
  window.TouchHelmRemote=TouchHelmRemote;
})();
