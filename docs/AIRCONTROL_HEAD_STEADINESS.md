# AirControl Head & Face steadiness — 18 October 2026

## Problem

In practice mode the Head & Face cursor shook and was hard to hold on a point.
Head yaw/pitch from the face transformation matrix is noisy at 10–15 camera
frames per second, and the old filter barely reduced it: the resting cutoff was
about 0.86 Hz at the default smoothing, and the 1€ speed term opened the filter
further on every noisy frame, so tracking noise leaked straight to the cursor.

## Changes

- **Quieter resting filter.** The resting cutoff is now `0.12 × (1 + 4.6 × (1 − smoothing))`
  Hz (0.34 Hz at the default 60% smoothing).
- **Noise floor on the speed term** (`OneEuro(floor=…)`). Head speed below
  0.1 normalized screen widths per second (about 3.6°/s at the default range)
  is treated as tracking noise and does not open the filter. Faster, deliberate
  moves still get the full beta response (16, up from 6), so the cursor
  responds sooner to a real move than before while a held pose stays calm. Hand
  mode passes no floor and is unchanged.
- **Larger default stillness hold.** `head_stability` defaults to 8 px (was 4)
  and can go to 20 px (was 12). It stays below the 22 px dwell radius.
- **Range compensation.** Cutoff, beta, floor and hold radius scale with
  `Sensitivity × 18° ÷ Head movement range`, so a narrower head range or a
  higher sensitivity, which magnify noise on screen, are steadied in proportion
  (as hand mode already did for its calibrated range).
- **Expression click release no longer jumps the pointer.** When a smile, wink
  or brow click ended after the head had drifted, the stillness hold kept its
  old position and the filter was reseeded with the held point as if it were a
  fast sample. The pointer jumped about 64 px on the first frame after release
  (a 2° drift at 1080p). The hold is now re-anchored and the filter starts at
  the held point without a fake speed spike, so the pointer glides to the head.
- **Recenter averages the recent pose.** Head Recenter (button and gesture) used
  one camera frame as the new neutral, baking that frame's noise into the
  cursor's center. It now uses the mean of the last steady samples, as
  calibration does, and falls back to the latest frame if there are fewer than
  five steady samples.

## Evidence (synthetic, not a camera)

Held head with Gaussian yaw/pitch noise σ = 0.3°, 1080p, default profile. Raw
mapped noise is about 22.6 px RMS. Mean over 8 seeds of 14 s each:

| Delivery rate | RMS before | RMS now | Peak before | Peak now | 90% step before | 90% step now |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 fps | 8.3 px | 3.5 px | about 22 px | 9 px | 200 ms | 100 ms |
| 15 fps | 7.2 px | 2.6 px | about 24 px | 9 px | 133 ms | 67 ms |
| 30 fps | 5.0 px | 1.5 px | about 19 px | 8 px | 100 ms | 67 ms |

A 0.6°/s slow drift is followed with a 26 px lag at 10 fps (13 px before), so
slow, careful aiming trails slightly more but is not swallowed by the hold.
With noisier tracking (σ = 0.5°) the cursor still wanders about 10 px RMS at
10 fps (about 14–16 px before). If it still shakes, raise Head steadiness or
Smoothing, or improve lighting and sit square to the camera.

Regressions are in `tests/test_aircontrol_head_steadiness.py` and
`tests/test_aircontrol_service.py`. The replay benchmark
(`tests/aircontrol_replay.py --baseline-ref HEAD`) passes its comparison.

## Not verified

No physical face or camera was used; the numbers come from simulated noise.
Real tracking noise differs by camera, lighting and person, so whether 8 px of
hold and the new slow-drift lag feel right needs a person to try it in practice
mode. If aiming feels sluggish, lower Head steadiness or Smoothing.
