# AirControl Hand steadiness — 18 October 2026

## Problem

In practice mode the cursor shook and was hard to hold on a point. Head mode
already had a trailing stillness hold (`head_stability`). Hand mode had only a
weak 1€ filter (about 2.1 Hz minimum cutoff at the default smoothing), so every
landmark wobble reached the cursor. The practice cursor was also drawn directly
from a 100 ms poll, so a 10–15 fps camera made even a steady cursor visibly step.

## Changes

- **Hand stillness hold** (`hand_stability`, default 6 px, range 0–16, Settings →
  Hand steadiness). The output stays put until the filtered fingertip leaves a
  radius of that size, then trails it. Setting 0 disables the hold; turning
  Smoothing to 0 keeps the raw pointer for diagnostics, as before.
- **Hand filter retuned** for noisy 10–15 fps landmarks: minimum cutoff
  `0.15 + (1 − smoothing) × 0.65` Hz and beta 9, so fast moves still respond
  within a frame or two. Head and Combined-head filtering is unchanged.
- **Range compensation**: Quick setup maps only a 0.5 × 0.4 slice of the camera
  to the whole screen, which magnified landmark noise about 2× (7.5 px RMS at
  10 fps, peaks near 19 px). The filter cutoff, filter beta and hold radius now
  scale with that magnification (and with Sensitivity above 1), bringing the
  Quick-setup range to 4.7 px RMS at 10 fps and 1.8 px at 30 fps.
- **Combined pinch clicks** now hold the pointer at the pinch start. Previously
  only Hand mode did, so a 1.5° head drift during a pinch moved a Combined click
  about 60 px before it fired. Combined drags still follow the head once started.
- **Pinch release** re-anchors the hold at the release point so a click or drag
  does not nudge the cursor afterward.
- **Practice cursor easing**: the drawn cursor eases toward each polled point
  (about 45 ms time constant) on `requestAnimationFrame`. It snaps for large
  jumps and when the system asks for reduced motion.

## Evidence (synthetic, not a camera)

Held finger with Gaussian landmark noise σ = 0.004 normalized, 1080p. Raw
mapped noise is about 15.5 px RMS. Mean over 12 seeds of 14 s each:

| Delivery rate | RMS from rest point | Mean peak |
| ---: | ---: | ---: |
| 10 fps | 3.7 px | 8.6 px |
| 12 fps | 3.3 px | 7.8 px |
| 15 fps | 2.8 px | 7.3 px |
| 30 fps | 1.6 px | 4.1 px |

A 0.15-wide step reaches 90% within a frame or two, and a 0.04/s drift is not
swallowed by the hold. Regressions are in
`tests/test_aircontrol_hand_steadiness.py`. The Head replay benchmark
(`tests/aircontrol_replay.py --baseline-ref HEAD`) is identical to the previous
commit across all 36 scenarios.

## Not verified

No physical hand or camera was used. Whether 6 px feels right, and whether the
easing feels natural, needs a person to try it. If the cursor feels sluggish,
lower Hand steadiness or Smoothing; if it still shakes, raise Hand steadiness.
