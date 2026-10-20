/* Focused PC snapshots never travel through the native keystroke diff path. */
(() => {
  'use strict';
  // Bounded Myers diff keeps separate edits separate (for example autocorrect
  // near the start and punctuation at the end). Large rewrites use one range.
  function changes(original, next) {
    let prefix=0,suffix=0;
    while(prefix<original.length&&prefix<next.length&&original[prefix]===next[prefix])prefix++;
    while(suffix<original.length-prefix&&suffix<next.length-prefix&&original[original.length-1-suffix]===next[next.length-1-suffix])suffix++;
    const before=original.slice(prefix,original.length-suffix),after=next.slice(prefix,next.length-suffix);
    const fallback=[{start:prefix,end:original.length-suffix,insert:after}];
    if(!before.length||!after.length)return before.length||after.length?fallback:[];
    const frontier=new Map([[1,0]]),trace=[];
    let work=0;
    for(let distance=0;distance<=Math.min(before.length+after.length,128);distance++){
      trace.push(new Map(frontier));
      for(let diagonal=-distance;diagonal<=distance;diagonal+=2){
        if(++work>100000)return fallback;
        let x=diagonal===-distance||(diagonal!==distance&&(frontier.get(diagonal-1)??-Infinity)<(frontier.get(diagonal+1)??-Infinity))
          ?frontier.get(diagonal+1)??0:(frontier.get(diagonal-1)??0)+1;
        let y=x-diagonal;
        while(x<before.length&&y<after.length&&before[x]===after[y]){x++;y++;if(++work>100000)return fallback;}
        frontier.set(diagonal,x);
        if(x<before.length||y<after.length)continue;
        const operations=[];
        for(let d=trace.length-1;d>=0;d--){
          const prior=trace[d],k=x-y;
          const previous=k===-d||(k!==d&&(prior.get(k-1)??-Infinity)<(prior.get(k+1)??-Infinity))?k+1:k-1;
          const oldX=prior.get(previous)??0,oldY=oldX-previous;
          while(x>oldX&&y>oldY){operations.push(['equal']);x--;y--;}
          if(d===0)break;
          if(x===oldX){operations.push(['insert',after[--y]]);}else {operations.push(['delete']);x--;}
        }
        const equal=prefix+suffix+operations.filter(item=>item[0]==='equal').length;
        if(equal/Math.max(original.length,next.length)<.5)return fallback;
        const edits=[];let position=prefix,current=null;
        for(const [kind,value] of operations.reverse()){
          if(kind==='equal'){current=null;position++;continue;}
          if(!current){current={start:position,end:position,insert:[]};edits.push(current);}
          if(kind==='insert')current.insert.push(value);else {position++;current.end++;}
        }
        return edits;
      }
    }
    return fallback;
  }
  // Independent edits merge against shared text. Only overlapping hunks follow PC text.
  function mergeText(base, pc, phone) {
    if (phone === base || phone === pc) return pc;
    if (pc === base) return phone;
    const original = Array.from(base);
    const remote=changes(original,Array.from(pc)),local=changes(original,Array.from(phone)),accepted=[];
    for(const edit of local){
      let handled=false;
      for(const pcEdit of remote){
        if(edit.start===pcEdit.start&&edit.end===pcEdit.end&&edit.insert.join('')===pcEdit.insert.join('')){handled=true;break;}
        if(edit.start===edit.end&&pcEdit.start===pcEdit.end&&edit.start===pcEdit.start){
          pcEdit.insert.push(...edit.insert);handled=true;break;
        }
        const overlaps=edit.start===edit.end?edit.start>pcEdit.start&&edit.start<pcEdit.end
          :pcEdit.start===pcEdit.end?pcEdit.start>edit.start&&pcEdit.start<edit.end
          :edit.start<pcEdit.end&&pcEdit.start<edit.end;
        if(overlaps){handled=true;break;}
      }
      if(!handled)accepted.push(edit);
    }
    for(const edit of [...remote,...accepted].sort((a,b)=>b.start-a.start||b.end-a.end))
      original.splice(edit.start,edit.end-edit.start,...edit.insert);
    const merged=original.join('');
    return merged.length<=10000 ? merged : pc;
  }
  class FocusedTextSync {
    constructor(client) {
      this.client=client; this.sequence=0; this.localVersion=0; this.view='viewTrackpad';
      this.toggle=document.getElementById('pcTextSync'); this.status=document.getElementById('pcTextStatus');
      this.reset();
      client.typeInput.addEventListener('input',()=>{this.localVersion++;});
      try {this.toggle.checked=localStorage.getItem('touchhelm_pc_text_sync')!=='false';}catch{}
      this.toggle.addEventListener('change',()=>{
        try {localStorage.setItem('touchhelm_pc_text_sync',String(this.toggle.checked));}catch{}
        if(this.field) {this.client.liveTextValue='';this.client.liveTypingPaused=!!this.client.typeInput.value;this.client.updateTypingUi();}
        this.reset();
        this.describe(this.toggle.checked?'Waiting for a PC text field…':'PC reading off · native typing');
        this.poll();
      });
      this.timer=setInterval(()=>this.poll(),300);
      document.addEventListener('visibilitychange',()=>{if(document.hidden)this.suspend();else this.poll();});
    }
    describe(text) {
      this.status.textContent=text;
      if(this.status.dataset)this.status.dataset.state=!this.client.isConnected?'offline':this.needsRead||this.pending?'syncing':this.field?'linked':'ready';
    }
    enabled(){return this.canWrite()&&this.client.chkRealtimeTyping?.checked;}
    canWrite(){return this.toggle.checked&&this.view==='viewTrackpad'&&!document.hidden&&this.client.isConnected&&this.client.inputOwner!=='aircontrol';}
    reset(){
      this.field=null;this.pending=null;this.latest=null;this.enterPending=false;
      this.needsRead=false;this.lastAutoField=null;this.conflict=false;this.unconfirmed=null;this.clearTarget=null;
      clearTimeout(this.pointerTimer);
    }
    suspend(){
      if(this.pending?.action==='write')this.unconfirmed=this.pending;
      this.needsRead=!!this.field;this.pending=null;this.enterPending=false;
      clearTimeout(this.pointerTimer);
    }
    onView(view){if(view!=='viewTrackpad')this.suspend();this.view=view;if(view==='viewTrackpad')this.poll();}
    connected(value){this.reset();this.describe(value?'Waiting for a PC text field…':'Offline · phone draft kept');if(value)this.poll();}
    pointerAction(){
      if(!this.enabled())return;
      this.lastAutoField=null;clearTimeout(this.pointerTimer);
      this.pointerTimer=setTimeout(()=>this.poll(),100);
    }
    poll(){
      const explicit=(this.enterPending==='send'||!!this.clearTarget)&&this.canWrite();
      if((!this.enabled()&&!explicit)||this.client.isComposing)return;
      if(this.pending){
        if(performance.now()-this.pending.at>25000){
          const resumeSend=this.enterPending==='send';
          this.suspend();if(resumeSend)this.enterPending='send';
          this.describe('Reading PC text again…');
        }
        return;
      }
      if(this.field&&!this.needsRead&&this.client.typeInput.value!==this.client.liveTextValue){this.edit(explicit);return;}
      if(this.enterPending&&this.field&&!this.needsRead){this.finishEnter();return;}
      this.request('read');
    }
    request(action,extra={}){
      if(this.pending)return false;
      const request_id=++this.sequence;
      if(!this.client.send({type:'text_sync',action,request_id,...extra}))return false;
      this.pending={action,request_id,at:performance.now(),localVersion:this.localVersion,base:this.client.liveTextValue,...extra};
      this.pending.clearing=action==='write'&&this.clearTarget===extra.field_id;
      return true;
    }
    adopt(state,value=state.text){
      const input=this.client.typeInput,focused=document.activeElement===input;
      const start=input.selectionStart,end=input.selectionEnd,wasEnd=end===input.value.length;
      input.value=value;this.client.liveTextValue=state.text;this.client.liveTypingPaused=false;
      if(focused)input.setSelectionRange(wasEnd?value.length:Math.min(start,value.length),wasEnd?value.length:Math.min(end,value.length));
      this.field={field_id:state.field_id,revision:state.revision};this.needsRead=false;
      this.client.clearFeedback?.('typing');this.client.updateTypingUi();
      // A text update never reopens a dismissed dock. A PC focus transition does.
      if(this.lastAutoField!==state.field_id){
        if(!this.client.isDragging&&!this.client.leftBtnDown&&!document.querySelector?.('.modal-backdrop.open')){
          this.lastAutoField=state.field_id;
          this.client.controls?.expandTyping();input.focus?.({preventScroll:true});
        }
      }
      this.client.controls?.resizeTyping();this.describe('PC text linked · edits sync automatically');
    }
    receive(state){
      if(state.type!=='text_state')return false;
      if(state.request_id&&state.request_id!==this.pending?.request_id)return true;
      const pending=this.pending;this.pending=null;
      const explicit=(!!this.enterPending||!!this.clearTarget)&&this.canWrite();
      if(!this.enabled()&&!(pending?.action==='write'&&this.canWrite())&&!explicit)return true;
      if(!state.available){
        this.latest=null;this.needsRead=!!this.field;
        // Never carry an Enter press over to a newly focused field.
        if(this.enterPending!=='send')this.enterPending=false;
        this.lastAutoField=null;
        this.describe(this.field?'Waiting for the PC text field…':state.message||'Select a PC text field to type.');
        return true;
      }
      if(typeof state.text!=='string'||state.text.length>10000)return true;
      this.latest=state;
      const sameField=this.field?.field_id===state.field_id;
      if(pending?.action==='write'&&state.field_id===pending.field_id&&state.text===pending.text){
        this.unconfirmed=null;
        if(pending.clearing)this.clearTarget=null;
        this.field={field_id:state.field_id,revision:state.revision};this.client.liveTextValue=state.text;this.needsRead=false;
        if(this.client.isComposing)return true;
        if(pending.clearing&&!this.enabled()&&!this.enterPending)return true;
        if(this.client.typeInput.value!==state.text)this.edit(true);
        else if(this.enterPending)this.finishEnter();
        else this.describe('PC text linked · edits sync automatically');
        return true;
      }
      if(this.client.isComposing){this.needsRead=true;return true;}
      if(this.clearTarget){
        if(sameField&&this.clearTarget===state.field_id){
          const value=this.client.typeInput.value;
          const desired=this.enabled()||this.enterPending?value:'';
          this.unconfirmed=null;this.adopt(state,value);
          if(desired!==state.text)this.edit(true);else this.clearTarget=null;
          return true;
        }
        this.clearTarget=null;
      }
      // Native typing before attachment may race an older snapshot. Read again.
      if(!this.field&&pending?.action==='read'&&pending.localVersion!==this.localVersion
        &&this.client.typeInput.value===this.client.liveTextValue&&!this.client.liveTypingPaused)return true;
      let base=this.client.liveTextValue||'';
      const local=this.client.typeInput.value;
      // A write may have reached Windows even when its acknowledgement was
      // lost. Rebase subsequent phone edits on that attempted value, not on the
      // older baseline, unless the PC still contains the original baseline.
      const attempted=this.unconfirmed||(pending?.action==='write'?pending:null);
      if(sameField&&attempted?.field_id===state.field_id
          &&(state.text===attempted.text||state.acknowledged_write===attempted.request_id))base=attempted.text;
      this.unconfirmed=null;
      const value=sameField&&!this.client.liveTypingPaused?mergeText(base,state.text,local)
        :!this.field&&local!==base&&!this.client.liveTypingPaused?mergeText(base,state.text,local):state.text;
      if(this.field&&!sameField)this.enterPending=false;
      this.adopt(state,value);
      if(value!==state.text)this.edit(explicit);
      else if(this.enterPending)this.finishEnter();
      return true;
    }
    edit(force=false){
      if(!(force?this.canWrite():this.enabled()))return null;
      if(this.needsRead){if(!this.pending)this.request('read');return false;}
      if(!this.field)return null;
      if(this.client.isComposing||this.pending)return false;
      const value=this.clearTarget&&!this.enabled()&&!this.enterPending?'':this.client.typeInput.value;
      if(value===this.client.liveTextValue){this.clearTarget=null;return true;}
      this.request('write',{...this.field,text:value,newline_mode:this.client.newlineMode||'shift_enter'});
      this.describe('Syncing phone text…');return false;
    }
    submitEnter(){
      if(!this.canWrite()||!this.field)return false;
      this.enterPending=this.client.chkRealtimeTyping.checked&&!this.client.liveTypingPaused?'enter':'send';
      if(this.edit(true)===true)this.finishEnter();return true;
    }
    finishEnter(){
      const mode=this.enterPending;this.enterPending=false;
      if(mode&&(mode==='send'||this.client.send({type:'key',key:'enter'}))){
        this.client.typeInput.value='';this.client.liveTextValue='';this.field=null;this.client.liveTypingPaused=false;
        this.client.clearFeedback?.('typing');this.client.updateTypingUi();
        this.describe(mode==='send'?'Text sent to your PC.':'PC Enter sent');
      }
    }
    clear(){
      this.enterPending=false;this.localVersion++;
      if(this.field&&this.canWrite()){
        this.clearTarget=this.field.field_id;this.client.typeInput.value='';this.client.liveTypingPaused=false;
        this.edit(true);this.describe('Clearing PC text…');return true;
      }
      this.suspend();this.unconfirmed=null;this.clearTarget=null;this.describe('Phone draft cleared');return false;
    }
  }
  FocusedTextSync.mergeText=mergeText;
  window.TouchHelmTextSync=FocusedTextSync;
})();
