# AirControl daily-use workspace

Date: 18 October 2026

Status: Written design for user review; implementation has not started.

## Purpose and approved direction

The user wants TouchHelm to support both comfortable daily hands-free PC use and
a polished experience for other users. They approved improving the existing
engine and redesigning the desktop control workspace together. This document
defines the first release of that direction: guided setup, a focused session
workspace, useful practice exercises, head-only scrolling, and repeatable quality
checks.

Success means someone can understand the next step, practice without controlling
Windows, deliberately enable control, perform everyday pointer tasks, and recover
from interruptions. Visual polish must help those tasks. Recognition accuracy and
comfort must be measured with a participating person before they are described
as established.

## Starting point

The current system has an isolated MediaPipe/OpenCV worker, a pure gesture
engine, a desktop service that owns native input, a WebView2 interface, and a
non-activating native HUD. It already supports Hand, Head & Face, and Combined;
calibration; practice; personal expression thresholds; dwell click/drag; and
tracking-loss cleanup.

The latest reliability changes in this checkout preserve hand-drag release
position, require complete wink evidence, consume dwell after explicit drop,
and expose practice feedback. These changes remain part of the starting point.
Their evidence is 365 Python tests, 75 browser behavior checks, 83 JavaScript
passes with one optional skip, and three targeted visual checks. Those counts
are historical evidence, not acceptance of the release designed here.

Current problems include the movement area falling below the first viewport at
small desktop sizes, setup controls competing with session controls, practice
providing limited task feedback, and the lack of head-only scrolling. Prior
camera observations measured roughly 10 capture frames per second in that room;
software filtering cannot create observations the camera did not deliver.

## Scope and boundaries

Included:

- Reshape the AirControl desktop page and clarify the Phone/AirControl chooser.
- Make setup and everyday session use distinct views of the same service state.
- Add task-based click, drag, and scroll practice with clear completion feedback.
- Add a session-only Head scroll mode to the desktop panel and native HUD.
- Add bounded session diagnostics, deterministic motion checks, and accessibility
  checks using the existing browser test infrastructure.
- Document and run automated acceptance; provide a repeatable participating-user
  protocol for physical acceptance.

The phone remote, pairing protocols, authentication, Remote streaming, media
providers, speech integration, and seven-theme system retain their contracts.
This release does not replace MediaPipe, enroll face identities, introduce a new
frontend framework, record camera images, or claim a measured accuracy gain from
static reference images. A tracker replacement is a separately scoped decision
only if comparison evidence supports it.

## Visual direction

Use the existing Windows control-console identity. The live interaction area is
the distinctive element; avoid promotional eyebrows, large decorative gesture
art, repeated instruction cards, and competing primary actions. Left-align task
content. Keep the existing mouse mark and seven themes.

The default token values remain:

| Role | Default value |
| --- | --- |
| Background | `#0B131B` |
| Surface | `#1A2A37` |
| Accent | `#72D8E6` |
| Text | `#EEF7FA` |
| Supporting text | `#B4C8D2` |
| Error | `#FF8AA1` |

Implement through existing theme variables, not fixed default colors. Light
appearances use their existing theme counterparts. Segoe UI/system typography
preserves Windows familiarity: 26–30 px page title, 18–20 px section title,
14–16 px main controls/body, and at least 12 px supporting diagnostics. Body
instructions stay below 75 characters per line where space permits.

Use a consistent 4/8/12/16/24 px spacing scale. Panel edges group related tasks;
they do not wrap every fact in a separate card. Motion responds to user actions
and tracking state; reduced motion removes spatial animation. Existing ambient
effects remain suppressed while tracking.

## Workspace and navigation

```text
AirControl      Practice / PC control on       Pause or Resume   Stop
------------------------------------------------------------------
Camera -> Calibrate -> Practice -> Enable       [setup only]
------------------------------------------------------------------
Camera or practice movement area     Tracking / current instruction
                                     Contextual calibration action
                                     Click / Double / Right / Drag
                                     Scroll / Recenter
------------------------------------------------------------------
Session       Practice       Personal settings       Diagnostics
```

The persistent session bar always names whether Windows input is off, active, or
paused. It exposes the relevant primary action: Start camera, the current
calibration capture, Open practice, or Enable PC control. Pause/Resume and Stop
remain available during an owned session, including when another panel is open.
Camera start and Enable remain distinct actions.

At 820×620, the supported minimum desktop size, the movement area must begin in
the first viewport and expose at least 240 px of usable height. Compact the
navigation and session chrome before sacrificing that area. At 1120×800 and
1440×900, use a main stage with a narrower task inspector. At smaller effective
widths, including 200% zoom, use one column and vertical scrolling without
horizontal page overflow or covering escape controls.

Put camera, monitor, and control-mode selection in the setup inspector and
Personal settings. During a session, summarize the choices and provide an
explicit Change setup action that explains it stops control and requires
calibration/practice again. Existing saved mode/profile choices remain intact.

Session, Practice, Personal settings, and Diagnostics use accessible tab behavior
with selected state, panel association, keyboard arrows/Home/End, and stable
focus. Opening Practice to inspect exercises does not silently revoke active
ownership; starting an exercise explicitly enters the existing non-injecting
practice lifecycle. Device/configuration choices are never changed by rendering.

## Guided setup and recovery

Derive the setup step from the service snapshot, not a second frontend lifecycle:

1. Camera: show runtime readiness, camera and monitor choices, and Start camera.
2. Calibrate: show the current required source and a capture button beside the
   stage. Keep quick Hand center setup and optional five-target fine tuning.
3. Practice: show tracking and a click exercise. Head dwell is sufficient;
   expression calibration is optional and available in Personal settings.
4. Enable: explain input transfer and offer Enable PC control only when the
   service's existing calibration/practice, freshness, stable-tracking, neutral
   gesture, and monitor checks permit it.

Expose a service-derived activation-readiness reason so the UI can explain an
unavailable Enable action without guessing. The same readiness helper must be
used by activation validation. Snapshot reads do not acquire ownership or perform
slow hardware queries.

For tracking loss, show which required source is missing and the relevant
recovery action. Retain the 250 ms freshness watchdog and explicit Resume after
stable reacquisition. Combined continues to require both sources for PC control.
Invalid expression data must not remove otherwise valid head pointing.

Render command errors next to the task and preserve them until another relevant
attempt or successful recovery. Do not replace them with a generic practice
message. Status announcements occur on meaningful transitions, not each frame.
Stop clears preview/practice state and returns phone ownership. Changing tabs,
minimizing, and viewing diagnostics do not stop a session.

## Task-based practice

Practice consumes the gesture engine's proposed events; it never calls native
mouse, keyboard, wheel, speech, ownership, or HUD-injection operations. Service
state remains authoritative. A small practice module receives normalized points,
timestamps, and action proposals and returns exercise state for the snapshot.
The frontend renders that state without inventing successful actions.

Exercises are explicitly started and can be reset or exited:

- Click: three large targets in a deterministic sequence. A supported left-click
  proposal or a short stationary left-button press/release completes the current
  target only if it lands inside it. Count a click outside the target as a miss.
- Drag: press within a source target, move into the destination, and release
  there. Head two-dwell drag and held-expression/hand drag use the same exercise.
  An early release gives a retry instruction. Tracking loss cancels the attempt.
- Scroll: move a simulated document to a marked destination using hand scroll or
  the new Head scroll mode. The document moves only on proposed scroll events.

Hit testing uses the displayed stage's dimensions supplied as a validated,
bounded practice viewport, so target visuals and evaluation agree after resize.
A resize restarts the current attempt without counting a miss. Targets are at
least 64 CSS px and remain inset from the stage edges. Completion time and misses
are exercise results, not recognition-confidence percentages. A Pause proposal
pauses the exercise; no progress accrues until it is resumed explicitly.

Free practice remains available immediately after calibration. Its valid click
path continues to satisfy the existing activation practice requirement. During
a click exercise, an action inside the current target can also satisfy that
requirement; a miss cannot. Completing all three targets and the drag/scroll
exercises is optional training, not a new mandatory gate for people using only
a subset of controls. Head expressions remain optional. No calibration
thresholds are changed automatically from task results.

## Head-only scrolling

Head scrolling is a session submode, separate from gesture mappings and saved
profiles. It is available only after Head calibration, in practice or active
control. Existing Hand/Combined two-finger scrolling retains its behavior.

Choose Scroll from the panel or by dwelling on the native dock. Entering it
releases any owned drag, cancels pending click/expression confirmation, and
clears the ordinary desktop dwell timer. The native HUD shows Scroll up, Scroll
down, Done, Pause, and Stop. The main panel offers matching controls and an
explicit Return to pointer action. Practice draws equivalent controls inside its
stage and never opens the native overlay.

During Head scrolling:

- Head pose drives a visible virtual cursor for scroll/dock selection. Windows'
  cursor stays at the entry position so scroll targeting is stable. Physical
  mouse takeover detection remains enabled against that position.
- Ordinary pointer, click, drag, expression, and automatic-dictation proposals
  cannot inject PC input. Only scroll and escape/navigation actions are allowed.
- Dwelling on Up or Down for the configured dwell duration starts scrolling.
  Emit at most one small existing scroll unit (`dy=+2` or `dy=-2`) per 150 ms,
  using observation timestamps. Do not replay missed intervals after a stall.
  This is an internal wheel-adapter unit, not a promise of a physical notch.
- Leaving a direction target immediately stops repeat; entering another target
  starts a fresh dwell. There is no momentum or background repeat timer.
- Done returns to pointing and consumes dwell until deliberate departure. A
  held expression must relax before it can act again.
- Tracking loss, stale frames, physical takeover, Pause, Stop, Recenter, desktop
  lock, monitor change, practice transition, and worker failure terminate scroll
  mode and its repeat state. Resume returns to ordinary pointing.

Use one geometry description for native drawing and engine hit testing. Increase
the HUD bounds as needed rather than reducing action target sizes. Keep physical
monitor origins, mixed coordinate conversion, non-activation, and HUD escape
rearming behavior covered by regressions.

## Components and data flow

Keep the worker/engine/service boundary:

```text
Camera worker -> validated current observations -> GestureEngine proposals
                                                 |
                                  AirControlService lifecycle/ownership
                                       /                    \
                           practice evaluator        guarded native adapter
                                       \                    /
                                      bounded snapshot
                                       /           \
                                 desktop UI      native HUD
```

- `worker.py`: capture and landmark extraction remain isolated and latest-only.
- `engine.py`: own pointing/click/scroll submode transitions and timestamp-based
  repeat. It stays independent of Windows, browser layout, and camera imports.
- `service.py`: own calibration/readiness, activation, lifecycle cleanup,
  practice evaluation, metrics, and the final native-input allowlist.
- A focused practice module owns task geometry/evaluation and bounded results.
- `hud.py` and the native overlay share scroll/dock geometry and action names.
- `gui/web/aircontrol.js`: keep bridge calls and event binding, extracting pure
  view-state derivation or exercise rendering only where needed for clarity.
  Retain plain JavaScript and the existing desktop integration.

Desktop bridge commands remain authenticated and owned-window-only. New practice
viewport and scroll commands validate values, allowed lifecycle states, and
control mode. No phone endpoint is added. Saved profiles use existing validation
and migration behavior; this feature requires no new persistent profile fields.

## Measurement and open-source tools

Add a deterministic replay check that feeds timestamped synthetic observations
to the real engine and records stationary physical-pixel jitter, step-response
time, action counts, releases, and interruptions at 10, 15, and 30 observations
per second on HD and 4K coordinate scales. Compare the same fixtures/settings
against the pre-release implementation. These results measure the control
algorithm, not physical detector accuracy.

Diagnostics expose measured capture FPS, accepted observation FPS, inference
duration, current frame age, rolling median/p95 frame-to-input latency, tracking
interruptions, and existing worker CPU/memory. Label the sample window and show
unavailable values honestly. Snapshot rendering must not slow inference or block
Stop. Keep rolling latency data to 600 samples, completed exercise results to
100, and only aggregated counts for a long session. A Reset measurements action
clears these values without restarting capture or changing calibration.

An explicit Export report writes sanitized JSON containing mode, non-identifying
display dimensions, aggregate metrics, exercise results, build identifier, and
test duration. Do not include camera frames, landmarks, expression samples,
window titles, field contents, device identifiers, or file-system paths. Nothing
is uploaded. Recording a participating-user observation is opt-in; starting the
camera still requires the existing explicit action.

Use the installed Playwright harness and add pinned axe-core accessibility
tooling as a development dependency with its upstream license notice. Check the
active AirControl states and manual keyboard/zoom behavior; automated scanning
alone is not accessibility acceptance. Use Project Gameface/eViacam as design
references. OpenSeeFace is a candidate for a future isolated comparison; do not
install or ship another model/runtime in this release.

References researched for this design:

- [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python):
  built-in smoothing applies only with one face; retain multiple-face ambiguity
  protection and evaluate our own filtering rather than removing that guard.
- [Project Gameface](https://github.com/google/project-gameface): Apache-2.0;
  archived September 2025. Head/expression interaction reference.
- [eViacam](https://github.com/cmauri/eviacam): GPL-3.0. Interaction reference;
  no source is copied into TouchHelm by this design.
- [OpenSeeFace](https://github.com/emilianavt/OpenSeeFace): BSD-2-Clause code/models;
  CPU tracking candidate. Upstream FPS claims are not this PC's measurements.
- [axe-core](https://github.com/dequelabs/axe-core) and
  [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing).

## Acceptance and evidence

Automated release requirements:

1. All existing Python, JavaScript, and browser behavior suites pass, including
   the earlier hand release, wink evidence, and explicit-drop regressions.
2. New regression tests first reproduce failures for readiness guidance,
   practice hit testing, task completion/cancellation, scroll exclusivity,
   repeat timing, stale observations, all escape transitions, and rearming.
3. Practice causes zero native-input, dictation, or ownership effects. Entering
   Head scrolling while dragging releases once; no desktop click/drag occurs
   while scrolling or on exit.
4. Across seven themes, both appearances, and 820×620 / 1120×800 / 1440×900,
   essential controls remain visible/reachable, the stage meets the initial-view
   requirement, and no horizontal overflow or control overlap appears. At 200%
   zoom, reading order and escape controls remain usable through reflow.
5. Active AirControl states have no unresolved critical/serious axe findings.
   Main text meets 4.5:1 contrast; large text meets 3:1. Controls have visible
   keyboard focus and at least 44×44 CSS px targets. Native HUD actions also
   retain usable geometry and never activate another window.
6. Replay comparisons add no unintended actions on stationary/jitter/conflict
   fixtures, release on the first invalid required-source observation, preserve
   edge reachability, and do not worsen existing 90% step-response time by more
   than one observation interval. Publish the fixture/settings and measured
   jitter/response values rather than claiming unmeasured improvement.
7. Report export is bounded, parseable, and contains only the specified data.
   Phone authentication, retained drafts, ownership, Remote view/audio, and
   saved profile choices retain their existing regression coverage.

Physical acceptance is a separate participating-user session: set up from camera
off, complete click/drag/scroll tasks, exercise Pause/Resume and physical takeover,
test ordinary blinking and deliberate expressions, obscure/reacquire tracking,
and use the system for 30 minutes. Record actual delivery rate, latency window,
task outcomes, interruptions, resource values, and the person's comfort feedback.
Camera unplug/reconnect is checked with an available device. Mark any hardware
scenario that was not run as unverified. Do not call the product physically
validated until this session is completed.

## Delivery sequence

After written-spec approval, write and review an implementation plan that orders
the work as: pure session/readiness contracts; scroll engine/HUD integration;
practice evaluator; frontend workspace; diagnostics/accessibility tooling; then
regression, visual, and physical acceptance evidence. Add failing behavioral
tests before the corresponding changes. Preserve and review the current local
reliability work rather than resetting the checkout. Update PRODUCT.md, DESIGN.md,
and AirControl help to match the delivered behavior after implementation.

The final report must distinguish implemented behavior, automated verification,
and physical acceptance. External publication and tracker replacement are not
part of this release.
