const {test}=require('node:test');
const assert=require('node:assert/strict');
const {derive}=require('../gui/web/aircontrol-view.js');
test('AirControl view derives setup without mutating the snapshot',()=>{
  const s={camera_active:false,setup:{ready:true},profile:{mode:'head'}};
  const original=JSON.stringify(s),v=derive(s,{});
  assert.equal(v.step,'camera');assert.equal(v.primary.action,'start');
  assert.equal(JSON.stringify(s),original);
});
test('AirControl view preserves authoritative neutral-pose guidance',()=>{
  const v=derive({camera_active:true,calibrated:true,state:'practicing',practice_ready:true,
    activation:{ready:false,code:'release_gesture',message:'Relax the held gesture.'}},{});
  assert.equal(v.step,'enable');assert.equal(v.primary.disabled,true);
  assert.equal(v.instruction,'Relax the held gesture.');
});
test('AirControl active and scroll status never imply simulated input',()=>{
  const v=derive({camera_active:true,state:'active',owns_input:true,head_scroll:true,profile:{mode:'head'}},{});
  assert.match(v.status,/PC control on/);assert.equal(v.scrolling,true);
  assert.equal(v.primary.action,'pause');
});
