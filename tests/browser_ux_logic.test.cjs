const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('rebrand migrates old preferences and update drafts without replacing new values', () => {
  const ClientSource = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
  const migration = vm.runInNewContext(ClientSource + '\nmigrateLegacyStorage', {window: {}, document: {addEventListener(){}}});
  const entries = new Map([['phonepad_theme','oled'],['phonepad_resume:pc:8765','unsent draft'],['touchhelm_theme','light'],['other-app','preserved']]);
  const storage = {get length(){return entries.size;}, key(index){return [...entries.keys()][index];},
    getItem(key){return entries.get(key) ?? null;},setItem(key,value){entries.set(key,value);}};
  migration(storage);
  assert.equal(entries.get('touchhelm_theme'),'light');
  assert.equal(entries.get('touchhelm_resume:pc:8765'),'unsent draft');
  assert.equal(entries.get('other-app'),'preserved');
  assert.doesNotThrow(()=>migration({get length(){throw new Error('Storage denied');}}));
});

function fixture(overrides = {}) {
  const listeners = {};
  const document = { activeElement: null, hidden: false,
    documentElement: {}, body: null,
    addEventListener(name, fn) { listeners[name] = fn; },
  };
  function element() {
    const classes = new Set();
    return { value: '', textContent: '', checked: true, disabled: false, hidden: false,
      attrs: {}, style: {}, events: {}, isConnected: true,
      classList: { add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
        toggle(name, value) { if (value) classes.add(name); else classes.delete(name); } },
      setAttribute(name, value) { this.attrs[name] = String(value); },
      getAttribute(name) { return this.attrs[name]; },
      addEventListener(name, fn) { this.events[name] = fn; },
      emit(name, props = {}) { this.events[name]?.({ preventDefault() {}, ...props }); },
      click() { this.emit('click'); }, focus() { document.activeElement = this; },
      querySelectorAll() { return []; }, querySelector() { return null; },
      getClientRects() { return [{}]; },
      contains(node) { return this === node || this.children?.includes(node); },
      setCustomValidity(value) { this.validation = value; }, reportValidity() {},
    };
  }
  document.body = element();
  const context = vm.createContext({ document, window: { location: { protocol: 'http:' } },
    navigator: {}, console, URL, Intl, WebSocket: { OPEN: 1 },
    localStorage: { setItem() {} },
    setTimeout(...args) { const timer = setTimeout(...args); timer.unref(); return timer; },
    clearTimeout, setInterval, clearInterval,
    ...overrides });
  const Client = vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8') + '\nTouchHelmClient', context);
  const client = Object.create(Client.prototype);
  const messages = [];
  Object.assign(client, { isConnected: true, host: 'pc:8765', authPin: '', liveTextValue: '',
    isComposing: false, navTabs: [], views: [], keyBtns: [], macroBtns: [], numBtns: [],
    shortcutBtns: [], themeOptions: [], uiFeedback: element(), typingHint: element(),
    typeInput: element(), btnSendText: element(), btnClearText: element(),
    chkRealtimeTyping: element(), vibrate() {},
    send(msg) { if (!this.isConnected) return false; messages.push(JSON.parse(JSON.stringify(msg))); return true; },
  });
  return { client, messages, element, document, listeners, context };
}

test('successful Send and Clear return focus to the text field without changing live packets', () => {
  const { client, messages, document } = fixture();
  client.bindKeyboardControls();
  client.typeInput.value = 'hello';
  client.btnSendText.focus();
  client.btnSendText.click();
  assert.equal(document.activeElement, client.typeInput);
  assert.deepEqual(messages, [{ type: 'text', text: 'hello' }, { type: 'key', key: 'enter' }]);
  client.btnClearText.focus();
  client.btnClearText.click();
  assert.equal(document.activeElement, client.typeInput);
});

test('offline Send preserves the draft and explains recovery visibly', () => {
  const { client, messages } = fixture();
  client.bindKeyboardControls();
  client.isConnected = false;
  client.typeInput.value = 'keep this draft';
  client.btnSendText.click();
  assert.equal(client.typeInput.value, 'keep this draft');
  assert.equal(messages.length, 0);
  assert.match(client.uiFeedback.textContent, /connect|offline/i);
  assert.equal(client.uiFeedback.hidden, false);
});

test('typing mode names the existing Send/Enter action', () => {
  const { client } = fixture();
  client.bindKeyboardControls();
  assert.equal(client.btnSendText.textContent, 'Enter');
  client.chkRealtimeTyping.checked = false;
  client.chkRealtimeTyping.emit('change');
  assert.equal(client.btnSendText.textContent, 'Send');
  assert.match(client.typingHint.textContent, /send|draft/i);
});

test('settings failures preserve connected status and recover on a successful update', async () => {
  let success = false;
  const { client } = fixture({ fetch: async () => ({ ok: success, status: 500 }) });
  const statuses = [];
  client.setStatus = (...args) => statuses.push(args);
  assert.equal(await client.syncConfig({ scroll_speed: 1.2 }), false);
  assert.equal(client.isConnected, true);
  assert.deepEqual(statuses, []);
  assert.match(client.uiFeedback.textContent, /setting|save/i);
  success = true;
  assert.equal(await client.syncConfig({ scroll_speed: 1.2 }), true);
  assert.doesNotMatch(client.uiFeedback.textContent, /failed|could not/i);
});

test('modal traps Tab, dismisses Escape, and returns focus to its trigger', () => {
  const { client, document, element, listeners } = fixture();
  const modal = element(), trigger = element(), first = element(), last = element();
  modal.children = [first, last];
  modal.querySelectorAll = () => [first, last];
  client.themeModal = modal;
  trigger.focus();
  client.openModal(modal);
  assert.equal(document.activeElement, first);
  last.focus();
  listeners.keydown({ key: 'Tab', shiftKey: false, preventDefault() {} });
  assert.equal(document.activeElement, first);
  listeners.keydown({ key: 'Escape', preventDefault() {} });
  assert.equal(modal.classList.contains('open'), false);
  assert.equal(document.activeElement, trigger);
});

test('closing a modal accepts the browser NodeList navigation collection', () => {
  const { client, document, element } = fixture();
  const tab = element(), modal = element(), trigger = element();
  tab.classList.add('active');
  client.navTabs = { 0: tab, length: 1, [Symbol.iterator]: function* () { yield tab; } };
  trigger.focus();
  client.openModal(modal);
  client.closeModal(modal);
  assert.equal(document.activeElement, trigger);
});

test('theme selection opened from Settings returns to Settings and its appearance control', () => {
  const { client, document, element } = fixture();
  const settings = element(), theme = element(), opener = element(), appearance = element();
  settings.children = [appearance]; settings.querySelectorAll = () => [appearance];
  opener.focus(); client.openModal(settings); appearance.focus();
  client.openModal(theme); client.closeModal(theme);
  assert.equal(settings.classList.contains('open'), true);
  assert.equal(client.activeModal, settings);
  assert.equal(document.activeElement, appearance);
  client.closeModal(settings);
  assert.equal(document.activeElement, opener);
});

test('disconnected remote controls disable while drafts and local timer stay usable', () => {
  const { client, element } = fixture();
  client.keyBtns = [element()];
  client.btnMediaPlay = element();
  client.sliderSens = element();
  client.sliderAccel = element();
  client.sliderScroll = element();
  client.chkInvertScroll = element();
  client.chkHaptics = element();
  client.btnTimerStart = element();
  client.isConnected = false;
  client.setStatus('disconnected', 'Offline');
  assert.equal(client.keyBtns[0].disabled, true);
  assert.equal(client.btnMediaPlay.disabled, true);
  for (const control of [client.sliderSens, client.sliderAccel, client.sliderScroll, client.chkInvertScroll]) {
    assert.equal(control.disabled, true);
  }
  assert.equal(client.chkHaptics.disabled, false);
  assert.equal(client.typeInput.disabled, false);
  assert.equal(client.btnTimerStart.disabled, false);
  client.isConnected = true;
  client.setStatus('connected', 'Connected');
  assert.equal(client.keyBtns[0].disabled, false);
  assert.equal(client.sliderSens.disabled, false);
});

test('selected navigation tab exposes its selected state', () => {
  const { client, element } = fixture();
  client.navTabs = [element(), element()];
  client.navTabs[0].attrs['data-view'] = 'viewTrackpad';
  client.navTabs[1].attrs['data-view'] = 'viewMedia';
  client.views = [Object.assign(element(), { id: 'viewTrackpad' }), Object.assign(element(), { id: 'viewMedia' })];
  client.releaseDragLock = client.disableGyro = () => {};
  client.switchView('viewMedia');
  assert.equal(client.navTabs[0].attrs['aria-selected'], 'false');
  assert.equal(client.navTabs[1].attrs['aria-selected'], 'true');
});

test('wake-lock and fullscreen capability failures are visible with accurate toggle state', async () => {
  const { client, element } = fixture();
  client.btnWakeLock = element();
  client.btnFullscreen = element();
  await client.toggleWakeLock();
  assert.match(client.uiFeedback.textContent, /awake|wake|https/i);
  assert.equal(client.btnWakeLock.attrs['aria-pressed'], 'false');
  await client.toggleFullscreen();
  assert.match(client.uiFeedback.textContent, /fullscreen/i);
});

test('pairing rejects unsupported addresses visibly and accepts a full PC URL', () => {
  const { client, element } = fixture();
  client.settingHost = element();
  client.closeSettings = client.connect = client.fetchServerConfig = () => {};
  client.settingHost.value = 'ftp://pc';
  assert.equal(client.connectToHost(), false);
  assert.match(client.settingHost.validation, /address|http|pc/i);
  client.settingHost.value = 'http://192.168.1.10:8765/';
  assert.equal(client.connectToHost(), true);
  assert.equal(client.host, '192.168.1.10:8765');
  assert.equal(client.settingHost.validation, '');
});

test('Air Mouse capability errors are visible and its pressed state follows the sensor listener', async () => {
  const { client, context, element } = fixture({ alert() {} });
  client.btnGyro = element();
  await client.toggleGyro();
  assert.match(client.uiFeedback.textContent, /air mouse|sensor|gyroscope/i);
  assert.equal(client.btnGyro.attrs['aria-pressed'], 'false');
  context.window.DeviceOrientationEvent = function () {};
  context.window.addEventListener = context.window.removeEventListener = () => {};
  await client.toggleGyro();
  assert.equal(client.btnGyro.attrs['aria-pressed'], 'true');
  await client.toggleGyro();
  assert.equal(client.btnGyro.attrs['aria-pressed'], 'false');
});

test('synthetic touches on disabled remote buttons do not invoke their action', () => {
  const { client, element } = fixture();
  const button = element();
  let calls = 0;
  client.onTap(button, () => calls++);
  button.disabled = true;
  button.emit('touchend', { touches: [] });
  button.click();
  assert.equal(calls, 0);
});

test('feedback expires after its display time without an older timeout hiding newer feedback', () => {
  const pending = [];
  const { client } = fixture({
    setTimeout(run, milliseconds) { pending.push({ run, milliseconds }); return pending.length; },
    clearTimeout() {},
  });
  client.showFeedback('Saved.', 'success', 'settings');
  assert.equal(pending[0].milliseconds, 4000);
  client.showFeedback('Connect to send.', 'error', 'typing');
  assert.equal(pending[1].milliseconds, 8000);
  pending[0].run();
  assert.equal(client.uiFeedback.textContent, 'Connect to send.');
  assert.equal(client.uiFeedback.hidden, false);
  pending[1].run();
  assert.equal(client.uiFeedback.hidden, true);
  assert.equal(client.uiFeedback.textContent, '');
});

test('unsaved settings remain identified after the transient toast expires, until a successful save', async () => {
  let success = false;
  const pending = [];
  const { client, element } = fixture({
    fetch: async () => ({ ok: success, status: 500 }),
    setTimeout(run) { pending.push(run); return pending.length; }, clearTimeout() {},
  });
  client.settingsFeedback = element();
  await client.syncConfig({ mouse_sensitivity: 2 });
  pending[0]();
  assert.equal(client.uiFeedback.hidden, true);
  assert.match(client.settingsFeedback.textContent, /not saved|unsaved/i);
  assert.equal(client.settingsFeedback.hidden, false);
  assert.equal(client.isConnected, true);
  success = true;
  await client.syncConfig({ mouse_sensitivity: 2 });
  assert.equal(client.settingsFeedback.textContent, '');
  assert.equal(client.settingsFeedback.hidden, true);
});

test('changing PCs retains the draft but never applies the old PC typing history to the new PC', () => {
  const { client, element, messages } = fixture();
  client.settingHost = element();
  client.closeSettings = client.connect = client.fetchServerConfig = () => {};
  client.bindKeyboardControls();
  client.typeInput.value = 'hello';
  client.liveTextValue = 'hello';
  client.settingHost.value = 'http://other-pc:8765/';
  assert.equal(client.connectToHost(), true);
  assert.equal(client.typeInput.value, 'hello');
  client.typeInput.value = 'he';
  client.typeInput.emit('input');
  assert.deepEqual(messages, [{ type: 'text', text: 'he' }]);
  client.settingHost.value = 'other-pc:8765';
  assert.equal(client.connectToHost(), true);
  client.typeInput.value = 'hey';
  client.typeInput.emit('input');
  assert.deepEqual(messages, [{ type: 'text', text: 'he' }, { type: 'text', text: 'y' }]);
});

test('an older settings success cannot hide the newest failed edit', async () => {
  const requests = [];
  const { client, element } = fixture({ fetch: () => new Promise(resolve => requests.push(resolve)) });
  client.settingsFeedback = element();
  const older = client.syncConfig({ mouse_sensitivity: 1.5 });
  const newer = client.syncConfig({ mouse_sensitivity: 2.5 });
  requests[1]({ ok: false, status: 500 });
  assert.equal(await newer, false);
  requests[0]({ ok: true, status: 200 });
  await older;
  assert.match(client.uiFeedback.textContent, /not saved/i);
  assert.equal(client.settingsFeedback.hidden, false);
});

test('saving another setting does not hide an earlier unsaved setting', async () => {
  let success = false;
  const { client, element } = fixture({ fetch: async () => ({ ok: success, status: 500 }) });
  client.settingsFeedback = element();
  await client.syncConfig({ mouse_sensitivity: 2.5 });
  success = true;
  await client.syncConfig({ theme: 'oled' });
  assert.equal(client.settingsFeedback.hidden, false);
  assert.match(client.settingsFeedback.textContent, /not saved|unsaved/i);
  await client.syncConfig({ mouse_sensitivity: 2.5 });
  assert.equal(client.settingsFeedback.hidden, true);
});

test('presentation timer uses elapsed wall time and reset leaves slide commands available', () => {
  let now = 10000, tick;
  const { client, element, messages } = fixture({ Date: { now: () => now },
    setInterval(fn) { tick = fn; return 1; }, clearInterval() {} });
  client.timerSeconds = client.timerInitial = 300;
  client.timerDisplay = element();
  client.btnTimerStart = element();
  client.timerRunning = false;
  client.toggleTimer();
  now += 73000;
  tick();
  assert.equal(client.timerSeconds, 227);
  client.resetTimer();
  assert.equal(client.timerSeconds, 300);
  assert.equal(client.timerRunning, false);
  assert.equal(client.timerInterval, null);
  assert.equal(client.timerDisplay.textContent, '05:00');
  assert.equal(client.send({ type: 'presentation', action: 'next' }), true);
  assert.deepEqual(messages, [{ type: 'presentation', action: 'next' }]);
});

test('timer finishes on the tick that reaches zero and can restart after reset', () => {
  let now = 1000, tick;
  const { client, element } = fixture({ Date: { now: () => now },
    setInterval(fn) { tick = fn; return 1; }, clearInterval() {} });
  client.timerSeconds = client.timerInitial = 1;
  client.timerDisplay = element(); client.btnTimerStart = element();
  client.toggleTimer(); now += 1000; tick();
  assert.equal(client.timerSeconds, 0);
  assert.equal(client.timerRunning, false);
  client.resetTimer(); client.toggleTimer();
  assert.equal(client.timerRunning, true);
  assert.equal(client.timerSeconds, 1);
});

test('confirmed new server UI preserves the draft before loading its versioned address', async () => {
  const saved = new Map(); let replacement;
  const { client, context } = fixture({
    sessionStorage: { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value) },
    fetch: async () => ({ ok: true, json: async () => ({ build: 'new-build' }) }),
  });
  context.window.location = { protocol: 'http:', host: 'pc:8765', origin: 'http://pc:8765',
    href: 'http://pc:8765/?build=old-build', replace: value => { replacement = value; } };
  client.buildId = 'old-build';
  client.typeInput.value = 'unsent draft'; client.liveTextValue = 'already sent';
  client.chkRealtimeTyping.checked = false;
  client.releaseDragLock = client.stopLaser = client.disableGyro = () => {};
  assert.equal(typeof client.checkServerVersion, 'function');
  assert.equal(await client.checkServerVersion(), true);
  assert.equal(new URL(replacement).searchParams.get('build'), 'new-build');
  const resumed = JSON.parse(saved.get('touchhelm_resume:pc:8765'));
  assert.equal(resumed.draft, 'unsent draft');
  assert.equal(resumed.baseline, 'already sent');
  assert.equal(resumed.live, false);
});

test('unchanged or unavailable server build never refreshes away a draft', async () => {
  let calls = 0;
  const { client, context } = fixture({ fetch: async () => ({ ok: true,
    json: async () => ({ build: 'same-build' }) }) });
  context.window.location = { host: 'pc:8765', origin: 'http://pc:8765', href: 'http://pc:8765/', replace() { calls++; } };
  client.buildId = 'same-build'; client.typeInput.value = 'keep';
  assert.equal(typeof client.checkServerVersion, 'function');
  assert.equal(await client.checkServerVersion(), false);
  context.fetch = async () => { throw new Error('offline'); };
  assert.equal(await client.checkServerVersion(), false);
  assert.equal(client.typeInput.value, 'keep');
  assert.equal(calls, 0);
});

test('restoring a draft does not erase the update-loop guard when an old worker returns stale HTML', async () => {
  const saved = new Map(); let reloads = 0;
  const { client, context } = fixture({ sessionStorage: { getItem: key => saved.get(key),
    setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key) },
    fetch: async () => ({ ok: true, json: async () => ({ build: 'new-build' }) }) });
  context.window.location = { host: 'pc:8765', origin: 'http://pc:8765', href: 'http://pc:8765/', replace() { reloads++; } };
  client.buildId = 'old-build'; client.releaseDragLock = client.stopLaser = client.disableGyro = () => {};
  client.typeInput.value = 'keep';
  await client.checkServerVersion();
  client.restoreSession();
  await client.checkServerVersion();
  assert.equal(client.typeInput.value, 'keep');
  assert.equal(reloads, 1);
});
