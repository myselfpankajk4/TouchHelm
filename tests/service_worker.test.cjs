const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function worker() {
  const handlers = {}, saved = [], removed = [], requests = [];
  const context = vm.createContext({
    self: { location: { origin: 'http://pc:8765' }, skipWaiting() {},
      clients: { claim() {} }, addEventListener(type, fn) { handlers[type] = fn; } },
    caches: { async keys() { return ['touchhelm-v3', 'phonepad-v3', 'another-app-v1']; },
      async delete(key) { removed.push(key); }, async match() {},
      async open() { return { async addAll(urls) { saved.push(...urls); }, async put() {} }; } },
    fetch: async (...args) => { requests.push(args); return new Response('asset'); }, URL, Response,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/sw.js'), 'utf8'), context);
  return { handlers, saved, removed, requests };
}

test('installation caches the versioned assets used by the phone page for offline startup', async () => {
  const { handlers, saved } = worker();
  let work;
  handlers.install({ waitUntil(promise) { work = promise; } });
  await work;
  assert.ok(saved.includes('/'));
  const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
  const assets = [...html.matchAll(/(?:href|src)="(\/[^" ]+\?v=__TOUCHHELM_BUILD__)"/g)].map(match => match[1]);
  assert.ok(assets.length >= 9);
  for (const asset of assets) assert.ok(saved.includes(asset), `missing offline asset ${asset}`);
});

test('activation removes only obsolete TouchHelm caches', async () => {
  const { handlers, removed } = worker();
  let work;
  handlers.activate({ waitUntil(promise) { work = promise; } });
  await work;
  assert.deepEqual(removed, ['touchhelm-v3', 'phonepad-v3']);
});

test('POSTs and other origins bypass the static asset cache', () => {
  const { handlers } = worker();
  for (const [url, method] of [['http://pc:8765/custom', 'POST'], ['http://other:8765/app.js', 'GET']]) {
    let intercepted = false;
    handlers.fetch({ request: { url, method }, respondWith() { intercepted = true; } });
    assert.equal(intercepted, false);
  }
});

test('live assets bypass HTTP caching so an installed worker cannot reopen stale UI', async () => {
  const { handlers, requests } = worker();
  let response;
  handlers.fetch({ request: { url: 'http://pc:8765/index.html?build=new', method: 'GET' },
    respondWith(value) { response = value; }, waitUntil() {} });
  assert.equal(await (await response).text(), 'asset');
  assert.equal(requests[0][1]?.cache, 'no-store');
});
