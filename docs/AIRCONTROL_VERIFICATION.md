# AirControl verification — 17 October 2026

**Latest update: 18 October 2026.** See the
[Head control release](AIRCONTROL_HEAD_RELEASE.md) for the default mode, dwell
action dock, smoothing and native click/drag evidence. The earlier
[reliability review](AIRCONTROL_RELIABILITY_REVIEW.md) covers prior repairs,
open-source comparison and measured camera limits. Earlier results below are
historical observations, not evidence of current physical gesture accuracy.
Current automated totals: **358 Python**, **74 browser behavior**, **83 JavaScript
unit passes** (one optional skip), and **9 AirControl browser/visual checks**.

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

## User-folder installer repair — 17 October 2026

The first workspace-directory installer check missed Microsoft Store Python's
LocalAppData redirection. Installation in the actual user directory reproduced
exit **106**, `failed to locate pyvenv.cfg`: Python saw a virtual path while the
native venv launcher looked outside its physical package LocalCache directory.

Setup now resolves its physical directory before passing paths to subprocesses,
and resolves again after creating a fresh directory. Runtime creation, package
installation and model-check failures report their stage, exit code and bounded
diagnostic text; package-source URLs are redacted. Owned failed/cancelled installer
processes and output streams are cleaned up.

The actual user's runtime was repaired through the same installer entry point.
Package installation, both model loads and Ready-marker reconstruction passed;
**no camera was opened**. Regression checks cover existing/fresh redirected paths,
the original pyvenv error and credential redaction. This resolves setup availability
but adds no physical gesture or speech accuracy evidence.

Final repair verification: **292 Python tests passed**. An existing 150 ms provider
deadline check timed out in an initial run, then passed both in isolation and in
the final full run; its timeout was not relaxed. The Latest shortcut relaunched
source `6edb02619f5a6b620cf168f9131babaa`, with Remote providers still available.

## Tracking and practice repair — 17 October 2026

The user's stationary Windows pointer occurred in **Practicing**. That mode
deliberately does not inject PC input, but Enable was below the main workspace and
the simulated cursor was hidden in another tab. Enable now stays in the sticky
session header, practice opens after calibration, and state/camera feedback say
explicitly whether the Windows cursor is being controlled. Hand mode explicitly
labels face tracking off.

Additional reproduced defects and fixes:

- Handedness score was used as hand-presence confidence. SDK-accepted landmarks
  now carry a tracked flag; left/right uncertainty cannot freeze the pointer.
- Pinches required a straight index and could be overridden by an Open Palm pose.
  Thumb/index landmark contact now drives pinch after its existing stability gate;
  closed-fist and conflicting-pinch guards remain.
- Canned weak/unknown classifications and hold timing looked like recognition
  certainty. Unsupported/weak poses are rejected (0.70 acceptance threshold), and
  the prominent percentage is removed. Supported poses still require their holds.
- Recenter in practice entered a paused state that could not Resume. It now stays
  in the non-injecting practice/calibration stage.
- Any simulated action, including Pause, could satisfy the practice click gate.
  Only a simulated mouse press/click now satisfies it.
- Open Palm froze ordinary steering even though Resume applies only while paused.
  It now steers in active/practice mode and retains held Resume while paused.
- Pinch distances now account for image aspect ratio. Mirrored face expressions
  retain the subject's left/right wink assignment. Stale observations no longer
  remain labeled tracked or retain a stale tracking-rate value.

**Native evidence:** `tests/native_aircontrol_pointer_check.py` moved the real
Windows cursor to two targets inside an owned blank scratch window through
AirControlService/GestureEngine/WindowsInputController, verified readback, checked
tracking-loss pause and restored the starting cursor. No clicks, keyboard input
or camera capture were sent. This tests actual pointer execution independently of
physical gesture accuracy.

**Actual model evidence:** `tests/native_aircontrol_model_check.py` runs the locked
isolated SDK in Video mode, using the production frame preprocessing, converter
and engine. Google's four public examples—Thumb_Down, Victory, Thumb_Up and
Pointing_Up—were accepted; a public portrait produced one head pose and recentered
correctly. Median inference across the hand reference frames was **22.9 ms** in
the recorded run; this is a static-reference benchmark, not webcam latency/FPS.
No camera or native input is used in this check.

```powershell
.\.venv\Scripts\python.exe tests/native_aircontrol_pointer_check.py
.\.venv\Scripts\python.exe tests/native_aircontrol_model_check.py --download-reference
```

The model check downloads only the fixed public Google sample images once, under
ignored `.tmp/aircontrol-reference/`; repeat runs use that cache. References:
[official gesture example](https://colab.research.google.com/github/googlesamples/mediapipe/blob/main/examples/gesture_recognizer/python/gesture_recognizer.ipynb),
[gesture outputs and score semantics](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python),
[Face Landmarker and mirrored blendshapes](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

Library research included [MediaPipe releases](https://github.com/google-ai-edge/mediapipe/releases)
and [OpenSeeFace](https://github.com/emilianavt/OpenSeeFace). MediaPipe remains the
selected provider: it supplies both supported hands and face outputs in the
already-locked Windows/Python runtime. OpenSeeFace is a face-focused alternative,
not a repair for this practice/input integration. This is an implementation-fit
decision, not a claim that any library recognizes every gesture perfectly.

Fresh Python regressions: **303 passed**. The seven-theme desktop bounds matrix
passed and a representative practice image was inspected. Physical hand/head/
combined accuracy, low-light robustness and the 30-minute camera session still
require a participating user; model/reference and scratch checks do not verify
those conditions.

## Unavailable camera repair — 17 October 2026

The next user attempt reported **Unavailable**, rather than an active pointer
that failed to move. Native panel inspection showed “Camera worker stopped.”
A short metadata-only camera diagnostic reproduced a Combined worker exiting
after exactly 15 observations, with no explicit JSON error.

The adaptive branch changed DirectShow's FPS from the inference thread while
the capture thread was inside `read()`. It also repeated that change on later
slow samples. The repair reduces inference frequency without changing the live
camera's properties. A failed camera read now raises a clear error instead of
ending the worker successfully. The stdout reader drains through EOF, including
errors written just before process exit; bounded stderr and exit-code details
are retained for native failures.

Evidence from this repair:

- The full isolated pipeline check deliberately slows real inference past the
  adaptive threshold and simulates a driver that rejects property changes while
  reading. It failed before the repair and passed afterward, delivering 12 native
  pointer proposals in its active interval. Windows input is mocked in this test;
  camera input is Google's cached public reference image.
- Two new pipe regressions first failed because explicit errors and crash details
  were lost, then passed. A failed-read test checks model/capture cleanup; a
  service regression checks error preservation, button release and ownership
  return after a camera failure.
- Actual local camera checks, with no image recording or PC input: Hand stayed
  running for the 22-second check (246 observations, 14.8 updates/s, maximum frame
  age 147.5 ms); Combined also stayed running (192 observations, 14.7 updates/s,
  maximum frame age 159.1 ms). Combined supplied 191 face observations; these
  checks did not ask the user to perform particular gestures.
- These are short capture/transport checks, not a verified 30-minute session or
  proof of physical click/drag accuracy. The measured rates do not establish the
  planned 20 updates/s Hand performance target. The repaired build was launched
  for a participating-user pointer check.

```powershell
.\.venv\Scripts\python.exe tests/native_aircontrol_pipeline_check.py
```

The pipeline check opens no webcam and injects no Windows input. Its temporary
profile does not replace the user's profile. Native camera diagnostics collected
counts, timings and errors only; images were not saved.

### Participating-user tracking and calibration inspection

The user confirmed the camera now stayed running but still saw no practice
cursor. Native inspection found **Calibrating, 0 targets captured**, rather than
Practice. With the user's index finger held in view, the panel displayed live
hand landmarks and **14.9 updates/s**. No Windows input was enabled during that
inspection. The fixed calibration target had been mistaken for a frozen cursor;
the Capture action was below the main preview.

The preview now shows a separate live **Your finger** pointer and labels the
fixed **Target**. Current step, instructions and Capture appear before the
preview. The live marker remains visible when landmark lines are disabled and
hides on tracking loss. The existing calibration, practice click and explicit
Enable PC control gates are preserved. Browser regressions cover marker position,
stale-state hiding and the visible Capture action. The existing all-theme desktop
matrix was inspected after the change.

The participating user completed the flow and confirmed **“Windows cursor moves
after Enable.”** This verifies Hand-mode pointer activation on this PC. It does
not establish physical click/drag accuracy, Head/Combined control accuracy,
low-light robustness or the planned 30-minute acceptance session.

Native inspection of the updated panel confirmed the live finger marker and a
successful center capture, advancing to target 2 of 5. The remaining captures
require the user to move their hand. Calibration captures use the physical mouse;
practice and calibration intentionally do not inject gesture-driven PC clicks.

Full browser verification also reproduced a buffered typing race: an explicit
Send could wait behind an earlier PC-field read, whose reply was ignored after
Live typing was disabled. The reply now resumes the queued explicit Send only
after checking the same field and unchanged PC-text baseline. A changed target
keeps the phone draft and requests relinking. Browser regressions cover both
cases. Read-only text queries are permitted by the ownership test, while replayed
edits, keys and clicks remain forbidden.

Final browser checks: **69/69 passed**. The first batched run hit one 3-second
navigation timeout in the existing PIN-dialog check under concurrent test load;
the final full browser run passed without relaxing timeouts. JavaScript units:
**83 passed, one optional skipped**. Latest-source launch matched
`eaef234e5c2c294e64a7e9bee3b7955d` and existing Remote video/audio providers remained
available. A live Hand-mode recheck was requested after deployment; no physical
gesture success is assumed from the automated evidence.
