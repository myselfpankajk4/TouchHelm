const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(data={},failures=0) {
  const nodes=new Map(),storage=new Map(),packets=[],requests=[],redirects=[];
  const document={addEventListener(){},getElementById(name){if(!nodes.has(name))nodes.set(name,{textContent:'',value:'',checked:false});return nodes.get(name);}};
  const window={location:{protocol:'https:',hash:'#handoff=single-use',pathname:'/',search:'',assign(url){redirects.push(url);}},TouchHelmThemes:{state:{id:'bloom',effects:'rich'},apply(id,prefs){this.state={...prefs,id};return this.state;}}};
  const context=vm.createContext({window,document,location:window.location,URL,URLSearchParams,Intl,console,history:{replaceState(){}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)},
    fetch:async(url,options)=>{requests.push({url,options});if(failures-->0)throw Error('Temporary network failure');return {ok:true,json:async()=>data};}});
  vm.runInContext(fs.readFileSync('web/experience.js','utf8'),context);
  const Client=vm.runInContext(fs.readFileSync('web/app.js','utf8')+'\nTouchHelmClient',context);
  const client=Object.create(Client.prototype);Object.assign(client,{isConnected:true,authPin:'5678',host:'pc:8765',typeInput:{value:'already sent'},liveTextValue:'already sent',chkRealtimeTyping:{checked:true},currentTheme:'bloom',newlineMode:'enter',hapticsEnabled:true,send:p=>{packets.push(JSON.parse(JSON.stringify(p)));return true;},updateTypingUi(){},showFeedback(){}});
  client.httpBase=()=> 'http://pc:8765';
  const experience=Object.create(window.TouchHelmExperience.prototype);experience.client=client;experience.cacheTheme=()=>{};
  return {experience,client,requests,redirects,packets,storage};
}
test('handoff request binds the secure target and carries live synchronization baseline',async()=>{
  const {experience,requests,redirects}=setup({token:'opaque-token',target_origin:'https://pc.example.ts.net:8443'});
  await experience.secureHandoff('https://pc.example.ts.net:8443/');
  const body=JSON.parse(requests[0].options.body);
  assert.equal(body.target_origin,'https://pc.example.ts.net:8443');assert.equal(body.live_baseline,'already sent');assert.equal(body.preferences.live_typing,true);assert.equal(body.preferences.effects,'rich');
  assert.equal(new URL(redirects[0]).origin,body.target_origin);
});
test('consuming a secure draft does not replay text and subsequent input sends only the new suffix',async()=>{
  const {experience,client,packets,storage,requests}=setup({draft:'already sent',live_baseline:'already sent',preferences:{live_typing:true,theme:'bloom',effects:'rich'}});
  await experience.consumeHandoff();assert.equal(packets.length,0);assert.equal(client.liveTextValue,'already sent');assert.equal(storage.get('touchhelm_live_typing'),'true');
  assert.equal(requests[0].options.headers['X-TouchHelm-Pin'],'5678');
  client.typeInput.value='already sent!';client.syncLiveText();assert.deepEqual(packets,[{type:'text',text:'!'}]);
});

test('a temporary handoff failure can retry without duplicate restoration or input',async()=>{
  const {experience,client,packets,requests}=setup({draft:'kept',live_baseline:'kept'},1);
  await experience.consumeHandoff();assert.equal(experience.handoffConsumed,undefined);assert.equal(experience.handoffInFlight,false);
  await experience.consumeHandoff();assert.equal(client.typeInput.value,'kept');assert.equal(experience.handoffConsumed,true);
  await experience.consumeHandoff();assert.equal(requests.length,2);assert.equal(packets.length,0);
});
