/**
 * TouchHelm - Client Application Logic
 * Ultra-low latency WebSocket input controller, presentation remote, and multi-touch gestures.
 */

// Carry forward settings and saved drafts when upgrading the former app name.
function migrateLegacyStorage(storage) {
  try {
    const oldKeys = [];
    for (let index = 0; index < storage.length; index++) {
      const key = storage.key(index);
      if (key?.startsWith('phonepad_')) oldKeys.push(key);
    }
    for (const key of oldKeys) {
      const next = 'touchhelm_' + key.slice('phonepad_'.length);
      if (storage.getItem(next) === null) storage.setItem(next, storage.getItem(key));
    }
  } catch { /* Restricted storage must not prevent the remote from opening. */ }
}

class TouchHelmClient {
  constructor() {
    migrateLegacyStorage(localStorage);
    if (typeof sessionStorage !== 'undefined') migrateLegacyStorage(sessionStorage);
    this.ws = null;
    const currentHost = (window.location.host && window.location.host.trim() !== "") ? window.location.host : null;
    this.host = currentHost || localStorage.getItem("touchhelm_host") || "localhost:8765";
    if (currentHost) {
      localStorage.setItem("touchhelm_host", currentHost);
    }
    this.currentTheme = localStorage.getItem("touchhelm_theme") || "cyber";

    // Settings
    this.sensitivity = parseFloat(localStorage.getItem("touchhelm_sens")) || 1.3;
    this.acceleration = parseFloat(localStorage.getItem("touchhelm_accel")) || 1.25;
    this.scrollSpeed = parseFloat(localStorage.getItem("touchhelm_scroll")) || 1.0;
    this.invertScroll = localStorage.getItem("touchhelm_invert") === "true";
    this.hapticsEnabled = localStorage.getItem("touchhelm_haptics") !== "false";
    this.tapToClick = localStorage.getItem("touchhelm_tap") !== "false";

    // Status
    this.isConnected = false;
    this.reconnectTimer = null;
    this.authPin = "";
    this.liveTextValue = "";
    this.isComposing = false;
    this.pingInterval = null;
    this.wakeLock = null;
    this.wakeLockRequested = false;
    this.deferredPrompt = null;

    // Touch & Trackpad State
    this.touchStartTime = 0;
    this.lastTouchPos = { x: 0, y: 0 };
    this.initialTouchPos = { x: 0, y: 0 };
    this.isDragging = false;
    this.tapTimer = null;
    this.lastTapTime = 0;
    this.twoFingerStartTime = 0;
    this.twoFingerMoved = false;

    // Telemetry rate tracking
    this.touchFrameCount = 0;
    this.lastFpsCalcTime = Date.now();

    // Gyro / Air Mouse
    this.gyroEnabled = false;
    this.lastOrientation = null;
    this.gyroHandler = null;

    // Laser state
    this.laserColor = "red";
    this.isLaserActive = false;

    // Timer state
    this.timerSeconds = 900; // 15 mins default
    this.timerInitial = 900;
    this.timerRunning = false;
    this.timerInterval = null;
    this.timerDeadline = null;

    // Volume & Brightness tracking state
    this.lastVolumeVal = null;
    this.isUserDraggingVol = false;
    this.lastVolSendTime = 0;
    this.lastBrightnessVal = null;
    this.isUserDraggingBright = false;
    this.lastBrightSendTime = 0;

    this.initElements();
    this.liveTypingExplicit=localStorage.getItem('touchhelm_live_typing')!==null;
    if(this.chkRealtimeTyping)this.chkRealtimeTyping.checked=localStorage.getItem('touchhelm_live_typing')!=='false';
    this.buildId = document.querySelector('meta[name="touchhelm-build"]')?.content || "";
    this.restoreSession();
    this.applyTheme(this.currentTheme, false);
    this.bindEvents();
    if (window.TouchHelmControls) this.controls = new window.TouchHelmControls(this);
    if (window.TouchHelmExperience) this.experience = new window.TouchHelmExperience(this);
    this.connect();
    this.initPwa();
    this.fetchServerConfig();
    if (this.timerRunning) {
      this.timerInterval = setInterval(() => this.tickTimer(), 250);
      this.tickTimer();
    }
  }

  vibrate(pattern = 12) {
    if (this.hapticsEnabled && navigator.vibrate) {
      try {
        navigator.vibrate(pattern);
      } catch (e) {}
    }
  }

  // --------------------------------------------------------------------------
  // DOM ELEMENT REFERENCES
  // --------------------------------------------------------------------------
  initElements() {
    // Status
    this.elStatusDot = document.getElementById("statusDot");
    this.elStatusLabel = document.getElementById("statusLabel");
    this.elStatusPing = document.getElementById("statusPing");
    this.elStatusPill = document.getElementById("statusPill");

    // Top buttons
    this.btnTheme = document.getElementById("btnTheme");
    this.btnWakeLock = document.getElementById("btnWakeLock");
    this.btnFullscreen = document.getElementById("btnFullscreen");
    this.btnSettings = document.getElementById("btnSettings");

    // Views & Nav
    this.views = document.querySelectorAll(".view");
    this.navTabs = document.querySelectorAll(".nav-tab");

    // Trackpad elements
    this.telCoords = document.getElementById("telCoords");
    this.telLink = document.getElementById("telLink");
    this.telFps = document.getElementById("telFps");
    this.touchSurface = document.getElementById("touchSurface");
    this.touchIndicator = document.getElementById("touchIndicator");
    this.dragLockBadge = document.getElementById("dragLockBadge");
    this.scrollStrip = document.getElementById("scrollStrip");
    this.btnLeftClick = document.getElementById("btnLeftClick");
    this.btnRightClick = document.getElementById("btnRightClick");
    this.btnMiddleClick = document.getElementById("btnMiddleClick");
    this.btnGyro = document.getElementById("btnGyro");

    // Scroll handle
    this.scrollHandle = document.querySelector("#scrollStrip .scroll-handle");

    // Presenter elements
    this.btnSlideNext = document.getElementById("btnSlideNext");
    this.btnSlidePrev = document.getElementById("btnSlidePrev");
    this.btnSlideStart = document.getElementById("btnSlideStart");
    this.btnSlideCurrent = document.getElementById("btnSlideCurrent");
    this.btnSlideBlack = document.getElementById("btnSlideBlack");
    this.btnSlideWhite = document.getElementById("btnSlideWhite");
    this.btnSlideEnd = document.getElementById("btnSlideEnd");

    // Presenter Timer
    this.timerDisplay = document.getElementById("timerDisplay");
    this.btnTimerStart = document.getElementById("btnTimerStart");
    this.btnTimerReset = document.getElementById("btnTimerReset");
    this.presetBtns = document.querySelectorAll(".preset-btn");

    // Laser Pointer
    this.laserSurface = document.getElementById("laserSurface");
    this.laserReticle = document.getElementById("laserReticle");
    this.laserColorIndicator = document.getElementById("laserColorIndicator");
    this.colorDots = document.querySelectorAll(".color-dot");

    // Media & Desktop
    this.btnVolUp = document.getElementById("btnVolUp");
    this.btnVolDown = document.getElementById("btnVolDown");
    this.btnVolMute = document.getElementById("btnVolMute");
    this.sliderVol = document.getElementById("sliderVol");
    this.lblVolLevel = document.getElementById("lblVolLevel");
    this.btnMediaPlay = document.getElementById("btnMediaPlay");
    this.btnMediaPrev = document.getElementById("btnMediaPrev");
    this.btnMediaNext = document.getElementById("btnMediaNext");
    this.btnShowDesktop = document.getElementById("btnShowDesktop");
    this.btnAppSwitch = document.getElementById("btnAppSwitch");
    this.btnTaskView = document.getElementById("btnTaskView");
    this.btnLockPc = document.getElementById("btnLockPc");
    this.btnWinSearch = document.getElementById("btnWinSearch");
    this.btnSnipTool = document.getElementById("btnSnipTool");
    this.shortcutBtns = document.querySelectorAll(".shortcut-btn");

    // Brightness elements
    this.btnBrightUp = document.getElementById("btnBrightUp");
    this.btnBrightDown = document.getElementById("btnBrightDown");
    this.sliderBright = document.getElementById("sliderBright");
    this.lblBrightLevel = document.getElementById("lblBrightLevel");

    // Keyboard & Macros
    this.typeInput = document.getElementById("typeInput");
    this.btnSendText = document.getElementById("btnSendText");
    this.btnClearText = document.getElementById("btnClearText");
    this.chkRealtimeTyping = document.getElementById("chkRealtimeTyping");
    this.btnKeyViewStart = document.getElementById("btnKeyViewStart");
    this.keyBtns = document.querySelectorAll(".key-btn");
    this.macroBtns = document.querySelectorAll(".macro-btn");

    // Numpad
    this.numBtns = document.querySelectorAll(".num-btn");

    this.pinModal = document.getElementById("pinModal");
    this.pinForm = document.getElementById("pinForm");
    this.pinInput = document.getElementById("pinInput");
    this.pinError = document.getElementById("pinError");
    this.uiFeedback = document.getElementById("uiFeedback");
    this.typingHint = document.getElementById("typingHint");
    this.settingsFeedback = document.getElementById("settingsFeedback");

    // Modals
    this.themeModal = document.getElementById("themeModal");
    this.btnCloseTheme = document.getElementById("btnCloseTheme");
    this.themeOptions = document.querySelectorAll(".theme-option");

    // Settings modal
    this.settingsModal = document.getElementById("settingsModal");
    this.btnCloseSettings = document.getElementById("btnCloseSettings");
    this.btnReconnect = document.getElementById("btnReconnect");
    this.settingHost = document.getElementById("settingHost");
    this.hostForm = document.getElementById("hostForm");
    this.sliderSens = document.getElementById("sliderSensitivity");
    this.valSens = document.getElementById("valSensitivity");
    this.sliderAccel = document.getElementById("sliderAccel");
    this.valAccel = document.getElementById("valAccel");
    this.sliderScroll = document.getElementById("sliderScroll");
    this.valScroll = document.getElementById("valScroll");
    this.chkInvertScroll = document.getElementById("chkInvertScroll");
    this.chkHaptics = document.getElementById("chkHaptics");
    this.chkTapToClick = document.getElementById("chkTapToClick");
    this.btnInstallPwa = document.getElementById("btnInstallPwa");
    this.pwaInstallBox = document.getElementById("pwaInstallBox");

    // Pre-populate settings form
    if (this.settingHost) this.settingHost.value = this.host;
    if (this.sliderSens) this.sliderSens.value = this.sensitivity;
    if (this.valSens) this.valSens.textContent = `${this.sensitivity.toFixed(1)}x`;
    if (this.sliderAccel) this.sliderAccel.value = this.acceleration;
    if (this.valAccel) this.valAccel.textContent = `${this.acceleration.toFixed(2)}x`;
    if (this.sliderScroll) this.sliderScroll.value = this.scrollSpeed;
    if (this.valScroll) this.valScroll.textContent = `${this.scrollSpeed.toFixed(1)}x`;
    if (this.chkInvertScroll) this.chkInvertScroll.checked = this.invertScroll;
    if (this.chkHaptics) this.chkHaptics.checked = this.hapticsEnabled;
    if (this.chkTapToClick) this.chkTapToClick.checked = this.tapToClick;
  }

  // --------------------------------------------------------------------------
  // THEME MANAGEMENT
  // --------------------------------------------------------------------------
  applyTheme(themeName, persist = true) {
    if (window.TouchHelmThemes) {
      const preference=window.TouchHelmThemes.apply(themeName,{},persist);
      this.currentTheme=preference.id;
      return;
    }
    if (!["cyber", "oled", "matrix", "nordic", "light"].includes(themeName)) return;
    this.currentTheme = themeName;
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("touchhelm_theme", themeName);

    // Update meta theme-color for mobile status bar
    const themeColors = {
      cyber: "#0d141c",
      oled: "#000000",
      matrix: "#050c08",
      nordic: "#0b1120",
      light: "#f8fafc"
    };
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme && themeColors[themeName]) {
      metaTheme.setAttribute("content", themeColors[themeName]);
    }

    // Update active checkmarks in Theme Picker modal
    if (this.themeOptions) {
      this.themeOptions.forEach(opt => {
        const optTheme = opt.getAttribute("data-theme-id");
        opt.classList.toggle("selected", optTheme === themeName);
        opt.setAttribute("aria-pressed", String(optTheme === themeName));
      });
    }

    if (persist) this.syncConfig({ theme: themeName });
  }

  // --------------------------------------------------------------------------
  // CONFIG SYNC WITH SERVER
  // --------------------------------------------------------------------------
  async fetchServerConfig() {
    const host = this.host;
    try {
      const resp = await fetch(`${this.httpBase()}/api/info`, { cache: "no-store" });
      if (resp.ok && host === this.host) {
        const info = await resp.json();
        this.applyServerConfig(info);
        if ('volume' in info) {
          this.onVolumeSync(info.volume, info.muted);
        }
        if ('brightness' in info) {
          this.onBrightnessSync(info.brightness);
        }
      }
    } catch (e) {
      // Offline or local file mode
    }
  }

  async syncConfig(delta) {
    const version = this.configRequestVersion = (this.configRequestVersion || 0) + 1;
    const keys = Object.keys(delta);
    this.configKeyVersions ||= new Map();
    this.unsavedConfigKeys ||= new Set();
    keys.forEach(key => this.configKeyVersions.set(key, version));
    const finish = (saved, message) => {
      // Each setting keeps its newest result, even when responses arrive out of order.
      for (const key of keys) {
        if (this.configKeyVersions.get(key) !== version) continue;
        if (saved) this.unsavedConfigKeys.delete(key);
        else this.unsavedConfigKeys.add(key);
      }
      this.updateSettingsFeedback();
      if (version === this.configRequestVersion) {
        this.showFeedback(saved && this.unsavedConfigKeys.size
          ? "This change was saved. Other changes still need to be saved." : message,
          saved ? "success" : "error", "settings");
      }
      return saved;
    };
    if (!this.isConnected) {
      return finish(false, "Connect to your PC to save these settings.");
    }
    const host = this.host;
    try {
      const resp = await fetch(`${this.httpBase()}/api/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-TouchHelm-Pin": this.authPin },
        body: JSON.stringify(delta)
      });
      if (host !== this.host) return false;
      if (!resp.ok) {
        return finish(false, resp.status === 401
          ? "Settings were not saved. Reconnect and enter your PC PIN."
          : "Settings were not saved. Try changing the setting again.");
      }
      return finish(true, "Settings saved.");
    } catch (e) {
      if (host === this.host) return finish(false, "Settings were not saved. Check your connection and try again.");
      return false;
    }
  }

  updateSettingsFeedback() {
    if (!this.settingsFeedback) return;
    const names = { mouse_sensitivity: "Pointer speed", mouse_acceleration: "Pointer acceleration",
      scroll_speed: "Scroll speed", invert_scroll: "Natural scrolling", theme: "Theme", laser_color: "Laser color" };
    const keys = Array.from(this.unsavedConfigKeys || []);
    this.settingsFeedback.textContent = keys.length
      ? `Changes were not saved: ${keys.map(key => names[key] || key).join(", ")}. Adjust these settings again to retry.` : "";
    this.settingsFeedback.hidden = !keys.length;
  }

  httpBase() {
    return `${window.location.protocol === "https:" ? "https:" : "http:"}//${this.host}`;
  }

  applyServerConfig(config) {
    const settings = [
      ["mouse_sensitivity", "sensitivity", "sliderSens", "valSens", "touchhelm_sens", 1],
      ["mouse_acceleration", "acceleration", "sliderAccel", "valAccel", "touchhelm_accel", 2],
      ["scroll_speed", "scrollSpeed", "sliderScroll", "valScroll", "touchhelm_scroll", 1],
    ];
    for (const [key, prop, slider, label, storage, digits] of settings) {
      if (typeof config[key] === "number" && Number.isFinite(config[key])) {
        this[prop] = config[key];
        if (this[slider]) this[slider].value = config[key];
        if (this[label]) this[label].textContent = `${config[key].toFixed(digits)}x`;
        localStorage.setItem(storage, config[key]);
      }
    }
    if (typeof config.invert_scroll === "boolean") {
      this.invertScroll = config.invert_scroll;
      if (this.chkInvertScroll) this.chkInvertScroll.checked = config.invert_scroll;
      localStorage.setItem("touchhelm_invert", config.invert_scroll);
    }
    // Theme is local to each device; host updates must not restyle other phones.
    if (config.laser_color) this.setLaserColor(config.laser_color, false);
  }

  // --------------------------------------------------------------------------
  // WEBSOCKET & NETWORK
  // --------------------------------------------------------------------------
  connect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.releaseDragLock();
    this.controls?.releaseKeys();
    this.stopLaser();
    this.stopPing();
    this.isConnected = false;
    if (this.ws) {
      this.ws.onopen = this.ws.onmessage = this.ws.onclose = this.ws.onerror = null;
      try { this.ws.close(); } catch (e) {}
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${this.host}/ws`;

    console.log("[TouchHelm] Connecting to WebSocket at", wsUrl);
    this.setStatus("connecting", "Connecting...");
    try {
      this.ws = new WebSocket(wsUrl);
    } catch (e) {
      console.error("[TouchHelm] WebSocket init failed:", e);
      this.setStatus("disconnected", "Offline");
      this.scheduleReconnect();
      return;
    }

    const socket = this.ws;
    socket.onopen = () => {
      if (this.ws !== socket) return;
      this.authenticate();
    };

    socket.onmessage = (event) => {
      if (this.ws !== socket) return;
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "pong") {
          const rtt = Math.max(1, Math.round(Date.now() - msg.t));
          if (this.elStatusPing) this.elStatusPing.textContent = `${rtt}ms`;
        } else if (msg.type === "auth_res") {
          if (!msg.success) {
            this.isConnected = false;
            this.stopPing();
            this.showPin(msg.message || "Invalid PIN");
            return;
          }
          this.isConnected = true;
          this.closeModal(this.pinModal);
          this.setStatus("connected", "Connected");
          this.clearFeedback("connection");
          this.clearFeedback("typing");
          if(this.liveTypingPaused)this.showFeedback('Draft edited offline. Use Send to sync it explicitly.','info','typing');
          this.startPing();
          if (msg.config) this.applyServerConfig(msg.config);
          if ('volume' in msg) {
            this.onVolumeSync(msg.volume, msg.muted);
          }
          if ('brightness' in msg) {
            this.onBrightnessSync(msg.brightness);
          }
        } else if (msg.type === "auth_required") {
          this.releaseDragLock();
          this.isConnected = false;
          this.stopPing();
          this.authPin = "";
          this.showPin();
        } else if (msg.type === "config_sync") {
          if (msg.config) this.applyServerConfig(msg.config);
        } else if (msg.type === "volume_sync") {
          this.onVolumeSync(msg.volume, msg.muted);
        } else if (msg.type === "brightness_sync") {
          this.onBrightnessSync(msg.level);
        } else if (msg.type === "desktop_state") {
          this.controls?.renderDesktopState(msg);
        } else if (msg.type === "apps_sync") {
          this.controls?.renderApps(msg.apps || []);
        } else if (msg.type === "media_library") {
          this.controls?.renderMediaLibrary(msg);
        } else if (msg.type === 'presentation_details') {
          this.experience?.presentationDetails(msg);
        } else if (msg.type === 'displays') {
          this.experience?.displays(msg);
        } else if (msg.type === "command_result") {
          if (this.controls) this.controls.commandResult(msg);
          else if (!msg.success) this.showFeedback(msg.message || "The PC could not complete this action.", "error", "command");
        }
      } catch (e) {}
    };

    socket.onclose = () => {
      if (this.ws !== socket) return;
      this.isConnected = false;
      this.stopPing();
      this.setStatus("disconnected", "Offline");
      if (this.pinModal?.classList.contains("open") && this.pinError) {
        this.pinError.textContent = "PC disconnected. Reconnecting…";
      }
      this.releaseDragLock();
      this.stopLaser();
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      if (this.ws !== socket) return;
      this.isConnected = false;
      this.stopPing();
      this.setStatus("disconnected", "Failed");
      this.releaseDragLock();
    };
  }

  scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.isConnected) this.connect();
    }, 2500);
  }

  authenticate() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "auth", pin: this.authPin,
        device_name: `${navigator.platform || "Mobile"} TouchHelm` }));
    }
  }

  showPin(error = "") {
    this.setStatus("disconnected", "PIN required");
    if (this.pinError) this.pinError.textContent = error;
    this.openModal(this.pinModal, this.pinInput);
    if (this.pinInput) { this.pinInput.value = ""; this.pinInput.focus(); }
  }

  showFeedback(message, kind = "info", source = "") {
    if (!this.uiFeedback) return;
    clearTimeout(this.feedbackTimer);
    const version = this.feedbackVersion = (this.feedbackVersion || 0) + 1;
    this.uiFeedback.textContent = message;
    this.uiFeedback.hidden = !message;
    this.uiFeedback.setAttribute("data-kind", kind);
    this.uiFeedback.setAttribute("data-source", source);
    if (message) {
      this.feedbackTimer = setTimeout(() => {
        if (this.feedbackVersion === version && this.uiFeedback.textContent === message && this.uiFeedback.getAttribute("data-source") === source) {
          this.clearFeedback(source);
        }
      }, kind === "error" ? 8000 : 4000);
    }
  }

  clearFeedback(source) {
    if (!this.uiFeedback || (source && this.uiFeedback.getAttribute("data-source") !== source)) return;
    clearTimeout(this.feedbackTimer);
    this.feedbackTimer = null;
    this.feedbackVersion = (this.feedbackVersion || 0) + 1;
    this.uiFeedback.textContent = "";
    this.uiFeedback.hidden = true;
  }

  openModal(modal, initialFocus) {
    if (!modal) return;
    if (this.activeModal === modal) return;
    this.controls?.releaseKeys();
    this.modalStack ||= [];
    if (modal === this.pinModal) this.modalStack = [];
    if (this.activeModal) {
      if (modal !== this.pinModal) this.modalStack.push({ modal: this.activeModal,
        focus: document.activeElement, returnFocus: this.modalReturnFocus });
      this.closeModal(this.activeModal, false);
    }
    this.modalReturnFocus = document.activeElement;
    this.activeModal = modal;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    if (!this.modalKeysBound) {
      this.modalKeysBound = true;
      document.addEventListener("keydown", (event) => {
        const current = this.activeModal;
        if (!current) return;
        if (event.key === "Escape") {
          event.preventDefault();
          if (current !== this.pinModal) this.closeModal(current);
        } else if (event.key === "Tab") {
          const controls = this.modalFocusables(current);
          const first = controls[0] || current, last = controls[controls.length - 1] || current;
          if (event.shiftKey && (document.activeElement === first || !current.contains(document.activeElement))) {
            event.preventDefault(); last.focus();
          } else if (!event.shiftKey && (document.activeElement === last || !current.contains(document.activeElement))) {
            event.preventDefault(); first.focus();
          }
        }
      });
      document.addEventListener("focusin", (event) => {
        if (this.activeModal && !this.activeModal.contains(event.target)) {
          (this.modalFocusables(this.activeModal)[0] || this.activeModal).focus();
        }
      });
    }
    const focus = initialFocus || this.modalFocusables(modal)[0] || modal;
    if (focus === modal) modal.setAttribute("tabindex", "-1");
    focus.focus();
  }

  modalFocusables(modal) {
    return Array.from(modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]'))
      .filter(control => !control.hidden && control.getClientRects().length > 0);
  }

  closeModal(modal, restoreFocus = true) {
    if (!modal || !modal.classList.contains("open")) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    const wasActive = this.activeModal === modal;
    if (wasActive) this.activeModal = null;
    if (restoreFocus) {
      if (wasActive && this.modalStack?.length) {
        const previous = this.modalStack.pop();
        this.openModal(previous.modal, previous.focus);
        this.modalReturnFocus = previous.returnFocus;
        return;
      }
      const previous = this.modalReturnFocus;
      const fallback = Array.from(this.navTabs || []).find(tab => tab.classList.contains("active")) || this.elStatusPill || document.body;
      const target = previous?.isConnected && !previous.disabled && previous.getClientRects().length ? previous : fallback;
      if (target === document.body) target.setAttribute("tabindex", "-1");
      target?.focus();
    }
    this.modalReturnFocus = null;
  }

  connectToHost() {
    const input = this.settingHost?.value.trim() || "";
    try {
      const url = new URL(input.includes("://") ? input : `http://${input}`);
      if (!input || !url.hostname || url.username || url.password || !["http:", "https:", "ws:", "wss:"].includes(url.protocol)) throw new Error("Invalid address");
      if (this.host !== url.host) {
        this.liveTextValue = "";
        this.configRequestVersion = (this.configRequestVersion || 0) + 1;
        this.configKeyVersions?.clear();
        this.unsavedConfigKeys?.clear();
        this.updateSettingsFeedback();
      }
      this.host = url.host;
    } catch (e) {
      const message = "Enter a PC address such as 192.168.1.10:8765.";
      this.settingHost?.setCustomValidity(message);
      this.settingHost?.reportValidity();
      this.showFeedback(message, "error", "connection");
      return false;
    }
    this.settingHost.setCustomValidity("");
    this.settingHost.value = this.host;
    this.authPin = "";
    localStorage.setItem("touchhelm_host", this.host);
    this.clearFeedback("connection");
    this.closeSettings();
    this.connect();
    this.fetchServerConfig();
    return true;
  }

  startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.isConnected) {
        this.send({ type: "ping", t: Date.now() });
      }
    }, 2000);
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  setStatus(state, label) {
    this.updateRemoteControls();
    this.controls?.setConnected(this.isConnected);
    if (this.telLink) {
      this.telLink.textContent = state === "connected" ? "Ready to control your PC"
        : state === "connecting" ? "Connecting to your PC…" : "Reconnect to control your PC";
      this.telLink.classList.toggle("live-pulse", state === "connected");
    }
    if (this.elStatusDot) this.elStatusDot.className = `status-dot ${state}`;
    if (this.elStatusLabel) this.elStatusLabel.textContent = label;
    if (state !== "connected" && this.elStatusPing) {
      this.elStatusPing.textContent = "--ms";
    }
  }

  updateRemoteControls() {
    const buttons = [this.btnLeftClick, this.btnRightClick, this.btnMiddleClick,
      this.btnSlideNext, this.btnSlidePrev, this.btnSlideStart, this.btnSlideCurrent,
      this.btnSlideBlack, this.btnSlideWhite, this.btnSlideEnd, this.btnKeyViewStart,
      this.btnGyro,
      this.btnVolUp, this.btnVolDown, this.btnVolMute, this.sliderVol, this.sliderBright,
      this.btnBrightUp, this.btnBrightDown, this.btnMediaPlay, this.btnMediaPrev, this.btnMediaNext,
      this.sliderSens, this.sliderAccel, this.sliderScroll, this.chkInvertScroll,
      this.btnShowDesktop, this.btnAppSwitch, this.btnTaskView, this.btnLockPc, this.btnWinSearch, this.btnSnipTool,
      ...(this.keyBtns || []), ...(this.macroBtns || []), ...(this.numBtns || []), ...(this.shortcutBtns || [])];
    for (const button of buttons) {
      if (button) button.disabled = !this.isConnected;
    }
    if(this.sliderVol)this.sliderVol.disabled=!this.isConnected||this.lastVolumeVal===null;
    for(const button of [this.sliderBright,this.btnBrightUp,this.btnBrightDown])if(button)button.disabled=!this.isConnected||this.lastBrightnessVal===null;
    for (const name of ['btnSendChord','presentationDisplay','btnOpenApp','btnFocusApp','btnPinApp','btnAppDetails']) {
      const button=document.getElementById?.(name);if(button)button.disabled=!this.isConnected;
    }
    for (const surface of [this.touchSurface, this.scrollStrip, this.laserSurface]) {
      surface?.setAttribute("aria-disabled", String(!this.isConnected));
    }
    if (!this.isConnected && this.gyroEnabled) this.disableGyro();
    this.updateTypingUi();
  }

  setButtonLabel(button, text, icon) {
    if (!button) return;
    const label = button.querySelector?.('.button-label');
    if (label) label.textContent = text;
    else button.textContent = text;
    if (icon) button.querySelector?.('use')?.setAttribute('href', `#th-icon-${icon}`);
  }

  updateTypingUi() {
    const live = !!this.chkRealtimeTyping?.checked;
    this.setButtonLabel(this.btnSendText, live && !this.liveTypingPaused ? "PC Enter" : "Send", live && !this.liveTypingPaused ? "enter" : "send");
    if (this.typeInput) this.typeInput.setAttribute?.("enterkeyhint", "enter");
    if (this.typingHint) this.typingHint.textContent = !this.isConnected
      ? "Offline. Your draft stays here until you reconnect."
      : live && this.liveTypingPaused ? "Live sync paused for an offline draft. Send restores it explicitly."
      : live ? "Live sync is on. Return adds a line; PC Enter presses Enter on your PC."
      : "Return adds a new line. Send or Ctrl+Enter sends your draft.";
  }

  send(data) {
    if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    if (data.type === "media" && this.selectedMediaSession && !data.session_id) {
      data = { ...data, session_id: this.selectedMediaSession };
    }
    if (data.type === 'text' && this.newlineMode === 'shift_enter') data = {...data,newline_mode:'shift_enter'};
    if (data.type === 'laser' && (this.presentationDisplay||this.autoPresentationDisplay)) data = {...data,display_id:this.presentationDisplay||this.autoPresentationDisplay};
    try { this.ws.send(JSON.stringify(data)); return true; } catch (e) { return false; }
  }

  // --------------------------------------------------------------------------
  // TAP & TOUCH EVENT UTILITY (0ms latency, eliminates 300ms delay)
  // --------------------------------------------------------------------------
  onTap(el, handler) {
    if (!el) return;
    let startX = 0;
    let startY = 0;
    let moved = false;
    let touchFired = false;

    el.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        moved = false;
      }
    }, { passive: true });

    el.addEventListener("touchmove", (e) => {
      if (e.touches.length === 1) {
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        if (Math.hypot(dx, dy) > 10) {
          moved = true;
        }
      }
    }, { passive: true });

    el.addEventListener("touchend", (e) => {
      if (el.disabled) return;
      if (!moved) {
        touchFired = true;
        e.preventDefault();
        handler(e);
        setTimeout(() => { touchFired = false; }, 400);
      }
    }, { passive: false });

    el.addEventListener("click", (e) => {
      if (el.disabled) return;
      if (touchFired) {
        e.preventDefault();
        return;
      }
      handler(e);
    });
  }

  // --------------------------------------------------------------------------
  // EVENT BINDINGS
  // --------------------------------------------------------------------------
  bindEvents() {
    if (this.pinForm) this.pinForm.addEventListener("submit", (e) => {
      e.preventDefault();
      this.authPin = this.pinInput.value.trim();
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        if (this.pinError) this.pinError.textContent = "PC disconnected. Reconnecting…";
        this.connect();
        return;
      }
      this.authenticate();
    });
    // Navigation Tabs (instant 0ms tap)
    this.navTabs.forEach((tab) => {
      this.onTap(tab, () => {
        const targetView = tab.getAttribute("data-view");
        this.switchView(targetView);
        this.vibrate(10);
      });
    });

    // Top action buttons
    if (this.elStatusPill) this.onTap(this.elStatusPill, () => this.connect());

    // Theme Modal Triggers
    if (this.btnTheme) {
      this.onTap(this.btnTheme, () => {
        this.openModal(this.themeModal);
        this.vibrate(12);
      });
    }
    if (this.btnCloseTheme) {
      this.onTap(this.btnCloseTheme, () => {
        this.closeModal(this.themeModal);
      });
    }
    if (this.themeOptions) {
      this.themeOptions.forEach(opt => {
        this.onTap(opt, () => {
          const tId = opt.getAttribute("data-theme-id");
          this.applyTheme(tId);
          this.vibrate(20);
          this.closeModal(this.themeModal);
        });
      });
    }

    // Settings Modal Triggers
    if (this.btnSettings) this.onTap(this.btnSettings, () => this.openSettings());
    if (this.btnCloseSettings) this.onTap(this.btnCloseSettings, () => this.closeSettings());
    if (this.hostForm) this.hostForm.addEventListener("submit", (e) => { e.preventDefault(); this.connectToHost(); });
    else if (this.btnReconnect) this.onTap(this.btnReconnect, () => this.connectToHost());
    if (this.settingHost) this.settingHost.addEventListener("input", () => this.settingHost.setCustomValidity(""));

    if (this.btnWakeLock) this.onTap(this.btnWakeLock, () => this.toggleWakeLock());
    if (this.btnFullscreen) this.onTap(this.btnFullscreen, () => this.toggleFullscreen());

    // Dismiss modals when clicking on dark backdrop
    if (this.themeModal) {
      this.themeModal.addEventListener("click", (e) => {
        if (e.target === this.themeModal) this.closeModal(this.themeModal);
      });
    }
    if (this.settingsModal) {
      this.settingsModal.addEventListener("click", (e) => {
        if (e.target === this.settingsModal) this.closeSettings();
      });
    }

    // Settings Sliders & Inputs
    if (this.sliderSens) {
      this.sliderSens.addEventListener("input", (e) => {
        this.sensitivity = parseFloat(e.target.value);
        if (this.valSens) this.valSens.textContent = `${this.sensitivity.toFixed(1)}x`;
        localStorage.setItem("touchhelm_sens", this.sensitivity);
        this.syncConfig({ mouse_sensitivity: this.sensitivity });
      });
    }

    if (this.sliderAccel) {
      this.sliderAccel.addEventListener("input", (e) => {
        this.acceleration = parseFloat(e.target.value);
        if (this.valAccel) this.valAccel.textContent = `${this.acceleration.toFixed(2)}x`;
        localStorage.setItem("touchhelm_accel", this.acceleration);
        this.syncConfig({ mouse_acceleration: this.acceleration });
      });
    }

    if (this.sliderScroll) {
      this.sliderScroll.addEventListener("input", (e) => {
        this.scrollSpeed = parseFloat(e.target.value);
        if (this.valScroll) this.valScroll.textContent = `${this.scrollSpeed.toFixed(1)}x`;
        localStorage.setItem("touchhelm_scroll", this.scrollSpeed);
        this.syncConfig({ scroll_speed: this.scrollSpeed });
      });
    }

    if (this.chkInvertScroll) {
      this.chkInvertScroll.addEventListener("change", (e) => {
        this.invertScroll = e.target.checked;
        localStorage.setItem("touchhelm_invert", this.invertScroll);
        this.syncConfig({ invert_scroll: this.invertScroll });
      });
    }

    if (this.chkHaptics) {
      this.chkHaptics.addEventListener("change", (e) => {
        this.hapticsEnabled = e.target.checked;
        localStorage.setItem("touchhelm_haptics", this.hapticsEnabled);
      });
    }

    if (this.chkTapToClick) {
      this.chkTapToClick.addEventListener("change", (e) => {
        this.tapToClick = e.target.checked;
        localStorage.setItem("touchhelm_tap", this.tapToClick);
      });
    }

    // Trackpad Multi-touch Surface
    this.bindTrackpadGestures();

    // Scroll Strip
    this.bindScrollStrip();

    // Trackpad Bottom Buttons:
    // Left Click supports both tap and hold-to-drag with second finger
    const onLeftDown = (e) => {
      if (e.button != null && e.button !== 0) return;
      e.preventDefault();
      this.leftBtnDown = true;
      this.vibrate(14);
      this.send({ type: "mousedown", button: "left" });
    };
    const onLeftUp = (e) => {
      e.preventDefault();
      if (this.leftBtnDown) {
        this.leftBtnDown = false;
        this.vibrate(8);
        this.send({ type: "mouseup", button: "left" });
      }
    };
    if (this.btnLeftClick) {
      this.btnLeftClick.addEventListener("touchstart", onLeftDown, { passive: false });
      this.btnLeftClick.addEventListener("touchend", onLeftUp, { passive: false });
      this.btnLeftClick.addEventListener("touchcancel", onLeftUp, { passive: false });
      this.btnLeftClick.addEventListener("mousedown", onLeftDown);
      this.btnLeftClick.addEventListener("mouseup", onLeftUp);
      window.addEventListener("mouseup", onLeftUp);
    }

    this.onTap(this.btnRightClick, () => {
      this.vibrate(22);
      this.send({ type: "click", button: "right" });
    });

    this.onTap(this.btnMiddleClick, () => {
      this.vibrate(18);
      this.send({ type: "click", button: "middle" });
    });

    if (this.btnKeyViewStart) {
      this.onTap(this.btnKeyViewStart, () => {
        this.vibrate(18);
        this.send({ type: "shortcut", name: "start" });
      });
    }

    this.onTap(this.btnGyro, () => this.toggleGyro());

    // Presenter Controls
    this.bindPresenterControls();

    // Media Controls
    this.bindMediaControls();

    // Keyboard & Macros
    this.bindKeyboardControls();

    // Numpad
    this.bindNumpadControls();

    // Safety: release drag lock on window blur or visibility change
    window.addEventListener("blur", () => { this.releaseDragLock(); this.controls?.releaseKeys(); this.stopLaser(); this.disableGyro(); });
    document.addEventListener("visibilitychange", async () => {
      if (document.hidden) {
        this.releaseDragLock();
        this.controls?.releaseKeys();
        this.stopLaser();
        this.disableGyro();
      } else if (this.wakeLockRequested && !this.wakeLock && document.visibilityState === "visible") {
        await this.requestWakeLock();
      }
    });
    document.addEventListener("fullscreenchange", () => {
      this.btnFullscreen?.setAttribute("aria-pressed", String(!!document.fullscreenElement));
    });
    this.btnWakeLock?.setAttribute("aria-pressed", "false");
    this.btnFullscreen?.setAttribute("aria-pressed", String(!!document.fullscreenElement));
  }

  switchView(viewId) {
    window.TouchHelmEffects?.reset?.();
    if(this.experience?.seeking){this.experience.seeking=false;this.experience.text('seekPreview','');this.experience.tickMedia();}
    this.releaseDragLock();
    this.controls?.onViewChange(viewId);
    if (viewId !== "viewTrackpad") this.disableGyro();
    this.navTabs.forEach((tab) => {
      const selected = tab.getAttribute("data-view") === viewId;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-selected", String(selected));
    });
    this.views.forEach((v) => {
      v.classList.toggle("active", v.id === viewId);
    });

    // Query fresh volume & brightness when switching to Media view
    if (viewId === "viewMedia") {
      this.send({ type: "get_volume" });
      this.send({ type: "get_brightness" });
    }

    // Cleanup active laser if switching away from Presenter
    if (viewId !== "viewPresenter" && this.isLaserActive) {
      this.isLaserActive = false;
      this.updateLaserStatus(false);
      if (this.laserReticle) this.laserReticle.classList.remove("active");
      this.send({ type: "laser", active: false });
      this.send({ type: "laser_hide" });
    }
  }

  openSettings() {
    this.openModal(this.settingsModal);
  }

  closeSettings() {
    this.closeModal(this.settingsModal);
  }

  // --------------------------------------------------------------------------
  // TRACKPAD GESTURES (TOUCH ENGINE)
  // --------------------------------------------------------------------------
  bindTrackpadGestures() {
    let lastScrollY = 0;
    let lastScrollX = 0;
    let movedTotal = 0;
    let maxTouches = 0;
    let twoFingerMoved = false;
    let twoFingerTapFired = false;
    let twoFingerStartTime = 0;
    let dismissingTyping = false;
    let pinchDistance=0,gestureMode='scroll',pinchAccumulator=0;

    const onStart = (e) => {
      e.preventDefault();
      if (dismissingTyping) return;
      if (this.controls?.ids.typingDock?.classList.contains('expanded')) {
        dismissingTyping = true;
        this.controls.collapseTyping();
        return;
      }
      window.TouchHelmThemes?.setInteractionActive(true);
      const count = e.touches.length;
      maxTouches = Math.max(maxTouches, count);

      if (count === 1) {
        this.touchStartTime = Date.now();
        movedTotal = 0;
        const t = e.touches[0];
        const rect = this.touchSurface.getBoundingClientRect();
        this.lastTouchPos = { x: t.clientX, y: t.clientY };
        this.initialTouchPos = { x: t.clientX, y: t.clientY };

        // Position touch visual indicator
        if (this.touchIndicator) {
          this.touchIndicator.style.left = `${t.clientX - rect.left}px`;
          this.touchIndicator.style.top = `${t.clientY - rect.top}px`;
          this.touchIndicator.classList.add("active");
        }

        // Tap & Hold Drag Lock check
        clearTimeout(this.tapTimer);
        this.tapTimer = setTimeout(() => {
          if (movedTotal < 12 && !this.isDragging && maxTouches === 1) {
            this.isDragging = true;
            if (this.dragLockBadge) this.dragLockBadge.classList.add("active");
            this.vibrate(40);
            this.send({ type: "mousedown", button: "left" });
          }
        }, 360);

      } else if (count === 2) {
        clearTimeout(this.tapTimer);
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        pinchDistance=Math.hypot(t2.clientX-t1.clientX,t2.clientY-t1.clientY);
        gestureMode=this.pinchZoom?'pending':'scroll';pinchAccumulator=0;
        lastScrollX = (t1.clientX + t2.clientX) / 2;
        lastScrollY = (t1.clientY + t2.clientY) / 2;
        twoFingerStartTime = Date.now();
        twoFingerMoved = false;
        twoFingerTapFired = false;
      }
    };

    const onMove = (e) => {
      e.preventDefault();
      if (dismissingTyping) return;
      const count = e.touches.length;
      maxTouches = Math.max(maxTouches, count);
      this.updateTouchFps();

      if (count === 1 && !twoFingerMoved) {
        const t = e.touches[0];
        const dx = t.clientX - this.lastTouchPos.x;
        const dy = t.clientY - this.lastTouchPos.y;
        const stepDist = Math.hypot(dx, dy);
        movedTotal += stepDist;

        if (movedTotal > 8) {
          clearTimeout(this.tapTimer);
        }

        if (this.touchIndicator) {
          const rect = this.touchSurface.getBoundingClientRect();
          this.touchIndicator.style.left = `${t.clientX - rect.left}px`;
          this.touchIndicator.style.top = `${t.clientY - rect.top}px`;
        }

        // Update telemetry coordinates
        if (this.telCoords) {
          this.telCoords.textContent = `ΔX: ${dx >= 0 ? "+" : ""}${Math.round(dx)} | ΔY: ${dy >= 0 ? "+" : ""}${Math.round(dy)}`;
        }

        // Send raw movement delta
        this.send({
          type: "move",
          dx: dx,
          dy: dy
        });

        this.lastTouchPos = { x: t.clientX, y: t.clientY };

      } else if (count === 2) {
        clearTimeout(this.tapTimer);
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const currentY = (t1.clientY + t2.clientY) / 2;
        const currentX = (t1.clientX + t2.clientX) / 2;

        const distance=Math.hypot(t2.clientX-t1.clientX,t2.clientY-t1.clientY);
        const distanceDelta=distance-pinchDistance;
        if(gestureMode==='pending') {
          if(Math.abs(distanceDelta)>8&&Math.abs(distanceDelta)>Math.hypot(currentX-lastScrollX,currentY-lastScrollY)*2)gestureMode='pinch';
          else if(Math.hypot(currentX-lastScrollX,currentY-lastScrollY)>6)gestureMode='scroll';
          else return;
        }
        if(gestureMode==='pinch') {
          twoFingerMoved=true;pinchAccumulator+=distanceDelta;pinchDistance=distance;
          const steps=Math.trunc(pinchAccumulator/20);
          if(steps){this.send({type:'zoom',delta:Math.max(-3,Math.min(3,steps))});pinchAccumulator-=steps*20;}
          return;
        }

        const dy = currentY - lastScrollY;
        const dx = currentX - lastScrollX;

        if (Math.hypot(dx, dy) > 6) {
          twoFingerMoved = true;
        }

        // Standard Windows scroll: dragging downward sends negative delta (scroll down)
        const sendDy = -Math.round(dy / 4);
        const sendDx = Math.round(dx / 4);

        if (Math.abs(sendDy) >= 1 || Math.abs(sendDx) >= 1) {
          twoFingerMoved = true;
          this.send({
            type: "scroll",
            dx: sendDx,
            dy: sendDy
          });
          lastScrollY = currentY;
          lastScrollX = currentX;
        }
      }
    };

    const onEnd = (e) => {
      e.preventDefault();
      if (dismissingTyping) { if (!e.touches.length) dismissingTyping=false; return; }
      if (!e.touches.length) window.TouchHelmThemes?.setInteractionActive(false);
      clearTimeout(this.tapTimer);
      const remainingTouches = e.touches.length;

      // Check 2-Finger Tap (Right Click) when one or both fingers lift
      if (maxTouches === 2 && !twoFingerMoved && !twoFingerTapFired) {
        const twoDuration = Date.now() - twoFingerStartTime;
        if (twoDuration < 360) {
          twoFingerTapFired = true;
          this.vibrate(28);
          this.send({ type: "click", button: "right" });
        }
      }

      // A remaining finger starts from its current position, never the old
      // one-finger position from before a two-finger gesture.
      if (remainingTouches === 1) {
        this.lastTouchPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }

      if (remainingTouches === 0) {
        if (this.touchIndicator) this.touchIndicator.classList.remove("active");

        if (this.isDragging) {
          this.releaseDragLock();
          maxTouches = 0;
          twoFingerTapFired = false;
          twoFingerMoved = false;
          return;
        }

        // 1-Finger Tap to Click (only if gesture was strictly 1-finger and no 2-finger tap fired)
        if (maxTouches === 1 && !twoFingerTapFired && this.tapToClick && (Date.now() - this.touchStartTime) < 280 && movedTotal < 12) {
          const now = Date.now();
          if (now - this.lastTapTime < 290) {
            // Double Tap
            this.vibrate([15, 30, 20]);
            // The first tap already sent one click. Windows combines this
            // second click into a double click; sending a pair makes three.
            this.send({ type: "click", button: "left" });
            this.lastTapTime = 0;
          } else {
            // Single Tap
            this.vibrate(12);
            this.send({ type: "click", button: "left" });
            this.lastTapTime = now;
          }
        }

        // Reset touch session flags
        maxTouches = 0;
        twoFingerTapFired = false;
        twoFingerMoved = false;
      }
    };

    const onCancel = (e) => {
      dismissingTyping = false;
      window.TouchHelmThemes?.setInteractionActive(false);
      e.preventDefault();
      clearTimeout(this.tapTimer);
      if (this.touchIndicator) this.touchIndicator.classList.remove("active");
      this.releaseDragLock();
      maxTouches = 0;
      twoFingerTapFired = false;
      twoFingerMoved = false;
    };

    this.touchSurface.addEventListener("touchstart", onStart, { passive: false });
    this.touchSurface.addEventListener("touchmove", onMove, { passive: false });
    this.touchSurface.addEventListener("touchend", onEnd, { passive: false });
    this.touchSurface.addEventListener("touchcancel", onCancel, { passive: false });
  }

  releaseDragLock() {
    clearTimeout(this.tapTimer);
    this.leftBtnDown = false;
    if (this.isDragging) {
      this.isDragging = false;
      if (this.dragLockBadge) this.dragLockBadge.classList.remove("active");
      this.vibrate(20);
    }
    // Unconditionally ensure left mouse button is released
    this.send({ type: "mouseup", button: "left" });
  }

  updateTouchFps() {
    this.touchFrameCount++;
    const now = Date.now();
    const elapsed = now - this.lastFpsCalcTime;
    if (elapsed >= 500) {
      const hz = Math.round((this.touchFrameCount * 1000) / elapsed);
      if (this.telFps) {
        this.telFps.textContent = `${hz} Hz`;
      }
      this.touchFrameCount = 0;
      this.lastFpsCalcTime = now;
    }
  }

  // --------------------------------------------------------------------------
  // EDGE SCROLL STRIP (With dynamic handle tracking & standard scroll direction)
  // --------------------------------------------------------------------------
  bindScrollStrip() {
    if (!this.scrollStrip) return;
    let lastStripY = 0;

    const updateHandlePos = (clientY) => {
      if (!this.scrollHandle || !this.scrollStrip) return;
      const rect = this.scrollStrip.getBoundingClientRect();
      const clampedY = Math.max(24, Math.min(rect.height - 24, clientY - rect.top));
      this.scrollHandle.style.top = `${clampedY}px`;
    };

    const resetHandlePos = () => {
      if (this.scrollHandle) {
        this.scrollHandle.style.top = "50%";
      }
    };

    const onStart = (e) => {
      e.preventDefault();
      const t = e.touches ? e.touches[0] : e;
      lastStripY = t.clientY;
      updateHandlePos(t.clientY);
      this.vibrate(10);
    };

    const onMove = (e) => {
      e.preventDefault();
      const t = e.touches ? e.touches[0] : e;
      const currentY = t.clientY;
      updateHandlePos(currentY);
      const dy = currentY - lastStripY;
      // Pulling strip downward scrolls content down (standard Windows scroll)
      const sendDy = -Math.round(dy / 4);

      if (Math.abs(sendDy) >= 1) {
        this.send({
          type: "scroll",
          dx: 0,
          dy: sendDy
        });
        lastStripY = currentY;
      }
    };

    const onEnd = (e) => {
      e.preventDefault();
      resetHandlePos();
    };

    this.scrollStrip.addEventListener("touchstart", onStart, { passive: false });
    this.scrollStrip.addEventListener("touchmove", onMove, { passive: false });
    this.scrollStrip.addEventListener("touchend", onEnd, { passive: false });
    this.scrollStrip.addEventListener("touchcancel", onEnd, { passive: false });

    // Desktop pointer / mouse drag support for scroll strip
    let isStripMouseDown = false;
    this.scrollStrip.addEventListener("mousedown", (e) => {
      isStripMouseDown = true;
      onStart(e);
    });
    window.addEventListener("mousemove", (e) => {
      if (isStripMouseDown) onMove(e);
    });
    window.addEventListener("mouseup", (e) => {
      if (isStripMouseDown) {
        isStripMouseDown = false;
        onEnd(e);
      }
    });
  }

  // --------------------------------------------------------------------------
  // GYROSCOPE / AIR MOUSE
  // --------------------------------------------------------------------------
  async toggleGyro() {
    if (this.gyroEnabled) {
      this.disableGyro();
      return;
    }

    if(window.isSecureContext===false){this.btnGyro?.setAttribute('aria-pressed','false');this.showFeedback('Air Mouse needs a trusted HTTPS connection. Complete Secure pairing in Settings first.','error','capability');return;}

    if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
      try {
        const permission = await DeviceOrientationEvent.requestPermission();
        if (permission === "granted") {
          this.enableGyro();
        } else {
          this.btnGyro?.setAttribute("aria-pressed", "false");
          this.showFeedback("Air Mouse needs motion access. Allow it in your browser and try again.", "error", "capability");
        }
      } catch (err) {
        this.btnGyro?.setAttribute("aria-pressed", "false");
        this.showFeedback("Air Mouse could not access motion sensors. Try a supported browser over HTTPS.", "error", "capability");
      }
    } else if (window.DeviceOrientationEvent) {
      this.enableGyro();
    } else {
      this.btnGyro?.setAttribute("aria-pressed", "false");
      this.showFeedback("Air Mouse motion sensors are unavailable on this device or browser.", "error", "capability");
    }
  }

  enableGyro() {
    this.gyroEnabled = true;
    if (this.btnGyro) this.btnGyro.classList.add("active");
    this.btnGyro?.setAttribute("aria-pressed", "true");
    this.lastOrientation = null;
    this.gyroHandler = (e) => this.handleGyro(e);
    window.addEventListener("deviceorientation", this.gyroHandler, true);
    this.clearFeedback("capability");
    this.vibrate(25);
  }

  disableGyro() {
    this.gyroEnabled = false;
    if (this.btnGyro) this.btnGyro.classList.remove("active");
    this.btnGyro?.setAttribute("aria-pressed", "false");
    if (this.gyroHandler) {
      window.removeEventListener("deviceorientation", this.gyroHandler, true);
      this.gyroHandler = null;
    }
    this.vibrate(15);
  }

  handleGyro(e) {
    if (e.gamma == null || e.beta == null || isNaN(e.gamma) || isNaN(e.beta)) return;
    if (!this.lastOrientation) {
      this.lastOrientation = { gamma: e.gamma, beta: e.beta };
      return;
    }

    const dGamma = e.gamma - this.lastOrientation.gamma;
    const dBeta = e.beta - this.lastOrientation.beta;

    // Prevent cursor teleports on gimbal flip or orientation wrap-around
    if (Math.abs(dGamma) > 30 || Math.abs(dBeta) > 30) {
      this.lastOrientation = { gamma: e.gamma, beta: e.beta };
      return;
    }

    const deadzone = 0.12;
    if (Math.abs(dGamma) > deadzone || Math.abs(dBeta) > deadzone) {
      const dx = dGamma * 3.5;
      const dy = dBeta * 3.5;

      this.send({
        type: "move",
        dx: dx,
        dy: dy
      });
    }

    this.lastOrientation = { gamma: e.gamma, beta: e.beta };
  }

  // --------------------------------------------------------------------------
  // PRESENTER CONTROLS & DIGITAL LASER
  // --------------------------------------------------------------------------
  bindPresenterControls() {
    // Massive Slide Buttons
    this.onTap(this.btnSlideNext, () => {
      this.vibrate(25);
      this.send({ type: "presentation", action: "next" });
    });

    this.onTap(this.btnSlidePrev, () => {
      this.vibrate(20);
      this.send({ type: "presentation", action: "prev" });
    });

    // Toolbar buttons
    this.onTap(this.btnSlideStart, () => {
      this.vibrate(20);
      this.send({ type: "presentation", action: "start" });
    });

    this.onTap(this.btnSlideCurrent, () => {
      this.vibrate(20);
      this.send({ type: "presentation", action: "start_current" });
    });

    this.onTap(this.btnSlideBlack, () => {
      this.vibrate(20);
      this.send({ type: "presentation", action: "black" });
    });

    this.onTap(this.btnSlideWhite, () => {
      this.vibrate(20);
      this.send({ type: "presentation", action: "white" });
    });

    this.onTap(this.btnSlideEnd, () => {
      this.vibrate(35);
      this.send({ type: "presentation", action: "end" });
    });

    // Timer Preset Buttons (instant onTap)
    this.presetBtns.forEach((btn) => {
      this.onTap(btn, () => {
        this.presetBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        let seconds = 900;
        if (btn.hasAttribute("data-mins")) {
          seconds = parseInt(btn.getAttribute("data-mins"), 10) * 60;
        } else if (btn.hasAttribute("data-time")) {
          seconds = parseInt(btn.getAttribute("data-time"), 10);
        }

        this.timerSeconds = seconds;
        this.timerInitial = seconds;
        if (this.timerRunning) this.timerDeadline = Date.now() + seconds * 1000;
        this.updateTimerDisplay();
        this.vibrate(10);
      });
    });

    if (this.btnTimerStart) {
      this.onTap(this.btnTimerStart, () => {
        this.toggleTimer();
      });
    }

    if (this.btnTimerReset) {
      this.onTap(this.btnTimerReset, () => {
        this.resetTimer();
      });
    }

    // Laser Color Pickers (instant onTap)
    this.colorDots.forEach((dot) => {
      this.onTap(dot, () => {
        const color = dot.getAttribute("data-color");
        this.setLaserColor(color);
        this.vibrate(12);
      });
    });

    // Laser Surface Touch & Pointer Handling
    if (this.laserSurface) {
      this.laserSurface.addEventListener("touchstart", (e) => {
        e.preventDefault();
        if (!this.isConnected) return;
        this.isLaserActive = true;
        window.TouchHelmThemes?.setInteractionActive(true);
        this.updateLaserPosition(e.touches[0]);
        this.vibrate(25);
      }, { passive: false });

      this.laserSurface.addEventListener("touchmove", (e) => {
        e.preventDefault();
        if (this.isLaserActive && e.touches.length > 0) {
          this.updateLaserPosition(e.touches[0]);
        }
      }, { passive: false });

      const endLaser = (e) => {
        if (e && e.cancelable) e.preventDefault();
        this.isLaserActive = false;
        window.TouchHelmThemes?.setInteractionActive(false);
        if (this.laserReticle) this.laserReticle.classList.remove("active");
        this.updateLaserStatus(false);
        this.send({ type: "laser", active: false });
        this.send({ type: "laser_hide" });
      };

      this.laserSurface.addEventListener("touchend", endLaser, { passive: false });
      this.laserSurface.addEventListener("touchcancel", endLaser, { passive: false });

      // Desktop mouse drag support for laser surface
      let isLaserMouseDown = false;
      this.laserSurface.addEventListener("mousedown", (e) => {
        if (!this.isConnected) return;
        isLaserMouseDown = true;
        this.isLaserActive = true;
        window.TouchHelmThemes?.setInteractionActive(true);
        this.updateLaserPosition(e);
        this.vibrate(25);
      });
      window.addEventListener("mousemove", (e) => {
        if (isLaserMouseDown && this.isLaserActive) {
          this.updateLaserPosition(e);
        }
      });
      window.addEventListener("mouseup", (e) => {
        if (isLaserMouseDown) {
          isLaserMouseDown = false;
          endLaser(e);
        }
      });
    }
  }

  setLaserColor(color, persist = true) {
    if (!color) return;
    this.laserColor = color;
    this.colorDots.forEach((d) => {
      d.classList.toggle("active", d.getAttribute("data-color") === color);
    });
    if (this.laserColorIndicator) {
      this.laserColorIndicator.className = `laser-dot ${color}`;
    }
    if (this.laserReticle) {
      this.laserReticle.setAttribute("data-color", color);
    }
    if (persist) this.syncConfig({ laser_color: color });
  }

  updateLaserStatus(active) {
    const status=document.getElementById('laserStatus'),activity=document.getElementById('laserActivity');
    if(status)status.dataset.active=String(!!active);
    if(activity)activity.textContent=active?'Pointing':'Ready';
    if(this.laserSurface)this.laserSurface.dataset.pointing=String(!!active);
  }

  stopLaser() {
    this.updateLaserStatus(false);
    window.TouchHelmThemes?.setInteractionActive(false);
    if (!this.isLaserActive) return;
    this.isLaserActive = false;
    if (this.laserReticle) this.laserReticle.classList.remove("active");
    this.send({ type: "laser_hide" });
  }

  updateLaserPosition(touch) {
    if (!this.laserSurface || !touch) return;
    this.updateLaserStatus(true);
    const rect = this.laserSurface.getBoundingClientRect();
    const relX = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
    const relY = Math.max(0, Math.min(1, (touch.clientY - rect.top) / rect.height));

    if (this.laserReticle) {
      this.laserReticle.style.left = `${touch.clientX - rect.left}px`;
      this.laserReticle.style.top = `${touch.clientY - rect.top}px`;
      this.laserReticle.classList.add("active");
    }

    this.send({
      type: "laser",
      x: relX,
      y: relY,
      active: true,
      color: this.laserColor
    });
  }

  toggleTimer() {
    if (this.timerRunning) {
      this.tickTimer();
      this.stopTimer();
      this.vibrate(15);
    } else {
      if (this.timerSeconds <= 0) this.timerSeconds = this.timerInitial;
      this.timerRunning = true;
      this.timerDeadline = Date.now() + this.timerSeconds * 1000;
      this.setButtonLabel(this.btnTimerStart, "Pause", "pause");
      this.vibrate(20);
      this.timerInterval = setInterval(() => this.tickTimer(), 250);
      this.updateTimerDisplay();
    }
  }

  stopTimer() {
    clearInterval(this.timerInterval);
    this.timerInterval = null;
    this.timerRunning = false;
    this.timerDeadline = null;
    this.setButtonLabel(this.btnTimerStart, "Start", "play");
  }

  tickTimer() {
    if (!this.timerRunning || this.timerDeadline == null) return;
    const before = this.timerSeconds;
    this.timerSeconds = Math.max(0, Math.ceil((this.timerDeadline - Date.now()) / 1000));
    if (before > 120 && this.timerSeconds <= 120 && this.timerSeconds > 0) this.vibrate([100, 100, 100]);
    this.updateTimerDisplay();
    if (this.timerSeconds === 0) {
      this.stopTimer();
      this.vibrate([200, 150, 200, 150, 300]);
    }
  }

  resetTimer() {
    this.stopTimer();
    this.timerSeconds = this.timerInitial;
    this.updateTimerDisplay();
    this.vibrate(12);
  }

  updateTimerDisplay() {
    if (!this.timerDisplay) return;
    const mins = Math.floor(this.timerSeconds / 60);
    const secs = this.timerSeconds % 60;
    this.timerDisplay.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  // --------------------------------------------------------------------------
  // VOLUME & BRIGHTNESS SYNCHRONIZATION
  // --------------------------------------------------------------------------
  onVolumeSync(volume, muted) {
    const known=typeof volume==='number'&&Number.isFinite(volume)&&volume>=0&&volume<=100;
    if(!known){this.lastVolumeVal=null;if(this.lblVolLevel)this.lblVolLevel.textContent='Unavailable';}
    if(this.sliderVol){this.sliderVol.disabled=!this.isConnected||!known;this.sliderVol.setAttribute('aria-valuetext',known?`${volume}%`:'Volume readback unavailable');}
    if (known) {
      this.lastVolumeVal = volume;
      if (this.sliderVol && !this.isUserDraggingVol) {
        this.sliderVol.value = volume;
      }
      if (this.lblVolLevel && !this.isUserDraggingVol) {
        this.lblVolLevel.textContent = muted ? `Muted (${volume}%)` : `Level: ${volume}%`;
      }
    }
    if (this.btnVolMute) {
      this.btnVolMute.classList.toggle("muted-active", !!muted);
    }
    if (this.sliderVol) {
      this.sliderVol.classList.toggle("slider-muted", !!muted);
    }
  }

  onBrightnessSync(level) {
    const known=typeof level==='number'&&Number.isFinite(level)&&level>=0&&level<=100;
    if(!known){this.lastBrightnessVal=null;if(this.lblBrightLevel)this.lblBrightLevel.textContent='Unavailable';}
    for(const button of [this.sliderBright,this.btnBrightUp,this.btnBrightDown])if(button)button.disabled=!this.isConnected||!known;
    this.sliderBright?.setAttribute('aria-valuetext',known?`${level}%`:'Brightness readback unavailable');
    if (known) {
      this.lastBrightnessVal = level;
      if (this.sliderBright && !this.isUserDraggingBright) {
        this.sliderBright.value = level;
      }
      if (this.lblBrightLevel && !this.isUserDraggingBright) {
        this.lblBrightLevel.textContent = `Level: ${level}%`;
      }
    }
  }

  // --------------------------------------------------------------------------
  // MEDIA & WINDOWS SHORTCUTS
  // --------------------------------------------------------------------------
  bindMediaControls() {
    // Volume buttons
    this.onTap(this.btnVolUp, () => {
      this.vibrate(12);
      this.send({ type: "volume", action: "up" });
    });

    this.onTap(this.btnVolDown, () => {
      this.vibrate(12);
      this.send({ type: "volume", action: "down" });
    });

    this.onTap(this.btnVolMute, () => {
      this.vibrate(20);
      this.send({ type: "volume", action: "mute" });
    });

    // Real-time Windows Master Volume Slider
    if (this.sliderVol) {
      let volDragTimeout = null;
      const onVolInput = (e) => {
        const val = parseInt(e.target.value, 10);
        this.isUserDraggingVol = true;
        if (this.lblVolLevel) {
          this.lblVolLevel.textContent = `Target: ${val}%`;
        }
        if (volDragTimeout) clearTimeout(volDragTimeout);
        volDragTimeout = setTimeout(() => {
          this.isUserDraggingVol = false;
        }, 400);

        const now = Date.now();
        if (now - this.lastVolSendTime > 40) {
          this.lastVolSendTime = now;
          this.send({ type: "volume", level: val });
        }
      };
      const endVolDrag = () => {
        if (volDragTimeout) clearTimeout(volDragTimeout);
        if (this.isUserDraggingVol) {
          this.isUserDraggingVol = false;
          const val = parseInt(this.sliderVol.value, 10);
          this.send({ type: "volume", level: val });
          this.vibrate(8);
        }
      };
      this.sliderVol.addEventListener("input", onVolInput);
      this.sliderVol.addEventListener("change", endVolDrag);
      this.sliderVol.addEventListener("pointerup", endVolDrag);
      this.sliderVol.addEventListener("touchend", endVolDrag);
      this.sliderVol.addEventListener("touchcancel", endVolDrag);
      this.sliderVol.addEventListener("mouseup", endVolDrag);
      window.addEventListener("pointerup", () => { if (this.isUserDraggingVol) endVolDrag(); });
      window.addEventListener("touchend", () => { if (this.isUserDraggingVol) endVolDrag(); });
    }

    // Windows Display Brightness Controls
    if (this.btnBrightUp) {
      this.onTap(this.btnBrightUp, () => {
        this.vibrate(12);
        this.send({ type: "brightness", action: "up" });
      });
    }

    if (this.btnBrightDown) {
      this.onTap(this.btnBrightDown, () => {
        this.vibrate(12);
        this.send({ type: "brightness", action: "down" });
      });
    }

    if (this.sliderBright) {
      let brightDragTimeout = null;
      const onBrightInput = (e) => {
        const val = parseInt(e.target.value, 10);
        this.isUserDraggingBright = true;
        if (this.lblBrightLevel) {
          this.lblBrightLevel.textContent = `Target: ${val}%`;
        }
        if (brightDragTimeout) clearTimeout(brightDragTimeout);
        brightDragTimeout = setTimeout(() => {
          this.isUserDraggingBright = false;
        }, 400);

        const now = Date.now();
        if (now - this.lastBrightSendTime > 50) {
          this.lastBrightSendTime = now;
          this.send({ type: "brightness", level: val });
        }
      };
      const endBrightDrag = () => {
        if (brightDragTimeout) clearTimeout(brightDragTimeout);
        if (this.isUserDraggingBright) {
          this.isUserDraggingBright = false;
          const val = parseInt(this.sliderBright.value, 10);
          this.send({ type: "brightness", level: val });
          this.vibrate(8);
        }
      };
      this.sliderBright.addEventListener("input", onBrightInput);
      this.sliderBright.addEventListener("change", endBrightDrag);
      this.sliderBright.addEventListener("pointerup", endBrightDrag);
      this.sliderBright.addEventListener("touchend", endBrightDrag);
      this.sliderBright.addEventListener("touchcancel", endBrightDrag);
      this.sliderBright.addEventListener("mouseup", endBrightDrag);
      window.addEventListener("pointerup", () => { if (this.isUserDraggingBright) endBrightDrag(); });
      window.addEventListener("touchend", () => { if (this.isUserDraggingBright) endBrightDrag(); });
    }

    // Playback buttons
    this.onTap(this.btnMediaPlay, () => {
      this.vibrate(18);
      const state=String(this.experience?.media?.status||'').toLowerCase();
      const action=state==='playing'?'pause':['paused','stopped'].includes(state)?'play':'play_pause';
      if(this.experience)this.experience.mediaAction(action);
      else this.send({ type: "media", action: "play_pause" });
    });

    this.onTap(this.btnMediaPrev, () => {
      this.vibrate(14);
      this.send({ type: "media", action: "prev" });
    });

    this.onTap(this.btnMediaNext, () => {
      this.vibrate(14);
      this.send({ type: "media", action: "next" });
    });

    // Windows Shortcuts (bound by data-shortcut and specific IDs)
    this.shortcutBtns.forEach((btn) => {
      this.onTap(btn, () => {
        const shortcut = btn.getAttribute("data-shortcut");
        if (shortcut) {
          this.vibrate(20);
          this.send({ type: "shortcut", name: shortcut });
        }
      });
    });
  }

  // --------------------------------------------------------------------------
  // KEYBOARD & MACROS (Full Android virtual keyboard & physical input support)
  // --------------------------------------------------------------------------
  bindKeyboardControls() {
    if (this.btnSendText) {
      this.onTap(this.btnSendText, () => {
        const text = this.typeInput ? this.typeInput.value : "";
        if ((text || this.chkRealtimeTyping?.checked) && !this.isComposing) {
          this.vibrate(15);
          let sent;
          if (this.chkRealtimeTyping && this.chkRealtimeTyping.checked && !this.liveTypingPaused) {
            sent = this.syncLiveText() && this.send({ type: "key", key: "enter" });
          } else {
            sent = this.liveTextValue ? this.syncLiveText(true) : this.send({ type: "text", text: text });
          }
          if (sent) {
            if (this.typeInput) this.typeInput.value = "";
            this.liveTextValue = "";
            this.liveTypingPaused = false;
            this.updateTypingUi();
            this.clearFeedback("typing");
            this.typeInput?.focus?.();
          } else {
            this.showFeedback(this.isConnected
              ? "Text was not sent. Your draft is kept; try again."
              : "Connect to your PC to send. Your draft is kept.", "error", "typing");
            this.typeInput?.focus?.();
          }
        }
      });
    }

    if (this.btnClearText) {
      this.onTap(this.btnClearText, () => {
        if (this.typeInput) this.typeInput.value = "";
        this.liveTextValue = "";
        this.liveTypingPaused = false;
        this.updateTypingUi();
        this.clearFeedback("typing");
        this.typeInput?.focus?.();
        this.vibrate(10);
      });
    }

    if (this.typeInput) {
      this.typeInput.addEventListener("compositionstart", () => { this.isComposing = true; });
      this.typeInput.addEventListener("compositionend", () => {
        this.isComposing = false;
        this.syncLiveText();
      });
      this.typeInput.addEventListener("input", (e) => {
        if (!e.isComposing && !this.isComposing) this.syncLiveText();
      });

      this.typeInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.ctrlKey) {
          if (e.isComposing || this.isComposing || e.keyCode === 229) return;
          e.preventDefault();
          this.vibrate(12);
          this.btnSendText?.click();
        }
      });
    }

    if (this.chkRealtimeTyping) this.chkRealtimeTyping.addEventListener("change", () => {
      this.liveTypingExplicit=true;
      try {localStorage.setItem('touchhelm_live_typing',String(this.chkRealtimeTyping.checked));} catch {}
      if (this.chkRealtimeTyping.checked) this.syncLiveText();
      this.updateTypingUi();
    });
    this.updateTypingUi();

    // Virtual Function Keys
    this.keyBtns.forEach((btn) => {
      this.onTap(btn, () => {
        const key = btn.getAttribute("data-key");
        if (key) {
          this.vibrate(14);
          this.send({ type: "key", key: key });
        }
      });
    });

    // Productivity Macros
    this.macroBtns.forEach((btn) => {
      this.onTap(btn, () => {
        const hotkey = btn.getAttribute("data-hotkey");
        if (hotkey) {
          const keys = hotkey.split(",");
          this.vibrate(20);
          this.send({ type: "hotkey", keys: keys });
        }
      });
    });
  }

  syncLiveText(force = false) {
    if ((!force && !this.chkRealtimeTyping?.checked) || this.isComposing || !this.typeInput) return false;
    if(!this.isConnected){if(this.typeInput.value!==this.liveTextValue)this.liveTypingPaused=true;this.updateTypingUi();return false;}
    if(this.liveTypingPaused&&!force){this.updateTypingUi();this.showFeedback('Draft edited offline. Use Send to sync it explicitly.','info','typing');return false;}
    const value = this.typeInput.value;
    // Compare complete values: paste often supplies null data and IMEs replace
    // existing text. Graphemes keep an emoji or composed character intact.
    const segment = (text) => typeof Intl.Segmenter === "function"
      ? Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(text), item => item.segment)
      : Array.from(text);
    const before = segment(this.liveTextValue || "");
    const after = segment(value);
    let common = 0;
    while (common < before.length && common < after.length && before[common] === after[common]) common++;
    for (let i = before.length; i > common; i--) {
      if (!this.send({ type: "key", key: "backspace" })) return false;
      this.liveTextValue = before.slice(0, i - 1).join("");
    }
    const suffix = after.slice(common).join("");
    if (suffix && !this.send({ type: "text", text: suffix })) return false;
    this.liveTextValue = value;
    return true;
  }

  // --------------------------------------------------------------------------
  // NUMPAD
  // --------------------------------------------------------------------------
  bindNumpadControls() {
    this.numBtns.forEach((btn) => {
      this.onTap(btn, () => {
        const key = btn.getAttribute("data-key");
        if (!key) return;
        this.vibrate(12);
        if (key === "backspace" || key === "enter" || key === "numlock") {
          this.send({ type: "key", key: key });
        } else {
          this.send({ type: "text", text: key });
        }
      });
    });
  }

  // --------------------------------------------------------------------------
  // WAKE LOCK & FULLSCREEN & PWA
  // --------------------------------------------------------------------------
  restoreSession() {
    try {
      const key = `touchhelm_resume:${window.location.host}`;
      const raw = sessionStorage.getItem(key);
      if (!raw) return;
      sessionStorage.removeItem(key);
      const state = JSON.parse(raw);
      if (!Number.isFinite(state.savedAt) || Date.now() - state.savedAt > 60000) return;
      if (state.host && /^[\w.:[\]-]+$/.test(state.host)) {
        this.host = state.host;
        if (this.settingHost) this.settingHost.value = state.host;
      }
      if (this.typeInput && typeof state.draft === "string") this.typeInput.value = state.draft;
      if (typeof state.baseline === "string") this.liveTextValue = state.baseline;
      this.liveTypingPaused = this.typeInput.value !== this.liveTextValue;
      if (this.chkRealtimeTyping && state.liveExplicit && typeof state.live === "boolean") this.chkRealtimeTyping.checked = state.live;
      if (Number.isFinite(state.timerInitial) && Number.isFinite(state.timerSeconds)
          && state.timerInitial > 0 && state.timerInitial <= 86400) {
        this.timerInitial = state.timerInitial;
        this.timerSeconds = Math.max(0, Math.min(state.timerSeconds || 0, 86400));
        this.timerRunning = !!state.timerRunning && Number.isFinite(state.timerDeadline);
        this.timerDeadline = this.timerRunning ? state.timerDeadline : null;
        this.setButtonLabel(this.btnTimerStart, this.timerRunning ? "Pause" : "Start", this.timerRunning ? "pause" : "play");
        this.presetBtns?.forEach(button => {
          const seconds = Number(button.getAttribute("data-time")) || Number(button.getAttribute("data-mins")) * 60;
          const selected = seconds === this.timerInitial;
          button.classList.toggle("active", selected);
          button.setAttribute("aria-pressed", String(selected));
        });
        this.updateTimerDisplay();
      }
    } catch (error) { /* The current UI still works if session storage is unavailable. */ }
  }

  async checkServerVersion() {
    if (this.versionChecking || !window.location.host || !this.buildId || this.buildId.includes("__TOUCHHELM_")) return false;
    this.versionChecking = true;
    try {
      const response = await fetch(`${window.location.origin}/api/version`, { cache: "no-store" });
      if (!response.ok) return false;
      const info = await response.json();
      if (!/^[a-zA-Z0-9-]{1,64}$/.test(info.build || "")) return false;
      const retryKey = `touchhelm_update_attempt:${window.location.host}`;
      if (info.build === this.buildId) {
        sessionStorage?.removeItem?.(retryKey);
        return false;
      }
      const key = `touchhelm_resume:${window.location.host}`;
      const previous = sessionStorage.getItem(retryKey);
      if (previous) {
        const attempt = JSON.parse(previous);
        if (attempt.build === info.build && Date.now() - attempt.savedAt < 30000) {
          this.showFeedback("An updated interface is available. Reload this page to finish updating.", "info", "connection");
          return false;
        }
      }
      sessionStorage.setItem(key, JSON.stringify({ build: info.build, savedAt: Date.now(), host: this.host,
        draft: this.typeInput?.value || "", baseline: this.liveTextValue || "", live: !!this.chkRealtimeTyping?.checked, liveExplicit:!!this.liveTypingExplicit,
        timerInitial: this.timerInitial, timerSeconds: this.timerSeconds,
        timerRunning: this.timerRunning, timerDeadline: this.timerDeadline }));
      sessionStorage.setItem(retryKey, JSON.stringify({ build: info.build, savedAt: Date.now() }));
      this.controls?.releaseKeys();
      this.releaseDragLock(); this.stopLaser(); this.disableGyro();
      const target = new URL(window.location.href);
      target.searchParams.set("build", info.build);
      window.location.replace(target.href);
      return true;
    } catch (error) { return false; }
    finally { this.versionChecking = false; }
  }

  async toggleWakeLock() {
    this.wakeLockRequested = !this.wakeLockRequested;
    if (!this.wakeLockRequested) {
      const lock = this.wakeLock;
      this.wakeLock = null;
      if (lock) { try { await lock.release(); } catch (e) {} }
      if (this.btnWakeLock) this.btnWakeLock.style.color = "var(--text-muted)";
      this.btnWakeLock?.setAttribute("aria-pressed", "false");
      if (this.btnWakeLock) this.btnWakeLock.title = "Keep Screen Awake";
      this.showFeedback("Keep Screen Awake is off.", "info", "capability");
      this.vibrate(15);
      return;
    }
    await this.requestWakeLock();
  }

  async requestWakeLock() {
    try {
      if(window.isSecureContext===false)throw new Error('A trusted secure context is required');
      if (!navigator.wakeLock?.request) throw new Error("Wake lock unavailable");
      const lock = await navigator.wakeLock.request("screen");
      if (!this.wakeLockRequested) { await lock.release(); return; }
      this.wakeLock = lock;
      if (this.btnWakeLock) {
        this.btnWakeLock.style.color = "var(--primary)";
        this.btnWakeLock.title = "Turn off Keep Screen Awake";
        this.btnWakeLock.setAttribute("aria-pressed", "true");
      }
      lock.addEventListener("release", () => {
        if (this.wakeLock === lock) this.wakeLock = null;
        if (!this.wakeLock && this.btnWakeLock) this.btnWakeLock.style.color = "var(--text-muted)";
        if (!this.wakeLock) this.btnWakeLock?.setAttribute("aria-pressed", "false");
      });
      this.showFeedback("Your screen will stay awake while TouchHelm is open.", "success", "capability");
      this.vibrate(25);
    } catch (e) {
      this.wakeLockRequested = false;
      this.wakeLock = null;
      if (this.btnWakeLock) {
        this.btnWakeLock.style.color = "var(--text-muted)";
        this.btnWakeLock.title = "Keep Screen Awake is unavailable. Use a supported browser over HTTPS.";
        this.btnWakeLock.setAttribute("aria-pressed", "false");
      }
      this.showFeedback("Keep Screen Awake is unavailable. Use a supported browser over HTTPS.", "error", "capability");
    }
  }

  async toggleFullscreen() {
    this.vibrate(15);
    const action = document.fullscreenElement
      ? document.exitFullscreen?.bind(document)
      : document.documentElement.requestFullscreen?.bind(document.documentElement);
    if (action) {
      try {
        await action();
        this.btnFullscreen?.setAttribute("aria-pressed", String(!!document.fullscreenElement));
        this.clearFeedback("capability");
      } catch (e) {
        this.showFeedback("Fullscreen could not start. Try again in your browser.", "error", "capability");
      }
    } else {
      if (this.btnFullscreen) this.btnFullscreen.title = "Fullscreen is unavailable in this browser";
      this.showFeedback("Fullscreen is unavailable in this browser.", "error", "capability");
    }
  }

  initPwa() {
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      this.deferredPrompt = e;
      if (this.pwaInstallBox) this.pwaInstallBox.style.display = "flex";
    });

    if (this.btnInstallPwa) {
      this.btnInstallPwa.addEventListener("click", async () => {
        if (this.deferredPrompt) {
          this.deferredPrompt.prompt();
          const { outcome } = await this.deferredPrompt.userChoice;
          if (outcome === "accepted" && this.pwaInstallBox) {
            this.pwaInstallBox.style.display = "none";
          }
          this.deferredPrompt = null;
        }
      });
    }

    if ("serviceWorker" in navigator) {
      const version = this.buildId && !this.buildId.includes("__TOUCHHELM_") ? `?v=${this.buildId}` : "";
      navigator.serviceWorker.register(`/sw.js${version}`, { updateViaCache: "none" })
        .then(registration => registration.update()).catch(() => {});
    }
    this.checkServerVersion();
    window.addEventListener("pageshow", () => this.checkServerVersion());
    window.addEventListener("focus", () => this.checkServerVersion());
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) this.checkServerVersion();
    });
  }
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  window.touchhelm = new TouchHelmClient();
});
