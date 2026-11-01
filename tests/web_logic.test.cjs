const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function loadClient() {
  const context = vm.createContext({
    document: { addEventListener() {} },
    window: {}, navigator: {}, console,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Intl, WebSocket: { OPEN: 1 },
  });
  return vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8') + '\nTouchHelmClient', context);
}

function element() {
  return {
    value: '', checked: true, events: {},
    addEventListener(name, fn) { this.events[name] = fn; },
    click() { this.events.click?.({ preventDefault() {} }); },
    emit(name, props = {}) { this.events[name]?.({ preventDefault() {}, ...props }); },
  };
}

function keyboard() {
  const client = Object.create(loadClient().prototype);
  const messages = [];
  Object.assign(client, {
    typeInput: element(), btnSendText: element(), btnClearText: element(),
    chkRealtimeTyping: element(), keyBtns: [], macroBtns: [],
    liveTextValue: '', isComposing: false, isConnected: true,
    send(msg) { if (!this.isConnected) return false; messages.push(JSON.parse(JSON.stringify(msg))); return true; },
    vibrate() {},
  });
  client.bindKeyboardControls();
  const input = (value, props = {}) => {
    client.typeInput.value = value;
    client.typeInput.emit('input', props);
  };
  return { client, messages, input };
}

test('live typing transmits pasted text even when InputEvent.data is null', () => {
  const { messages, input } = keyboard();
  input('pasted text', { inputType: 'insertFromPaste', data: null });
  assert.deepEqual(messages, [{ type: 'text', text: 'pasted text' }]);
});

test('autocorrect replaces the existing remote suffix instead of appending a duplicate', () => {
  const { messages, input } = keyboard();
  input('helo', { data: 'helo' });
  input('hello', { inputType: 'insertReplacementText', data: 'hello' });
  assert.deepEqual(messages, [
    { type: 'text', text: 'helo' }, { type: 'key', key: 'backspace' },
    { type: 'text', text: 'lo' },
  ]);
});

test('deleting a selected word sends every required backspace', () => {
  const { messages, input } = keyboard();
  input('hello world', { data: 'hello world' });
  messages.length = 0;
  input('hello ', { inputType: 'deleteContentBackward', data: null });
  assert.equal(messages.length, 5);
  assert.ok(messages.every(msg => msg.type === 'key' && msg.key === 'backspace'));
});

test('composition commits once and ignores Enter used to accept an IME candidate', () => {
  const { client, messages, input } = keyboard();
  client.typeInput.emit('compositionstart');
  input('に', { data: 'に', isComposing: true });
  input('日本', { data: '日本', isComposing: true });
  client.typeInput.emit('keydown', { key: 'Enter', isComposing: true });
  assert.equal(messages.length, 0);
  client.typeInput.emit('compositionend');
  input('日本', { data: '日本', isComposing: false });
  assert.deepEqual(messages, [{ type: 'text', text: '日本' }]);
});

test('Send preserves an offline buffered draft', () => {
  const { client, messages } = keyboard();
  client.isConnected = false;
  client.chkRealtimeTyping.checked = false;
  client.typeInput.value = 'keep me';
  client.btnSendText.click();
  assert.equal(client.typeInput.value, 'keep me');
  assert.equal(messages.length, 0);
});

test('turning live sync on transmits the buffered draft before further edits', () => {
  const { client, messages, input } = keyboard();
  client.chkRealtimeTyping.checked = false;
  input('draft');
  client.chkRealtimeTyping.checked = true;
  client.chkRealtimeTyping.emit('change');
  input('draft!', { data: '!' });
  assert.deepEqual(messages, [{ type: 'text', text: 'draft' }, { type: 'text', text: '!' }]);
});

test('Clear resets the local baseline without deleting already sent text', () => {
  const { client, messages, input } = keyboard();
  input('first', { data: 'first' });
  client.btnClearText.click();
  input('second', { data: 'second' });
  assert.deepEqual(messages, [{ type: 'text', text: 'first' }, { type: 'text', text: 'second' }]);
});

test('a double tap emits two clicks total', () => {
  const client = Object.create(loadClient().prototype);
  const messages = [];
  Object.assign(client, {
    touchSurface: element(), touchStartTime: 0, lastTapTime: 0,
    tapToClick: true, isDragging: false, touchIndicator: null,
    send(msg) { messages.push(JSON.parse(JSON.stringify(msg))); return true; }, vibrate() {},
  });
  client.touchSurface.getBoundingClientRect = () => ({ left: 0, top: 0 });
  client.bindTrackpadGestures();
  const point = { clientX: 20, clientY: 20 };
  for (let i = 0; i < 2; i++) {
    client.touchSurface.emit('touchstart', { touches: [point] });
    client.touchSurface.emit('touchend', { touches: [] });
  }
  assert.deepEqual(messages, [{ type: 'click', button: 'left' }, { type: 'click', button: 'left' }]);
});

test('focused trackpad has keyboard movement, scroll and click alternatives', () => {
  const client = Object.create(loadClient().prototype), messages = [];
  client.touchSurface=element();client.send=packet=>messages.push(JSON.parse(JSON.stringify(packet)));
  client.bindTrackpadGestures();
  client.touchSurface.emit('keydown',{key:'ArrowRight'});
  client.touchSurface.emit('keydown',{key:'ArrowUp',shiftKey:true});
  client.touchSurface.emit('keydown',{key:'PageDown'});
  client.touchSurface.emit('keydown',{key:'Enter'});
  assert.deepEqual(messages,[{type:'move',dx:12,dy:0},{type:'move',dx:0,dy:-36},{type:'scroll',dx:0,dy:-3},{type:'click',button:'left'}]);
});

test('send rejects disconnected input and reports the outcome', () => {
  const client = Object.create(loadClient().prototype);
  const messages = [];
  client.ws = { readyState: 1, send(text) { messages.push(JSON.parse(text)); } };
  client.isConnected = false;
  assert.equal(client.send({ type: 'text', text: 'blocked' }), false);
  client.isConnected = true;
  assert.equal(client.send({ type: 'text', text: 'ready' }), true);
  assert.deepEqual(messages, [{ type: 'text', text: 'ready' }]);
});

test('slow two-finger scrolling never sends a right click when fingers lift', () => {
  const client = Object.create(loadClient().prototype);
  const messages = [];
  Object.assign(client, {
    touchSurface: element(), lastTapTime: 0, tapToClick: true, isDragging: false,
    send(msg) { messages.push(JSON.parse(JSON.stringify(msg))); return true; },
    vibrate() {}, updateTouchFps() {},
  });
  client.bindTrackpadGestures();
  const points = y => [{ clientX: 20, clientY: y }, { clientX: 40, clientY: y }];
  client.touchSurface.emit('touchstart', { touches: points(20) });
  for (const y of [24, 28, 32, 36]) client.touchSurface.emit('touchmove', { touches: points(y) });
  client.touchSurface.emit('touchend', { touches: [] });
  assert.equal(messages.filter(msg => msg.type === 'scroll').length, 4);
  assert.equal(messages.filter(msg => msg.type === 'click').length, 0);
});
