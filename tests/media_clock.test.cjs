const test = require('node:test');
const assert = require('node:assert/strict');
const {MediaClock} = require('../web/media-clock.js');

function fixture() {
  let time=0;
  const clock=new MediaClock({now:()=>time});
  const media={available:true,session_id:'one',title:'Video',status:'Playing',position:240,duration:900,min_seek:0,max_seek:900,updated_at:100};
  return {clock,media,advance:ms=>time+=ms};
}
test('playing without a supplied rate advances at effective 1x',()=>{
  const {clock,media,advance}=fixture();clock.update(media);advance(5000);
  assert.equal(clock.position(),245);assert.equal(media.playback_rate,undefined);
});
test('repeated unchanged snapshots do not restart the playback anchor',()=>{
  const {clock,media,advance}=fixture();clock.update(media);advance(2000);clock.update({...media});advance(3000);
  assert.equal(clock.position(),245);
});
test('sampled positions use their received monotonic anchor and reject older snapshots',()=>{
  const {clock,media,advance}=fixture();clock.update({...media,sampled_at:100});advance(2000);
  clock.update({...media,position:242,sampled_at:102});advance(1000);
  assert.equal(clock.update({...media,position:200,sampled_at:101}),false);
  assert.equal(clock.position(),243);
});
test('pause, resume and rate changes establish actual new anchors',()=>{
  const {clock,media,advance}=fixture();clock.update(media);advance(2000);
  clock.update({...media,status:'Paused',position:242});advance(2000);assert.equal(clock.position(),242);
  clock.update({...media,position:242,playback_rate:2});advance(1000);assert.equal(clock.position(),244);
});
test('actual external seek and a new item replace the preceding timeline',()=>{
  const {clock,media,advance}=fixture();clock.update(media);advance(1000);
  clock.update({...media,position:30,updated_at:101});assert.equal(clock.position(),30);
  clock.update({...media,title:'Next video',position:0,updated_at:90});advance(1000);assert.equal(clock.position(),1);
});
test('timeline respects seek bounds and unavailable state',()=>{
  const {clock,media,advance}=fixture();clock.update({...media,position:895,max_seek:897});advance(5000);assert.equal(clock.position(),897);
  clock.update({available:false,status:'unavailable'});assert.equal(clock.position(),null);
});
