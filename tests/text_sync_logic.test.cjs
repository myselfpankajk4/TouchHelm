const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
  const nodes = {}, events = {}, packets = [];
  const node = () => ({checked:true, value:'', hidden:true, textContent:'', dataset:{},
    addEventListener(name, fn) { (this.events ||= {})[name] = fn; }});
  const document = {hidden:false, activeElement:null, getElementById(id) { return nodes[id] ||= node(); },
    addEventListener(name, fn) { events[name] = fn; }};
  let opens=0,focuses=0;
  const client = {typeInput:node(), chkRealtimeTyping:node(), liveTextValue:'', isConnected:true,
    controls:{expandTyping(){opens++;},resizeTyping(){}},
    updateTypingUi() {}, send(packet) { packets.push(packet); return true; }};
  client.typeInput.focus=()=>{focuses++;};
  const window = {};
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/text-sync.js'),'utf8'), {
    window, document, localStorage:{getItem(){return null;},setItem(){}}, performance:{now(){return 30000;}}, setInterval(){},setTimeout(){},clearTimeout(){},
  });
  const sync = new window.TouchHelmTextSync(client);
  const receive = (text, revision='r1') => sync.receive({type:'text_state', available:true, field_id:'field', revision, text});
  const input = text => { client.typeInput.value = text; client.typeInput.events.input(); sync.edit(); };
  return {sync, client, packets, nodes, document, events, receive, input,get opens(){return opens;},get focuses(){return focuses;}};
}

test('temporary PC focus loss relinks a clean snapshot automatically', () => {
  const f = fixture(); f.receive('PC draft');
  f.sync.receive({type:'text_state',available:false});
  f.receive('Updated on PC','r2');
  assert.equal(f.client.typeInput.value,'Updated on PC');
  assert.equal(f.sync.conflict,false);
});

test('overlapping edits during focus loss follow the PC without blocking typing', () => {
  const f = fixture(); f.receive('PC draft');
  f.sync.receive({type:'text_state',available:false}); f.input('Phone draft'); f.receive('Other PC text');
  assert.equal(f.client.typeInput.value,'Other PC text');
  assert.equal(f.sync.conflict,false);
  assert.equal(f.packets.filter(p=>p.action==='write').length,0);
});

test('write acknowledgement during IME advances revision without replacing composition', () => {
  const f = fixture(); f.receive(''); f.input('a');
  f.client.isComposing = true; f.client.typeInput.value = 'a日本'; f.receive('a','r2');
  assert.equal(f.client.typeInput.value,'a日本');
  assert.equal(f.client.liveTextValue,'a');
  assert.equal(f.sync.field.revision,'r2');
  f.client.isComposing = false; f.sync.edit();
  assert.equal(f.packets.at(-1).revision,'r2');
  assert.equal(f.packets.at(-1).text,'a日本');
});

test('Send from a paused linked draft resumes subsequent live typing', () => {
  const f = fixture(); f.receive('PC draft');
  f.client.typeInput.value = 'Saved edit'; f.client.liveTypingPaused = true;
  f.sync.submitEnter(); f.receive('Saved edit','r2');
  assert.equal(f.client.liveTypingPaused,false);
  assert.equal(f.client.typeInput.value,'');
  assert.equal(f.packets.some(packet => packet.type==='key'),false,'Send must not submit a chat');
});

test('hiding the phone does not expose a linked baseline to native diff fallback', () => {
  const f = fixture(); f.receive('PC draft');
  f.document.hidden=true; f.events.visibilitychange(); f.document.hidden=false;
  f.input('Saved phone draft');
  assert.equal(f.sync.edit(),false);
  assert.equal(f.packets.filter(p=>p.action==='write'||p.type==='text'||p.type==='key').length,0);
});

test('an initial read timeout leaves native typing available', () => {
  const f = fixture(); f.sync.poll(); f.sync.pending.at=0; f.sync.poll();
  assert.equal(f.sync.edit(),null);
});

test('edits during the initial read merge with PC text without a relink step', () => {
  const f = fixture(); f.sync.poll(); f.input('Phone draft'); f.receive('PC draft');
  assert.equal(f.client.typeInput.value,'PC draftPhone draft');
  assert.equal(f.sync.conflict,false);
  assert.equal(f.packets.at(-1).text,'PC draftPhone draft');
});

test('an initial read racing successful native typing does not disable live input', () => {
  const f = fixture(); f.sync.poll();
  f.client.typeInput.value='New phone text';f.client.liveTextValue='New phone text';f.client.typeInput.events.input();
  f.receive('');
  assert.equal(f.sync.conflict,false);assert.equal(f.sync.edit(),null);
  f.sync.poll();f.receive('Existing PC text. New phone text','r2');
  assert.equal(f.client.typeInput.value,'Existing PC text. New phone text');
  assert.equal(f.sync.field.revision,'r2');
});

test('PC Enter with no outstanding edit sends exactly one Enter', () => {
  const f = fixture();f.receive('Synced');f.sync.submitEnter();
  assert.equal(f.packets.length,1);assert.equal(f.packets[0].key,'enter');
});

test('a lost write acknowledgement can recover automatically against the PC revision', () => {
  const f=fixture();f.receive('');f.input('Phone edit');f.sync.pending.at=0;f.sync.poll();
  f.receive('Phone edit');assert.equal(f.client.typeInput.value,'Phone edit');assert.equal(f.sync.conflict,false);
});

test('clean suspension survives several tabs and a background/foreground cycle', () => {
  const f=fixture();f.receive('PC original');
  f.sync.onView('viewMedia');f.sync.onView('viewKeyboard');
  f.document.hidden=true;f.events.visibilitychange();f.document.hidden=false;f.events.visibilitychange();
  f.sync.onView('viewTrackpad');f.receive('PC revised','r2');
  assert.equal(f.client.typeInput.value,'PC revised');assert.equal(f.sync.conflict,false);
});

test('overlapping edits between suspensions follow PC text automatically', () => {
  const f=fixture();f.receive('PC original');f.sync.onView('viewMedia');
  f.client.typeInput.value='Local changes';f.sync.onView('viewKeyboard');
  f.sync.onView('viewTrackpad');f.receive('PC revised','r2');
  assert.equal(f.client.typeInput.value,'PC revised');assert.equal(f.sync.conflict,false);
});

test('detecting a PC field opens and focuses typing once, without repeated keyboard popups', () => {
  const f=fixture();f.receive('PC text');
  assert.equal(f.opens,1);assert.equal(f.focuses,1);
  f.receive('PC revised','r2');assert.equal(f.opens,1);assert.equal(f.focuses,1);
});

test('a rejected write automatically reads again and resumes typing without recovery buttons', () => {
  const f=fixture();f.receive('hello');f.input('hello phone');
  f.sync.receive({type:'text_state',available:false,message:'PC field changed'});
  f.sync.poll();assert.equal(f.packets.at(-1).action,'read');
  f.receive('PC hello','r2');
  assert.equal(f.client.typeInput.value,'PC hello phone');
  assert.equal(f.packets.at(-1).action,'write');assert.equal(f.packets.at(-1).revision,'r2');
  assert.equal(f.sync.conflict,false);
});

test('simultaneous typing merges independent edits automatically', () => {
  const f=fixture();f.receive('hello');f.sync.poll();f.input('hello phone');
  f.receive('PC hello','r2');
  assert.equal(f.client.typeInput.value,'PC hello phone');assert.equal(f.packets.at(-1).text,'PC hello phone');
});

test('overlapping edits follow PC text automatically and leave typing usable', () => {
  const f=fixture();f.receive('hello');f.input('phone');
  f.sync.receive({type:'text_state',available:false});f.sync.poll();f.receive('PC edit','r2');
  assert.equal(f.client.typeInput.value,'PC edit');assert.equal(f.sync.conflict,false);
  f.input('PC edit!');assert.equal(f.packets.at(-1).text,'PC edit!');
});

test('new PC focus adopts its text and opens typing instead of replaying a previous draft', () => {
  const f=fixture();f.receive('First');f.input('First phone draft');
  f.sync.receive({type:'text_state',available:false});f.sync.poll();
  f.sync.receive({type:'text_state',available:true,field_id:'second',revision:'two',text:'Second'});
  assert.equal(f.client.typeInput.value,'Second');assert.equal(f.opens,2);assert.equal(f.sync.conflict,false);
  assert.equal(f.packets.filter(p=>p.action==='write'&&p.field_id==='second').length,0);
});

for(const interruption of ['timeout','background'])test('an applied write with a lost acknowledgement is not duplicated after '+interruption,()=>{
  const f=fixture();f.receive('');f.input('a');f.input('ab');
  if(interruption==='timeout'){f.sync.pending.at=0;f.sync.poll();}
  else {f.document.hidden=true;f.events.visibilitychange();f.document.hidden=false;}
  f.sync.poll();f.receive('a','r2');
  assert.equal(f.client.typeInput.value,'ab');assert.equal(f.packets.at(-1).text,'ab');
});

test('independent autocapitalization and phone append survive a PC middle insertion',()=>{
  const f=fixture();f.receive('hello world');f.sync.poll();f.input('Hello world!');
  f.receive('hello brave world','r2');
  assert.equal(f.client.typeInput.value,'Hello brave world!');
});

test('only an overlapping hunk follows PC while unrelated phone edits survive',()=>{
  const f=fixture();f.receive('hello world');f.sync.poll();f.input('Hi world!');
  f.receive('Hey world','r2');assert.equal(f.client.typeInput.value,'Hey world!');
});

test('buffered Send re-reads and retries a stale revision with Live off',()=>{
  const f=fixture();f.receive('hello');f.client.chkRealtimeTyping.checked=false;f.client.typeInput.value='hello phone';
  f.sync.submitEnter();f.sync.receive({type:'text_state',available:false});f.sync.poll();
  assert.equal(f.packets.at(-1).action,'read');f.receive('PC hello','r2');
  assert.equal(f.packets.at(-1).text,'PC hello phone');f.receive('PC hello phone','r3');
  assert.equal(f.client.typeInput.value,'');assert.equal(f.packets.filter(p=>p.type==='key').length,0);
});

test('a committed but unacknowledged write rebases further edits after PC typing',()=>{
  const f=fixture();f.receive('');f.input('a');f.input('ab');const request=f.sync.pending.request_id;
  f.sync.suspend();f.sync.poll();
  f.sync.receive({type:'text_state',available:true,field_id:'field',revision:'r2',text:'a PC',acknowledged_write:request});
  assert.equal(f.client.typeInput.value,'a PCb');
});

test('buffered Send also resumes automatically after an acknowledgement timeout',()=>{
  const f=fixture();f.receive('hello');f.client.chkRealtimeTyping.checked=false;f.client.typeInput.value='hello phone';
  f.sync.submitEnter();const request=f.sync.pending.request_id;f.sync.pending.at=0;f.sync.poll();f.sync.poll();
  assert.equal(f.packets.at(-1).action,'read');
  f.sync.receive({type:'text_state',available:true,field_id:'field',revision:'r2',text:'hello phone',acknowledged_write:request});
  assert.equal(f.client.typeInput.value,'');assert.equal(f.packets.filter(p=>p.type==='key').length,0);
});

test('Clear writes an empty linked field and keeps the baseline until PC acknowledgement',()=>{
  const f=fixture();f.receive('PC text');
  assert.equal(f.sync.clear(),true);
  assert.equal(f.client.typeInput.value,'');assert.equal(f.client.liveTextValue,'PC text');
  assert.equal(f.packets.at(-1).action,'write');assert.equal(f.packets.at(-1).text,'');
  f.receive('','r2');assert.equal(f.client.typeInput.value,'');assert.equal(f.client.liveTextValue,'');
  f.sync.poll();f.receive('','r2');assert.equal(f.client.typeInput.value,'');
});

test('Clear waits for an outstanding write and then clears its acknowledged revision',()=>{
  const f=fixture();f.receive('PC text');f.input('Phone text');f.sync.clear();
  assert.equal(f.packets.filter(p=>p.action==='write').length,1);
  f.receive('Phone text','r2');
  assert.equal(f.packets.at(-1).text,'');assert.equal(f.packets.at(-1).revision,'r2');
});

test('Clear retries after a stale read and works with Live off',()=>{
  const f=fixture();f.receive('PC text');f.client.chkRealtimeTyping.checked=false;f.sync.poll();f.sync.clear();
  f.sync.receive({type:'text_state',available:false});f.sync.poll();
  assert.equal(f.packets.at(-1).action,'read');f.receive('PC edited meanwhile','r2');
  assert.equal(f.packets.at(-1).action,'write');assert.equal(f.packets.at(-1).text,'');
  assert.equal(f.packets.at(-1).revision,'r2');
});

test('Clear never follows focus into a different PC field',()=>{
  const f=fixture();f.receive('First');f.sync.poll();f.sync.clear();
  f.sync.receive({type:'text_state',available:true,field_id:'other',revision:'r2',text:'Other field'});
  assert.equal(f.client.typeInput.value,'Other field');
  assert.equal(f.packets.filter(p=>p.action==='write'&&p.field_id==='other').length,0);
});

test('typing immediately after Clear survives the clear acknowledgement',()=>{
  const f=fixture();f.receive('PC text');f.sync.clear();f.input('Next');f.receive('','r2');
  assert.equal(f.client.typeInput.value,'Next');assert.equal(f.packets.at(-1).text,'Next');
  assert.equal(f.packets.at(-1).revision,'r2');
});

test('Clear preserves new buffered typing without sending it while Live is off',()=>{
  const f=fixture();f.receive('PC text');f.client.chkRealtimeTyping.checked=false;
  f.sync.clear();f.input('New draft');f.receive('','r2');
  assert.equal(f.client.typeInput.value,'New draft');assert.equal(f.client.liveTextValue,'');
  assert.equal(f.packets.filter(p=>p.action==='write').length,1);
});

test('Clear waits for an outstanding read and uses the latest revision of that field',()=>{
  const f=fixture();f.receive('PC text');f.sync.poll();f.sync.clear();
  assert.equal(f.packets.at(-1).action,'read');f.receive('New PC text','r2');
  assert.equal(f.packets.at(-1).text,'');assert.equal(f.packets.at(-1).revision,'r2');
});
