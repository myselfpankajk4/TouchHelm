/* Only explicit preview=1 uses fixtures; this transport never reaches Windows. */
(() => {
  if(new URLSearchParams(location.search).get('preview')!=='1')return;
  const sockets=new Set();
  const config={theme:'glass',mouse_sensitivity:1.3,mouse_acceleration:1.25,scroll_speed:1,invert_scroll:false};
  let stateName='ready';
  const media={available:true,session_id:'demo:player',app:'Demo player',title:'Morning light',artist:'Preview artist',album:'Illustrative album',status:'Playing',position:65,duration:240,min_seek:0,max_seek:240,playback_rate:1,shuffle:false,repeat:'none',artwork_id:'demo:record',capabilities:{play:true,pause:true,next:true,prev:true,stop:true,seek:true,shuffle:true,repeat:true,rate:true}};
  const presentation={available:true,active:true,app:'PowerPoint · preview',title:'Quarterly review',slide:3,total:12,slide_title:'Results',capabilities:{details:true,goto:true},message:''};
  const apps=[{id:'demo:touchhelm',name:'TouchHelm',icon_id:'demo:brand',running:true,launches:8,pinned:true,windows:[{id:'demo:window',title:'TouchHelm preview'}]},{id:'demo:editor',name:'Demo editor',running:true,launches:4,windows:[{id:'demo:editor-window',title:'Example document'}]},{id:'demo:music',name:'Demo music',running:false,launches:3,windows:[]}];
  const state=()=>({presentation:stateName==='unavailable'?{available:false,title:'No supported presentation',message:'Preview of unavailable provider state.'}:presentation,media:stateName==='unavailable'?{available:false,status:'unavailable',message:'No media session exposed.'}:{...media,status:stateName==='paused'?'Paused':stateName==='playing'?'Playing':media.status,artwork_id:stateName==='missing-artwork'?null:media.artwork_id}});
  class Socket {
    static OPEN=1; static CLOSED=3;
    constructor(){this.readyState=1;sockets.add(this);setTimeout(()=>{this.onopen?.();this.receive({type:'auth_res',success:true,config,volume:37,muted:false,brightness:62});this.receive({type:'desktop_state',...state()});},20);}
    receive(value){if(stateName==='loading'&&value.type==='apps_sync')return;if(value.type==='desktop_state'&&stateName==='loading')value={type:'desktop_state',presentation:{available:false,title:'Loading presentation…',message:'Waiting for presentation context…'},media:{available:false,status:'loading',title:'Loading Now Playing…',message:'Waiting for player metadata…'}};this.onmessage?.({data:JSON.stringify(value)});}
    send(raw){const p=JSON.parse(raw);let reply;
      if(p.type==='get_desktop_state')reply={type:'desktop_state',...state()};
      if(p.type==='get_apps')reply={type:'apps_sync',apps};
      if(p.type==='get_media_library')reply={type:'media_library',sessions:[{...media,id:media.session_id}],items:[],playlist_supported:false};
      if(p.type==='get_displays')reply={type:'displays',displays:[{id:'demo:display',name:'Presentation display',primary:true}]};
      if(p.type==='remote_query')reply={type:'remote_capabilities',success:true,video:true,audio:true,enabled:true,secure:true,message:'Simulated Remote preview. No PC capture.',displays:[{id:'demo:display',name:'Sample monitor',primary:true,rect:{x:0,y:0,width:960,height:540}}]};
      if(p.type==='get_presentation_details')reply={type:'presentation_details',available:true,current:{index:3,title:'Results',artwork_id:'demo:slide'},next:{index:4,title:'Next steps',artwork_id:'demo:slide'},notes:'Illustrative speaker notes.\nThis preview does not read a real deck.',slides:Array.from({length:12},(_,i)=>({index:i+1,title:`Demo slide ${i+1}`})),capabilities:{goto:true}};
      if(p.type==='ping')reply={type:'pong',t:p.t};
      if(p.type==='media'){if(p.action==='pause')media.status='Paused';if(p.action==='play')media.status='Playing';if(p.action==='play_pause')media.status=media.status==='Playing'?'Paused':'Playing';if(p.action==='seek')media.position=p.value;reply={type:'command_result',command:'media',success:true};}
      if(['launch_app','app_action','presentation'].includes(p.type))reply={type:'command_result',command:p.type,success:true,message:'Preview action only.'};
      if(p.type==='app_action'&&p.action==='close'){
        const app=apps.find(value=>value.id===p.app_id);
        if(app){app.windows=app.windows.filter(value=>value.id!==p.window_id);app.running=app.windows.length>0;}
        reply={type:'command_result',command:'app_action',action:'close',app_id:p.app_id,window_id:p.window_id,success:!!app,requested:!!app,confirmed:false,message:'Preview close requested.'};
      }
      if(reply)setTimeout(()=>this.receive(reply),20);
    }
    close(){this.readyState=3;sockets.delete(this);this.onclose?.();}
  }
  const originalFetch=window.fetch.bind(window);
  window.fetch=async (url,options)=>{
    const pathname=new URL(String(url),location.href).pathname;
    if(pathname==='/api/config'||pathname==='/api/info')return new Response(JSON.stringify({...config,volume:37,muted:false,brightness:62}),{headers:{'Content-Type':'application/json'}});
    if(pathname==='/api/version')return new Response(JSON.stringify({build:document.querySelector('meta[name="touchhelm-build"]')?.content}),{headers:{'Content-Type':'application/json'}});
    if(pathname.startsWith('/api/assets/demo')){
      if(decodeURIComponent(pathname).endsWith('demo:brand'))return originalFetch('/icons/icon.svg');
      const slide=decodeURIComponent(pathname).endsWith('demo:slide');
      const svg=slide?'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#17394a"/><text x="42" y="72" fill="#ffffff" font-size="32" font-family="sans-serif">Results · preview</text><rect x="42" y="240" width="100" height="64" fill="#83ccd8"/><rect x="162" y="180" width="100" height="124" fill="#83ccd8"/><rect x="282" y="130" width="100" height="174" fill="#83ccd8"/></svg>':'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" rx="28" fill="#16353b"/><circle cx="256" cy="240" r="170" fill="#10191c"/><circle cx="256" cy="240" r="124" fill="none" stroke="#36504e" stroke-width="3"/><circle cx="256" cy="240" r="70" fill="#b7ddba"/><circle cx="256" cy="240" r="12" fill="#183a39"/><text x="256" y="460" text-anchor="middle" fill="#dfeddd" font-size="24" font-family="sans-serif">Illustrative artwork</text></svg>';
      return new Response(svg,{headers:{'Content-Type':'image/svg+xml'}});
    }
    return originalFetch(url,options);
  };
  window.WebSocket=Socket;
  window.TouchHelmDemo={setState(name){
    if(name.startsWith('remote_')&&window.touchhelm?.remote){
      const client=window.touchhelm,r=client.remote;
      client.switchView('viewRemote');r.reset('stopped','Simulated Remote preview.');
      const live=['remote_control','remote_view'].includes(name);
      r.session=live||name==='remote_connecting'?'preview-session':'';r.revision='preview-geometry';
      r.mode=name==='remote_view'?'view':'control';r.selectedMode=r.mode;
      r.state=live?'live':name==='remote_connecting'?'connecting':name==='remote_paused'?'paused':'unavailable';
      r.video.poster='/icons/remote-preview.svg';r.geometry={width:960,height:540};r.render();
      document.getElementById('remoteStats').textContent='Simulated 720p preview';document.getElementById('remoteLatency').textContent='No live connection';
      r.status('Interface preview only. No desktop capture or PC input.');return;
    }
    stateName=name;const client=window.touchhelm;client?.controls?.releaseKeys();
    if(name!=='typing')client?.controls?.collapseTyping();
    if(!['menu','closing'].includes(name))client?.closeModal(document.getElementById('appActionsModal'));
    client?.experience?.clearPending();
    if(name!=='notes')document.getElementById('presentationDetails').open=false;
    if(name==='offline'||name==='disconnected'){for(const socket of [...sockets])socket.close();client?.stopPing();clearTimeout(client?.reconnectTimer);return;}
    if(client&&!client.isConnected)client.connect();
    for(const socket of sockets)socket.receive({type:'desktop_state',...state()});
    if(client?.typeInput&&name==='typing'){client.typeInput.value='A multiline draft\nReturn creates a new line.';client.typeInput.focus();}
    if(name==='loading'){if(client?.controls)client.controls.renderApps([]);document.getElementById('appsStatus').textContent='Loading installed apps…';}
    if(name==='held'){client?.controls?.down('lctrl');client?.controls?.latched.add('lctrl');client?.controls?.down('lshift');client?.controls?.latched.add('lshift');client?.controls?.updateHeld();}
    if(name==='menu'&&client?.experience)client.experience.openAppMenu(apps[0],document.getElementById('btnRefreshApps'));
    if(name==='closing'&&client?.experience){client.experience.openAppMenu(apps[0],document.getElementById('btnRefreshApps'));document.getElementById('appActionDetails').textContent='Close requested. A save prompt may be waiting on your PC.';}
    if(name==='seeking'&&client?.experience){client.experience.pending=true;client.experience.pendingSeek={value:180,requestedAt:performance.now(),session:media.session_id};document.getElementById('seekPreview').textContent='Seeking to 3:00';document.getElementById('mediaCommandStatus').textContent='Seeking to 3:00…';}
    if(name==='touch')setTimeout(()=>window.TouchHelmEffects?.react(document.querySelector('#viewTrackpad .touch-surface'),{kind:'press'}),80);
    if(name==='notes')document.getElementById('presentationDetails').open=true;
  },state};
  document.addEventListener('DOMContentLoaded',()=>{const status=document.createElement('p');status.className='preview-notice';status.textContent='Interactive preview · simulated data · no PC input';document.body.prepend(status);});
})();
