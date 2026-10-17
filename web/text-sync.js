/* Focused-field snapshots never travel through the native keystroke diff path. */
(() => {
  'use strict';
  class FocusedTextSync {
    constructor(client) {
      this.client=client;this.field=null;this.pending=null;this.latest=null;
      this.sequence=0;this.conflict=false;this.enterPending=false;this.view='viewTrackpad';
      this.localVersion=0;
      client.typeInput.addEventListener('input',()=>{this.localVersion++;});
      this.toggle=document.getElementById('pcTextSync');this.status=document.getElementById('pcTextStatus');
      this.use=document.getElementById('usePCText');
      try {this.toggle.checked=localStorage.getItem('touchhelm_pc_text_sync')!=='false';}catch{}
      this.toggle.addEventListener('change',()=>{
        try{localStorage.setItem('touchhelm_pc_text_sync',String(this.toggle.checked));}catch{}
        if(this.field){this.client.liveTextValue='';this.client.liveTypingPaused=!!this.client.typeInput.value;this.client.updateTypingUi();}
        this.reset();this.describe(this.toggle.checked?'Focus a PC text field to link it.':'PC reading off · native typing');
      });
      this.use.addEventListener('click',()=>{if(this.latest?.available){this.adopt(this.latest);this.client.liveTypingPaused=false;this.client.updateTypingUi();}});
      this.timer=setInterval(()=>this.poll(),900);
      document.addEventListener('visibilitychange',()=>{if(document.hidden)this.reset();});
    }
    describe(text){this.status.textContent=text;this.use.hidden=!this.conflict||!this.latest?.available;}
    enabled(){return this.toggle.checked&&this.client.chkRealtimeTyping?.checked&&this.view==='viewTrackpad'&&!document.hidden&&this.client.isConnected&&this.client.inputOwner!=='aircontrol';}
    canWrite(){return this.toggle.checked&&this.view==='viewTrackpad'&&!document.hidden&&this.client.isConnected&&this.client.inputOwner!=='aircontrol';}
    reset(){this.field=null;this.pending=null;this.latest=null;this.enterPending=false;this.conflict=false;this.use.hidden=true;}
    onView(view){this.view=view;if(view!=='viewTrackpad')this.reset();}
    connected(value){this.reset();this.describe(value?'Focus a PC text field to link it.':'PC text sync offline · draft kept');}
    poll(){
      if(!this.enabled()||this.client.isComposing)return;
      if(this.pending){
        if(performance.now()-this.pending.at>25000){this.pending=null;this.conflict=true;this.enterPending=false;this.describe('PC text timed out. Your draft is kept.');}
        return;
      }
      if(this.field&&!this.conflict&&this.client.typeInput.value!==this.client.liveTextValue){this.edit();return;}
      this.request('read');
    }
    request(action,extra={}){
      const request_id=++this.sequence;
      if(!this.client.send({type:'text_sync',action,request_id,...extra}))return false;
      this.pending={action,request_id,at:performance.now(),localVersion:this.localVersion,...extra};return true;
    }
    adopt(state){
      const field=this.client.typeInput, focused=document.activeElement===field;
      const start=field.selectionStart,end=field.selectionEnd,wasEnd=end===field.value.length;
      field.value=state.text;this.client.liveTextValue=state.text;
      if(focused)field.setSelectionRange(wasEnd?state.text.length:Math.min(start,state.text.length),wasEnd?state.text.length:Math.min(end,state.text.length));
      this.field={field_id:state.field_id,revision:state.revision};this.conflict=false;
      this.client.controls?.resizeTyping();this.describe('Linked to focused PC field · two-way text');
    }
    receive(state){
      if(state.type!=='text_state')return false;
      if(state.request_id&&state.request_id!==this.pending?.request_id)return true;
      const pending=this.pending;this.pending=null;
      const queuedSend=pending?.action==='read'&&this.enterPending&&this.canWrite();
      if(!this.enabled()&&!(pending?.action==='write'&&this.canWrite())&&!queuedSend)return true;
      if(!state.available){
        this.latest=null;
        if(pending?.action==='write'||queuedSend){this.conflict=true;this.enterPending=false;}
        else if(this.field)this.conflict=true;
        else this.field=null;
        this.describe(state.message||'PC field unavailable · native typing');return true;
      }
      if(typeof state.text!=='string'||state.text.length>10000)return true;
      this.latest=state;
      if(this.client.isComposing){this.describe('Finishing phone composition…');return true;}
      if(queuedSend){
        // Explicit Send may wait behind a read started before Live was disabled.
        // Revalidate its target/baseline before sending the buffered edit.
        if(this.field?.field_id!==state.field_id||state.text!==this.client.liveTextValue){
          this.conflict=true;this.enterPending=false;
          this.describe('PC text changed · draft kept. Choose Use PC text to relink.');return true;
        }
        this.field.revision=state.revision;
        if(this.edit(true)===true)this.finishEnter();return true;
      }
      if(pending?.action==='read'&&pending.localVersion!==this.localVersion){
        if(this.field?.field_id===state.field_id&&state.text===this.client.liveTextValue){this.field.revision=state.revision;this.edit();}
        else this.describe('Waiting for PC text after phone input…');
        return true;
      }
      if(pending?.action==='write'&&state.field_id===pending.field_id&&state.text===pending.text){
        this.field={field_id:state.field_id,revision:state.revision};this.client.liveTextValue=state.text;
        if(this.client.typeInput.value!==state.text){this.edit(true);return true;}
        this.describe('Linked to focused PC field · two-way text');
        if(this.enterPending)this.finishEnter();return true;
      }
      if(this.conflict||this.client.liveTypingPaused||this.client.typeInput.value!==this.client.liveTextValue){
        this.conflict=true;this.describe('PC text changed · draft kept. Choose Use PC text to relink.');return true;
      }
      this.adopt(state);return true;
    }
    edit(force=false){
      if(!(force?this.canWrite():this.enabled()))return null;
      if(this.conflict){this.describe('Draft kept · review PC text before relinking.');return false;}
      if(!this.field)return null;
      if(this.client.isComposing)return false;
      if(this.pending)return false;
      if(this.client.typeInput.value===this.client.liveTextValue)return true;
      this.request('write',{...this.field,text:this.client.typeInput.value,newline_mode:this.client.newlineMode||'shift_enter'});
      this.describe('Syncing phone edit…');return false;
    }
    submitEnter(){
      if(!this.canWrite()||(!this.field&&!this.conflict))return false;
      if(this.conflict){this.describe('Draft kept · choose Use PC text before pressing PC Enter.');return true;}
      this.enterPending=this.client.chkRealtimeTyping.checked?'enter':'send';
      if(this.edit(true)===true)this.finishEnter();return true;
    }
    finishEnter(){
      const mode=this.enterPending;
      this.enterPending=false;
      if(mode==='send'||this.client.send({type:'key',key:'enter'})){
        this.client.typeInput.value='';this.client.liveTextValue='';this.field=null;
        this.client.updateTypingUi();this.describe(mode==='send'?'Text sent to linked PC field.':'PC Enter sent · waiting for field update');
      }
    }
    clear(){const attached=!!this.field||this.conflict||this.pending?.action==='write';this.reset();this.conflict=attached;this.describe(attached?'Draft cleared locally · use PC text to relink.':'Local draft cleared · native typing');}
  }
  window.TouchHelmTextSync=FocusedTextSync;
})();
