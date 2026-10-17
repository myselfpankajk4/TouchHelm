# Head-first control — 18 October 2026

## Changes and root causes

Head mode previously offered only dwell left-click. Profile validation and the
mapping UI restricted drag to hand pinches, leaving no head-only drag path and
no accessible click-type selector. The new panel and non-activating native dock
offer Click, Double-click, Right-click and Drag. Dwelling on the native dock
selects its action without injecting a desktop click. Both render and hit-test
use the same physical geometry, including negative monitor origins.

Drag uses a first dwell to press and a second dwell after moving to release.
The floating Drop action and explicit Release drag also release immediately.
Right/double click and completed drag return to left-click. Tracking loss,
physical takeover, Pause and Stop retain input cleanup. Practice remains
non-injecting. Personally calibrated expressions may now hold a drag; relaxing
releases it. Head facial-click confirmation stabilizes the pre-expression target.
Releasing an expression drag consumes dwell at the drop point, preventing an
extra click there. HUD actions stay disarmed across Resume/Drop until the pointer
leaves the dock, avoiding automatic pause/resume or drag-selection loops.

Fresh profiles default to Head & Face with 60% smoothing. Explicit saved modes
and smoothing values remain intact; this PC's saved profile already selected
Head with 60% smoothing. A configurable 4-pixel steadiness zone suppresses tiny
motion; monitor corners remain reachable. Dwell radius defaults to 22 physical
pixels and can be adjusted separately from the existing dwell duration.

## Research decision

[eViacam](https://github.com/cmauri/eviacam) documents a click-type dock and dwell
interaction. [Project Gameface's design](https://developers.googleblog.com/en/project-gameface-makes-gaming-accessible-to-everyone/)
emphasizes adjustable smoothing and personal expression thresholds. These inform
our interaction approach; no eViacam GPL implementation was copied. Retain the
installed MediaPipe runtime rather than introducing a provider whose superiority
has not been measured on this PC. This release does not claim market-leading
recognition accuracy.

## Evidence and limits

- Native Windows scratch-window check passed real left/right/double clicks and
  drag/drop at two targets. All inputs were guarded to that owned blank window;
  the cursor was restored and no key/camera input was used. Synthetic face
  observations tested dispatch, **not physical face recognition**.
- Earlier attempts aborted on physical takeover or an occluded scratch surface;
  no guard was disabled to obtain the final successful result.
- Native HUD compiled, showed head action buttons without foreground activation,
  delivered Pause and showed the paused virtual pointer. Camera enumeration
  opened no camera.
- At 1920×1080, default Head settings, a synthetic 5-degree step reached 90% of its
  target in 200 ms at 10/15 updates per second and 133 ms at 30. The prior
  adaptive-filter setting took 400, 333 and 267 ms respectively. These measure
  filtering response only, excluding camera/inference/display delay.
- Synthetic tests cover jitter at HD/4K, exact corners, action rearming, facial
  holds, conflict/loss cleanup, practice, guarded HUD actions and saved modes.
- A physical webcam comfort/accuracy check and 30-minute session remain open.
  Prior room checks measured roughly 10 capture fps. No camera-rate improvement
  is claimed; improved filtering cannot manufacture new observations.

Follow [Head-only clicks and dragging](AIRCONTROL.md#head-only-clicks-and-dragging)
to try the updated controls. Camera start and PC control remain separate actions.

## Release checks

| Check | Result |
| --- | --- |
| Final full Python suite | 358 passed; native effects mocked |
| Full browser behavior | 74/74 passed |
| JavaScript units | 83 passed, 1 optional skipped |
| AirControl browser/visual batch | 9/9 passed; seven themes, both appearances, three desktop sizes; sampled screenshots inspected |
| Native HUD | Passed non-activation, Head dock buttons, Pause callback and paused pointer |
| Native Head actions | Real guarded left/right/double click and drag/drop passed in an owned scratch window |
| Latest-source shortcut | Running source matched `c09ee3841c12ca4e512524ae87664d3b`; Remote video/audio providers remained available |

No webcam was opened for the current release checks. Synthetic camera poses do
not establish personal expression accuracy. The repository remains private.
