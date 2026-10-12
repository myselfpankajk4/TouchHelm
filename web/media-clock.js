/* A sampled desktop timeline, advanced only by a confirmed playback state. */
((root) => {
  'use strict';
  const finite=value=>typeof value==='number'&&Number.isFinite(value);
  class MediaClock {
    constructor({now=()=>performance.now()}={}) {this.now=now;this.anchor=null;}
    update(media={}) {
      const item=JSON.stringify([media.session_id||media.id||media.app||'',media.title||'',media.artist||'',media.album||'',media.duration]);
      const previous=this.anchor;
      if(previous?.item===item&&finite(media.sampled_at)&&finite(previous.sampledAt)&&media.sampled_at<previous.sampledAt)return false;
      if(media.available===false||!finite(media.position)){this.anchor=null;return true;}
      const rate=finite(media.playback_rate)&&media.playback_rate>0?media.playback_rate:1;
      const playing=String(media.status||'').toLowerCase()==='playing';
      const lower=finite(media.min_seek)?Math.max(0,media.min_seek):0;
      const upper=Math.max(lower,Math.min(finite(media.duration)&&media.duration>0?media.duration:Infinity,finite(media.max_seek)?media.max_seek:Infinity));
      const fingerprint=JSON.stringify([item,media.position,media.updated_at,playing,rate,lower,upper]);
      if(previous?.fingerprint===fingerprint){previous.sampledAt=media.sampled_at;return true;}
      this.anchor={item,fingerprint,position:Math.max(lower,Math.min(upper,media.position)),time:this.now(),playing,rate,lower,upper,sampledAt:media.sampled_at};
      return true;
    }
    position() {
      if(!this.anchor)return null;
      const a=this.anchor,elapsed=a.playing?Math.max(0,this.now()-a.time)/1000*a.rate:0;
      return Math.max(a.lower,Math.min(a.upper,a.position+elapsed));
    }
  }
  root.TouchHelmMediaClock=MediaClock;
  if(typeof module!=='undefined'&&module.exports)module.exports={MediaClock};
})(typeof window==='undefined'?globalThis:window);
