/* Internet loads this page/pairing only. PC traffic uses host-only DTLS. */
(() => {
  'use strict';
  if(!document.querySelector('meta[name="touchhelm-browser-link"]'))return;
  const gate={public:true,local:true,allowed:false,settled:false,assets:new Map()};
  window.TouchHelmBrowserLink=gate;
  const values=new URLSearchParams(location.hash.slice(1));let secret=values.get('browser-link');
  const pinned=values.get('fingerprint');
  if(location.hash)history.replaceState(null,'',location.pathname+location.search);
  const panel=document.createElement('section'),heading=document.createElement('h1'),detail=document.createElement('p');
  panel.className='browser-link-gate';panel.setAttribute('role','status');
  heading.textContent='Connecting on local Wi-Fi';detail.textContent='Preparing an encrypted direct connection…';panel.append(heading,detail);document.body.append(panel);
  document.documentElement.classList.add('browser-link-pending');
  function ended(){gate.allowed=false;heading.textContent='Local connection ended';detail.textContent='On your PC choose Pair your phone → Start browser link, then scan the new QR. Keep this page open during a session; control never falls back to the internet.';if(!panel.isConnected)document.body.append(panel);document.documentElement.classList.add('browser-link-pending');}
  gate.staticURL=url=>gate.assets.get(new URL(url,location.href).pathname)||url;
  gate.fetch=(url,options)=>{if(!gate.allowed||!gate.transport)return Promise.reject(Error('Pair a local connection first.'));return gate.transport.fetch(new URL(url,location.href).pathname,options);};
  gate.socket=()=>{if(!gate.allowed||!gate.transport||gate.transport.readyState!==1)throw Error('Scan a fresh PC QR.');return gate.transport;};
  async function post(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(15000)});if(!response.ok){const error=Error('Pairing rejected.');error.status=response.status;throw error;}return response.json();}
  gate.ready=(async()=>{
    let pc;
    try{
      if(!/^[A-Za-z0-9_-]{43}$/.test(secret||'')||!/^[a-f0-9]{64}$/.test(pinned||''))throw Error('Scan the current PC QR.');
      if(!window.isSecureContext||!window.RTCPeerConnection||!crypto.subtle)throw Error('Use current Android Chrome over HTTPS.');
      const protocol=window.TouchHelmLocalTransport;
      await Promise.all(['bloom','resonance','companion','clay','glass','soft','ink'].map(async id=>{const path='/themes/'+id+'.css';const response=await fetch(path,{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('Could not prepare the phone interface.');gate.assets.set(path,URL.createObjectURL(new Blob([await response.text()],{type:'text/css'})));}));
      const response=await fetch('/api/browser-link/status',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('Pairing is unavailable.');
      const {nonce}=await response.json();if(!/^[A-Za-z0-9_-]{43}$/.test(nonce||''))throw Error('Invalid pairing challenge.');
      const offer=await post('/api/browser-link/offer',{proof:await protocol.proof(secret,'offer',nonce)});
      if(offer.type!=='offer'||protocol.fingerprint(offer.sdp)!==pinned)throw Error('This connection does not match the PC QR.');
      pc=new RTCPeerConnection({iceServers:[]});gate.peer=pc;
      let rejectOpened;
      const opened=new Promise((resolve,reject)=>{
        rejectOpened=reject;const timer=setTimeout(()=>reject(Error('The local Wi-Fi route could not connect. Check Windows Firewall and Wi-Fi isolation.')),20000);
        pc.ondatachannel=event=>{const channel=event.channel;if(channel.label!=='touchhelm-control'||channel.ordered!==true||channel.maxRetransmits!==null||channel.maxPacketLifeTime!==null){channel.close();return;}
          channel.onopen=()=>{clearTimeout(timer);gate.transport=new protocol.Socket(channel,ended);resolve();};};
        pc.onconnectionstatechange=()=>{if(['failed','closed'].includes(pc.connectionState)){clearTimeout(timer);reject(Error('Local connection closed.'));if(gate.allowed)ended();}};
      });
      await pc.setRemoteDescription(offer);await pc.setLocalDescription(await pc.createAnswer());
      if(pc.iceGatheringState!=='complete')await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Local network discovery timed out.')),10000);pc.addEventListener('icegatheringstatechange',()=>{if(pc.iceGatheringState==='complete'){clearTimeout(timer);resolve();}});});
      const sdp=pc.localDescription.sdp,proof=await protocol.proof(secret,'answer',nonce,sdp);secret='';
      post('/api/browser-link/answer',{sdp,proof}).catch(error=>{if(error.status>=400&&error.status<500)rejectOpened(error);});
      await opened;
      gate.allowed=true;panel.remove();document.documentElement.classList.remove('browser-link-pending');
      return true;
    }catch(error){secret='';pc?.close();heading.textContent='Scan a fresh QR code';detail.textContent=(error.message||'Pairing failed.')+' On the PC choose Start browser link or New QR code. Both devices must be on the same local network. There is no internet control fallback.';return false;}
    finally{gate.settled=true;}
  })();
})();
