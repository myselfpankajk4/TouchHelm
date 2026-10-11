/* Independent control-console surfaces. Native effects only cross client.send. */
(() => {
  const modifiers = new Set(['lctrl', 'rctrl', 'lshift', 'rshift', 'lalt', 'ralt', 'win']);
  const keyGroups = [
    ['Numbers', [['backquote','`'], ...'1234567890'.split('').map(key => [key,key]), ['minus','−'], ['equal','=']]],
    ['Letters', [...'qwertyuiopasdfghjklzxcvbnm'.split('').map(key => [key,key.toUpperCase()])]],
    ['Chords', [['lctrl','Ctrl'], ['lshift','Shift'], ['lalt','Alt'], ['win','Win'], ['space','Space'], ['backspace','Backspace'], ['enter','Enter']]],
    ['Symbols', [['bracketleft','['], ['bracketright',']'], ['backslash','\\'], ['semicolon',';'], ['quote',"'"], ['comma',','], ['period','.'], ['slash','/']]],
    ['Navigation', [['esc','Esc'], ['tab','Tab'], ['insert','Insert'], ['delete','Delete'], ['home','Home'], ['end','End'], ['pageup','Pg Up'], ['pagedown','Pg Down'], ['left','Left'], ['up','Up'], ['down','Down'], ['right','Right']]],
    ['Function keys', Array.from({length:12},(_,i) => [`f${i+1}`,`F${i+1}`])],
    ['Advanced keys', [['rctrl','Right Ctrl'], ['rshift','Right Shift'], ['ralt','Right Alt'],
      ['capslock','Caps lock'], ['printscreen','Print screen'], ['scrolllock','Scroll lock'], ['pause','Pause'],
      ...Array.from({length:12},(_,i) => [`f${i+13}`,`F${i+13}`])]],
  ];
  const numpad = [['numlock','Num lock'], ['numpaddivide','/'], ['numpadmultiply','×'], ['numpadsubtract','−'],
    ['numpad7','7'], ['numpad8','8'], ['numpad9','9'], ['numpadadd','+'],
    ['numpad4','4'], ['numpad5','5'], ['numpad6','6'], ['numpadenter','Enter'],
    ['numpad1','1'], ['numpad2','2'], ['numpad3','3'], ['numpad0','0'], ['numpaddecimal','.']];
  const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
  const clock = value => { const seconds = number(value); if (seconds === null) return '—';
    const whole = Math.max(0, Math.floor(seconds)); return `${Math.floor(whole/60)}:${String(whole%60).padStart(2,'0')}`; };

  class TouchHelmControls {
    constructor(client) {
      this.client = client; this.connected = !!client.isConnected;
      this.held = new Set(); this.latched = new Set(); this.pointers = new Map();
      this.keyButtons = []; this.apps = []; this.mediaItems = []; this.pendingApps = new Set();
      this.ids = {};
      for (const id of ['typingDock','typeInput','btnTypingDone','typingActions','touchSurface',
        'nativeKeyboard','nativeNumpad','keyboardModeKeys','keyboardModeNumpad','viewNumpad','keyboardKeys',
        'heldKeys','btnReleaseKeys','presentationApp','presentationTitle','presentationStatus','presentationSlide','presentationSlideTitle',
        'mediaSessionSelect','mediaTitle','mediaArtist','mediaStatus','mediaPosition','mediaDuration','mediaProgress',
        'mediaLibraryMessage','mediaLibrary','btnRefreshMedia','appSearch','appsStatus','appsList','btnRefreshApps']) {
        this.ids[id] = document.getElementById(id);
      }
      this.buildKeyboard(); this.bindTyping(); this.bindCatalogs();
      this.ids.btnReleaseKeys?.addEventListener('click', () => this.releaseKeys());
      this.ids.keyboardModeKeys?.addEventListener('click', () => this.showKeyboardMode('keys'));
      this.ids.keyboardModeNumpad?.addEventListener('click', () => this.showKeyboardMode('numpad'));
      window.addEventListener('blur', () => this.releaseKeys());
      document.addEventListener('visibilitychange', () => { if (document.hidden) this.releaseKeys(); });
      window.addEventListener('pagehide', () => this.releaseKeys());
      document.addEventListener('pointerup', event => this.endPointer(event));
      document.addEventListener('pointercancel', () => this.releaseKeys());
      this.showKeyboardMode('keys'); this.updateHeld(); this.updateConnection();
      this.syncViewport(); window.addEventListener('resize', () => this.syncViewport());
      window.visualViewport?.addEventListener('resize', () => this.syncViewport());
    }

    send(message) { return this.client.send(message) === true; }
    node(tag, text, className) {
      const element = document.createElement(tag); if (text != null) element.textContent = String(text);
      if (className) element.className = className; return element;
    }
    text(id, value) { if (this.ids[id]) this.ids[id].textContent = String(value ?? ''); }

    buildKeyboard() {
      const ordered = [keyGroups[2], keyGroups[1], keyGroups[0], ...keyGroups.slice(3)];
      for (const [label, keys] of ordered) {
        const primary = label === 'Chords' || label === 'Letters';
        const section = this.node(primary ? 'section' : 'details', null, 'keyboard-group');
        section.appendChild(this.node(primary ? 'h3' : 'summary', label === 'Chords' ? 'Modifiers & editing' : label, 'key-group-label'));
        const grid = this.node('div', null, 'native-key-grid');
        for (const [key, name] of keys) grid.appendChild(this.makeKey(key, name));
        section.appendChild(grid); this.ids.nativeKeyboard?.appendChild(section);
      }
      for (const [key, label] of numpad) this.ids.nativeNumpad?.appendChild(this.makeKey(key,label));
    }
    makeKey(key, label) {
      const button = this.node('button', label, `native-key${modifiers.has(key) ? ' modifier-key' : ''}`);
      button.type = 'button'; button.dataset.key = key;
      button.setAttribute('aria-label', `${label}${key.startsWith('numpad') ? ' on numpad' : ''}`);
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('pointerdown', event => this.startPointer(event,key,button));
      button.addEventListener('pointerup', event => this.endPointer(event));
      button.addEventListener('pointercancel', () => this.releaseKeys());
      button.addEventListener('lostpointercapture', event => {
        if (this.pointers.has(event.pointerId)) this.releaseKeys();
      });
      button.addEventListener('click', event => {
        if (event.detail !== 0 || button.disabled) return;
        if (modifiers.has(key)) {
          if (this.latched.has(key)) this.up(key);
          else if (this.down(key)) this.latched.add(key);
        } else if (this.down(key)) { this.up(key); this.releaseLatched(); }
        this.updateHeld();
      });
      this.keyButtons.push(button); return button;
    }
    down(key) {
      if (!this.connected || this.held.has(key)) return false;
      if (!this.send({type:'keydown',key})) return false;
      this.held.add(key); this.client.vibrate?.(8); this.updateHeld(); return true;
    }
    up(key) {
      if (this.held.has(key)) this.send({type:'keyup',key});
      this.held.delete(key); this.latched.delete(key); this.updateHeld();
    }
    startPointer(event, key, button) {
      if (button.disabled || !this.connected || (event.button != null && event.button !== 0)) return;
      event.preventDefault();
      if (this.pointers.has(event.pointerId)) return;
      const toggledOff = modifiers.has(key) && this.latched.has(key);
      if (toggledOff) this.up(key);
      else if (!this.down(key)) return;
      if (!modifiers.has(key)) for (const pointer of this.pointers.values()) if (modifiers.has(pointer.key)) pointer.used = true;
      this.pointers.set(event.pointerId,{key,button,started:Date.now(),used:false,toggledOff});
      try { button.setPointerCapture(event.pointerId); } catch (_) {}
      this.updateHeld();
    }
    endPointer(event) {
      const pointer = this.pointers.get(event.pointerId); if (!pointer) return;
      event.preventDefault(); this.pointers.delete(event.pointerId);
      if (!pointer.toggledOff) {
        if (modifiers.has(pointer.key) && !pointer.used && Date.now()-pointer.started < 400) this.latched.add(pointer.key);
        else this.up(pointer.key);
      }
      try { pointer.button.releasePointerCapture(event.pointerId); } catch (_) {}
      if (!modifiers.has(pointer.key) && ![...this.held].some(key => !modifiers.has(key))) this.releaseLatched();
      this.updateHeld();
    }
    releaseLatched() { for (const key of [...this.latched]) this.up(key); }
    releaseKeys() {
      this.pointers.clear();
      for (const key of [...this.held]) this.up(key);
      this.latched.clear(); this.updateHeld();
    }
    updateHeld() {
      for (const button of this.keyButtons) {
        const held = this.held.has(button.dataset.key);
        button.setAttribute('aria-pressed',String(held)); button.classList.toggle('held',held);
      }
      const labels = [...this.held].map(key => this.keyButtons.find(button => button.dataset.key === key)?.textContent || key);
      this.text('heldKeys', labels.length ? `Held: ${labels.join(' + ')}` : 'Tap a modifier to latch it for the next key.');
      if (this.ids.btnReleaseKeys) this.ids.btnReleaseKeys.disabled = this.held.size === 0;
    }
    showKeyboardMode(mode) {
      this.releaseKeys(); const numpad = mode === 'numpad';
      if (this.ids.keyboardKeys) this.ids.keyboardKeys.hidden = numpad;
      if (this.ids.viewNumpad) this.ids.viewNumpad.hidden = !numpad;
      this.ids.keyboardModeKeys?.setAttribute('aria-selected',String(!numpad));
      this.ids.keyboardModeNumpad?.setAttribute('aria-selected',String(numpad));
    }

    bindTyping() {
      this.ids.typeInput?.addEventListener('focus', () => this.expandTyping());
      this.ids.typeInput?.addEventListener('input', () => this.resizeTyping());
      this.ids.btnTypingDone?.addEventListener('click', () => this.collapseTyping());
    }
    expandTyping() {
      this.ids.typingDock?.classList.add('expanded');
      document.getElementById('viewTrackpad')?.classList.add('typing-expanded');
      this.ids.btnTypingDone?.setAttribute('aria-expanded','true'); this.resizeTyping();
    }
    collapseTyping() {
      this.ids.typingDock?.classList.remove('expanded');
      document.getElementById('viewTrackpad')?.classList.remove('typing-expanded');
      this.ids.btnTypingDone?.setAttribute('aria-expanded','false');
      if (this.ids.typeInput) this.ids.typeInput.style.height = '44px';
      this.ids.typeInput?.blur(); this.ids.touchSurface?.focus();
    }
    resizeTyping() {
      const field = this.ids.typeInput; if (!field || !this.ids.typingDock?.classList.contains('expanded')) return;
      field.style.height = 'auto';
      const limit = Math.max(72, Math.min(176, (window.visualViewport?.height || window.innerHeight)*.34));
      field.style.height = `${Math.max(44, Math.min(field.scrollHeight,limit))}px`;
    }
    syncViewport() {
      const height = window.visualViewport?.height || window.innerHeight;
      document.documentElement.style.setProperty('--viewport-height',`${Math.round(height)}px`); this.resizeTyping();
    }

    bindCatalogs() {
      this.ids.appSearch?.addEventListener('input', () => this.drawApps());
      this.ids.btnRefreshApps?.addEventListener('click', () => this.requestApps());
      this.ids.btnRefreshMedia?.addEventListener('click', () => this.requestMedia());
      this.ids.mediaSessionSelect?.addEventListener('change', () => {
        this.client.selectedMediaSession = this.ids.mediaSessionSelect.value;
        if (this.lastDesktopState) this.renderDesktopState(this.lastDesktopState);
        this.send({type:'get_desktop_state'}); this.requestMedia();
      });
    }
    requestApps() {
      if (!this.connected) return;
      this.text('appsStatus','Loading installed apps…'); this.send({type:'get_apps'});
    }
    requestMedia() {
      if (!this.connected) return;
      this.text('mediaLibraryMessage','Loading media…'); this.send({type:'get_media_library'});
    }
    onViewChange(viewId) {
      this.releaseKeys();
      if (viewId !== 'viewTrackpad') this.collapseTyping();
      if (!this.connected) return;
      if (viewId === 'viewApps') this.requestApps();
      if (viewId === 'viewMedia') this.requestMedia();
      if (viewId === 'viewPresenter' || viewId === 'viewMedia') this.send({type:'get_desktop_state'});
    }
    setConnected(connected) {
      const wasConnected = this.connected;
      if (!connected) this.releaseKeys();
      this.connected = !!connected; this.updateConnection();
      if (this.connected && !wasConnected) {
        this.send({type:'get_desktop_state'}); this.requestApps(); this.requestMedia();
      }
    }
    updateConnection() {
      for (const button of this.keyButtons) button.disabled = !this.connected;
      for (const id of ['btnRefreshApps','btnRefreshMedia','mediaSessionSelect']) if (this.ids[id]) this.ids[id].disabled = !this.connected;
      this.drawApps(); this.drawMediaItems();
      if (!this.connected) {
        this.text('appsStatus','Connect to your PC to launch apps.');
        this.text('mediaLibraryMessage','Connect to your PC to load media.');
        this.text('presentationStatus','Offline'); this.text('mediaStatus','Offline');
      }
    }

    renderApps(apps) {
      this.apps = (Array.isArray(apps) ? apps : []).filter(app => app && typeof app.id === 'string' && typeof app.name === 'string');
      this.apps.sort((a,b) => Number(!!b.running)-Number(!!a.running) || (number(b.launches)||0)-(number(a.launches)||0) || a.name.localeCompare(b.name));
      this.pendingApps.clear(); this.drawApps();
    }
    drawApps() {
      const list = this.ids.appsList; if (!list) return;
      const query = (this.ids.appSearch?.value || '').trim().toLocaleLowerCase();
      const apps = this.apps.filter(app => app.name.toLocaleLowerCase().includes(query));
      list.replaceChildren();
      for (const app of apps) {
        const button = this.node('button',null,'catalog-item app-item'); button.type='button'; button.dataset.appId=app.id;
        button.disabled=!this.connected || this.pendingApps.has(app.id);
        const mark=this.node('span',(Array.from(app.name.trim())[0] || 'A').toUpperCase(),'app-monogram'); mark.setAttribute('aria-hidden','true');
        const text=this.node('span',null,'catalog-text'); text.appendChild(this.node('strong',app.name));
        text.appendChild(this.node('span',app.running ? 'Running' : number(app.launches)>0 ? `${app.launches} TouchHelm launches` : 'Installed app'));
        button.append(mark,text);
        button.addEventListener('click',() => {
          if (!this.connected || this.pendingApps.has(app.id)) return;
          if (this.send({type:'launch_app',app_id:app.id})) {
            this.pendingApps.add(app.id); button.disabled=true; this.text('appsStatus',`Opening ${app.name}…`);
          }
        }); list.appendChild(button);
      }
      this.text('appsStatus', !this.connected ? 'Connect to your PC to launch apps.' : apps.length ? `${apps.length} ${apps.length===1?'app':'apps'}` : query ? 'No apps match your search.' : 'No apps reported. Refresh to try again.');
    }
    renderMediaLibrary(catalog = {}) {
      const selector=this.ids.mediaSessionSelect, selected=this.client.selectedMediaSession || '';
      const sessions=Array.isArray(catalog.sessions)?catalog.sessions:[];
      this.mediaSessions=sessions;
      if (selector) {
        selector.replaceChildren(); const automatic=this.node('option','Active player'); automatic.value=''; selector.appendChild(automatic);
        for (const session of sessions) {
          const id=session.id || session.session_id; if (typeof id !== 'string') continue;
          const option=this.node('option',session.app || session.title || id); option.value=id; selector.appendChild(option);
        }
        selector.value=sessions.some(session => (session.id||session.session_id)===selected)?selected:'';
        this.client.selectedMediaSession=selector.value;
      }
      this.mediaItems=(Array.isArray(catalog.items)?catalog.items:[]).filter(item => item && typeof item.id==='string');
      this.text('mediaLibraryMessage',catalog.playlist_message || (catalog.playlist_supported ? 'Player queue' : 'No player queue is available. Local media appears here when available.'));
      this.drawMediaItems();
      if (this.lastDesktopState) this.renderDesktopState(this.lastDesktopState);
    }
    drawMediaItems() {
      const list=this.ids.mediaLibrary; if (!list) return; list.replaceChildren();
      for (const item of this.mediaItems) {
        const button=this.node('button',null,'catalog-item media-item'); button.type='button'; button.dataset.itemId=item.id; button.disabled=!this.connected;
        const text=this.node('span',null,'catalog-text'); text.appendChild(this.node('strong',item.title || 'Untitled media'));
        text.appendChild(this.node('span',item.subtitle || (item.kind==='local'?'Local file':item.kind==='queue'?'Player queue':'Media session')));
        button.appendChild(text); button.addEventListener('click',() => {
          if (!this.connected) return;
          const message={type:'play_media',item_id:item.id}; if (this.client.selectedMediaSession) message.session_id=this.client.selectedMediaSession;
          if (this.send(message)) this.text('mediaLibraryMessage',`Opening ${item.title || 'media'}…`);
        }); list.appendChild(button);
      }
    }
    renderDesktopState(state = {}) {
      this.lastDesktopState=state;
      const presentation=state.presentation || {};
      let media=state.media || {};
      if (this.client.selectedMediaSession) {
        const sessions=Array.isArray(media.sessions)?media.sessions:(this.mediaSessions || []);
        media=sessions.find(session => (session.session_id || session.id)===this.client.selectedMediaSession) || {
          available:false, title:'Selected player unavailable',
          message:'The selected player is no longer available. Refresh to choose another.',
        };
      }
      this.text('presentationApp',presentation.app || 'Presentation');
      this.text('presentationTitle',presentation.title || 'No presentation in focus');
      this.text('presentationStatus',presentation.message || (presentation.available ? presentation.active?'Slideshow active':'Ready to present':'Presentation details unavailable'));
      const slide=number(presentation.slide), total=number(presentation.total);
      this.text('presentationSlide',slide!==null && slide>0 ? `Slide ${slide}${total!==null && total>0?` of ${total}`:''}` : 'Slide details unavailable');
      this.text('presentationSlideTitle',presentation.slide_title || '');
      if (this.ids.presentationSlideTitle) this.ids.presentationSlideTitle.hidden=!presentation.slide_title;
      this.text('mediaTitle',media.title || 'Nothing playing');
      this.text('mediaArtist',[media.artist,media.album].filter(Boolean).join(' · ') || media.app || 'Choose a player or open media on your PC.');
      this.text('mediaStatus',media.message || (media.available ? media.status || 'Playback status unavailable':'No media session available'));
      this.text('mediaPosition',clock(media.position)); this.text('mediaDuration',clock(media.duration));
      const position=number(media.position), duration=number(media.duration), progress=this.ids.mediaProgress;
      if (progress) {
        progress.hidden=position===null || duration===null || duration<=0;
        if (!progress.hidden) {
          progress.style.setProperty('--progress',`${Math.max(0,Math.min(100,position/duration*100))}%`);
          progress.setAttribute('aria-label',`${clock(position)} of ${clock(duration)}`);
        }
      }
    }
    commandResult(result = {}) {
      const quietSuccess = ['presentation','media','play_media','get_desktop_state','get_apps','get_media_library'].includes(result.command);
      if (!result.success || !quietSuccess) {
        this.client.showFeedback?.(result.message || (result.success?'Command completed.':'The PC could not complete this command.'),result.success?'success':'error','command');
      }
      if (!result.success && result.command==='get_apps') this.text('appsStatus',result.message || 'Apps could not load. Refresh to try again.');
      if (!result.success && result.command==='get_media_library') this.text('mediaLibraryMessage',result.message || 'Media could not load. Refresh to try again.');
      if (!result.success && result.command==='get_desktop_state') {
        this.text('presentationStatus',result.message || 'Desktop context is unavailable.');
        this.text('mediaStatus',result.message || 'Desktop context is unavailable.');
      }
      if (result.command==='launch_app') { this.pendingApps.clear(); this.drawApps(); if (result.success) this.requestApps(); }
      if (result.command==='play_media' || result.command==='media') {
        if (!result.success) this.text('mediaLibraryMessage',result.message || 'Media could not start.');
        else { this.send({type:'get_desktop_state'}); this.requestMedia(); }
      }
    }
  }
  window.TouchHelmControls=TouchHelmControls;
})();
