const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.events = {};
    this.dataset = {}; this.attributes = {}; this.style = {setProperty(){}};
    this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false;
    this.scrollHeight = 80; this.classes = new Set();
    this.classList = {add: (...names) => names.forEach(n => this.classes.add(n)),
      remove: (...names) => names.forEach(n => this.classes.delete(n)),
      contains: name => this.classes.has(name),
      toggle: (name, force) => { const value = force ?? !this.classes.has(name); value ? this.classes.add(name) : this.classes.delete(name); return value; }};
  }
  set innerHTML(_) { throw new Error('Catalog content must never use innerHTML'); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  emit(name, details = {}) { for (const fn of this.events[name] || []) fn({preventDefault(){},
    stopPropagation(){}, target: this, currentTarget: this, button: 0, pointerId: 1, detail: 0, ...details}); }
  appendChild(element) { this.children.push(element); element.parentElement = this; return element; }
  append(...elements) { elements.forEach(el => this.appendChild(el)); }
  replaceChildren(...elements) { this.children = []; this.append(...elements); }
  focus() { this.focused = true; }
  blur() { this.focused = false; }
  setPointerCapture() {}
  releasePointerCapture() {}
}
function setup() {
  const elements = new Map();
  const doc = {documentElement: new Element('html'), events: {}, hidden: false,
    getElementById(id) { if (!elements.has(id)) elements.set(id, new Element(id === 'mediaSessionSelect' ? 'select' : 'div')); return elements.get(id); },
    createElement(tag) { return new Element(tag); },
    addEventListener(name, fn) { (this.events[name] ||= []).push(fn); },
    querySelectorAll() { return []; }};
  const win = {events: {}, innerHeight: 844,
    addEventListener(name, fn) { (this.events[name] ||= []).push(fn); },
    visualViewport: {height: 844, addEventListener(){}}};
  const sandbox = vm.createContext({window: win, document: doc, console, Date, Intl,
    setTimeout, clearTimeout, requestAnimationFrame: fn => fn()});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/controls.js'), 'utf8'), sandbox);
  const messages = [], feedback = [];
  const client = {isConnected: true, selectedMediaSession: '',
    send(message) { if (!this.isConnected) return false; messages.push(JSON.parse(JSON.stringify(message))); return true; },
    showFeedback(...args) { feedback.push(args); }, vibrate(){}};
  const controls = new win.TouchHelmControls(client);
  const all = () => [...elements.values()].flatMap(function flatten(element) {
    return [element, ...element.children.flatMap(flatten)];
  });
  const key = name => all().find(el => el.dataset.key === name);
  return {controls, client, messages, feedback, elements, doc, win, key};
}

test('ordinary native keys emit one keydown and one keyup with no duplicate click', () => {
  const {key, messages} = setup();
  key('a').emit('pointerdown'); key('a').emit('pointerup'); key('a').emit('click', {detail: 1});
  assert.deepEqual(messages, [{type: 'keydown', key: 'a'}, {type: 'keyup', key: 'a'}]);
});
test('tap Ctrl and Shift latch a native chord and release after A', () => {
  const {key, messages} = setup();
  key('lctrl').emit('pointerdown'); key('lctrl').emit('pointerup');
  key('lshift').emit('pointerdown'); key('lshift').emit('pointerup');
  key('a').emit('pointerdown'); key('a').emit('pointerup');
  assert.deepEqual(messages, [
    {type: 'keydown', key: 'lctrl'}, {type: 'keydown', key: 'lshift'},
    {type: 'keydown', key: 'a'}, {type: 'keyup', key: 'a'},
    {type: 'keyup', key: 'lctrl'}, {type: 'keyup', key: 'lshift'},
  ]);
});
test('simultaneously held modifiers stay down until their actual pointer releases', () => {
  const {key, messages} = setup();
  key('lctrl').emit('pointerdown', {pointerId: 1});
  key('a').emit('pointerdown', {pointerId: 2});
  key('a').emit('pointerup', {pointerId: 2});
  assert.equal(messages.some(msg => msg.type === 'keyup' && msg.key === 'lctrl'), false);
  key('lctrl').emit('pointerup', {pointerId: 1});
  assert.deepEqual(messages.at(-1), {type: 'keyup', key: 'lctrl'});
});
test('pointer cancellation, blur, and disconnect clear native held-key state', () => {
  const {controls, key, messages, win} = setup();
  key('lctrl').emit('pointerdown'); key('lctrl').emit('pointerup');
  key('a').emit('pointerdown', {pointerId: 2}); key('a').emit('pointercancel', {pointerId: 2});
  assert.deepEqual(messages.slice(-2).sort((a,b) => a.key.localeCompare(b.key)),
    [{type: 'keyup', key: 'a'}, {type: 'keyup', key: 'lctrl'}]);
  key('b').emit('pointerdown'); win.events.blur.forEach(fn => fn());
  assert.deepEqual(messages.at(-1), {type: 'keyup', key: 'b'});
  controls.setConnected(false);
  assert.equal(key('a').disabled, true);
});
test('collapsing the typing dock preserves its entire draft and returns to the pad', () => {
  const {controls, elements} = setup();
  elements.get('typeInput').value = 'unsent\nmultiline draft';
  elements.get('typeInput').emit('focus');
  assert.equal(elements.get('typingDock').classList.contains('expanded'), true);
  elements.get('btnTypingDone').emit('click');
  assert.equal(elements.get('typingDock').classList.contains('expanded'), false);
  assert.equal(elements.get('typeInput').value, 'unsent\nmultiline draft');
  assert.equal(elements.get('touchSurface').focused, true);
});
test('apps use safe text, real running/frequency order, and catalog IDs for launch', () => {
  const {controls, elements, messages} = setup();
  controls.renderApps([
    {id: 'safe:1', name: '<img src=x onerror=alert(1)>', running: false, launches: 0},
    {id: 'safe:2', name: 'Editor', running: true, launches: 1},
    {id: 'safe:3', name: 'Music', running: false, launches: 3},
  ]);
  const list = elements.get('appsList');
  assert.equal(list.children[0].dataset.appId, 'safe:2');
  assert.equal(list.children[1].dataset.appId, 'safe:3');
  elements.get('appSearch').value = '<img'; elements.get('appSearch').emit('input');
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].dataset.appId, 'safe:1');
  list.children[0].emit('click');
  assert.deepEqual(messages.at(-1), {type: 'launch_app', app_id: 'safe:1'});
});
test('media playback sends item/session IDs and accurately states unavailable queues', () => {
  const {controls, elements, messages, client} = setup();
  controls.renderMediaLibrary({sessions: [{id: 'player-1', app: 'Music'}],
    items: [{id: 'media:1', title: '<script>bad()</script>', subtitle: 'Local file', kind: 'local'}],
    playlist_supported: false, playlist_message: 'This player does not expose its queue.'});
  assert.equal(elements.get('mediaLibraryMessage').textContent, 'This player does not expose its queue.');
  elements.get('mediaSessionSelect').value = 'player-1'; elements.get('mediaSessionSelect').emit('change');
  assert.equal(client.selectedMediaSession, 'player-1');
  elements.get('mediaLibrary').children[0].emit('click');
  assert.deepEqual(messages.at(-1), {type: 'play_media', item_id: 'media:1', session_id: 'player-1'});
});
test('missing presentation/media metadata does not invent counts or positions', () => {
  const {controls, elements} = setup();
  controls.renderDesktopState({presentation: {available: true, app: 'PowerPoint', title: 'Deck',
    active: true, slide: 2, total: null, slide_title: 'Overview'}, media: {available: false, message: 'No sessions'}});
  assert.equal(elements.get('presentationSlide').textContent, 'Slide 2');
  assert.equal(elements.get('mediaProgress').hidden, true);
  assert.equal(elements.get('mediaStatus').textContent, 'No sessions');
});
test('selected media session renders its own metadata and reports when that player disappears', () => {
  const {controls, client, elements} = setup();
  client.selectedMediaSession = 'chosen';
  controls.renderDesktopState({media: {available: true, session_id: 'active', title: 'Wrong song',
    sessions: [{available: true, session_id: 'chosen', title: 'Chosen song', artist: 'Artist',
      status: 'paused', position: 62, duration: 180}]}});
  assert.equal(elements.get('mediaTitle').textContent, 'Chosen song');
  assert.equal(elements.get('mediaPosition').textContent, '1:02');
  controls.renderDesktopState({media: {available: true, title: 'Wrong song', sessions: []}});
  assert.match(elements.get('mediaStatus').textContent, /selected player|refresh/i);
  assert.notEqual(elements.get('mediaTitle').textContent, 'Wrong song');
});
test('failed catalog commands stop loading and expose the provider error', () => {
  const {controls, elements} = setup();
  controls.requestApps(); controls.commandResult({command:'get_apps',success:false,message:'Apps provider unavailable'});
  assert.equal(elements.get('appsStatus').textContent, 'Apps provider unavailable');
  controls.requestMedia(); controls.commandResult({command:'get_media_library',success:false,message:'Queue unavailable'});
  assert.equal(elements.get('mediaLibraryMessage').textContent, 'Queue unavailable');
});

test('advanced function keys and right-side modifiers retain their native identities', () => {
  const {key, messages} = setup();
  for (const name of ['rctrl','rshift','ralt','f13','f24','capslock','printscreen','scrolllock','pause']) {
    assert.ok(key(name), `Missing ${name}`);
  }
  key('rctrl').emit('pointerdown'); key('rctrl').emit('pointerup');
  key('f24').emit('pointerdown'); key('f24').emit('pointerup');
  assert.deepEqual(messages, [{type:'keydown',key:'rctrl'}, {type:'keydown',key:'f24'},
    {type:'keyup',key:'f24'}, {type:'keyup',key:'rctrl'}]);
});

test('routine playback and presentation success is quiet while failures remain visible', () => {
  const {controls, feedback} = setup();
  for (const command of ['presentation','media','play_media','get_desktop_state','get_apps','get_media_library']) {
    controls.commandResult({command,success:true,message:'Completed'});
  }
  assert.equal(feedback.length, 0);
  controls.commandResult({command:'presentation',success:false,message:'Presentation unavailable'});
  assert.deepEqual(feedback.at(-1), ['Presentation unavailable','error','command']);
});
