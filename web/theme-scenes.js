/* Generative theme scenes: fragment shaders for the TouchHelm WebGL backdrop.
   Pure data (GLSL text plus fallback palettes). theme-gl.js compiles and drives them. */
(function(global){
  'use strict';
  const PRELUDE=`
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
#define N __N__
#define PI 3.14159265
uniform vec2 uRes;
uniform float uTime,uDark,uDarkPrev,uAmp,uPlay,uConn,uType,uScroll,uFade,uSeed;
uniform vec3 uPointer,uReveal,uBg,uBgPrev,uA,uB,uC;
uniform vec4 uStamps[N];
float asp;
float amp;
vec3 cA;vec3 cB;vec3 cC;
float sq(float x){return x*x;}
float hash21(vec2 p){vec3 p3=fract(vec3(p.xyx)*.1031);p3+=dot(p3,p3.yzx+33.33);return fract((p3.x+p3.y)*p3.z);}
vec2 hash22(vec2 p){vec3 p3=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));p3+=dot(p3,p3.yzx+33.33);return fract((p3.xx+p3.yz)*p3.zy);}
float vnoise(vec2 p){vec2 i=floor(p);vec2 f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash21(i),hash21(i+vec2(1.,0.)),f.x),mix(hash21(i+vec2(0.,1.)),hash21(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float a=.5;float s=0.;for(int i=0;i<4;i++){s+=a*vnoise(p);p=p*2.03+17.1;a*=.5;}return s;}
vec3 desat(vec3 c){return mix(vec3(dot(c,vec3(.299,.587,.114))),c,.3+.7*uConn);}
/* Dark: restrained additive glow. Light: pastel wash toward the accent, so text keeps its contrast. */
vec3 paint(vec3 base,vec3 c,float k,float dark){
  vec3 add=base+c*k;
  vec3 wash=mix(base,c,clamp(k*.6,0.,.85));
  return mix(wash,add,dark);
}
`;
  const MAIN=`
void main(){
  asp=uRes.x/uRes.y;
  vec2 uv=gl_FragCoord.xy/uRes;
  vec2 p=vec2(uv.x*asp,uv.y);
  cA=desat(uA);cB=desat(uB);cC=desat(uC);
  amp=uAmp*(.6+.4*uConn);
  float dark=uDark;vec3 bg=uBg;float rim=0.;
  if(uReveal.z>0.){
    float d=length(p-vec2(uReveal.x*asp,uReveal.y));
    float inside=1.-smoothstep(uReveal.z-.015,uReveal.z+.015,d);
    dark=mix(uDarkPrev,uDark,inside);bg=mix(uBgPrev,uBg,inside);
    rim=exp(-sq((d-uReveal.z)*22.));
  }
  vec3 col=scene(p,uv,dark,bg);
  col=mix(bg,col,uFade);
  col=paint(col,cA,rim*.85,dark);
  col+=(hash21(gl_FragCoord.xy+uTime)-.5)/255.;
  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

  /* Stamp layout: xy = position (0..1, y up), z = age in seconds (<0 = unused), w = kind + seed fraction.
     kind 0 tap, 1 key, 2 button, 3 drag trail, 4 success. */

  const aurora=`
vec3 scene(vec2 p,vec2 uv,float dark,vec3 bg){
  float t=uTime*(.045+.03*uPlay)+uSeed;
  vec2 pp=vec2(uPointer.x*asp,uPointer.y);
  vec2 q=p;
  vec2 dv=p-pp;float dl=length(dv)+1e-3;
  q+=dv/dl*.06*uPointer.z*exp(-dl*2.6);
  float ring=0.;
  for(int i=0;i<N;i++){
    vec4 s=uStamps[i];
    if(s.z<0.)continue;
    vec2 d=p-vec2(s.x*asp,s.y);float l=length(d)+1e-3;
    float f=exp(-sq((l-s.z*.5)/.11))*exp(-s.z*1.2);
    q+=d/l*f*.055;
    ring+=f;
  }
  ring=min(ring,1.5);
  vec3 col=bg;
  for(int k=0;k<3;k++){
    float fk=float(k);
    float x=q.x*(1.1+.3*fk)+fk*5.3;
    float n=fbm(vec2(x+t*(1.+.35*fk),fk*3.1+t*.7));
    float cy=.30+.2*fk+(n-.5)*.7+sin(q.x*2.3+t*3.+fk*2.1)*.04+uScroll*.04;
    float h=q.y-cy;
    float prof=h<0.?exp(-h*h*480.):exp(-h*3.4);
    float streak=.5+.5*vnoise(vec2(q.x*(20.+7.*fk)+fk*9.,t*4.+fk*2.));
    streak=mix(1.,streak,smoothstep(0.,.3,h));
    float inten=prof*(.4+.85*streak)*(.55+.3*uPlay+.3*ring)*(1.-.2*fk);
    vec3 c=mix(mix(cA,cB,smoothstep(-.1,.4,h)),cC,fk*.5);
    col=paint(col,c,inten*amp,dark);
  }
  vec2 sg=p*64.;vec2 si=floor(sg);float sr=hash21(si);
  float sd=length(fract(sg)-hash22(si));
  float star=step(.94,sr)*exp(-sd*sd*380.)*(.45+.55*sin(uTime*(1.+sr*3.)+sr*40.))*(.5+uType);
  col+=vec3(.9,.95,1.)*star*dark*.55*amp;
  return col;
}
`;

  const bloom=`
vec3 flower(vec3 col,vec2 p,vec4 s,float dark){
  float kind=floor(s.w);float seed=fract(s.w);float age=s.z;
  float R=kind<.5?.13:(kind<1.5?.075:(kind<2.5?.105:(kind<3.5?.05:.19)));
  R*=.8+.4*fract(seed*7.3);
  vec2 d=p-vec2(s.x*asp,s.y);float l=length(d);
  if(l>R*1.6)return col;
  float life=(kind>2.5&&kind<3.5)?3.2:9.;
  float fade=1.-smoothstep(life*.45,life,age);
  float open=clamp(1.-exp(-age*5.5)*cos(age*10.),0.,1.12)*(1.+.05*uPlay*sin(uTime*5.+seed*6.));
  float n=5.+floor(seed*3.9);
  float a=atan(d.y,d.x)+seed*6.283+age*.3;
  float pr=R*open*(.42+.58*pow(abs(cos(a*n*.5)),.7));
  float body=1.-smoothstep(pr-.006,pr,l);
  float depth=l/max(pr,1e-3);
  vec3 pc=mix(cA,cB,fract(seed*3.7));
  col=paint(col,pc,exp(-sq(l/(R*1.15)))*.32*fade*amp,dark);
  col=paint(col,pc,body*(.5+.5*(1.-depth))*1.05*fade*amp,dark);
  col=paint(col,mix(pc,cC,.5),body*smoothstep(.72,.97,depth)*.5*fade*amp,dark);
  col=paint(col,cC,(1.-smoothstep(R*.12*open,R*.2*open,l))*1.2*fade,dark);
  return col;
}
vec3 scene(vec2 p,vec2 uv,float dark,vec3 bg){
  float t=uTime*(.05+.04*uPlay)+uSeed;
  vec2 pp=vec2(uPointer.x*asp,uPointer.y);
  vec3 leaf=vec3(.30,.72,.45);
  vec3 col=bg;
  float lf=fbm(p*2.4+vec2(t*.5,-t*.3));
  col=paint(col,leaf,smoothstep(.42,.9,lf)*.3*amp,dark);
  for(int L=0;L<2;L++){
    float fl=float(L);
    float S=6.+5.*fl;
    vec2 g=p*S;vec2 id=floor(g);vec2 f=g-id;
    vec2 rnd=hash22(id+fl*13.7);
    vec2 off=(rnd-.5)*.24+.08*vec2(sin(t*6.*(1.+rnd.x)+rnd.y*6.283),cos(t*5.*(1.+rnd.y)+rnd.x*6.283));
    vec2 node=vec2(.5)+off;
    vec2 toP=pp*S-(id+node);
    float near=1.-smoothstep(0.,3.5,length(toP));
    node+=clamp(toP*.35,-.14,.14)*uPointer.z*near;
    float d=length(f-node);
    float tw=.5+.5*sin(uTime*(1.+uType*3.)*(1.5+rnd.x*2.)+rnd.y*40.);
    float fly=exp(-d*d*(260.+120.*fl))*(.35+.65*tw)*(.6+.7*near*uPointer.z+.8*uType);
    col=paint(col,cC,fly*.75*amp,dark);
  }
  col=paint(col,cC,exp(-sq(length(p-pp)*6.))*uPointer.z*.3*amp,dark);
  for(int i=0;i<N;i++){
    vec4 s=uStamps[i];
    if(s.z<0.)continue;
    col=flower(col,p,s,dark);
  }
  return col;
}
`;

  const resonance=`
vec3 scene(vec2 p,vec2 uv,float dark,vec3 bg){
  float t=uTime*.18+uSeed;
  float n=2.4+4.8*uPointer.x+.5*sin(t*.9)+uType*.6*sin(uTime*7.);
  float m=3.1+4.8*uPointer.y+.5*cos(t*.77);
  vec2 q=p*PI;
  float rip=0.;
  for(int i=0;i<N;i++){
    vec4 s=uStamps[i];
    if(s.z<0.)continue;
    float l=length(p-vec2(s.x*asp,s.y));
    rip+=sin(l*38.-s.z*9.)*exp(-s.z*1.3)*exp(-l*2.2);
  }
  float pulse=1.+.3*uPlay*sin(uTime*6.3);
  float f=(cos(n*q.x)*cos(m*q.y)+cos(m*q.x)*cos(n*q.y))*.5*pulse+rip*.45;
  float w=.09+.05*uPlay;
  float line=1.-smoothstep(0.,w,abs(f));
  float glow=exp(-abs(f)*6.);
  float grain=.6+.4*vnoise(p*210.);
  vec3 c=mix(cA,cB,smoothstep(.2,.8,vnoise(p*3.+t)));
  vec3 col=bg;
  col=paint(col,cC,glow*.22*amp,dark);
  col=paint(col,c,line*grain*.95*amp,dark);
  return col;
}
`;

  const constellation=`
vec2 nodeAt(vec2 id,float t){vec2 n=hash22(id);return .5+.4*sin(t*(.4+n.yx*.7)+n*6.2831);}
float seg(vec2 p,vec2 a,vec2 b){vec2 pa=p-a;vec2 ba=b-a;float h=clamp(dot(pa,ba)/dot(ba,ba),0.,1.);return length(pa-ba*h);}
float link(vec2 p,vec2 a,vec2 b,float reach){
  float len=length(a-b);
  float m=1.-smoothstep(0.,.035,seg(p,a,b));
  return m*(1.-smoothstep(reach*.5,reach,len));
}
vec3 scene(vec2 p,vec2 uv,float dark,vec3 bg){
  float t=uTime*(.5+.4*uPlay)+uSeed;
  float S=7.;
  vec2 pp=vec2(uPointer.x*asp,uPointer.y);
  vec2 g=p*S;vec2 id=floor(g);vec2 f=g-id;
  vec2 pc=pp*S-id;
  vec2 pts[9];
  float twk[9];
  for(int y=-1;y<=1;y++){
    for(int x=-1;x<=1;x++){
      vec2 o=vec2(float(x),float(y));
      vec2 pt=o+nodeAt(id+o,t);
      vec2 tp=pc-pt;
      pt+=tp*uPointer.z*.45*(1.-smoothstep(0.,3.,length(tp)));
      pts[(y+1)*3+(x+1)]=pt;
      twk[(y+1)*3+(x+1)]=hash21(id+o);
    }
  }
  float lines=0.;float nodes=0.;float tolink=0.;
  for(int i=0;i<9;i++){
    if(i==4)continue;
    lines+=link(f,pts[4],pts[i],1.2);
    tolink+=link(f,pc,pts[i],2.4);
  }
  lines+=link(f,pts[1],pts[3],1.2)+link(f,pts[1],pts[5],1.2)+link(f,pts[7],pts[3],1.2)+link(f,pts[7],pts[5],1.2);
  for(int i=0;i<9;i++){
    float d=length(f-pts[i]);
    float tw=.6+.4*sin(uTime*(1.+twk[i]*2.)*(1.+uPlay*1.5)+twk[i]*30.);
    nodes+=(1.-smoothstep(.035,.085,d))*tw;
  }
  float pulse=0.;
  for(int i=0;i<N;i++){
    vec4 s=uStamps[i];
    if(s.z<0.)continue;
    float d=length(p-vec2(s.x*asp,s.y));
    pulse+=exp(-sq((d-s.z*.65)/.09))*exp(-s.z*.8);
  }
  float ptr=uPointer.z*exp(-sq(length(p-pp)*3.2));
  float wave=min(pulse+ptr*.8+uType*.35*(.5+.5*sin(p.x*9.-uTime*14.)),2.);
  vec3 lc=mix(cA,cB,uv.x);
  vec3 col=bg;
  col=paint(col,lc,min(lines,1.5)*(.2+.9*wave)*.6*amp,dark);
  col=paint(col,lc,min(tolink,1.)*uPointer.z*.8*amp,dark);
  col=paint(col,cC,min(nodes,1.5)*(.55+.9*wave)*amp,dark);
  col=paint(col,cC,ptr*.25*amp,dark);
  return col;
}
`;

  const palette=(bg,a,b,c)=>Object.freeze({bg,a,b,c});
  const scenes={
    aurora:{source:aurora,defaults:{dark:palette('#0b1220','#34e0b4','#7a7cff','#ff7ad9'),light:palette('#eef5f7','#19b89a','#7b7dff','#ff8ad8')}},
    bloom:{source:bloom,defaults:{dark:palette('#0e1e19','#ff8fab','#ffb870','#ffe08a'),light:palette('#f2f5eb','#f0728f','#f39a4a','#f5c63c')}},
    resonance:{source:resonance,defaults:{dark:palette('#130f1c','#ffb454','#ff6f91','#6fd4ff'),light:palette('#f6efe3','#e8892b','#e0527a','#2a9fd0')}},
    constellation:{source:constellation,defaults:{dark:palette('#070b16','#6a9bff','#b087ff','#5af0d0'),light:palette('#eef1fa','#4a78e8','#8f63e8','#14a98a')}},
  };
  /* Fragment uniform vectors are scarce on old phones: spend them on stamps only when there is room. */
  const stampCount=maxVectors=>maxVectors>=64?12:maxVectors>=32?8:4;
  const fragmentSource=(id,stamps)=>{
    const scene=Object.prototype.hasOwnProperty.call(scenes,id)?scenes[id]:null;if(!scene)return null;
    return PRELUDE.replace('__N__',String(stamps))+scene.source+MAIN;
  };
  global.TouchHelmScenes=Object.freeze({ids:Object.freeze(Object.keys(scenes)),scenes,stampCount,fragmentSource});
})(typeof window==='undefined'?globalThis:window);
