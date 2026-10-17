# AirControl implementation ledger

Approved 17 October 2026: desktop Phone/AirControl chooser; PC webcam; Hand,
Head & Face and Combined modes; calibration and non-injecting practice;
remappable supported gestures; native overlay; Windows dictation/Voice Access;
isolated worker/runtime; exclusive app input ownership; seven themed surfaces.

Execution is sequential, without subagents. Physical camera/speech results must
be reported separately from mocked tests and synthetic observations.

Ruling: Work in the existing clean D:/Mouse checkout — the user's latest-source
shortcut and approved continuing workflow use this location. Preserve the private
repository and the existing phone server. Do not create a second managed checkout.

Ruling: Use OpenCV contrib from MediaPipe's dependency graph, not an additional
headless OpenCV distribution — both publish cv2 and must not share one runtime.

Stages:
1. Tracking engine, profiles, setup and worker.
2. Native ownership/lifecycle, overlay, hotkey and desktop bridge.
3. Desktop chooser/panel, animated guides, calibration, practice and speech.
4. Regression, visual/native checks, documentation and private GitHub update.

Progress and verification will be recorded below.

Implemented:
- Isolated checksum-locked runtime/setup, bundled model provenance and latest-frame
  camera/inference worker. Actual isolated installation and model loading passed
  without opening a camera.
- Pure hand/head/combined gesture engine, calibration, practice, profile bank,
  expression practice, stable acquisition and native input executor.
- Exclusive input transfer, Remote-to-View preservation, phone draft retention,
  watchdog/worker/monitor cleanup and physical-mouse override paths.
- Desktop chooser/panel, animated SVG tutorials, seven theme integration, native
  non-activating Forms HUD, paused Head virtual cursor, tray and hotkey fallback.
- Guarded Windows dictation, metadata-only field checks and separate Voice Access.

Review fixes included scroll-to-pinch conflicts, worker EOF behind a buffered
frame, stale reacquisition, practice lease release, disappeared selected monitors,
queued speech after pause and slow accessibility work delaying Stop. The first Tk
HUD prototype failed no-activation verification; it was replaced by Windows Forms
and its native no-activation/callback/virtual-cursor smoke test passed.

Fresh final verification: 288 Python tests, 68 browser checks and 83 JavaScript
tests passed (one optional JS check skipped). The bounded theme/layout matrix and
native scratch-text checks passed. See AIRCONTROL_VERIFICATION.md for exact scope.
Physical webcam/speech accuracy and the requested 30-minute measurements remain
unperformed; no success or performance claim is made for them.

Documentation, preview image and third-party notices are included. Delivery uses
the existing private repository and Latest shortcut; camera start stays explicit.

Review ruling: perform the final source/requirement review directly because the
user explicitly prohibited subagents. The existing approved private GitHub update
supplies the integration decision; no additional branch/PR menu is required.
Latest shortcut verification matched source 9538f8e2ccd9d682d49dc5d2ba16ac3e and
confirmed existing Remote video/audio provider availability.
