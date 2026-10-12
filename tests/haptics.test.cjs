const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={window:{},document:{hidden:false},navigator:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/haptics.js'),'utf8'),context);
test('haptic acceptance is not physical confirmation and repeated input is throttled',()=>{
 let calls=0,clock=100; const h=new context.window.TouchHelmHaptics({hapticsEnabled:true},{vibrate(p){calls++;return true;}},()=>clock);
 assert.equal(h.pulse(8),'accepted');assert.match(h.description(),/Did you feel/);
 assert.equal(h.pulse(8),'throttled');assert.equal(calls,1);clock+=100;assert.equal(h.pulse(8),'accepted');
});
test('haptic unsupported, disabled, activation and rejected states remain distinct',()=>{
 const H=context.window.TouchHelmHaptics;
 assert.equal(new H({hapticsEnabled:true},{}).test(),'unsupported');
 assert.equal(new H({hapticsEnabled:false},{vibrate(){throw Error('Must not run');}}).test(),'disabled');
 assert.equal(new H({hapticsEnabled:true},{vibrate(){return false;}}).test(),'rejected');
 assert.equal(new H({hapticsEnabled:true},{userActivation:{hasBeenActive:false},vibrate(){return true;}}).test(),'activation-required');
});
