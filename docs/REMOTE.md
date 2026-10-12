# Remote screen control and mirroring

TouchHelm 2.2 adds a sixth **Remote** tab. Existing Trackpad, Presenter, Media,
Keyboard and Apps remain available. No TouchHelm Android app is required.

## Setup

1. Install the optional providers in the host runtime:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-remote.txt
   ```

2. In desktop Settings, set a four-digit host PIN and enable **Remote screen access**.
   It is disabled by default. The desktop bridge is the only interface that can
   enable it; the phone settings API cannot.
3. Connect using trusted local HTTPS or private Tailscale HTTPS from desktop Pairing.
   For Tailscale, install/sign in on both devices and join the same tailnet.
4. Open **Remote → Control PC** or **View PC**. PC audio starts off; enable it and
   tap Unmute when the browser requires a playback gesture.

The PC must remain powered on, signed in and running TouchHelm. Remote access does
not unlock Windows, cross UAC, start the PC or control elevated applications.
Trusted local certificates still require phone trust installation. Tailscale is
the supported alternative without installing TouchHelm's CA.

## Using the viewer

- **Trackpad:** move the PC pointer with one finger. Tap for a left click. Use the
  click row and Drag lock for explicit mouse-button control.
- **Direct touch:** map touches to the displayed monitor, including zoom and
  letterboxing. Taps outside the desktop picture do not click the PC.
- **Pan view:** move the viewer without sending PC movement. Pinch zoom is local
  in every mode. Two-finger vertical/horizontal scrolling controls the PC in
  Control mode. A gesture cannot change from scrolling into zoom midway through.
- **View PC:** streaming input is disabled. Switching into it releases held input.
- Open **Typing, keys & combinations** for multiline buffered text, PC Enter,
  held/sticky native keys, numpad and combinations such as Ctrl+Shift+A. Return in
  the text field creates a newline; sending remains explicit.
- Balanced is 720p/30fps; Saver is 540p/15fps; Clear is 1080p/30fps. These are caps,
  not guaranteed frame rates. Sustained very low received FPS reduces the preset.
  The readouts show decoded frames and network RTT, not claimed end-to-end latency.
- Desktop/tray Stop ends the stream and releases app-owned input. Backgrounding
  the phone or leaving Remote pauses it. Resume is explicit; drafts are retained.

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

WebSocket signaling uses the selected HTTPS origin. **WebRTC media does not pass
through Tailscale Serve's HTTP proxy.** It needs a reachable LAN/tailnet UDP path.
Private host/mDNS ICE candidates are accepted; public/relay candidates are omitted.
No public TURN service, Funnel or router port forwarding is configured.

If negotiation fails, check that both devices are on the reachable LAN/tailnet,
that Windows Firewall permits the host Python application on the intended private
network, and that tailnet access rules allow peer traffic. Managed browser/network
policies can block WebRTC. Streaming dependencies stay optional; missing providers
do not prevent the original controls from working.

Protected content, inactive sessions and unsupported drivers may be uncapturable.
The pointer marker represents measured physical pointer position. It does not
reproduce every application-specific Windows cursor shape.

## Phone-to-PC system casting

Android Chrome and iPhone Safari currently cannot capture a phone screen through
the browser screen-sharing API. The Remote tab provides an honest **system casting
guide**, not a reverse WebRTC capture feature. Installing a PWA does not change this.

Desktop **Wireless Display setup** opens Windows Projecting to this PC. Install
the Windows optional Wireless Display feature and open the receiver application.
On a compatible Android phone, use Cast, Wireless Display, Screen sharing or Smart
View and select the PC. Names vary by manufacturer.

Both devices need compatible **Miracast** support. Google Cast-only phones and
iPhone AirPlay do not connect directly to that receiver. A registered Windows
receiver is shown when detected; hardware compatibility stays Unknown until tested.
The guide never claims a casting connection is active. System controls start/stop
casting, and Tailscale does not extend Miracast over the internet.

## Verification

Software and local transport checks are recorded in `REMOTE_PLAN.md`. Automated
PC input remains mocked. The opt-in `tests/remote_transport_check.cjs` exercises
real Windows capture/audio to a real local browser without saving footage. Its
temporary test certificate is bypassed only in the probe; it does **not** verify
trusted phone pairing.

The preview board covers all six tabs and Remote control/view/connecting/paused/
unavailable states across all seven themes. Its desktop picture is an authored,
clearly labeled SVG fixture; it contains no captured personal desktop data.

**Still unperformed:** physical Android typing/gesture/audio/performance checks,
30-minute LAN and Tailscale sessions with background/resume and source restart,
trusted Android HTTPS, and compatible Miracast hardware acceptance. Local loopback
success must not be presented as those device/network results.

Sources: [Windows capture](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api),
[Windows loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording),
[browser screen-capture support](https://github.com/mdn/browser-compat-data/blob/main/api/MediaDevices.json),
[Windows casting setup](https://support.microsoft.com/en-us/windows/hardware/display-graphics/screen-mirroring-and-projecting-to-your-pc-or-wireless-display).
