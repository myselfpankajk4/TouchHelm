# TouchHelm

**Your PC, at your fingertips.**

Turn your phone into a Windows trackpad, keyboard, presentation remote, media controller, and app launcher. TouchHelm runs on your PC and serves its controls to a phone browser over your local network. Scan the desktop QR code to connect; no phone APK is needed.

<p>
  <img src="docs/images/desktop.png" alt="TouchHelm desktop pairing and connected-device panel" width="620">
  <img src="docs/images/trackpad.png" alt="TouchHelm phone trackpad with compact typing dock" width="250">
</p>

*Previews use synthetic QA device data and illustrate the interface rather than an active connection.*

## Features

| Tab | What it does |
| --- | --- |
| **Trackpad** | Large movement surface, left/middle/right clicks, tap, hold-to-drag, two-finger scrolling, edge scrolling, and optional air mouse. |
| **Typing dock** | Expands for typing, paste, Send/Enter, Clear, and live sync. Done collapses it while keeping your draft. |
| **Presenter** | Previous/next, start/from-current/end, black/white screen, current presentation context, independent countdown timer, and desktop laser. |
| **Media** | Current player/track details, player selection, playback controls, volume, brightness, exposed queues, and local files. |
| **Keyboard** | Native press/release, F1–F24, letters, symbols, navigation, left/right modifiers, editing shortcuts, and integrated Numpad. Hold or latch modifiers for chords such as **Ctrl+Shift+A**. |
| **Apps** | Search registered Windows apps and launch them, with running apps and successful TouchHelm launch frequency first. |

Five themes, optional PIN pairing, shared pointer settings, desktop device status, and system-tray support are included. Versioned QR links and assets help the browser load current UI updates while preserving drafts.

## Requirements

- **Host:** Windows 10/11, Python with Tkinter, and Windows PowerShell. Verified with **Python 3.13**.
- **Phone:** a modern browser on the same reachable local network as the PC. The UI supports phone, landscape, and desktop browser sizes.
- **Network:** default HTTP/WebSocket port **8765**. Allow the host through Windows Firewall on your private network if prompted. The experimental Android wrapper uses UDP **53317** for discovery.

Node.js is needed only for development tests, not normal app use.

## Quick start

This repository is private. Clone it with a GitHub account that has access:

```powershell
git clone https://github.com/myselfpankajk4/TouchHelm.git
cd TouchHelm
.\run.bat
```

On first launch, `run.bat` creates `.venv` and installs the pinned Python dependencies. Later launches use that environment and run the current source.

1. Keep the phone and PC on the same network.
2. Scan the QR code in the TouchHelm desktop window.
3. Open the link and enter a PIN if enabled.
4. Select a tab and control your PC.

The selectable PC address and **Copy URL** button provide an alternative to scanning. Keep the host running; **Minimize to tray** hides its window without disconnecting the phone.

### Manual setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Enable PIN pairing or run without the desktop window:

```powershell
.\.venv\Scripts\python.exe main.py --pin 1234
.\.venv\Scripts\python.exe main.py --headless
```

Use your own four-digit PIN; `1234` is an example. Changing/enabling a PIN revokes phone authorization and releases held inputs.

### Updates

Pull changes, quit the existing host completely, then launch `run.bat` again. Minimizing to the tray keeps the old Python process running. The QR carries the current web build; the phone checks the server version on open/focus and can refresh a confirmed changed build while keeping a draft.

Browser preferences and saved update drafts migrate from the former app name. This workspace's desktop shortcut is **TouchHelm (Latest)** and points to the source launcher.

## App compatibility

Details depend on what each desktop application exposes:

| Integration | Available behavior |
| --- | --- |
| **PowerPoint** | Deck title, slide number/count/title, slideshow state, and direct COM commands. |
| **Other recognized presenter/browser/PDF windows** | Window/app context and keyboard fallback. Generic shortcuts depend on the focused application; unavailable slide counts remain unknown. |
| **Windows media sessions** | Player selection, metadata, state/timeline where exposed, and supported playback commands. |
| **Windows Media Player** | Selectable queue when a running instance exposes it through COM. |
| **Local media** | Music/Videos files combined with session/queue items into a list bounded to 200 entries. |
| **Volume/brightness** | Native volume keys request the Windows flyout. Absolute volume and brightness show a transient TouchHelm indicator; brightness depends on monitor/driver support. |

Unsupported queues or slide details show explicit unavailable states. Running-app flags use process/window matching and can misidentify generic names. Launch counts record successful requests, not proof that an app finished opening.

## Settings and privacy

Local settings are saved automatically in `config.json`, which is excluded from Git. `config.example.json` is a clean reference without a personal hostname or enabled PIN. Launch history in `.touchhelm_usage.json` is also excluded.

| Setting | Default | Range/values |
| --- | --- | --- |
| Port | `8765` | 1–65535; restart to change listening port |
| Pointer sensitivity | `1.3` | 0.4–3.5 |
| Pointer acceleration | `1.25` | 1.0–2.5 |
| Scroll speed | `1.0` | 0.3–2.5 |
| Natural scrolling | Off | On/off |
| PIN required | Off | Four ASCII digits when enabled |
| Laser color | Red | Red, green, blue, amber |
| Theme | Cyber | Cyber, OLED, Matrix, Nordic, Light |

The default transport is HTTP/WebSocket for a trusted local network. Keep the host on that network rather than exposing it to the public Internet. An enabled PIN gates input, context/catalog queries, and settings; public responses omit the PIN. App/media commands use registered catalog IDs, not phone-supplied shell commands or arbitrary paths.

## Development and verification

The host uses Python/aiohttp/Tkinter and Win32 input. The phone uses plain HTML/CSS/JavaScript. A lazy hidden PowerShell bridge provides COM/WinRT context; slow provider work runs outside the input event loop and returns bounded failure states.

### Safe Python regressions

After installing `requirements.txt`, run on Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_build_version tests.test_desktop_regressions tests.test_native_controls tests.test_desktop_services tests.test_server_regressions -v
```

### Browser checks

With Node.js 20 or later:

```powershell
npm ci
npm test
npx playwright install chromium
npm run test:browser
```

`npm run test:visual` additionally writes screenshots to `tests/artifacts/`. `PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` can select an existing installation. No Codex runtime is required.

These suites mock native effects so they do not type, click, launch apps, play media, change volume/brightness, or lock the PC. **`test_touchhelm.py` is an older manual native-action script, not a safe regression suite.** Do not run it for unattended verification.

Physical phone gestures, live PowerPoint/player integration, and native feedback still need a device smoke test. See [BUGFIX_REPORT.md](BUGFIX_REPORT.md) for evidence and limitations.

## Project layout

```text
main.py                    Desktop/headless entry point
run.bat                    Source launcher and first-run setup
gui/app_window.py          Pairing, devices, settings, tray
server/web_server.py       HTTP/WebSocket and authentication
server/windows_input.py    Native input, volume and brightness
server/desktop_services.py Async catalog/context interface
server/desktop_bridge.ps1  COM/WinRT providers
server/osd_overlay.py      Desktop feedback
server/build_version.py    Content-derived browser versions
web/                       Phone controls, themes, PWA assets
android/                   Experimental Android WebView wrapper
tests/                     Safe regressions and previews
docs/images/               README interface previews
```

The browser is the supported phone entry point. The Android scaffold has been renamed to `com.touchhelm.app`; no APK build or Android device test is claimed. See [android/README.md](android/README.md).

## Troubleshooting

- **Cannot connect:** check the displayed address, reachable network, running host, and private-network firewall permission. Guest Wi-Fi/client isolation may block access.
- **Old UI:** quit/restart the host and scan its new QR. Python changes require a process restart.
- **No media/presentation details:** open the application on the PC; unavailable fields depend on provider support.
- **Air mouse, keep-awake, or installation unavailable:** permissions and secure-context/device rules vary. Other remote controls remain usable.

This is a private development repository. No public release or open-source license is currently declared.
