# Remote screen control and mirroring

TouchHelm 2.2 adds a sixth **Remote** tab. Existing Trackpad, Presenter, Media,
Keyboard and Apps remain available. No phone app is required.

## Setup

1. Install the optional providers in the host runtime:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-remote.txt
   ```

2. In desktop Settings, enable **Remote screen access**. TouchHelm enables password
   protection automatically and has a random four-digit numeric PIN ready for new
   setups. Existing four-digit PINs remain compatible. Use **Generate four-digit PIN**
   to rotate the PIN when needed. Previously configured passwords remain compatible.
   It is disabled by default. The desktop bridge is the only interface that can
   enable it; the phone settings API cannot.
3. Connect from the phone over the same Wi-Fi using the desktop Pairing QR code and PIN.
4. Open **Remote → Control PC** or **View PC**. PC audio starts off; enable it and
   tap Unmute when the browser requires a playback gesture.

Screen and audio providers can also be installed from desktop Settings.

## Listening without screen access

Media → **Hear PC audio on this phone** starts an authenticated audio-only stream:
it creates no desktop capture, sends no video track, and grants no input lease.
Tap **Unmute PC audio** if requested by the browser. Media and Remote use one audio
controller and one stream; both checkboxes reflect confirmed host state, including
pending requests, failures and Stop. Turning audio off during screen viewing leaves
video running. From audio-only listening, choosing Control/View ends the audio-only
transport cleanly and starts the requested screen stream with audio retained.
Backgrounding the phone still pauses the stream; returning requires explicit Resume.

The PC must remain powered on, signed in and running TouchHelm. Remote access does
not unlock Windows, cross UAC, start the PC or control elevated applications.

## Using the viewer

- **Trackpad:** move the PC pointer with one finger. Tap for a left click. Use the
  click row and Drag lock for explicit mouse-button control.
- **Direct touch:** map touches to the displayed monitor, including zoom and
  letterboxing. Taps outside the desktop picture do not click the PC.
- **Pan view:** move the viewer without sending PC movement. Pinch zoom is local
  in every mode. Two-finger vertical/horizontal scrolling controls the PC in
  Control mode. A gesture cannot change from scrolling into zoom midway through.
- **View PC:** streaming input is disabled. Switching into it releases held input.
- **Fullscreen:** request landscape after entering fullscreen. Unsupported browser
  orientation locks receive a manual-rotation hint. Exit fullscreen and Stop remain
  available over the video. The cursor marker uses measured PC pointer position;
  the SVG visibility attribute is updated explicitly.
- Open **Typing, keys & combinations** for multiline buffered text, PC Enter,
  held/sticky native keys, numpad and combinations such as Ctrl+Shift+A. Return in
  the text field creates a newline; sending remains explicit.
- Clear, the new default, is 1080p/30fps; Detail is 1440p/24fps; Balanced is
  720p/30fps; Saver is 540p/15fps. These are caps, not guaranteed frame rates.
  The selected preset is remembered per browser. Low capture FPS no longer silently
  reduces resolution; WebRTC still uses receiver feedback to adjust encoding bitrate.
  The readouts show decoded frames and network RTT, not claimed end-to-end latency.
- Desktop/tray Stop ends the stream and releases app-owned input while other tabs
  stay connected. Tab switching keeps streaming; backgrounding the phone pauses it.
  Resume after backgrounding is explicit; drafts are retained.

Only one stream may exist. Control mode reserves app input for its owning phone
and releases input held by other phones before granting that lease. Disconnect,
pairing revocation, Windows lock, monitor changes and host shutdown clean up the
session. If media cleanup fails, retry is blocked until a host restart.

## Transport and provider limits

Windows Desktop Duplication/DXcam captures a registered monitor by its identity;
a dedicated capture thread and separate media event loop keep capture/encoding
outside pointer processing. aiortc sends H.264/VP8 video and Opus audio. Buffers
are bounded, and PC audio uses WASAPI output loopback rather than a microphone.
Audio is normalized to stereo 48 kHz across output-device format changes.

WebSocket signaling uses the local HTTP origin. WebRTC media needs a reachable LAN UDP
path. Private host/mDNS ICE candidates are accepted; public/relay candidates are omitted.
No public TURN service or router port forwarding is configured.

If negotiation fails, check that both devices are on the same reachable LAN,
that Windows Firewall permits the host Python application on the intended private
network. Managed browser/network
policies can block WebRTC. Streaming dependencies stay optional; missing providers
do not prevent the original controls from working.

Protected content, inactive sessions and unsupported drivers may be uncapturable.
The pointer marker represents measured physical pointer position. It does not
reproduce every application-specific Windows cursor shape.

## Phone-to-PC system casting

Android Chrome and iPhone Safari currently cannot capture a phone screen through
the browser screen-sharing API. The Remote tab provides an honest **system casting
guide**, not a reverse WebRTC capture feature. Installing a PWA does not change this.

Desktop Settings includes **Install Wireless Display**, with first-time setup
guidance, live Windows installation progress, cancellation/error feedback, and
restart requirements. Accept Windows' administrator prompt and keep the PC online
while Windows Update supplies the feature. TouchHelm checks the actual optional
feature before installation and verifies it afterward. **Open casting settings**
opens Windows Projecting to this PC, where you enable/open the receiver application.
On a compatible Android phone, use Cast, Wireless Display, Screen sharing or Smart
View and select the PC. Names vary by manufacturer.

Both devices need compatible **Miracast** support. Google Cast-only phones and
iPhone AirPlay do not connect directly to that receiver. A registered Windows
receiver is shown when detected; hardware compatibility stays Unknown until tested.
The guide never claims a casting connection is active. System controls start/stop
casting. Miracast does not work over the internet.

## Verification

Software and local transport checks are recorded in `REMOTE_PLAN.md`. Automated
PC input remains mocked. The opt-in `tests/remote_transport_check.cjs` exercises
real Windows capture/audio to a real local browser without saving footage.

The preview board covers all six tabs and Remote control/view/connecting/paused/
unavailable states across all seven themes. Its desktop picture is an authored,
clearly labeled SVG fixture; it contains no captured personal desktop data.

**Still unperformed:** physical Android typing/gesture/audio/performance checks,
30-minute LAN sessions with background/resume and source restart,
and compatible Miracast hardware acceptance. Local loopback
success must not be presented as those device/network results.

Sources: [Windows capture](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api),
[Windows loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording),
[browser screen-capture support](https://github.com/mdn/browser-compat-data/blob/main/api/MediaDevices.json),
[Windows casting setup](https://support.microsoft.com/en-us/windows/hardware/display-graphics/screen-mirroring-and-projecting-to-your-pc-or-wireless-display).

## Remote reliability repairs (October 2026)

Stop ends Remote only, keeping the authenticated WebSocket and other tabs usable.
Switching tabs keeps the stream and releases held Remote inputs; backgrounding the
phone still pauses capture for privacy and requires Resume. Passwords survive page
refreshes in tab-scoped session storage, but are cleared after a rejected password
or host change. Missing/empty startup credentials do not count against the global
wrong-password attempt limit. Actual submitted wrong passwords retain rate limiting.

The pinned DXcam 0.3.0 cleanup adapter avoids explicitly releasing comtypes-owned
pointers twice. This addresses the native capture cleanup failure also tracked in
[DXcam issue 144](https://github.com/ra1nty/DXcam/issues/144). No installed library
files are modified. Desktop encoding budgets are increased, with congestion feedback
retained; the locally verified results are not Android/network performance claims.

Phone multiline text now defaults to Shift+Enter on the PC, keeping two phone
Return presses from becoming ordinary submit keys in apps that support that
convention. **PC Enter** stays explicit; the target application determines how it
interprets these keys. The editor-style Enter option remains selectable.

All seven existing themes support bounded procedural SVG/CSS/JavaScript reactions.
Bloom and Companion no longer load background photographs. Branch growth, flowers,
robot eyes, musical motifs, clay compression, glass droplets, soft contours and ink
strokes use generated elements with randomized movement. Rich/Calm/Off and reduced
motion remain available; large scenes pause around live remote video and input.
