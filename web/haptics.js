/* Haptics report API acceptance, never pretend to observe physical vibration. */
(() => {
  class TouchHelmHaptics {
    constructor(client, navigatorObject=navigator, now=()=>Date.now()) {
      this.client=client; this.navigator=navigatorObject; this.now=now; this.last=-Infinity;
      this.result='untested';
    }
    pulse(pattern=22, force=false) {
      if (!this.client.hapticsEnabled) return this.result='disabled';
      if (typeof this.navigator.vibrate!=='function') return this.result='unsupported';
      if (typeof document!=='undefined' && document.hidden) return this.result='background';
      if (this.navigator.userActivation && !this.navigator.userActivation.hasBeenActive) return this.result='activation-required';
      if (!force && this.now()-this.last<90) return this.result='throttled';
      const bounded=Array.isArray(pattern)?pattern.slice(0,9).map(x=>Math.max(0,Math.min(250,Number(x)||0))):Math.max(18,Math.min(250,Number(pattern)||22));
      try { this.last=this.now(); return this.result=this.navigator.vibrate(bounded)?'accepted':'rejected'; }
      catch { return this.result='rejected'; }
    }
    test() { return this.pulse([60,70,60],true); }
    cancel() { try { this.navigator.vibrate?.(0); } catch {} }
    description() {
      return {accepted:'Vibration request accepted. Did you feel two pulses? If not, check system vibration and Do Not Disturb settings.',
        rejected:'The browser declined vibration. Check device vibration settings and try again.',
        unsupported:'This browser does not support vibration. Button press feedback remains visible.',
        disabled:'Vibration is turned off. Enable Touch vibration to test.',
        'activation-required':'Tap Test vibration after interacting with this page.',background:'Vibration is paused while the page is hidden.'}[this.result] || 'Tap Test vibration to check this device.';
    }
  }
  window.TouchHelmHaptics=TouchHelmHaptics;
})();
