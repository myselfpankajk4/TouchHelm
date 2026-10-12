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
