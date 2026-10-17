# AirControl verification — 17 October 2026

Implementation is available in the modern WebView2 desktop. Hardware acceptance
remains open: synthetic observations and model loading do not establish physical
gesture accuracy or end-to-end speech behavior.

## Completed checks

| Check | Result |
| --- | --- |
| Python regressions | **288 passed** with native effects mocked |
| Browser behavior | **68/68 passed** in Chrome, including Phone/Air chooser, mappings, ownership and retained drafts |
| JavaScript units | **83 passed, 1 optional skipped**, no failures |
| AirControl layout matrix | Passed automated bounds/44px target checks for 7 themes × 2 appearances × 3 desktop sizes × Home/4 Air tabs (**210 combinations**) |
| Visual inspection | Sampled chooser, controls, settings and state images; one correction batch and confirmation; synthetic previews only |
| Reduced motion | Animated guide stops spatial animation under reduced-motion preference |
| Isolated installer | Actual installer completed in a disposable private test directory, verified model hashes, loaded both models, and retained Ready after reconstruction |
| Runtime | Windows x64, Python 3.13; OpenCV 5.0.0 / MediaPipe 1.1.1; main phone environment unchanged |
| Native HUD | Visible without foreground activation; owned Pause callback works; paused virtual cursor appears without moving the real cursor |
| Camera discovery | Two DirectShow devices enumerated; **neither opened** |
| Native focused-text scratch window | Two-way write/read, stale revision rejection, password/read-only exclusion and metadata-only dictation targeting passed |
| Hotkey | Registration unavailable on this PC; HUD/tray fallbacks remain available and the UI reports the conflict |
| Latest shortcut | Relaunched current source `9538f8e2ccd9d682d49dc5d2ba16ac3e`; running WebView build matched; existing Remote video/audio providers and monitor query remained available |
| Repository | GitHub visibility rechecked as **PRIVATE** before delivery |

Regression coverage includes pinch stability/hysteresis, single drag release,
conflicting gesture cancellation, scroll-to-pinch locking, pause/resume holds,
head dwell rearming, normal blink exclusion, Combined source requirements,
calibration, synthetic 21-point hand conversion and face matrix/expression output,
stale/nonfinite observations and worker EOF after a buffered frame.

Lifecycle tests cover the 250 ms observation watchdog, simulated versus native
button state, stable reacquisition, monitor removal, negative monitor origins,
physical mouse takeover, return to practice without stopping the camera, worker
stop, phone input blocking without disconnect, and in-flight Remote configuration
that cannot reclaim AirControl's lease. Remote viewing/audio are preserved.

Speech tests cover once-per-field requests, toolbar already open, Voice Access
priority, unsupported/protected fields, pause cancellation, and a slow
accessibility provider that cannot delay Stop. No automated test starts listening
or claims that a Windows microphone is ready.

The guide and runtime privacy copy distinguish local camera-image processing from
MediaPipe's documented SDK metrics. Bundled model digests and pinned wheel hashes
are checked. Phone requests have no AirControl start/frame endpoint; desktop
commands require the owned window URL and its token.

## Repeatable commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
npm test
$env:CHROMIUM_EXECUTABLE='C:/Program Files/Google/Chrome/Application/chrome.exe'
node tests/test_web_client.cjs --behavior-only
node tests/test_web_client.cjs --visual '--filter=AirControl theme'
```

The visual matrix was run as one inspection batch, one correction batch and one
confirmation. Later functional changes were covered with targeted/full behavior
regressions. The browser tests need permission to access their own loopback test
server; a restricted-browser network denial is not an app regression.

Opt-in native checks below show only an owned HUD/scratch window, enumerate
cameras and inspect metadata. They do not open a webcam, request speech or read
unrelated user text:

```powershell
.\.venv\Scripts\python.exe tests/native_aircontrol_check.py
.\.venv\Scripts\python.exe tests/native_text_check.py
```

## Physical checks still required

| Check | Current evidence |
| --- | --- |
| Hand / Head / Combined real gesture accuracy | **Not run**; no webcam capture was started during implementation |
| Low light, camera obstruction, unplug/reconnect and minimized tracking | **Not physically run**; lifecycle/error paths tested with mocks |
| Real mouse override and drag safety during camera control | Synthetic/native helper coverage; **physical camera session pending** |
| Mixed DPI, rotation, negative multi-monitor layout and monitor removal | Coordinate/native-helper tests; **hardware combinations pending** |
| Win+H microphone permissions, cancelled language setup and Voice Access speech interaction | Metadata and mocked flow checked; **real speech pending** |
| All themes at Windows display scaling levels | Browser viewport matrix passed; **Windows scaling hardware check pending** |
| 30-minute real session | **Not run** |

The performance targets remain acceptance targets, not measured claims:

| Metric | Target | Actual camera-session result |
| --- | --- | --- |
| Hand updates | ≥20/sec | Unmeasured |
| Combined updates | ≥15/sec | Unmeasured |
| Median pointer latency | <150 ms | Unmeasured |
| 30-minute CPU/memory behavior | Record actual values | Unmeasured |

The panel exposes observed update rate, inference duration, host frame-to-input
latency, worker CPU share of total PC capacity and working-set memory. Its capture
timestamp is taken after camera read; this is not a photon-to-display latency
measurement. A real test requires a person positioning themselves, practicing and
explicitly starting/enabling control. Camera and microphone were left off.

The latest-source shortcut and private GitHub delivery are checked separately at
release time; the commit history identifies the delivered source.
