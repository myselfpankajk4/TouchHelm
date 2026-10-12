const {test}=require('node:test');
const assert=require('node:assert/strict');
const {mapPoint,gestureChoice,validateQuality}=require('../web/remote.js');
test('direct coordinates account for letterboxing, zoom and pan',()=>{
 const geometry={box:{left:0,top:0,width:300,height:300},width:1920,height:1080,scale:1,panX:0,panY:0};
 assert.equal(mapPoint(geometry,150,30),null);
 assert.deepEqual(mapPoint(geometry,150,150),{x:.5,y:.5});
 assert.deepEqual(mapPoint({...geometry,scale:2,panX:30},180,150),{x:.5,y:.5});
 assert.equal(mapPoint(geometry,Infinity,150),null);
});
test('a locked gesture cannot change from scroll to pinch',()=>{
 assert.equal(gestureChoice('scroll',1.5,50),'scroll');
 assert.equal(gestureChoice(null,1.12,25),'zoom');
 assert.equal(gestureChoice(null,1.01,20),'scroll');
 assert.equal(gestureChoice(null,1.01,2),null);
});
test('quality downgrade has a bounded floor',()=>{
 assert.equal(validateQuality('clear'),'balanced');
 assert.equal(validateQuality('balanced'),'saver');
 assert.equal(validateQuality('saver'),'saver');
});
