/* Shared interaction feedback: press, ripple, busy/success/error, connection
   and view/panel/dialog arrivals. Effects use the Web Animations API on a
   pointer-events:none overlay, so CSS state rules stay untouched. Reduced
   motion keeps short opacity-only feedback and drops all movement. */
(function () {
  'use strict';
  const root = document.documentElement;
  const EASE = 'cubic-bezier(0.16,1,0.3,1)';
  const PRESSABLE = 'button,[role="button"],[role="tab"],[role="switch"],[role="option"],summary,a[href],label:has(>input[type="checkbox"]),label:has(>input[type="radio"])';
  const systemReduced = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const reduced = () => root.dataset.motion === 'reduced' || (root.dataset.motion !== 'full' && systemReduced.matches);
  const pressed = new Set();
  let layer = null, lastTrigger = null, lastTriggerAt = 0;

  function overlay() {
    if (layer && layer.isConnected) return layer;
    layer = document.createElement('div');
    layer.id = 'th-fx';
    layer.setAttribute('aria-hidden', 'true');
    document.body.appendChild(layer);
    return layer;
  }
  function usable(el) {
    return el && !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !el.closest('[inert],[data-th-static]');
  }
  function target(node) {
    const el = node && node.closest ? node.closest(PRESSABLE) : null;
    return usable(el) ? el : null;
  }
  function box(el, extra) {
    const r = el.getBoundingClientRect();
    const node = document.createElement('span');
    node.style.cssText = `left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;border-radius:${getComputedStyle(el).borderRadius};color:${getComputedStyle(el).color}`;
    if (extra) node.className = extra;
    overlay().appendChild(node);
    return { node, rect: r };
  }
  function play(node, keyframes, options) {
    const animation = node.animate(keyframes, options);
    const done = () => node.remove();
    animation.onfinish = done;
    animation.oncancel = done;
    return animation;
  }

  function pressIn(el) {
    if (reduced() || !el.animate) return;
    const scale = el.offsetWidth > 220 || el.offsetHeight > 120 ? 0.985 : 0.96;
    if (el.__thPress) el.__thPress.cancel();
    el.__thPress = el.animate([{ scale: '1' }, { scale: String(scale) }], { duration: 110, easing: EASE, fill: 'forwards' });
    pressed.add(el);
  }
  function pressOut(el) {
    pressed.delete(el);
    const held = el.__thPress;
    if (!held) return;
    const from = getComputedStyle(el).scale;
    const back = el.animate([{ scale: from === 'none' ? '1' : from }, { scale: '1' }], { duration: 180, easing: EASE });
    held.cancel();
    el.__thPress = back;
    back.onfinish = back.oncancel = () => { if (el.__thPress === back) el.__thPress = null; };
  }
  function releaseAll() { for (const el of [...pressed]) pressOut(el); }

  function ripple(el, x, y) {
    if (!overlay().animate) return;
    if (reduced()) return flash(el);
    const { node, rect } = box(el, 'th-fx-clip');
    const px = x == null ? rect.width / 2 : x - rect.left, py = y == null ? rect.height / 2 : y - rect.top;
    const size = 2 * Math.hypot(Math.max(px, rect.width - px), Math.max(py, rect.height - py));
    const dot = document.createElement('span');
    dot.className = 'th-fx-ripple';
    dot.style.cssText = `width:${size}px;height:${size}px;left:${px - size / 2}px;top:${py - size / 2}px`;
    node.appendChild(dot);
    const duration = Math.min(560, 340 + size / 3);
    play(node, [{ opacity: 1 }, { opacity: 1, offset: 0.55 }, { opacity: 0 }], { duration, easing: 'linear' });
    dot.animate([{ transform: 'scale(0.1)' }, { transform: 'scale(1)' }], { duration, easing: EASE });
  }
  function flash(el, color) {
    const { node } = box(el, 'th-fx-flash');
    if (color) node.style.color = color;
    play(node, [{ opacity: 0 }, { opacity: 1, offset: 0.3 }, { opacity: 0 }], { duration: 220, easing: 'linear' });
  }
  function ring(el, color, { round = false, grow = 1.06 } = {}) {
    const { node } = box(el, 'th-fx-ring');
    node.style.setProperty('--th-fx-color', color);
    if (round) node.style.borderRadius = '50%';
    const frames = reduced()
      ? [{ opacity: 0 }, { opacity: 1, offset: 0.25 }, { opacity: 0 }]
      : [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: `scale(${grow})` }];
    play(node, frames, { duration: reduced() ? 320 : round ? 640 : 520, easing: reduced() ? 'linear' : EASE });
  }
  function badge(el, kind) {
    const r = el.getBoundingClientRect();
    if (!r.width) return;
    const node = document.createElement('span');
    node.className = 'th-fx-badge';
    node.style.cssText = `left:${r.right - 14}px;top:${r.top - 6}px`;
    node.style.setProperty('--th-fx-color', kind === 'success' ? 'var(--th-success)' : 'var(--th-danger)');
    node.innerHTML = kind === 'success'
      ? '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'
      : '<svg viewBox="0 0 24 24"><path d="M12 6v7M12 17.5v.5"/></svg>';
    overlay().appendChild(node);
    const motion = !reduced();
    play(node, [
      { opacity: 0, transform: motion ? 'scale(0.6)' : 'none' },
      { opacity: 1, transform: 'none', offset: 0.18 },
      { opacity: 1, transform: 'none', offset: 0.8 },
      { opacity: 0, transform: 'none' }
    ], { duration: 1300, easing: EASE });
  }
  function result(el, ok) {
    if (!el || !el.isConnected) return;
    const color = ok ? 'var(--th-success)' : 'var(--th-danger)';
    ring(el, color);
    badge(el, ok ? 'success' : 'error');
  }

  /* Busy -> success/error around an async command started from a control.
     The busy shimmer only appears when the command takes longer than 140ms. */
  function track(el, pending) {
    if (!el || !pending || typeof pending.then !== 'function') return pending;
    const token = (el.__thToken || 0) + 1;
    el.__thToken = token;
    const timer = setTimeout(() => {
      if (el.__thToken !== token) return;
      el.dataset.thState = 'busy';
      el.setAttribute('aria-busy', 'true');
    }, 140);
    const settle = ok => {
      clearTimeout(timer);
      if (el.__thToken !== token) return;
      el.removeAttribute('aria-busy');
      el.dataset.thState = ok ? 'success' : 'error';
      result(el, ok);
      setTimeout(() => { if (el.__thToken === token) delete el.dataset.thState; }, 1400);
    };
    pending.then(value => settle(!(value && value.success === false)), () => settle(false));
    return pending;
  }
  function recentTrigger() {
    const el = lastTrigger;
    if (!el || performance.now() - lastTriggerAt > 800) return null;
    lastTrigger = null;
    return el.isConnected ? el : null;
  }

  /* Connection states: connecting draws the header progress line (CSS);
     arriving at connected rings the status dot; dropping flashes the pill. */
  function connection(state, el) {
    const previous = root.dataset.connection;
    root.dataset.connection = state;
    if (el) el.dataset.state = state;
    if (!el || !previous || previous === state || !overlay().animate) return;
    const dot = el.querySelector('.status-dot') || el;
    if (state === 'connected') ring(dot, 'var(--th-success)', { round: true, grow: 3.2 });
    else if (state === 'disconnected' && previous === 'connected') flash(el, 'var(--th-danger)');
  }

  function arrive(el, { dx = 0, dy = 8, duration = 280 } = {}) {
    if (!el || !el.animate) return;
    const frames = reduced()
      ? [{ opacity: 0 }, { opacity: 1 }]
      : [{ opacity: 0, translate: `${dx}px ${dy}px` }, { opacity: 1, translate: '0 0' }];
    el.animate(frames, { duration: reduced() ? 120 : duration, easing: EASE });
  }

  function watch() {
    const views = [...document.querySelectorAll('.view')];
    if (views.length) {
      const order = [...document.querySelectorAll('.nav-tab[data-view]')].map(tab => tab.getAttribute('data-view'));
      const rank = view => { const i = order.indexOf(view.id); return i < 0 ? views.indexOf(view) : i; };
      let current = views.find(view => view.classList.contains('active'));
      const observer = new MutationObserver(() => {
        const next = views.find(view => view.classList.contains('active'));
        if (!next || next === current) return;
        const dx = current ? (rank(next) > rank(current) ? 14 : -14) : 0;
        current = next;
        arrive(next, { dx, dy: 0 });
      });
      views.forEach(view => observer.observe(view, { attributes: true, attributeFilter: ['class'] }));
    }
    const pages = [...document.querySelectorAll('[data-page]')];
    if (pages.length) {
      const observer = new MutationObserver(records => {
        for (const record of records) if (!record.target.hidden && record.oldValue !== null) arrive(record.target, { dy: 8, duration: 300 });
      });
      pages.forEach(page => observer.observe(page, { attributes: true, attributeFilter: ['hidden'], attributeOldValue: true }));
    }
    const notices = [...document.querySelectorAll('[role="status"][hidden],[role="alert"][hidden],.save-error')];
    if (notices.length) {
      const observer = new MutationObserver(records => {
        for (const record of records) if (!record.target.hidden && record.oldValue !== null) arrive(record.target, { dy: -6, duration: 220 });
      });
      notices.forEach(notice => observer.observe(notice, { attributes: true, attributeFilter: ['hidden'], attributeOldValue: true }));
    }
    const dialogs = [...document.querySelectorAll('.modal-backdrop')];
    if (dialogs.length) {
      const observer = new MutationObserver(records => {
        for (const record of records) {
          const dialog = record.target;
          if (!dialog.classList.contains('open') || (record.oldValue || '').split(/\s+/).includes('open')) continue;
          dialog.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: EASE });
          const card = dialog.querySelector('.modal-card');
          if (card) arrive(card, { dy: 14, duration: 320 });
        }
      });
      dialogs.forEach(dialog => observer.observe(dialog, { attributes: true, attributeFilter: ['class'], attributeOldValue: true }));
    }
  }

  window.addEventListener('pointerdown', event => {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    const el = target(event.target);
    if (!el) return;
    pressIn(el);
    ripple(el, event.clientX, event.clientY);
  }, { capture: true, passive: true });
  window.addEventListener('pointerup', releaseAll, { capture: true, passive: true });
  window.addEventListener('pointercancel', releaseAll, { capture: true, passive: true });
  window.addEventListener('blur', releaseAll);
  window.addEventListener('keydown', event => {
    if (event.repeat || (event.key !== 'Enter' && event.key !== ' ')) return;
    const el = target(event.target);
    if (el && !el.matches('a[href]') || (el && event.key === 'Enter')) pressIn(el);
  }, true);
  window.addEventListener('keyup', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const el = target(event.target);
    if (el && pressed.has(el)) { pressOut(el); ripple(el); }
  }, true);
  document.addEventListener('click', event => {
    const el = target(event.target);
    if (el) { lastTrigger = el; lastTriggerAt = performance.now(); }
  }, true);
  document.addEventListener('submit', event => {
    if (event.submitter) { lastTrigger = event.submitter; lastTriggerAt = performance.now(); }
  }, true);
  document.addEventListener('focusin', event => {
    const el = event.target;
    if (reduced() || !el.animate || !el.matches || !el.matches(':focus-visible')) return;
    const offset = parseFloat(getComputedStyle(el).outlineOffset) || 0;
    el.animate([{ outlineOffset: `${offset + 4}px` }, { outlineOffset: `${offset}px` }], { duration: 180, easing: EASE });
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch, { once: true });
  else watch();

  window.TouchHelmMotion = { reduced, pressIn, pressOut, ripple, flash, ring, result, track, recentTrigger, connection, arrive };
})();
