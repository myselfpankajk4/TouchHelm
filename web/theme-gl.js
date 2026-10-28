/* Generative WebGL backdrop for the themes. Decoration only: it never takes input, never talks to the
   network and stays out of the way (low-power context, low render scale, paused when hidden).
   Input only moves the picture (position and timing); key identity and typed text are never read.
   Scene shaders live in theme-scenes.js; themes.js selects them through [data-theme]. */
(() => {
  'use strict';
  const root = document.documentElement;
  const Scenes = window.TouchHelmScenes;
  if (!Scenes || window.TouchHelmEffects) return;

  const KIND = {tap: 0, key: 1, button: 2, trail: 3, success: 4};
  const LIFE = [9, 9, 9, 3.2, 9];
  const INTERACTIVE = 'button,[role="button"],[role="tab"],a[href],summary,select,label,.native-key,.nav-tab,[data-key]';
  const KEYISH = '.native-key,[data-key],.keyboard-container,.native-numpad';
  const IGNORED_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'AltGraph', 'Tab', 'Escape', 'ContextMenu']);
  const UNIFORMS = ['uRes', 'uTime', 'uDark', 'uDarkPrev', 'uAmp', 'uPlay', 'uConn', 'uType', 'uScroll', 'uFade', 'uSeed',
    'uPointer', 'uReveal', 'uBg', 'uBgPrev', 'uA', 'uB', 'uC', 'uStamps'];
  const COLOR_KEYS = ['bg', 'a', 'b', 'c'];
  const VERT = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}';
  const MIN_SCALE = .28, MAX_SCALE = .7, MAX_PIXELS = 600000;
  const FROZEN_TIME = 4;

  const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
  const ease = t => 1 - Math.pow(1 - t, 3);
  const rand = Math.random;

  const canvas = document.createElement('canvas');
  canvas.id = 'th-gl';
  canvas.setAttribute('aria-hidden', 'true');

  const S = {
    gl: null, buffer: null, programs: new Map(), failed: new Set(), current: null, stampN: 4, stampData: null,
    scene: null, dark: null, mode: 'rich', frozen: false, suspended: false, lost: false, enabled: false, destroyed: false,
    stampList: [], next: 0, scale: window.matchMedia?.('(pointer: coarse)').matches ? .45 : .5,
    cssW: 0, cssH: 0, resizeDirty: true, still: true,
    time: 0, last: 0, lastRender: 0, raf: 0, load: 1, cool: 60, good: 0,
    px: .5, py: .5, tx: .5, ty: .5, strength: 0, held: new Set(), hoverUntil: 0, trailOK: false, trail: {x: -999, y: -999, t: 0},
    type: 0, scroll: 0, play: 0, playT: 0, conn: 1, connT: 1, lastKey: 0, lastKeyDown: 0, tops: new WeakMap(),
    seed: rand() * 40, fadeT0: 0, fade: 1, reveal: null, darkPrev: 0, bgPrev: [0, 0, 0],
    colors: null, colorSig: '',
  };

  const parseColor = text => {
    const s = (text || '').trim();
    let m = /^#([0-9a-f]{3})$/i.exec(s);
    if (m) return [...m[1]].map(h => parseInt(h + h, 16) / 255);
    m = /^#([0-9a-f]{6})/i.exec(s);
    if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16) / 255);
    m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/i.exec(s);
    if (m) return [m[1], m[2], m[3]].map(v => clamp(+v / 255, 0, 1));
    return null;
  };
  const copyColors = c => Object.fromEntries(COLOR_KEYS.map(k => [k, c[k].slice()]));

  /* ---- GL setup ---- */
  function buildBuffer() {
    const gl = S.gl;
    S.buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, S.buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  }
  function initGL() {
    if (S.gl) return !S.lost;
    const options = {alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'low-power'};
    let gl = null;
    try { gl = canvas.getContext('webgl', options) || canvas.getContext('experimental-webgl', options); } catch (_) { /* Falls back to CSS. */ }
    if (!gl) return false;
    S.gl = gl;
    S.stampN = Scenes.stampCount(gl.getParameter(gl.MAX_FRAGMENT_UNIFORM_VECTORS));
    S.stampData = new Float32Array(S.stampN * 4);
    S.stampList = new Array(S.stampN).fill(null);
    buildBuffer();
    return true;
  }
  function compile(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(log || 'shader compile failed');
    }
    return shader;
  }
  function program(id) {
    if (S.programs.has(id)) return S.programs.get(id);
    if (S.failed.has(id) || !S.gl) return null;
    const gl = S.gl;
    try {
      const source = Scenes.fragmentSource(id, S.stampN);
      if (!source) throw new Error('unknown scene');
      const vs = compile(gl, gl.VERTEX_SHADER, VERT), fs = compile(gl, gl.FRAGMENT_SHADER, source);
      const p = gl.createProgram();
      gl.attachShader(p, vs); gl.attachShader(p, fs);
      gl.bindAttribLocation(p, 0, 'a');
      gl.linkProgram(p);
      gl.deleteShader(vs); gl.deleteShader(fs);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'link failed');
      const entry = {p, u: Object.fromEntries(UNIFORMS.map(name => [name, gl.getUniformLocation(p, name)]))};
      S.programs.set(id, entry);
      return entry;
    } catch (error) {
      S.failed.add(id);
      console.warn(`TouchHelm theme scene "${id}" unavailable: ${error.message}`);
      return null;
    }
  }

  /* ---- colours: theme CSS supplies --th-bg and --th-gl-a/b/c; scene defaults fill gaps ---- */
  function readColors(id, dark) {
    const style = getComputedStyle(root), defaults = Scenes.scenes[id].defaults[dark ? 'dark' : 'light'];
    const pick = (prop, fallback) => parseColor(style.getPropertyValue(prop)) || parseColor(fallback);
    return {bg: pick('--th-bg', defaults.bg), a: pick('--th-gl-a', defaults.a), b: pick('--th-gl-b', defaults.b), c: pick('--th-gl-c', defaults.c)};
  }
  function setColors(next, {snap = false, snapBg = false} = {}) {
    const sig = COLOR_KEYS.map(k => next[k].join(',')).join('|');
    if (S.colors && sig === S.colorSig) return false;
    S.colorSig = sig;
    if (!S.colors || snap) {
      S.colors = {cur: copyColors(next), from: copyColors(next), to: next, t0: -1e9};
      return true;
    }
    S.colors.from = copyColors(S.colors.cur);
    S.colors.to = next;
    S.colors.t0 = performance.now();
    if (snapBg) { S.colors.cur.bg = next.bg.slice(); S.colors.from.bg = next.bg.slice(); }
    return true;
  }
  function stepColors(now) {
    const c = S.colors, k = S.frozen ? 1 : ease(clamp((now - c.t0) / 600, 0, 1));
    for (const key of COLOR_KEYS) for (let i = 0; i < 3; i++) c.cur[key][i] = c.from[key][i] + (c.to[key][i] - c.from[key][i]) * k;
  }

  /* ---- sizing and governor ---- */
  function resize() {
    const gl = S.gl;
    if (!gl) return;
    const cw = root.clientWidth || window.innerWidth, ch = window.innerHeight;
    const scale = Math.min(S.scale, Math.sqrt(MAX_PIXELS / Math.max(1, cw * ch)));
    const w = Math.max(2, Math.round(cw * scale)), h = Math.max(2, Math.round(ch * scale));
    S.cssW = cw; S.cssH = ch; S.resizeDirty = false;
    if (w === canvas.width && h === canvas.height) return;
    canvas.width = w; canvas.height = h;
    gl.viewport(0, 0, w, h);
    S.still = true;
  }
  function govern(ratio) {
    S.load = S.load * .9 + ratio * .1;
    if (S.cool > 0) { S.cool--; return; }
    if (S.load > 1.5 && S.scale > MIN_SCALE) {
      S.scale = Math.max(MIN_SCALE, S.scale * .85); S.cool = 40; S.load = 1; S.good = 0; S.resizeDirty = true;
    } else if (S.load < 1.12 && S.scale < MAX_SCALE) {
      if (++S.good > 240) { S.scale = Math.min(MAX_SCALE, S.scale * 1.08); S.good = 0; S.cool = 40; S.resizeDirty = true; }
    } else S.good = 0;
  }

  /* ---- stamps: where the visitor touched, pressed or typed ---- */
  function addStamp(nx, ny, kind) {
    if (!S.enabled || S.frozen || S.suspended) return false;
    S.stampList[S.next++ % S.stampN] = {x: clamp(nx, 0, 1), y: clamp(ny, 0, 1), t0: performance.now(), kind, seed: rand() * .97, life: LIFE[kind]};
    kick();
    return true;
  }
  const norm = (x, y) => [x / (S.cssW || window.innerWidth), 1 - y / (S.cssH || window.innerHeight)];
  function stampAtElement(el, kind, along = false) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) return false;
    const cx = along ? r.left + r.width * (.15 + .7 * rand()) : r.left + r.width / 2;
    const [nx, ny] = norm(cx, r.top + r.height / 2);
    return addStamp(nx, ny, kind);
  }

  /* ---- drawing ---- */
  function isActive(now) {
    return S.reveal || S.fade < 1 || S.strength > .02 || S.type > .02 || Math.abs(S.scroll) > .02 || S.stampList.some(Boolean);
  }
  function render(now, dt) {
    const gl = S.gl, entry = S.programs.get(S.scene);
    if (!gl || !entry || !S.colors) return;
    const {u} = entry, calm = S.mode === 'calm' || S.frozen;
    if (S.current !== entry) { gl.useProgram(entry.p); S.current = entry; }
    const k = rate => 1 - Math.exp(-dt * rate);
    if (S.frozen) { S.time = FROZEN_TIME; S.strength = 0; S.play = 0; S.type = 0; S.scroll = 0; S.conn = S.connT; S.fade = 1; }
    else {
      S.time += dt * (calm ? .6 : 1);
      S.px += (S.tx - S.px) * k(14); S.py += (S.ty - S.py) * k(14);
      const target = Math.max(S.held.size ? 1 : 0, now < S.hoverUntil ? .35 : 0);
      S.strength += (target - S.strength) * k(target > S.strength ? 12 : 2.5);
      S.play += (S.playT - S.play) * k(2.5); S.conn += (S.connT - S.conn) * k(3);
      S.type *= Math.exp(-dt * 2.4); S.scroll *= Math.exp(-dt * 1.6);
      S.fade = ease(clamp((now - S.fadeT0) / 700, 0, 1));
    }
    stepColors(now);
    const aspect = S.cssW / S.cssH;
    let rev = -1;
    if (S.reveal) {
      const t = (now - S.reveal.t0) / 900;
      if (t >= 1) S.reveal = null; else rev = Math.max(.0001, ease(t) * (Math.hypot(aspect, 1) + .08));
    }
    const data = S.stampData;
    for (let i = 0; i < S.stampN; i++) {
      const s = S.stampList[i];
      let age = -1;
      if (s && !S.frozen) {
        age = (now - s.t0) / 1000;
        if (age > s.life) { S.stampList[i] = null; age = -1; }
      }
      data[i * 4] = s ? s.x : 0; data[i * 4 + 1] = s ? s.y : 0; data[i * 4 + 2] = age; data[i * 4 + 3] = s ? s.kind + s.seed : 0;
    }
    const c = S.colors.cur, dark = S.dark ? 1 : 0;
    gl.uniform2f(u.uRes, canvas.width, canvas.height);
    gl.uniform1f(u.uTime, S.time);
    gl.uniform1f(u.uDark, dark);
    gl.uniform1f(u.uDarkPrev, S.darkPrev);
    gl.uniform1f(u.uAmp, calm ? .5 : 1);
    gl.uniform1f(u.uPlay, S.play);
    gl.uniform1f(u.uConn, S.conn);
    gl.uniform1f(u.uType, Math.min(S.type, 1.2));
    gl.uniform1f(u.uScroll, clamp(S.scroll, -1.5, 1.5));
    gl.uniform1f(u.uFade, S.fade);
    gl.uniform1f(u.uSeed, S.seed);
    gl.uniform3f(u.uPointer, S.px, S.py, S.strength);
    gl.uniform3f(u.uReveal, S.reveal ? S.reveal.x : .5, S.reveal ? S.reveal.y : .5, rev);
    gl.uniform3fv(u.uBg, c.bg); gl.uniform3fv(u.uBgPrev, S.bgPrev);
    gl.uniform3fv(u.uA, c.a); gl.uniform3fv(u.uB, c.b); gl.uniform3fv(u.uC, c.c);
    gl.uniform4fv(u.uStamps, data);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    S.still = false;
  }
  function frame(now) {
    S.raf = 0;
    if (!canRun()) return;
    if (S.resizeDirty) resize();
    if (S.frozen) { render(now, 0); return; }
    const active = isActive(now), interval = active ? 15 : 32, since = now - S.lastRender;
    if (since < interval - 1) { S.raf = requestAnimationFrame(frame); return; }
    const dt = Math.min(.1, (now - (S.last || now)) / 1000);
    if (S.last && since < 200) govern(since / (active ? 16.7 : 33.3));
    S.last = now; S.lastRender = now;
    render(now, dt);
    S.raf = requestAnimationFrame(frame);
  }
  const canRun = () => S.enabled && !S.suspended && !S.lost && !document.hidden && !S.destroyed;
  function kick() {
    if (S.raf || !canRun()) return;
    S.last = 0;
    S.raf = requestAnimationFrame(frame);
  }
  function stop() {
    if (S.raf) cancelAnimationFrame(S.raf);
    S.raf = 0; S.last = 0;
  }
  function disable(state) {
    S.enabled = false; S.scene = null; S.dark = null; S.reveal = null;
    stop();
    root.dataset.gl = state;
  }

  /* ---- theme / appearance / preference changes ---- */
  function synchronize() {
    if (S.destroyed) return;
    const d = root.dataset, id = d.theme, effects = d.effects || 'rich', dark = d.appearance === 'dark';
    S.frozen = d.motion === 'reduced';
    S.mode = effects;
    S.playT = d.playing === 'true' ? 1 : 0;
    S.connT = d.connected === 'false' ? .55 : 1;
    if (!Scenes.ids.includes(id) || effects === 'off') { disable('off'); return; }
    if (!initGL() || !program(id)) { disable('fallback'); return; }
    const now = performance.now(), sceneChanged = S.scene !== id, wasDark = S.dark;
    const next = readColors(id, dark);
    if (sceneChanged) {
      S.seed = rand() * 40;
      S.fadeT0 = now;
      S.fade = S.frozen ? 1 : 0;
      S.scene = id;
      setColors(next, {snap: !S.enabled || !S.colors});
    } else if (wasDark !== null && wasDark !== dark && !S.frozen && S.colors) {
      S.darkPrev = wasDark ? 1 : 0;
      S.bgPrev = S.colors.cur.bg.slice();
      S.reveal = {x: S.px, y: S.py, t0: now};
      setColors(next, {snapBg: true});
    } else setColors(next, {snap: S.frozen});
    S.dark = dark;
    S.enabled = true;
    root.dataset.gl = 'on';
    S.resizeDirty = true;
    S.still = true;
    kick();
  }

  /* ---- input: position and timing only ---- */
  function onPointerDown(e) {
    if (!S.enabled || S.frozen) return;
    const [nx, ny] = norm(e.clientX, e.clientY);
    S.tx = nx; S.ty = ny;
    if (S.strength < .05) { S.px = nx; S.py = ny; }
    S.held.add(e.pointerId);
    const target = e.target instanceof Element ? e.target.closest(INTERACTIVE) : null;
    S.trailOK = !target;
    S.trail = {x: e.clientX, y: e.clientY, t: performance.now()};
    if (target) {
      if (target.matches(KEYISH) || target.closest(KEYISH)) S.type = Math.min(1.2, S.type + .4);
      stampAtElement(target, target.matches(KEYISH) || target.closest(KEYISH) ? KIND.key : KIND.button);
    } else addStamp(nx, ny, KIND.tap);
    kick();
  }
  function onPointerMove(e) {
    if (!S.enabled || S.frozen) return;
    const [nx, ny] = norm(e.clientX, e.clientY);
    S.tx = nx; S.ty = ny;
    if (e.pointerType === 'mouse' && !e.buttons) S.hoverUntil = performance.now() + 1800;
    if (S.held.has(e.pointerId) && S.trailOK) {
      const now = performance.now();
      if (Math.hypot(e.clientX - S.trail.x, e.clientY - S.trail.y) >= 36 && now - S.trail.t >= 60) {
        S.trail = {x: e.clientX, y: e.clientY, t: now};
        addStamp(nx, ny, KIND.trail);
      }
    }
    kick();
  }
  function onPointerEnd(e) { S.held.delete(e.pointerId); }
  function onKey(e) {
    if (!S.enabled || S.frozen) return;
    const now = performance.now();
    if (e.type === 'keydown') {
      if (IGNORED_KEYS.has(e.key)) return;
      S.lastKeyDown = now;
    } else if (now - S.lastKeyDown < 35) return;
    S.type = Math.min(1.2, S.type + .4);
    if (now - S.lastKey >= 70) {
      S.lastKey = now;
      const el = e.target instanceof Element && e.target.closest('input,textarea,[contenteditable],[contenteditable="true"]');
      if (!el || !stampAtElement(el, KIND.key, true)) addStamp(S.tx, S.ty, KIND.key);
    }
    kick();
  }
  function onWheel(e) { S.scroll = clamp(S.scroll + e.deltaY * .002, -1.5, 1.5); kick(); }
  function onScroll(e) {
    const t = e.target === document ? document.scrollingElement : e.target;
    if (!(t instanceof Element)) return;
    const previous = S.tops.get(t);
    S.tops.set(t, t.scrollTop);
    if (previous !== undefined) S.scroll = clamp(S.scroll + (t.scrollTop - previous) * .003, -1.5, 1.5);
    kick();
  }

  /* ---- lifecycle ---- */
  const listeners = [];
  function listen(target, type, fn, options) {
    target.addEventListener(type, fn, options);
    listeners.push(() => target.removeEventListener(type, fn, options));
  }
  const passive = {passive: true, capture: true};
  function start() {
    if (S.destroyed || canvas.isConnected) return;
    document.body.insertBefore(canvas, document.body.firstChild);
    listen(window, 'pointerdown', onPointerDown, passive);
    listen(window, 'pointermove', onPointerMove, passive);
    listen(window, 'pointerup', onPointerEnd, passive);
    listen(window, 'pointercancel', onPointerEnd, passive);
    listen(window, 'keydown', onKey, passive);
    listen(window, 'input', onKey, passive);
    listen(window, 'wheel', onWheel, passive);
    listen(window, 'scroll', onScroll, passive);
    listen(window, 'resize', () => { S.resizeDirty = true; kick(); });
    listen(window, 'orientationchange', () => { S.resizeDirty = true; kick(); });
    listen(document, 'visibilitychange', () => { if (document.hidden) stop(); else { S.last = 0; kick(); } });
    listen(canvas, 'webglcontextlost', e => { e.preventDefault(); S.lost = true; stop(); });
    listen(canvas, 'webglcontextrestored', () => {
      S.lost = false; S.programs.clear(); S.current = null; buildBuffer();
      S.cool = 60; S.still = true; kick();
    });
    synchronize();
  }

  const diagnostics = () => ({
    mode: S.mode, gl: root.dataset.gl || 'off', scene: S.scene, theme: S.scene, procedural: true, scheduled: S.raf !== 0,
    running: canRun(), idle: S.enabled && !isActive(performance.now()) ? 1 : 0, frozen: S.frozen, scale: S.scale,
    width: canvas.width, height: canvas.height, stamps: S.stampList.filter(Boolean).length, stampSlots: S.stampN,
  });
  const api = Object.freeze({
    react(el, options = {}) {
      if (!(el instanceof Element) || !S.enabled || S.frozen || S.suspended || document.hidden) return false;
      const kind = options.kind === 'success' ? KIND.success : options.kind === 'press' ? KIND.tap : KIND.button;
      return stampAtElement(el, kind);
    },
    suspend(flag) {
      S.suspended = !!flag;
      if (S.suspended) stop(); else { S.last = 0; kick(); }
    },
    reset() {
      S.stampList.fill(null); S.held.clear(); S.type = 0; S.scroll = 0; S.reveal = null; S.still = true;
      kick();
    },
    synchronize,
    destroy() {
      S.destroyed = true; stop();
      for (const off of listeners.splice(0)) off();
      canvas.remove();
      root.dataset.gl = 'off';
      delete window.TouchHelmEffects;
    },
    get diagnostics() { return diagnostics(); },
  });
  window.TouchHelmEffects = api;
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start, {once: true});
})();
