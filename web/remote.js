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
      try{$('remoteText').value=(localStorage.getItem('touchhelm_remote_draft')||'').slice(0,10000);}catch{}
      $('remoteText').addEventListener('input',()=>{try{localStorage.setItem('touchhelm_remote_draft',$('remoteText').value);}catch{}});
      for(const button of document.querySelectorAll('[data-remote-mode]'))button.addEventListener('click',()=>this.start(button.dataset.remoteMode));
      $('remoteStop').addEventListener('click',()=>this.stop());
      $('remoteResume').addEventListener('click',()=>this.start(this.selectedMode));
      $('remoteRefresh').addEventListener('click',()=>this.query());
      $('remoteCastOpen').addEventListener('click',()=>{$('remoteCastGuide').hidden=!$('remoteCastGuide').hidden;});
      $('remoteFit').addEventListener('click',()=>{this.scale=1;this.panX=this.panY=0;this.transform();});
      $('remoteActual').addEventListener('click',()=>{const r=this.stage.getBoundingClientRect();this.scale=Math.max(1,1/Math.min(r.width/(this.video.videoWidth||r.width),r.height/(this.video.videoHeight||r.height)));this.panX=this.panY=0;this.transform();});
      $('remoteFullscreen').addEventListener('click',()=>{const promise=document.fullscreenElement?document.exitFullscreen():this.stage.requestFullscreen?.();promise?.catch(()=>this.status('Fullscreen is unavailable. Rotate your phone for a larger view.'));});
      for(const id of ['remoteMonitor','remoteQuality','remoteAudio','remoteMode'])$(id).addEventListener('change',()=>this.configure());
      $('remoteUnmute').addEventListener('click',()=>{this.video.muted=!$('remoteAudio').checked;this.video.play().then(()=>{$('remoteUnmute').hidden=true;}).catch(()=>this.status('Tap the playback button again to allow browser playback.'));});
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
    status(text){$('remoteStatus').textContent=text;}
    query(){this.client.send({type:'remote_query'});}
    onView(view){if(view==='viewRemote')this.query();else if(this.session)this.pause('Paused after leaving Remote.');}
    connected(value){if(value)this.query();else this.reset('disconnected','PC disconnected. Reconnect, then tap Resume.');}
    wrap(data){return this.session&&document.querySelector('#viewRemote.active')&&inputs.has(data.type)?{type:'remote_input',session_id:this.session,revision:this.revision,command:data}:data;}
    input(command){if(this.mode!=='control'||this.state!=='live')return false;if(command.type==='text'&&this.client.newlineMode==='shift_enter')command={...command,newline_mode:'shift_enter'};return this.client.send({type:'remote_input',session_id:this.session,revision:this.revision,command});}
    start(mode){
      if(new URLSearchParams(location.search).get('preview')==='1'&&window.TouchHelmDemo)return window.TouchHelmDemo.setState(mode==='control'?'remote_control':'remote_view');
      if(!this.client.isConnected)return this.status('Connect to your PC first.');
      if(!window.isSecureContext||location.protocol!=='https:')return this.status('Choose trusted HTTPS in desktop Pairing before starting Remote.');
      if(!window.RTCPeerConnection)return this.status('WebRTC is unavailable in this browser. Use current Android Chrome.');
      this.selectedMode=mode;this.mode=mode;this.state='connecting';$('remoteMode').value=mode;this.status('Starting desktop stream…');this.render();
      this.client.send({type:'remote_start',mode,quality:$('remoteQuality').value,display_id:$('remoteMonitor').value||undefined,audio:$('remoteAudio').checked});
    }
    async connect(){
      const session=this.session;
      this.pc=new RTCPeerConnection({iceServers:[]});const pc=this.pc;
      pc.addTransceiver('video',{direction:'recvonly'});pc.addTransceiver('audio',{direction:'recvonly'});
      this.stream=new MediaStream();this.video.srcObject=this.stream;
      pc.ontrack=event=>{if(this.pc!==pc)return;this.stream.addTrack(event.track);this.video.muted=true;this.video.play().catch(()=>{$('remoteUnmute').hidden=false;$('remoteUnmute').textContent=$('remoteAudio').checked?'Unmute':'Play video';});};
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
        if(!this.session)this.status(!msg.enabled?'Enable Remote screen access and a PIN in desktop Settings.':!msg.secure?'Use trusted HTTPS from desktop Pairing.':msg.message);
        $('remoteAudio').disabled=!msg.audio;this.render();return;
      }
      if(msg.success===false){if(this.state==='connecting'&&!this.session)this.state='unavailable';this.status(msg.message||'Remote request failed.');this.render();return;}
      if(msg.type==='remote_answer'){
        if(msg.session_id!==this.session||!this.pc)return;
        try{await this.pc.setRemoteDescription({type:'answer',sdp:msg.sdp});}catch(error){this.stop();this.status(`Media negotiation: ${error.message}`);}return;
      }
      if(msg.type!=='remote_state')return;
      if(!msg.session_id){
        if(msg.device){if(!this.session)this.status(`Remote is in use by ${msg.device}. Stop it on the desktop first.`);return;}
        this.reset(msg.state||'stopped',msg.message);return;
      }
      if(this.session&&this.session!==msg.session_id)return;
      this.session=msg.session_id;this.revision=msg.revision;this.mode=msg.mode;this.serverState=msg.state;
      if(!this.pc){this.previousFrames=0;this.lastFrame=performance.now();this.connect();}
      this.state=msg.state==='live'?'connecting':msg.state;
      this.geometry=msg.display?.rect;$('remoteMode').value=msg.mode;$('remoteQuality').value=msg.quality;
      if(msg.display)$('remoteMonitor').value=msg.display.id;
      $('remoteAudio').checked=!!msg.audio;$('remoteUnmute').hidden=!msg.audio;
      $('remoteUnmute').textContent=msg.audio?'Unmute':'Play video';
      if(!msg.audio)this.video.muted=true;
      this.status(msg.message);this.render();
    }
    configure(){
      if(!this.session)return;
      this.cancelGesture();this.client.controls?.releaseKeys();this.state='connecting';this.render();
      this.client.send({type:'remote_config',session_id:this.session,mode:$('remoteMode').value,display_id:$('remoteMonitor').value,quality:$('remoteQuality').value,audio:$('remoteAudio').checked});
    }
    stop(){this.cancelGesture();this.client.controls?.releaseKeys();this.client.send({type:'remote_stop',session_id:this.session||undefined});this.reset('stopped','Remote stopped.');}
    pause(message){this.cancelGesture();this.client.controls?.releaseKeys();this.client.send({type:'remote_pause',session_id:this.session||undefined});this.reset('paused',message);}
    reset(state,message){
      this.cancelGesture();this.client.controls?.releaseKeys();this.session='';this.revision='';this.serverState='stopped';
      const pc=this.pc;this.pc=null;if(pc){pc.ontrack=pc.onconnectionstatechange=null;pc.close();}
      this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.video.srcObject=null;
      this.cursor=null;$('remoteCursor').hidden=true;
      this.state=state;this.status(message||'Remote stopped.');this.render();
    }
    render(){
      const active=!!this.session||this.state==='connecting';$('remoteWelcome').hidden=active;$('remoteViewer').hidden=!active;
      $('remoteResume').hidden=!['paused','disconnected'].includes(this.state);$('remoteState').textContent=this.state[0].toUpperCase()+this.state.slice(1);
      $('remoteStage').dataset.state=this.state;
      for(const id of ['remoteLeft','remoteRight','remoteDrag','remoteTextSend','remoteEnter','remoteChordSend','remoteRelease'])$(id).disabled=this.state!=='live'||this.mode!=='control';
      for(const button of $('remoteKeys').querySelectorAll('button'))button.disabled=this.state!=='live'||this.mode!=='control';
      $('remoteTyping').hidden=this.mode!=='control';window.TouchHelmEffects?.suspend(active);
      this.renderCursor();
    }
    transform(){this.video.style.transform=`translate(${this.panX}px,${this.panY}px) scale(${this.scale})`;this.renderCursor();}
    renderCursor(){
      const marker=$('remoteCursor'),c=this.cursor;marker.hidden=!c?.visible||this.state!=='live';if(marker.hidden)return;
      const r=this.stage.getBoundingClientRect(),width=this.video.videoWidth||this.geometry?.width,height=this.video.videoHeight||this.geometry?.height;
      if(!width||!height)return;
      const fit=Math.min(r.width/width,r.height/height),w=width*fit*this.scale,h=height*fit*this.scale;
      marker.style.left=`${r.width/2+this.panX+(c.x-.5)*w}px`;marker.style.top=`${r.height/2+this.panY+(c.y-.5)*h}px`;
    }
    point(event){return mapPoint({box:this.stage.getBoundingClientRect(),width:this.video.videoWidth||this.geometry?.width,height:this.video.videoHeight||this.geometry?.height,scale:this.scale,panX:this.panX,panY:this.panY},event.clientX,event.clientY);}
    pointer(type,event){
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
          if(stat.type==='inbound-rtp'&&stat.kind==='video'){
            const count=stat.framesDecoded||0,frames=count-this.previousFrames;this.previousFrames=count;
            if(frames>0){this.lastFrame=performance.now();if(this.serverState==='live'&&this.state!=='live'){this.state='live';this.status('Desktop stream connected.');this.render();}}
            $('remoteStats').textContent=`${Math.max(0,frames)} fps · ${stat.frameWidth||this.video.videoWidth} × ${stat.frameHeight||this.video.videoHeight}`;
            this.badSamples=frames>0&&frames<8?(this.badSamples||0)+1:0;
            if(this.badSamples>=5&&$('remoteQuality').value!=='saver'){this.badSamples=0;$('remoteQuality').value=validateQuality($('remoteQuality').value);this.configure();}
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
