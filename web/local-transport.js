/* Ordered, bounded WebRTC transport for the existing validated command protocol. */
(() => {
  'use strict';
  const encoder=new TextEncoder(),decoder=new TextDecoder('utf-8',{fatal:true});
  async function proof(secret,stage,nonce,sdp=''){
    const key=await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
    return Array.from(new Uint8Array(await crypto.subtle.sign('HMAC',key,encoder.encode(stage+'\n'+nonce+'\n'+sdp))),v=>v.toString(16).padStart(2,'0')).join('');
  }
  function fingerprint(sdp){
    const values=new Set(Array.from(sdp.matchAll(/^a=fingerprint:sha-256 ([A-Fa-f0-9:]+)\r?$/gm),match=>match[1].replaceAll(':','').toLowerCase()));
    if(values.size!==1||!/^[a-f0-9]{64}$/.test([...values][0]))throw Error('The PC certificate could not be verified.');
    return [...values][0];
  }
  function frames(raw){
    const bytes=encoder.encode(raw);if(bytes.length>256*1024)throw Error('Local request is too large.');
    if(bytes.length<50000)return [raw];
    const id=crypto.getRandomValues(new Uint32Array(1))[0],count=Math.ceil(bytes.length/32768),result=[];
    for(let i=0;i<count;i++){const chunk=bytes.subarray(i*32768,(i+1)*32768);result.push(JSON.stringify({type:'local_chunk',id,index:i,count,data:btoa(Array.from(chunk,v=>String.fromCharCode(v)).join(''))}));}
    return result;
  }
  class Receiver{
    accept(raw){
      if(typeof raw!=='string'||encoder.encode(raw).length>50000)throw Error('Invalid local frame.');
      const value=JSON.parse(raw);
      if(value?.type!=='local_chunk'){if(this.group)throw Error('Interleaved local frames.');return raw;}
      if(!Number.isInteger(value.id)||!Number.isInteger(value.index)||!Number.isInteger(value.count)||value.count<1||value.count>192||typeof value.data!=='string')throw Error('Invalid local chunks.');
      if(value.index===0){if(this.group)throw Error('Interleaved chunks.');this.group={id:value.id,count:value.count,index:0,bytes:0,chunks:[],started:Date.now()};}
      const group=this.group;
      if(!group||group.id!==value.id||group.count!==value.count||group.index!==value.index||Date.now()-group.started>10000)throw Error('Incomplete local response.');
      const bytes=Uint8Array.from(atob(value.data),v=>v.charCodeAt(0));group.bytes+=bytes.length;
      if(group.bytes>6*1024*1024)throw Error('Local response is too large.');
      group.chunks.push(bytes);group.index++;
      if(group.index<group.count)return null;
      const combined=new Uint8Array(group.bytes);let offset=0;for(const chunk of group.chunks){combined.set(chunk,offset);offset+=chunk.length;}
      this.group=null;return decoder.decode(combined);
    }
  }
  class Socket{
    constructor(channel,onEnded){
      this.channel=channel;this.readyState=1;this.pending=new Map();this.sequence=0;this.queue=[];this.queuedBytes=0;this.receiver=new Receiver();this.backlog=[];
      let listener=null;
      let openListener=null;
      Object.defineProperty(this,'onopen',{get:()=>openListener,set:value=>{openListener=value;if(value&&this.readyState===1)queueMicrotask(()=>openListener?.({}));}});
      Object.defineProperty(this,'onmessage',{get:()=>listener,set:value=>{listener=value;if(value){for(const raw of this.backlog.splice(0))queueMicrotask(()=>listener?.({data:raw}));}}});
      channel.bufferedAmountLowThreshold=65536;
      channel.addEventListener('bufferedamountlow',()=>this.pump());
      channel.addEventListener('message',event=>{try{const raw=this.receiver.accept(event.data);if(raw===null)return;const message=JSON.parse(raw);if(message.type==='local_rpc_result'){const pending=this.pending.get(message.id);if(pending){clearTimeout(pending.timer);this.pending.delete(message.id);let body=JSON.stringify(message.body),type='application/json';if(message.kind==='bytes'){body=Uint8Array.from(atob(message.body),v=>v.charCodeAt(0));type='image/png';}pending.resolve(new Response(body,{status:message.status,headers:{'Content-Type':type}}));}return;}if(listener)listener({data:raw});else if(this.backlog.length<32)this.backlog.push(raw);else this.close();}catch(_){this.close();}});
      channel.addEventListener('close',()=>{if(this.readyState===3)return;this.readyState=3;clearTimeout(this.pumpTimer);for(const pending of this.pending.values()){clearTimeout(pending.timer);pending.reject(Error('Local connection ended.'));}this.pending.clear();onEnded();this.onclose?.({});});
    }
    get bufferedAmount(){return this.channel.bufferedAmount+this.queuedBytes;}
    send(raw){if(this.readyState!==1)throw Error('Local connection closed.');const parts=frames(raw);for(const part of parts){const size=encoder.encode(part).length;if(this.queuedBytes+size>2*1024*1024){this.close();throw Error('Local connection is too slow.');}this.queue.push([part,size]);this.queuedBytes+=size;}this.pump();}
    pump(){clearTimeout(this.pumpTimer);if(this.readyState!==1)return;try{while(this.queue.length&&this.channel.bufferedAmount<256*1024){const [raw,size]=this.queue.shift();this.queuedBytes-=size;this.channel.send(raw);}if(this.queue.length)this.pumpTimer=setTimeout(()=>this.pump(),20);}catch(_){this.close();}}
    close(){if(this.readyState===3)return;this.channel.close();}
    fetch(path,options={}){
      if(this.pending.size>=16)return Promise.reject(Error('Too many local requests.'));
      const id=++this.sequence;
      return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('Local request timed out.'));},15000);this.pending.set(id,{resolve,reject,timer});try{this.send(JSON.stringify({type:'local_rpc',id,path,method:options.method||'GET',...(options.body?{body:JSON.parse(options.body)}:{})}));}catch(error){clearTimeout(timer);this.pending.delete(id);reject(error);}});
    }
  }
  window.TouchHelmLocalTransport={proof,fingerprint,frames,Receiver,Socket};
})();
