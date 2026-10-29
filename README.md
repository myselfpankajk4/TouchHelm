# TouchHelm

**Your PC, at your fingertips.** Turn your phone into a Windows trackpad, keyboard, presentation remote, media controller, app launcher, file browser and live desktop viewer/controller. TouchHelm runs on your PC and serves its controls to the phone's browser over your local Wi-Fi. Scan the desktop QR code and enter the PIN; no phone app is needed and no internet is needed after setup.

<p>
  <img src="docs/images/desktop.png" alt="TouchHelm desktop pairing and connected-device panel" width="620">
  <img src="docs/images/trackpad.png" alt="TouchHelm phone trackpad with compact typing dock" width="250">
</p>

*Previews use synthetic QA device data and illustrate the interface rather than an active connection.*

## Install (Windows 10/11 x64)

Download the latest `TouchHelm-<version>-setup-win-x64.exe` from the
[Releases page](https://github.com/myselfpankajk4/TouchHelm/releases/latest) and run it. It installs
to Installed apps with a Start Menu shortcut, an optional desktop shortcut and an uninstaller.
Python, the screen/audio libraries and the isolated AirControl camera runtime and models are
included; no Python, PATH change or pip command is needed. Setup reuses Windows' WebView2 and
prepares it if missing (only that Microsoft runtime may need internet). Keep one installed copy:
uninstall an older version before installing a new one. See [installer details](docs/WINDOWS_INSTALLER.md).

The installer is unsigned, so SmartScreen, firewall and camera prompts can appear.

## Pairing

1. Keep the phone and PC on the same Wi-Fi (not a guest network with client isolation).
2. Open TouchHelm on the PC, choose **Pair your phone** and scan the QR code.
3. Enter the PC's four-digit PIN. The selectable address and **Copy URL** are an alternative to scanning.
4. Pick a tab and control your PC.

Everything runs over local HTTP/WebSocket; Windows Firewall must allow TouchHelm on the private
network. There is no HTTPS, certificate, VPN or internet relay. See [Local Wi-Fi and Files](docs/LOCAL_WIFI.md)
and [pairing and text sync](docs/PAIRING.md).

## Features

**AirControl:** choose **Control via phone** or **AirControl** at startup. Head & Face is the
fresh-profile default; hand pointing uses the knuckle centre, and clicks anchor to where the
pointer was just before the gesture was recognised. Defaults are pinch, middle pinch, two
fingers, fist (pause) and palm (resume); extra gestures sit under "More gestures (advanced)".
Calibration, a practice cursor, remappable profiles, a status HUD and Windows dictation are included.
The camera starts only on **Start camera**. [Setup guide](docs/AIRCONTROL.md) ·
[Verification](docs/AIRCONTROL_VERIFICATION.md) · [Accuracy research](docs/AIRCONTROL_ACCURACY_RESEARCH.md).

**Remote:** Control PC or View PC with live monitor video, trackpad or direct touch, pinch zoom,
keyboard/numpad, quality presets (Clear 1080p default, 1440p Detail) and optional PC audio over
WebRTC on the local network. Streaming starts disabled and needs the host PIN. Media can stream
**PC audio only**. The Cast phone to PC guide uses Windows Wireless Display; desktop Settings has
its installer. [Remote guide](docs/REMOTE.md).

**Files:** browse, preview and transfer files between phone and PC after enabling File access
once on the PC. [Details](docs/LOCAL_WIFI.md).

**Typing:** live typing by default, with two-way sync for supported focused Windows fields
(password and read-only fields are excluded).

| Tab | What it does |
| --- | --- |
| **Trackpad** | Large movement surface, left/middle/right clicks, tap, hold-to-drag, two-finger scrolling and edge scrolling. |
| **Remote** | Live PC viewing/control, monitor selection, zoom, native keys, optional system audio and a casting guide. |
| **Files** | Browse the PC, preview, send and receive files. |
| **Presenter** | Previous/next above a large laser surface, monitor selection, countdown and an optional PowerPoint slide/notes drawer. |
| **Media** | Now Playing with artwork, metadata, timeline, seeking and supported repeat/shuffle/speed controls. |
| **Keyboard** | Native press/release, F1-F24, symbols, navigation, modifiers and integrated Numpad. |
| **Apps** | Real Windows icons and verified windows; open, focus, pin and close. |

Five generative themes, **Aurora** (default), **Bloom**, **Resonance**, **Constellation** and
**Ink**, cover the phone and desktop, each with light/dark appearance, reduced motion and increased
contrast. Preferences belong to each device. See [Themes](docs/THEMES.md).

Open **`/preview.html`** on a running host for a preview board of tabs, themes and simulated states
(it cannot send PC input).

## Source-development requirements

These apply when running from the checkout. The Windows installer includes its
own Python and application libraries; testers do not need the setup below.

- **Host:** Windows 10/11, Python, Windows PowerShell, WebView2 Runtime and .NET Framework 4.6.2 or later. Python 3.13 is used in this workspace. Tkinter remains available for the classic rollback UI.
- **Phone:** a modern browser on the same reachable local network as the PC. The UI supports phone, landscape, and desktop browser sizes.
- **Network:** HTTP/WebSocket **8765** and discovery UDP **53317**. Allow the LAN host through Windows Firewall on your private network if prompted.

Node.js is needed only for development tests, not normal app use.

## Run from source

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

Enable PIN pairing, run without the desktop window, or choose the classic desktop:

```powershell
.\.venv\Scripts\python.exe main.py --pin 1234
.\.venv\Scripts\python.exe main.py --headless
.\.venv\Scripts\python.exe main.py --classic-ui
```

Use your own four-digit PIN; `1234` is an example. Changing/enabling a PIN revokes phone authorization and releases held inputs.

### Updates

Pull changes, then launch `run.bat` again. The single-instance launcher restores the current window when source and startup settings match. Changed source requests graceful shutdown and starts the new build after ownership is released. It reports failure if that handoff cannot finish safely. The QR carries the current browser build; the phone checks on open/focus and refreshes a confirmed changed build while keeping its draft.

Browser preferences and saved update drafts migrate from the former app name. This workspace's **TouchHelm (Latest)** shortcut points to the source launcher and uses the TouchHelm icon. For a host started before v2, quit that older host once before using the new single-instance lifecycle.

## App compatibility

Details depend on what each desktop application exposes:

| Integration | Available behavior |
| --- | --- |
| **PowerPoint** | Deck title, slide count/title, slideshow state, direct COM commands, on-demand current/next previews, notes and slide selection. |
| **Other recognized presenter/browser/PDF windows** | Verified presentation-window context and guarded keyboard fallback. Generic browser windows are rejected; unavailable slide counts/previews remain unavailable. |
| **Windows media sessions** | Player selection, artwork, metadata, state/timeline, seek bounds, and supported playback/seek/shuffle/repeat/rate commands. |
| **Windows Media Player** | Selectable queue when a running instance exposes it through COM. |
| **Volume/brightness** | Native volume keys request the Windows flyout. TouchHelm overlays use measured readback. Missing readback stays unavailable; brightness depends on monitor/driver support. |

Windows media sessions provide no universal playlist API. TouchHelm does not scan Music/Videos folders in this flow. App windows use registered or executable identity; uncertain matches are not labeled Running. Windows may refuse foreground activation. Launch counts record successful requests, not proof that an app finished opening. Elevated applications can reject ordinary native input; hardware Fn functions are not promised.

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
| Theme | Aurora | Aurora, Bloom, Resonance, Constellation, Ink; device-local |
| Live typing | On for a new device | Device-local opt-out; offline drafts require explicit Send |
| Theme effects | Rich | Rich / Calm / Off; system reduced motion wins |

Traffic uses HTTP/WebSocket on the local Wi-Fi only; screen and audio use encrypted WebRTC between verified local peers. Tokens and settings are kept in a restricted per-user folder outside served assets.

An enabled PIN gates input, context/catalog queries, settings and private artwork/icons. Asset URLs contain opaque IDs; authentication uses headers. App/media commands use registered catalog IDs. The privileged desktop bridge belongs only to the owned local desktop window and has no phone HTTP command route.

## Development and verification

The host uses Python/aiohttp, an owned WebView2 desktop shell (with Tk rollback), and Win32 input. The phone uses plain HTML/CSS/JavaScript. A lazy hidden PowerShell bridge provides COM/WinRT context; slow provider work runs outside the input event loop and returns bounded failure states.

### Safe Python regressions

After installing `requirements.txt`, run on Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
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
gui/webview_window.py      Owned WebView2 bridge, pairing, devices, tray
gui/web/                   Shared themed desktop interface
gui/app_window.py          Classic Tk rollback interface
server/web_server.py       HTTP/WebSocket and authentication
server/windows_input.py    Native input, volume and brightness
server/aircontrol/         Isolated webcam worker, gestures, ownership, HUD and speech
server/desktop_services.py Async catalog/context interface
server/desktop_bridge.ps1  COM/WinRT providers
server/osd_overlay.py      Desktop feedback
server/build_version.py    Content-derived browser versions
server/instance_control.py Latest-source restore/restart lifecycle
server/private_storage.py  Restricted per-user storage for tokens and settings
server/asset_store.py      Bounded opaque artwork/icon cache
web/                       Phone controls, generative themes, PWA assets
tests/                     Safe regressions and previews
docs/images/               README interface previews
```

The browser is the only phone entry point; there is no phone app.

## Troubleshooting

- **Cannot connect:** check the displayed address, reachable network, running host, and private-network firewall permission. Guest Wi-Fi/client isolation may block access.
- **Old UI:** launch TouchHelm (Latest) and scan the current QR. Changed source uses the graceful single-instance restart. Quit a pre-v2 host once if it is still running.
- **No media/presentation details:** open the application on the PC; unavailable fields depend on provider support.
- **Vibration missing:** use Settings → Test vibration. An accepted API request is not proof of a physical pulse; browser support, user activation and phone settings matter.
- **Phone screen turns off:** change the phone's screen timeout; the page cannot keep it awake over plain HTTP.

This is a private development repository. No public release or open-source license is currently declared.
