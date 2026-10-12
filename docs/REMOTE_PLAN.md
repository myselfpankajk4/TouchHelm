# TouchHelm Remote implementation record

Approved scope: sixth Remote tab, Control PC / View PC / system casting guide;
browser-only phone experience; optional PC audio; LAN HTTPS and private Tailscale.
No recording, file transfer, public relay or Android companion.

## Execution
- Stage 1: isolated media worker, authenticated single-session manager, bounded
  capture/audio, native input mapping, cancellation and lock cleanup.
- Stage 2: phone viewer/gestures and desktop enable/status/stop/casting settings.
- Stage 3: protocol, gesture and browser tests; visual matrix; real local transport
  check; documentation and private repository update.

## Rulings and evidence
- Execute without subagents, including final review, as explicitly requested.
- A managed worktree landed outside writable roots; archived it and created the
  isolated `codex/remote-controls` checkout under the workspace instead.
- The project venv launcher is inaccessible inside the sandbox, but works outside
  it. Verified using the actual Python 3.13 app runtime and installed the optional
  providers there. The earlier bundled-Python attempt lacked base dependencies.
- DXcam initially failed at first frame because its processor dependency was
  absent. Added explicit OpenCV fallback, selected NumPy processing and kept
  capture operations on one dedicated thread. Real capture then passed.
- Self-review found a disable-during-start race; reproduced both lookup/start
  variants before fixing them. Cleanup failures now block a replacement stream.
- Keep Tailscale media separate from Serve signaling; private ICE candidates only.
- Runtime audio formats are normalized to stereo 48 kHz when output devices change.
- Android, Tailscale and Miracast hardware checks remain unperformed until those
  devices/connections are available. Never substitute browser mocks for them.

## Software verification
- 215 Python tests passed with native input mocked.
- 83 JavaScript tests passed; one optional jsdom effects test skipped because jsdom
  is not installed. Existing effect logic tests still passed.
- 52 browser behaviors passed, including six-tab navigation, view-only input,
  direct coordinates, multiline text, draft restoration and pause without replay.
- Real Windows capture reached a real Chrome receiver at 1280×720, with measured
  12–15 fps and 1–5 ms network RTT in local probes. These are loopback observations,
  not promised Android/LAN/Tailscale performance or end-to-end latency.
- Actual WASAPI capture opened and the browser received Opus audio packets.
  Quality changes, mode changes and Stop passed; real PC input remained mocked.
- Batched preview inspections cover seven themes, two appearances, six phone
  sizes, six tabs and five Remote states plus casting; four desktop panels at two
  sizes. Screenshot fixtures contain only an authored sample desktop.
- Final review was performed in this session without subagents, per user request.
- Review regressions also cover failed worker construction and audio-driver
  failure during configuration. Audio state uses actual worker readback.
- 1,120 theme/appearance/viewport/state combinations passed the batched layout
  checks. The visual correction replaced browser-default gray buttons with themed
  controls and made the monitor/mode/Stop row sticky. Confirmation passed.
- Actual Windows provider returned the primary monitor at 2560×1440; receiver
  compatibility remained Unknown, as reported in the UI. No casting was started.
- Dependency check passed. The actual Latest desktop shortcut launched the current
  source from `D:\Mouse` with WebView2. A read-only capability query confirmed
  video/audio providers available and remote access still disabled by default.

## Progress
- Stage 1: software complete; physical LAN/Tailscale acceptance outstanding.
- Stage 2: complete.
- Stage 3: software verification, documentation, private main integration and
  latest-source launcher confirmation complete. Device acceptance stays outstanding.

## Follow-up reliability and setup repairs — 13 October 2026

- Reproduced the main WebSocket dropping with code 1006 after Remote Stop/tab
  exit. Native DXcam 0.3.0 teardown double-released comtypes-owned COM pointers.
  The version-scoped adapter corrects release ownership without editing dependencies.
- Switching tabs now preserves the stream while releasing gestures/held keys.
  Phone backgrounding still pauses capture; Stop does not end phone authentication.
- New video default: Clear 1080p/30, plus Detail 1440p/24, remembered per device.
  Increased desktop encoding budgets retain WebRTC congestion feedback. Removed
  the low-FPS resolution downgrade that mistook capture load for network congestion.
- Empty startup credentials no longer count as wrong guesses. Pairing survives
  reloads in tab-scoped session storage. Real wrong passwords retain global backoff.
- New host configurations get unique 12-character passwords, persisted on creation.
  Desktop Remote enablement enables password protection automatically. Existing
  configured PINs remain compatible; desktop Generate password rotates credentials.
- Added a desktop-owned Windows Wireless Display optional-feature installer with
  UAC handling, actual DISM progress, indeterminate download/check states, installed
  readback, restart/error reporting, and no phone-accessible privileged endpoint.

Verification: 224 Python tests; 83 JavaScript tests passed (one optional test
skipped); 53 browser interactions; full seven-theme light/dark layout matrix passed.
PowerShell installation helper parsed successfully. Installer/native authorization
effects are mocked in automated tests; no Windows feature installation was performed.
The real local Chrome probe received 1920×1080 video (13 decoded fps sample),
2560×1440 Detail video (12 fps sample), 1ms network RTT and 270 audio packets.
It passed tab switching, Stop/restart, and 12 consecutive paired page refreshes.
These are short local samples, not guaranteed frame rates or Android performance.
Trusted Android/Tailscale endurance and actual Miracast/Windows installation remain
unverified on physical devices.

## Shared audio and procedural-theme follow-up — 13 October 2026

- Media and Remote share requested/pending/confirmed PC-audio state. Audio-only
  mode creates no monitor capture, video track or input lease. Switching to screen
  viewing cleanly replaces it. Disabling audio while viewing preserves video.
  Missing/failed audio rolls both toggles back.
- Fullscreen requests landscape after entering fullscreen and releases orientation
  on exit. Unsupported browsers show manual rotation guidance; exit/Stop remain
  over the video. Cursor visibility removes the SVG `hidden` attribute explicitly.
- Phone text defaults to Shift+Enter for multiline Live typing; two phone Return
  presses preserve the draft. Ordinary PC Enter remains explicit/selectable.
- New PINs are four ASCII digits, including leading zeroes. Previously configured
  passwords stay compatible; wrong-guess backoff is preserved.
- All seven existing themes generate bounded SVG/CSS/JavaScript effects. Botanical
  and robot bitmap backdrops are unused; logos and real app/media artwork remain.
  Scenes use randomized motion, touch proximity, growth, eye tracking and material
  reactions with reduced motion and Rich/Calm/Off support.
- Desktop Set up trusted pairing installs missing PC providers/Tailscale, enables
  a PIN, creates private HTTPS and enables screen/audio access after success.
  Signed-out/unavailable states stay honest. Setup preserves theme preferences,
  saves the selected origin, and adds no public endpoint or phone CA certificate.
- Off-tab video receipt keeps streaming alive if mobile video decoding pauses.
  The visible viewer still requires fresh decoded frames for Live.

Evidence: 228 Python tests; 83 JavaScript tests (one optional skipped); 59 browser
interactions; seven-theme appearance/viewport matrix passed. Real local Chrome
received 1080p/1440p video and audio-only playback with zero video tracks. Shared
audio-off preserved video; audio-only → screen, 18 seconds off-tab, Stop/restart
and 12 paired refreshes passed. Native input was mocked; no personal screen footage
was saved. Short local samples reached 12fps, not an Android performance guarantee.

Physical Android orientation, destination-app double-Return behavior, listening,
theme performance, Tailscale sign-in/endurance and real installer acceptance remain
unperformed. Browser-only private-LAN trust requires domain/certificate provisioning
infrastructure; reserved IP/internal-name certificates cannot be publicly trusted.

Final live-host verification found a cold native-provider bootstrap taking seven
seconds while the normal command timeout was four seconds. The helper now warms
its read-only display/receiver context and emits readiness under a separate bounded
20-second startup budget. Commands retain their short deadline, queued cancellations
are checked before dispatch, and provider work stays outside the input event loop.
A mocked regression reproduces the original timeout and verifies the separation.
