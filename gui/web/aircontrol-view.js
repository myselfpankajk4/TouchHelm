/* Pure view state. Native lifecycle remains owned by the desktop service. */
((root,factory)=>{const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.TouchHelmAirView=api;})(globalThis,()=>{
  'use strict';
  function derive(s={},draft={}){
    const camera=!!s.camera_active,owned=!!s.owns_input,mode=s.profile?.mode||draft.mode||'head';
    const step=!camera?'camera':!s.calibrated?'calibrate':!s.practice_ready?'practice':'enable';
    const readiness=s.activation||{ready:!!s.practice_ready,message:s.practice_ready?'Ready to enable PC control.':'Move the practice pointer and test a click.'};
    const primary=owned?{action:s.state==='active'?'pause':'resume',label:s.state==='active'?'Pause':'Resume',disabled:false}:
      step==='camera'?{action:s.setup?.ready?'start':'setup',label:s.setup?.ready?'Start camera':'Set up AirControl',disabled:false}:
      step==='calibrate'?{action:'calibrate',label:'Capture neutral position',disabled:!(s.calibration_ready??s.tracking)}:
      step==='practice'?{action:'practice',label:'Open practice',disabled:false}:{action:'enable',label:'Enable PC control',disabled:!readiness.ready};
    return {step,primary,status:owned?(s.state==='active'?'PC control on':'PC input paused'):camera?'Practice · PC input off':'Camera off',
      modeSummary:{hand:'Hand',head:'Head & Face',combined:'Combined'}[mode],
      instruction:camera&&s.calibrated?readiness.message:camera?'Hold a comfortable neutral position, then capture it.':'Choose your camera and monitor. Start when you are ready.',scrolling:!!s.head_scroll};
  }
  return {derive};
});
