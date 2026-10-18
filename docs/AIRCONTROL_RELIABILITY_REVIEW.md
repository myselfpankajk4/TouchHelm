# AirControl reliability review — 18 October 2026

## Follow-up: release continuity and expression evidence

The approved follow-up repaired three reproducible control defects and the
practice feedback display:

- A stationary hand could jump about 219 pixels horizontally on a 1920-pixel
  display after releasing a drag with smoothing off. Hand release now anchors
  movement at the drop location and maps subsequent movement toward the screen
  edges. Recenter/tracking interruption clears the session adjustment. Boundary
  releases require moving inward and back before reaching that edge again.
- Partial expression observations treated missing/invalid opposite-eye data as
  an open eye. Winks now require valid readings from both eyes. Smile activation
  uses the same bilateral average even when unrelated channels are unavailable.
- Explicit Release drag cleared dwell consumption and allowed an extra click
  without deliberate departure. It now consumes dwell at the release position;
  a held expression must also relax before it can trigger another action.
- The practice header replaced server feedback with a generic instruction.
  Calibration/action feedback now remains visible, while practice readiness and
  Windows-input status retain their dedicated indicators.

Seven Python regressions and one browser regression were added. The reproduced
failures were observed before their fixes. Final checks: **365 Python tests
passed**, **75/75 browser behavior checks passed**, **83 JavaScript tests passed
with one optional skip**, and **3/3 targeted visual checks passed**. Practice and
facial-calibration screenshots were inspected at 820×620 and 1120×800. Native
input was mocked and no webcam was opened for these checks. The independent
reviewer could not start because the delegation tool rejected its configured
model; the diff was reviewed directly instead. Physical accuracy and comfort
remain unmeasured by this follow-up.

## Scope and research

Audited camera observations, hand/head/combined arbitration, smoothing, calibration,
saved profiles, native shortcuts, ownership, pause/recovery, voice requests, HUD
controls and the owned desktop panel. Existing phone/Remote behavior is covered by
the broad regression suites. This is not a claim that every possible bug has been
eliminated.

| Project | Relevant finding | Decision |
| --- | --- | --- |
| [Project Gameface](https://github.com/google/project-gameface/tree/main/Windows) | Head/face mouse controller using MediaPipe, configurable gesture thresholds and smoothing; repository archived September 2025 | Useful design reference. Do not ship its old Python installer as a replacement. |
| [OpenSeeFace](https://github.com/emilianavt/OpenSeeFace) | Independent ONNX face/landmark models with CPU trade-offs | Candidate for a separate comparative benchmark. No verified superiority on this user's camera; it does not provide hand controls. |
| [opentrack](https://github.com/opentrack/opentrack) | Mature head-tracking architecture and filters | Reference for centering/filtering; not a drop-in hand/expression mouse engine. |
| [1€ filter](https://gery.casiez.net/1euro/) | Published speed-adaptive filtering method | Independently implement the algorithm for normalized pointer samples; no new dependency. |
| [MediaPipe face configuration](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python) | Default thresholds are 0.5; built-in smoothing applies only with one face | Use documented defaults, retain two-face ambiguity rejection, and filter pointer motion ourselves. |

The fixture comparison tested original/mirrored, dimmed, blurred and reduced-size
public portrait images. Both 0.65 and 0.5 tracked all six positive variants and
rejected a blank image. This does **not** show a measured accuracy gain from the
threshold change, or establish real-world expression accuracy.

## Reproduced defects and repairs

- Shared pinch hysteresis raised the other pinch's threshold during a drag,
  causing false conflicts/releases. Each pinch now has its own release threshold.
- Curling the tracked index finger displaced the click target. Confirmation now
  stabilizes the target; a held drag uses relative movement from pinch contact.
- Unassigned thumbs-up/smile gestures froze steering or prevented head dwell.
  Unassigned actions no longer consume those interactions.
- Sub-degree head jitter prevented dwell completion, especially at 4K. Adaptive
  smoothing, scaled for resolution, preserves the existing dwell radius.
- A facial click could be followed by a second dwell click. The dwell now waits
  for deliberate departure/rearming. Conflicting assigned expressions cancel.
- Missing optional expression/matrix/hand-classification outputs could crash the
  worker. Missing expression data retains valid head tracking; missing pose
  safely loses tracking and reports a reason.
- Fine calibration mutated the live profile before validating its range. Invalid
  captures now leave the prior profile/targets intact. Single-center quick Hand
  setup is available; five-target fine tuning remains optional.
- Combined face calibration unnecessarily depended on hand visibility. A separate
  current face sample buffer supports face calibration while PC control still
  requires both sources.
- Fixed high expression thresholds made personal movements difficult to calibrate.
  Explicit relaxed/expression captures now learn bounded activation/release
  thresholds. Quick assignment remains non-injecting during practice.
- Enabling control could replay a practice gesture still being held. Activation
  requires its release first.
- Adaptive inference could remain permanently slowed after a temporary load spike.
  It now recovers after sustained faster samples, without changing live capture
  properties. Capture FPS is measured separately from the inference target.
- Interrupted key taps/shortcuts could skip key releases. Cleanup now runs in
  `finally` and attempts all modifier releases.
- Windows lock/secure desktop was not explicitly stopping the camera. Start,
  activation, resume and the loop now guard it; capture/input ownership stop.
- A late setup cancellation could disable an already-installed runtime in memory.
  A completed Ready state is now retained.
- Resource metrics described the venv launcher rather than its Python child on
  this Store-Python installation. The interpreter now reports its own bounded
  usage samples. Shutdown requests an orderly interpreter exit before an owned
  process-tree fallback; unrelated applications are never targeted.
- Stop retained stale calibration/practice readiness. Those flags and simulated
  pointer visibility now clear. Start camera is reachable in the sticky header;
  unavailable Stop/Resume/Enable actions remain hidden until relevant.

## Recorded device observations

The final metadata-only 15-second checks stayed running in Hand, Head and Combined
modes and rejected no stale observations. Camera delivery was about **10 fps** in
this room, below the planned Hand/Combined tracking-rate targets. No claim is made
that changing a detector improves that capture limit.

| Mode | Accepted observations | Face observations | Median frame age | Median CPU, whole PC | Peak interpreter memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hand | 103 | Not enabled | 31.9 ms | 2.9% | 163.6 MB |
| Head | 69 | 11 | 25.3 ms | 2.0% | 144.7 MB |
| Combined | 103 | 15 | 41.2 ms | 4.9% | 189.1 MB |

No hand was presented during those observation checks. Face tracking was
intermittent, so these counts do not establish robust gesture recognition.
A subsequent owned-window inspection confirmed **Face tracked**, successful
neutral-head calibration into Practice, and movement of the simulated cursor.
Windows PC control was never enabled in that diagnostic; the camera was stopped
afterward. These are observation checks, not a controlled accuracy benchmark.

## Remaining physical acceptance

Reference images and synthetic observations do not establish comfort or gesture
accuracy for a particular person. A participating-user check is still required
for the new personal thresholds, click/drag feel, low light, camera obstruction,
unplug/reconnect, speech behavior and the planned 30-minute session. Camera
observation checks save no images and inject no PC input.

## Release verification

- Python regressions: **340 passed**, with native effects mocked.
- Browser behavior: **73/73 passed** across the existing phone/Remote flows and
  AirControl calibration, practice, ownership and facial assignment.
- JavaScript units: **83 passed, 1 optional skipped**.
- Final AirControl browser/visual run: **8/8 passed**, including all seven themes,
  both appearances, three desktop sizes and reduced motion. Sampled calibration,
  controls and facial-calibration screenshots were inspected.
- Actual isolated SDK reference-model, transformed-face and worker-to-parent
  pipeline checks passed. Reference images do not establish physical accuracy.
- Desktop shortcut launched source build `467c61eb301f3aa1cf4f0d055e057fa6`;
  authenticated Remote capabilities still reported video/audio available.
- A previously timing-sensitive provider test allowed only 10 ms scheduling
  margin beyond the provider deadline. Its test-only delay/budget now leave
  Windows scheduling room while still rejecting a blocking provider call.

The refreshed app was left with its camera off. The repository remains private.
