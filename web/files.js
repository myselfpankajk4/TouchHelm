/* PC files stay on the local server. File bodies never enter the control socket. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const text=(tag,value,className)=>{const node=document.createElement(tag);node.textContent=value;if(className)node.className=className;return node;};
  const size=value=>{if(!Number.isFinite(value)||value<0)return 'Unknown size';const unit=value>=1024**3?'GiB':value>=1024**2?'MiB':value>=1024?'KiB':'B';const divisor={B:1,KiB:1024,MiB:1024**2,GiB:1024**3}[unit];return `${new Intl.NumberFormat(undefined,{maximumFractionDigits:unit==='B'?0:1}).format(value/divisor)} ${unit}`;};
  const uid=()=>Array.from(crypto.getRandomValues(new Uint8Array(12)),n=>n.toString(16).padStart(2,'0')).join('');
  const icon=kind=>{const image=document.createElement('img');image.src=`/icons/files/${['downloads','documents','pictures','videos','music','desktop','drive','folder','pdf','audio','video','image','download'].includes(kind)?kind:'download'}.svg`;image.alt='';image.width=64;image.height=64;return image;};
  function button(label,action,className){const node=text('button',label,className);node.type='button';if(action)node.addEventListener('click',action);return node;}
  class TouchHelmFiles {
    constructor(client){
      this.client=client;this.ready=false;this.active=false;this.enabled=false;this.locations=[];this.folder=null;this.selected=new Map();this.transfers=[];this.queue=[];this.receiveQueue=[];this.downloadActive=null;this.grid=false;this.generation=0;this.page=0;this.listRequest=0;
      $('filesSend').addEventListener('click',()=>$('filesPicker').click());
      $('filesPicker').addEventListener('change',()=>{const files=[...$('filesPicker').files];$('filesPicker').value='';if(files.length)this.chooseDestination(files);});
      $('filesReceive').addEventListener('click',()=>{if(!this.selected.size){this.status('Select one or more files using their checkboxes, then choose Receive.');return;}if(this.pendingCount()+this.selected.size>32){this.status('Queue up to 32 transfers at a time. Finish or cancel some first.',true);return;}for(const entry of this.selected.values())this.receive(entry);});
      $('filesClearSelection').addEventListener('click',()=>{this.selected.clear();this.drawEntries();});
      $('filesSearch').addEventListener('input',()=>{clearTimeout(this.searchTimer);this.searchTimer=setTimeout(()=>this.load(this.folder?.id,false),250);});
      $('filesSort').addEventListener('change',()=>this.load(this.folder?.id,false));
      $('filesView').addEventListener('click',()=>{this.grid=!this.grid;$('filesEntries').classList.toggle('files-grid',this.grid);$('filesView').setAttribute('aria-pressed',String(this.grid));$('filesView').setAttribute('aria-label',this.grid?'Show file list':'Show file grid');});
      $('filesRefresh').addEventListener('click',()=>this.refresh());$('filesRetry').addEventListener('click',()=>this.refresh());
      $('filesMore').addEventListener('click',()=>this.load(this.folder?.id,false,true));
      $('filesNewFolder').addEventListener('click',()=>this.newFolder(false));
      $('filesDestinationNew').addEventListener('click',()=>this.newFolder(true));
      $('filesDestinationClose').addEventListener('click',()=>$('filesDestination').close());
      $('filesDestinationConfirm').addEventListener('click',()=>this.confirmSend());
      $('filesDestinationMore').addEventListener('click',()=>this.destination(this.destinationFolder?.id,true));
      $('filesFolderCancel').addEventListener('click',()=>$('filesFolderDialog').close());
      $('filesFolderForm').addEventListener('submit',event=>{event.preventDefault();this.createFolder();});
      $('filesPreviewBack').addEventListener('click',()=>{if(history.state?.filePreview)history.back();else this.closePreview();});
      $('filesPreviewReceive').addEventListener('click',()=>this.previewEntry&&this.receive(this.previewEntry));
      window.addEventListener('popstate',()=>{if(!this.active)return;const state=history.state||{};this.load(state.fileFolder||null,false).then(()=>{if(state.filePreview){const entry=this.entries?.find(item=>item.id===state.filePreview);if(entry)this.preview(entry,false);}else this.closePreview();});});
      window.addEventListener('pagehide',()=>this.disconnected());
    }
    status(message,error=false){$('filesStatus').textContent=message;$('filesStatus').dataset.error=String(error);$('filesRetry').hidden=!error;}
    connected(config){this.enabled=!!config?.files_enabled;this.pcName=config?.server_name||'My PC';$('filesPC').textContent=this.pcName;this.renderAccess();}
    configure(config){const before=this.enabled;this.enabled=!!config.files_enabled;if(!this.enabled)this.disconnected();else if(!before&&this.client.isConnected)this.requestSession();this.renderAccess();}
    requestSession(){if(this.client.isConnected)this.client.send({type:'files_ticket'});}
    async acceptTicket(ticket){
      if(!ticket){this.ready=false;this.renderAccess();return;}
      const generation=++this.generation;
      try{
        const response=await fetch('/api/files/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket}),credentials:'same-origin',cache:'no-store'});
        if(!response.ok)throw Error('Open Files again or reconnect with the PC PIN.');
        const value=await response.json();if(generation!==this.generation||!this.client.isConnected)return;
        this.csrf=value.csrf;this.ready=true;this.renderAccess();if(this.active)await this.refresh();
      }catch(error){if(generation===this.generation){this.ready=false;this.status(error.message,true);}}
    }
    disconnected(){
      this.ready=false;this.csrf='';this.generation++;this.closePreview();
      for(const transfer of this.transfers)if(['sending','queued','receiving'].includes(transfer.state)){transfer.controller?.abort();transfer.state='interrupted';transfer.message='Reconnect, then retry.';}
      this.queue=[];this.receiveQueue=[];this.downloadActive=null;this.drawTransfers();this.renderAccess();
    }
    renderAccess(){
      $('filesSend').disabled=!this.ready;$('filesReceive').disabled=!this.ready;$('filesNewFolder').disabled=!this.ready||!this.folder?.writable;
      if(this.ready)return;
      $('filesQuick').replaceChildren();$('filesDrives').replaceChildren();$('filesEntries').replaceChildren();$('filesBreadcrumbs').replaceChildren(button('This PC',()=>this.load(null)));$('filesSelection').hidden=true;
      this.status(!this.client.isConnected?'Connect to your PC to browse files.':!this.enabled?'File access is off. On your PC, open Pair your phone → File access → Enable.':'Preparing local file access…');
    }
    onView(view){this.active=view==='viewFiles';if(!this.active){this.pausePreview();return;}if(this.ready)this.refresh();else if(this.enabled&&this.client.isConnected)this.requestSession();else this.renderAccess();}
    async api(path,options={}){
      if(!this.ready)throw Error('Connect to the PC and enable File access first.');
      const response=await fetch('/api/files'+path,{credentials:'same-origin',cache:'no-store',...options,headers:{...(options.body&&!(options.body instanceof Blob)?{'Content-Type':'application/json'}:{}),'X-TouchHelm-Files':this.csrf,...options.headers}});
      if(!response.ok){let message='The file operation failed. Refresh the folder and try again.';try{const value=await response.json();message=value.message||message;}catch{if(response.status===401)message='Your file session ended. Reconnect with the PC PIN.';if(response.status===403)message='File access is off or this folder is unavailable. Check TouchHelm on the PC.';}if(response.status===401){this.disconnected();this.requestSession();}throw Error(message);}
      return response.json();
    }
    async refresh(){
      if(!this.ready)return this.renderAccess();
      try{const value=await this.api('/locations');this.locations=value.locations;this.maxSize=value.max_file_size;this.drawLocations();await this.load(this.folder?.id||null,false);}catch(error){this.status(error.message,true);}
    }
    drawLocations(){
      const make=entry=>{const node=button('',()=>this.load(entry.id,true),'files-location');node.append(icon(entry.kind),text('span',entry.name),text('span','›','files-chevron'));return node;};
      const order=['downloads','documents','pictures','videos','desktop','music'];
      $('filesQuick').replaceChildren(...this.locations.filter(entry=>entry.kind!=='drive').sort((a,b)=>order.indexOf(a.kind)-order.indexOf(b.kind)).map(make));
      $('filesDrives').replaceChildren(...this.locations.filter(entry=>entry.kind==='drive').map(make));
    }
    async load(id,push=true,more=false){
      if(!this.ready)return this.renderAccess();
      const request=++this.listRequest;this.closePreview();
      if(push){$('filesSearch').value='';this.page=0;}
      if(!more){this.selected.clear();this.entries=[];$('filesEntries').replaceChildren();this.page=0;}
      this.status('Opening folder…');$('filesMore').disabled=true;
      try{
        if(!id){this.folder=null;this.entries=[];$('filesBreadcrumbs').replaceChildren(button('This PC',()=>this.load(null)));$('filesEntries').replaceChildren(...this.locations.map(entry=>{const li=document.createElement('li');const node=button('',()=>this.load(entry.id),'files-open-entry');node.append(icon(entry.kind),text('strong',entry.name));li.append(node);return li;}));$('filesMore').hidden=true;this.status(this.locations.length?'Choose a folder or drive to browse.':'No local folders are available. Check Windows permissions on the PC.');}
        else{
          const query=new URLSearchParams({id,q:$('filesSearch').value,sort:$('filesSort').value,offset:String(more?this.page:0)});
          const data=await this.api('/list?'+query);if(request!==this.listRequest)return;
          this.folder=data;this.entries=more?[...this.entries,...data.entries]:data.entries;this.page=data.next_offset;
          this.breadcrumbs($('filesBreadcrumbs'),data.breadcrumbs,entry=>this.load(entry.id));this.drawEntries();
          $('filesMore').hidden=!data.has_more;this.status(data.limited?'This folder has more than 50,000 entries. Open a smaller subfolder.':data.total?`${new Intl.NumberFormat().format(data.total)} ${data.total===1?'item':'items'}${data.writable?'':' · Read-only folder'}`:$('filesSearch').value?'No matching files. Try another name.':'This folder is empty. Send a file here from your phone.');
        }
        $('filesWorkspace').dataset.folder=String(!!this.folder);$('filesNewFolder').disabled=!this.folder?.writable;
        if(push)this.remember();else if(this.active)this.remember(false);
      }catch(error){if(request===this.listRequest)this.status(error.message,true);}
      finally{$('filesMore').disabled=false;}
    }
    remember(push=true,preview=null){const state={fileFolder:this.folder?.id||null,filePreview:preview};const url=new URL(location.href);url.hash=new URLSearchParams({files:state.fileFolder||'pc',...(preview?{preview}:{}),q:$('filesSearch').value,sort:$('filesSort').value});history[push?'pushState':'replaceState'](state,'',url);}
    breadcrumbs(node,entries,action){node.replaceChildren(button('This PC',()=>action({id:null})),...entries.flatMap(entry=>[text('span','›','files-separator'),button(entry.name,()=>action(entry))]));}
    drawEntries(){
      $('filesEntries').replaceChildren(...(this.entries||[]).map(entry=>{
        const row=document.createElement('li');row.className='files-entry';row.dataset.selected=String(this.selected.has(entry.id));
        if(!entry.directory&&!entry.unavailable){const label=document.createElement('label');label.className='files-select';const check=document.createElement('input');check.type='checkbox';check.checked=this.selected.has(entry.id);check.setAttribute('aria-label',`Select ${entry.name}`);check.addEventListener('change',()=>{if(check.checked)this.selected.set(entry.id,entry);else this.selected.delete(entry.id);row.dataset.selected=String(check.checked);this.drawSelection();});label.append(check);row.append(label);}
        const open=button('',()=>entry.directory?this.load(entry.id):this.preview(entry),'files-open-entry');
        const details=document.createElement('span');details.className='files-entry-text';details.append(text('strong',entry.name),text('small',entry.unavailable||(entry.directory?'Folder':`${entry.preview==='download'?(entry.name.split('.').pop()||'File').toUpperCase():entry.preview.toUpperCase()} · ${size(entry.size)}`)));open.append(icon(entry.directory?'folder':entry.preview),details);open.disabled=!!entry.unavailable;row.append(open);
        if(!entry.directory&&!entry.unavailable){const receive=button('↓',()=>this.receive(entry),'files-icon-button');receive.setAttribute('aria-label',`Receive ${entry.name}`);receive.title=`Receive ${entry.name}`;row.append(receive);}else if(!entry.unavailable)row.append(text('span','›','files-chevron'));
        return row;
      }));this.drawSelection();
    }
    drawSelection(){$('filesSelection').hidden=!this.selected.size;$('filesSelectionCount').textContent=`${this.selected.size} selected`;$('filesReceive').textContent=this.selected.size?`↓ Receive (${this.selected.size})`:'↓ Receive';}
    async chooseDestination(files){
      if(!this.ready)return;
      if(files.length>32){this.status('Send up to 32 files at a time. Choose fewer files.',true);return;}
      const tooLarge=files.find(file=>file.size>this.maxSize);if(tooLarge){this.status(`${tooLarge.name} is too large. Files can be up to 16 GiB each.`,true);return;}
      this.pendingFiles=files;$('filesSendCount').textContent=`${files.length} ${files.length===1?'file':'files'} · ${size(files.reduce((total,file)=>total+file.size,0))}`;
      $('filesDestination').showModal();await this.destination(this.folder?.writable?this.folder.id:this.locations.find(entry=>entry.kind==='downloads')?.id||null);
    }
    async destination(id,more=false){
      const request=this.destinationRequest=(this.destinationRequest||0)+1;
      $('filesDestinationConfirm').disabled=true;$('filesDestinationStatus').textContent='Opening destination…';$('filesDestinationMore').disabled=true;
      if(!more){$('filesDestinationEntries').replaceChildren();this.destinationOffset=0;}
      try{
        let entries;
        if(id){const data=await this.api('/list?'+new URLSearchParams({id,offset:String(more?this.destinationOffset:0)}));if(request!==this.destinationRequest)return;this.destinationFolder=data;this.destinationOffset=data.next_offset;entries=data.entries.filter(entry=>entry.directory);this.breadcrumbs($('filesDestinationPath'),data.breadcrumbs,entry=>this.destination(entry.id));$('filesDestinationMore').hidden=!(data.has_more&&data.entries.every(entry=>entry.directory));}
        else{this.destinationFolder=null;entries=this.locations;$('filesDestinationPath').replaceChildren(button('This PC',()=>this.destination(null)));$('filesDestinationMore').hidden=true;}
        $('filesDestinationEntries').append(...entries.map(entry=>{const li=document.createElement('li');const node=button('',()=>this.destination(entry.id));node.disabled=!!entry.unavailable;node.append(icon(entry.kind||'folder'),text('span',entry.name),text('span',entry.unavailable?'Offline':'›'));li.append(node);return li;}));
        $('filesDestinationConfirm').disabled=!this.destinationFolder?.writable;$('filesDestinationNew').disabled=!this.destinationFolder?.writable;
        $('filesDestinationStatus').textContent=this.destinationFolder?this.destinationFolder.writable?`Files will be saved in ${this.destinationFolder.breadcrumbs.map(entry=>entry.name).join(' / ')}. Existing files keep their names; duplicates get a numbered name.`:'This folder is read-only. Choose another destination.':'Choose a local folder or drive.';
      }catch(error){$('filesDestinationStatus').textContent=error.message;}
      finally{$('filesDestinationMore').disabled=false;}
    }
    newFolder(destination){this.creatingInDestination=destination;this.createParent=destination?this.destinationFolder:this.folder;if(!this.createParent?.writable)return;$('filesFolderName').value='';$('filesFolderError').textContent='';$('filesFolderDialog').showModal();}
    async createFolder(){const submit=$('filesFolderForm').querySelector('[type=submit]');submit.disabled=true;try{const result=await this.api('/folders',{method:'POST',body:JSON.stringify({parent:this.createParent.id,name:$('filesFolderName').value})});$('filesFolderDialog').close();if(this.creatingInDestination)await this.destination(result.id);else await this.load(result.id);}catch(error){$('filesFolderError').textContent=error.message;}finally{submit.disabled=false;}}
    confirmSend(){
      if(!this.destinationFolder?.writable)return;
      if(this.pendingCount()+this.pendingFiles.length>32){$('filesDestinationStatus').textContent='Queue up to 32 transfers at a time. Finish or cancel some first.';return;}
      for(const file of this.pendingFiles){const transfer={id:uid(),file,name:file.name,size:file.size,sent:0,direction:'send',state:'queued',parent:this.destinationFolder.id,destination:this.destinationFolder.name};this.trackTransfer(transfer);this.queue.push(transfer);}
      this.pendingFiles=[];$('filesDestination').close();this.drawTransfers();this.pump();
    }
    async pump(){
      if(this.pumping)return;this.pumping=true;
      try{while(this.queue.length&&this.ready){const transfer=this.queue.shift();if(transfer.state!=='queued')continue;await this.upload(transfer);}}
      finally{this.pumping=false;this.drawTransfers();}
    }
    async upload(transfer){
      transfer.state='sending';transfer.sent=0;transfer.message='';transfer.controller=new AbortController();this.drawTransfers();
      try{
        const options={signal:transfer.controller.signal};const result=await this.api('/uploads',{method:'POST',body:JSON.stringify({parent:transfer.parent,name:transfer.file.name,size:transfer.size})});transfer.upload=result.id;
        if(transfer.state==='cancelled'||transfer.state==='interrupted'){await this.api('/uploads/'+result.id,{method:'DELETE'}).catch(()=>{});return;}
        while(transfer.sent<transfer.size){const offset=transfer.sent;const chunk=transfer.file.slice(offset,Math.min(offset+result.chunk_size,transfer.size));const value=await this.api(`/uploads/${result.id}?offset=${offset}`,{...options,method:'PUT',body:chunk,headers:{'Content-Type':'application/octet-stream'}});if(value.offset!==offset+chunk.size)throw Error('The PC did not confirm the full chunk. Retry this file.');transfer.sent=value.offset;this.drawTransfers();}
        const saved=await this.api(`/uploads/${result.id}/finish`,{...options,method:'POST',body:'{}'});transfer.name=saved.name;transfer.state='complete';transfer.message=`Saved to ${transfer.destination}`;transfer.upload=null;if(this.folder?.id===transfer.parent)await this.load(transfer.parent,false);
      }catch(error){if(transfer.state!=='cancelled'){transfer.state='interrupted';transfer.message=error.name==='AbortError'?'Transfer interrupted. Retry when connected.':error.message;}if(transfer.upload&&this.ready)await this.api('/uploads/'+transfer.upload,{method:'DELETE'}).catch(()=>{});}
      finally{this.drawTransfers();}
    }
    pendingCount(){return this.transfers.filter(item=>['sending','queued','receiving','browser'].includes(item.state)).length;}
    trackTransfer(transfer){const history=this.transfers.filter(item=>!['sending','queued','receiving','browser'].includes(item.state));const keep=new Set(history.slice(-31));this.transfers=this.transfers.filter(item=>['sending','queued','receiving','browser'].includes(item.state)||keep.has(item));this.transfers.push(transfer);}
    async cancel(transfer){transfer.state='cancelled';transfer.message='Cancelled';transfer.controller?.abort();if(transfer.direction==='receive'){if(this.ready)await this.api(`/downloads/${transfer.id}/cancel`,{method:'POST',body:'{}'}).catch(()=>{});if(this.downloadActive===transfer.id)this.downloadActive=null;this.startReceive();}else if(transfer.upload&&this.ready)await this.api('/uploads/'+transfer.upload,{method:'DELETE'}).catch(()=>{});this.drawTransfers();}
    async retry(transfer){if(!this.ready){this.status('Reconnect to your PC before retrying.',true);return;}if(this.pendingCount()>=32){this.status('Finish or cancel a queued transfer before retrying.',true);return;}if(transfer.direction==='receive'){await this.cancel(transfer);this.receive(transfer.entry,true);return;}transfer.state='queued';transfer.message='';transfer.sent=0;transfer.upload=null;this.queue.push(transfer);this.drawTransfers();this.pump();}
    receive(entry,first=false){
      if(!this.ready)return;if(this.pendingCount()>=32){this.status('Queue up to 32 transfers at a time. Finish or cancel some first.',true);return;}
      const transfer={id:uid(),name:entry.name,size:entry.size,sent:0,direction:'receive',state:'queued',entry,message:'Queued for Chrome downloads'};this.trackTransfer(transfer);this.receiveQueue[first?'unshift':'push'](transfer);this.drawTransfers();this.startReceive();
    }
    startReceive(){
      if(!this.ready||this.downloadActive)return;
      let transfer;while(this.receiveQueue.length){const next=this.receiveQueue.shift();if(next.state==='queued'){transfer=next;break;}}
      if(!transfer)return;transfer.state='receiving';transfer.message='Opening Chrome download…';this.downloadActive=transfer.id;this.drawTransfers();
      const entry=transfer.entry;
      const link=document.createElement('a');link.href=this.contentURL(entry,true,transfer.id);link.download=entry.name;document.body.append(link);link.click();link.remove();
      setTimeout(()=>{if(transfer.state==='receiving'&&transfer.sent===0){transfer.state='browser';transfer.message='Check Chrome downloads. Allow downloads if Chrome asks.';this.drawTransfers();}},8000);
    }
    downloadUpdate(message){const transfer=this.transfers.find(entry=>entry.id===message.id&&entry.direction==='receive');if(!transfer||transfer.state==='cancelled')return;transfer.sent=message.sent;transfer.state=message.state;transfer.message=message.state==='transferred'?'Transferred to Chrome downloads':message.state==='cancelled'?'Cancelled':message.state==='interrupted'?'Download interrupted. Retry or check Chrome downloads.':'Receiving from PC';if(['transferred','cancelled','interrupted'].includes(message.state)&&this.downloadActive===message.id){this.downloadActive=null;this.startReceive();}this.drawTransfers();}
    drawTransfers(){
      const live=this.transfers.filter(item=>['sending','queued','receiving','browser'].includes(item.state));
      const recent=[...live.filter(item=>item.state!=='queued'),...live.filter(item=>item.state==='queued'),...this.transfers.filter(item=>!live.includes(item)).reverse()].slice(0,32);$('filesTransfers').hidden=!recent.length;
      const active=recent.filter(item=>['sending','queued','receiving'].includes(item.state));const summary=active.length?`${active.length} ${active.length===1?'transfer':'transfers'} in progress · Show all`:`${recent.length} ${recent.length===1?'transfer':'transfers'} · Show history`;
      if($('filesTransferSummary').textContent!==summary)$('filesTransferSummary').textContent=summary;
      const list=$('filesTransferList'),current=$('filesCurrentTransfer'),wanted=new Set(recent.map(item=>item.id));
      let announcement='';
      for(const row of [...current.children,...list.children])if(!wanted.has(row.dataset.transfer))row.remove();
      recent.forEach((transfer,index)=>{
        let row=[...current.children,...list.children].find(item=>item.dataset.transfer===transfer.id);
        if(!row){
          row=document.createElement('li');row.className='files-transfer';row.dataset.transfer=transfer.id;
          const content=document.createElement('div'),name=text('strong',''),direction=text('small',''),progress=document.createElement('progress'),status=text('small','');
          content.append(name,direction,progress,status);row.append(icon(transfer.direction==='send'?'documents':'downloads'),content);row.parts={name,direction,progress,status};
        }
        const container=index===0?current:list,position=index===0?0:index-1;
        if(container.children[position]!==row)container.insertBefore(row,container.children[position]||null);
        const {name,direction,progress,status}=row.parts;
        if(row.dataset.state&&row.dataset.state!==transfer.state&&['complete','transferred','interrupted','cancelled','browser'].includes(transfer.state))announcement=`${transfer.name}. ${transfer.message||transfer.state}.`;
        row.dataset.state=transfer.state;
        name.textContent=transfer.name;direction.textContent=transfer.direction==='send'?`To PC · ${transfer.destination}`:'From PC · Chrome downloads';progress.max=transfer.size||1;progress.value=transfer.size?transfer.sent:transfer.state==='complete'?1:0;progress.setAttribute('aria-label',`${transfer.name} transfer progress`);
        status.textContent=transfer.message||`${size(transfer.sent)} of ${size(transfer.size)}`;
        const action=['sending','queued','receiving'].includes(transfer.state)?'cancel':transfer.state==='browser'?'browser':['interrupted','cancelled'].includes(transfer.state)?'retry':'';
        if(row.dataset.action!==action){
          if(row.contains(document.activeElement))$('filesTransferSummary').focus({preventScroll:true});
          row.querySelectorAll('button').forEach(control=>control.remove());row.dataset.action=action;
          for(const type of action==='browser'?['retry','cancel']:action?[action]:[]){const control=button(type==='cancel'?'×':'Retry',()=>type==='cancel'?this.cancel(transfer):this.retry(transfer),type==='cancel'?'files-icon-button':'');control.setAttribute('aria-label',`${type==='cancel'?'Cancel':'Retry'} ${transfer.name}`);row.append(control);}
        }
      });
      if(announcement)$('filesTransferAnnouncement').textContent=announcement;
    }
    contentURL(entry,download=false,transfer=null){return `/api/files/content/${encodeURIComponent(entry.id)}${download?'?download=1'+(transfer?'&transfer='+transfer:''):''}`;}
    preview(entry,push=true){
      this.previewEntry=entry;$('filesPreview').hidden=false;$('filesWorkspace').dataset.preview='true';$('filesPreviewName').textContent=entry.name;
      const url=this.contentURL(entry);let media;
      $('filesPreviewHint').textContent='';$('filesOpenExternal').href=url;$('filesOpenExternal').hidden=entry.preview==='download';
      if(entry.preview==='audio'||entry.preview==='video'){
        media=document.createElement(entry.preview);media.controls=true;media.preload='metadata';media.setAttribute('playsinline','');media.src=url;media.addEventListener('error',()=>{$('filesPreviewHint').textContent='Chrome cannot play this format. Receive the file to open it in a compatible app.';});
        if(entry.preview==='audio'){const wrap=document.createElement('div');wrap.className='files-audio-preview';wrap.append(icon('audio'),text('h3',entry.name),media);media=wrap;}
      }else if(entry.preview==='image'){media=document.createElement('img');media.src=url;media.alt=entry.name;media.addEventListener('error',()=>{$('filesPreviewHint').textContent='This image cannot be displayed. Receive it to open in another app.';});}
      else if(entry.preview==='pdf'){media=document.createElement('iframe');media.src=url;media.title=`PDF preview: ${entry.name}`;$('filesPreviewHint').textContent='If the PDF does not appear, choose Open file in Chrome or Receive.';}
      else{media=document.createElement('div');media.className='files-unsupported';media.append(icon('download'),text('h3','Ready to receive'),text('p','Receive this file to open it with an app on your phone. It will not run on the PC.'));}
      $('filesPreviewBody').replaceChildren(media);if(push)this.remember(true,entry.id);$('filesPreviewBack').focus({preventScroll:true});
    }
    pausePreview(){$('filesPreviewBody').querySelectorAll('audio,video').forEach(media=>media.pause());}
    closePreview(){this.pausePreview();$('filesPreviewBody').replaceChildren();$('filesPreview').hidden=true;delete $('filesWorkspace').dataset.preview;this.previewEntry=null;}
  }
  window.TouchHelmFiles=TouchHelmFiles;
})();
