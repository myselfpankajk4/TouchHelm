/* A public browser link must exchange its one-use fragment before any PC API. */
(() => {
  'use strict';
  if (!document.querySelector('meta[name="touchhelm-browser-link"]')) return;
  const gate = {public:true, allowed:false, settled:false};
  window.TouchHelmBrowserLink = gate;
  const token = new URLSearchParams(location.hash.slice(1)).get('browser-link');
  // Fragments never reach the server. Remove this one before any other code runs.
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  const panel = document.createElement('section');
  panel.className = 'browser-link-gate'; panel.setAttribute('role','status');
  const heading = document.createElement('h1'), detail = document.createElement('p');
  heading.textContent = 'Pairing with your PC';
  detail.textContent = 'Checking this secure link…';
  panel.append(heading, detail); document.body.append(panel);
  document.documentElement.classList.add('browser-link-pending');
  gate.ready = (async () => {
    try {
      if (token && !/^[A-Za-z0-9_-]{43}$/.test(token)) throw Error('expired');
      const response = await fetch(token ? '/api/browser-link/pair' : '/api/browser-link/status', {
        method:token ? 'POST' : 'GET', credentials:'same-origin', cache:'no-store',
        ...(token ? {headers:{'Content-Type':'application/json'},body:JSON.stringify({token})} : {}),
        signal:AbortSignal.timeout(15000)
      });
      if (!response.ok || !(await response.json()).ready) throw Error('expired');
      gate.allowed = true; panel.remove();
      document.documentElement.classList.remove('browser-link-pending');
      return true;
    } catch (_) {
      heading.textContent = 'Scan a fresh QR code';
      detail.textContent = 'This link expired, was already used, or could not connect. On your PC, open Pair your phone → New QR code, then scan it. Keep both devices online.';
      return false;
    } finally { gate.settled = true; }
  })();
})();
