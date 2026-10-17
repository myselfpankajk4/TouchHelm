# AirControl reliability implementation plan

> Execute sequentially with superpowers:executing-plans; no subagents.

**Goal:** Make the existing Hand, Head & Face and Combined modes easier to operate, repair recognition/mapping faults, and show actionable diagnostics.
**Architecture:** Retain the isolated camera worker, desktop-only bridge and validated parent input executor. Improve observations, filtering and calibration rather than silently replacing the provider or introducing another installer.
**Spec:** The approved AirControl plan in this conversation, expanded by the user's request for a comprehensive audit on 18 October 2026.
**Stack:** Existing MediaPipe Tasks/OpenCV, Python, owned WebView2 panel; no phone camera endpoint.

## Constraints and review focus

- Never inject input during calibration/practice; explicit Enable and input cleanup remain.
- Do not relax multiple-face rejection or the 250 ms stale-observation guard.
- Preserve saved profiles, custom mappings, themes, phone connections and Remote viewing/audio.
- Do not record camera images; keep physical accuracy separate from synthetic/reference tests.
- Keep ordinary blinks inactive, prevent duplicate dwell/expression clicks, and revalidate expression samples.

## Tasks

- [x] Reproduce shared pinch hysteresis, unassigned-gesture blocking, noisy head dwell, and incomplete face-output failures with tests.
- [x] Add a speed-adaptive pointer filter based on the published 1€ algorithm; test jitter, response, timestamps and resets.
- [x] Repair gesture arbitration and pinch release; keep holds and conflict cleanup deterministic.
- [x] Add single-center quick Hand calibration with optional existing five-target fine tuning; test ownership/gating and invalid captures.
- [x] Add explicit neutral/expression sampling with measured thresholds, hysteresis, clear scores and guarded quick assignment; migrate old profiles.
- [x] Improve face/hand diagnostics, incomplete output handling and adaptive inference recovery without mutating a running camera.
- [x] Audit lifecycle, voice requests, overlay, mappings and camera/monitor changes; fix demonstrated defects and document findings.
- [x] Run model/pipeline checks, full Python/browser regressions, themed desktop inspection and latest-source launch; record physical limits.
- [x] Commit and push the verified changes to the existing private repository.

## Research decision

Project Gameface (archived September 2025) demonstrates head/face mouse control using MediaPipe with adjustable gesture thresholds. OpenSeeFace offers separate ONNX face models; opentrack provides head tracking, not a hand-gesture engine. None proves better accuracy on this PC without a comparative physical benchmark. Keep the installed provider for this repair, use the published 1€ filtering method, and document the alternatives and their limits.

Sources: https://github.com/google/project-gameface/tree/main/Windows · https://github.com/emilianavt/OpenSeeFace · https://github.com/opentrack/opentrack · https://gery.casiez.net/1euro/ · https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python

## Execution rulings

- The user explicitly expanded the request to a complete AirControl audit and asked not to perform narrow question-driven debugging. Proceed within that scope without more design check-ins or subagents.
- Add pinch-target stabilization: synthetic observations proved that curling the tracked fingertip displaced the click target. Retain drag while held.
- Include native shortcut cleanup and lock-state camera shutdown: both were demonstrated lifecycle defects in the existing approved scope.
- Measure interpreter usage and request graceful stop: a direct PID check proved the Store/venv launcher and inference interpreter are different processes.
- Keep documented-default face thresholds with multi-face rejection; transformed fixtures showed equal detection at 0.5 and 0.65, so do not claim an accuracy improvement from that setting alone.
- Physical expression accuracy and the 30-minute acceptance test remain unverified. Record intermittent face detections and the observed camera-rate limit honestly.
