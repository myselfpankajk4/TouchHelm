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

## Second pass (same day): "improved but still shaking"

- **Your saved profile kept the old hold.** Saved profiles only filled *missing*
  keys with new defaults, so a profile saved with the old Head steadiness of 4 px
  never received 8 px. The profile file now records a tuning revision; the first
  time an older file is read, a Head steadiness that still equals the old default
  (4) becomes the new default (8). Every other saved value is left alone, and a
  value you save afterwards (including 4) is never overridden. If you changed
  Head steadiness yourself to something other than 4, it is kept as you set it.
- **Single-frame tracking glitches are rejected.** A jump in head yaw/pitch over
  1.5° waits one frame. If the next frame is back near the last good pose the
  glitch is dropped. Otherwise the move was real, the delayed frame is replayed
  into the filter, and the cursor is exactly where it would have been, so a
  deliberate move is delayed only on its first frame. Before this, a one-frame
  glitch opened the speed filter and went straight to the cursor (about 100 px).
  Does not apply with Smoothing at 0.
- **The stillness hold widens with measured noise.** The hold grows by 3× the
  average per-frame movement of the filtered pose (1.5 s time constant), ignoring
  frames that move farther than the hold itself, up to twice Head steadiness and
  never past 80% of the dwell radius (so 14 px at the default). Deliberate moves
  neither widen the hold nor lag behind it.

Held-pose results (RMS px, mean of 8 seeds, 1080p, default profile):

| Tracking model | 10 fps before → now | 30 fps before → now |
| --- | ---: | ---: |
| White noise 0.3° | 2.7 → 0.8 | 1.1 → 0.5 |
| White noise 0.5° | 9.2 → 6.1 | 8.2 → 5.7 |
| 0.3° noise + 1 s correlated sway 0.3° | 12.7 → 9.3 | 11.2 → 9.8 |
| 0.3° noise + 3% single-frame glitches of 1.5–3° | 27 → 6 | 33 → 13 |

The 90% step response is unchanged (100 ms at 10 fps, 67 ms at 15 and 30 fps).
Two glitched frames in a row are still treated as a real move, so peaks of about
60–100 px remain possible in that case. A genuine slow sway of the head is, by
design, followed rather than held, which is why the sway row stays highest.

## Third pass (same day): "holding is better but movement is not smooth"

- **Fast, continuous moves no longer stall every other frame.** The glitch gate
  compared each frame with the last accepted pose, so a sweep of more than 1.5° per
  frame (20°/s at 10 fps, 30°/s at 15 fps) looked like a glitch on every frame: the
  cursor held, then jumped, then held. At 10 fps and 20°/s the per-frame cursor
  step alternated 0 px and 217 px. The gate now judges a jump against where the
  last deliberate step was heading. Only a step larger than 1.5° sets that
  heading, so a held pose with tracking noise is gated exactly as before. After the
  change the same sweep moves 107 px every frame (spread under 1 px) at 10 fps, and
  the single-frame glitch tests, including one in the middle of a sweep, still pass.
- **The practice cursor drawing is smoother.** The page receives a frame about every
  100 ms and eased the drawn cursor toward it with one stage, which speeds up after
  each frame and then slows to a stop before the next. Two easing stages keep the
  drawn speed continuous (about 80 ms of extra display lag during steady motion).
  This only affects the practice cursor in the window; Windows input is unchanged.

## Fourth pass (same day): the real Windows cursor glides

With PC control on, the Windows cursor was moved once per camera frame (10–15 Hz)
with nothing in between, so it stepped even when the pointer math was smooth.
`server/aircontrol/glide.py` (`CursorGlide`) now eases it, for Hand, Head & Face and
Combined alike.

- **How.** Each engine pointer point is a target. A thread (about 100 Hz, started
  with the camera loop) moves the cursor at constant speed from where it is to the
  newest target over about one frame interval: the measured gap between frames,
  clamped to 30–160 ms. Constant speed, rather than an exponential ease, avoids the
  speed-up-then-stall after every frame that the practice cursor had. It never
  extrapolates or overshoots; after reaching the target it holds.
- **Latency.** The cursor trails the engine by one frame interval. Synthetic 90%
  step response (1000 px step, frames at the given rate): 150 ms at 6 fps, 90 ms at
  10 fps, 60 ms at 15 fps, 30 ms at 30 fps; always under the 250 ms budget (the
  clamp caps it at 144 ms). In a steady 1000 px/s sweep at 10 fps the cursor moves
  10 px every 10 ms instead of 100 px every 100 ms, trailing by 100 px (100 ms).
  The "latency" metric still records frame-to-command time, so it does not include
  this glide delay.
- **Clicks and drags land on the engine point.** Before any button press, release or
  action (click, double click, hotkeys) the cursor is snapped to the engine's latest
  point, so a dwell click or drop is where the engine settled, not where the glide
  had reached. A drag moves with the button held and drops at the engine point.
- **Stops at once.** Pause, tracking loss, Stop, a locked desktop and any write error
  halt the glide under a lock; no write happens after that returns. A button held
  at that moment is released in place. The first point after a pause still jumps
  straight to the engine point, as before.
- **Does not fight the physical mouse.** The glide thread compares the cursor with
  its last write before each step. If you moved the mouse, it stops writing and the
  camera loop pauses AirControl ("Physical mouse took over") within one 16 ms tick.
  The 12 px takeover check on camera frames compares against the glide's last write,
  not the trailing target, so fast sweeps do not trip it.
- **Without the thread** (unit tests, camera stopped) every point is written
  immediately, as before.

Tests: `tests/test_aircontrol_glide.py` (easing, step response, no overshoot,
settle/halt/takeover, a real thread, and the service wiring: click and drag order,
pause/stop, loop cleanup).

Not changed: the practice cursor drawing (third pass).

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

The native cursor glide was tested only with a fake clock, a real thread writing to a
mock, and a mocked input controller. It has not been run against `SetPhysicalCursorPos`
on real hardware: actual thread timing under load (Windows timer granularity, the cost
of attaching to the input desktop on every write at 100 Hz), how it looks and feels on
a real display, whether the 12 px takeover check misfires in real sweeps, and
interaction with games or remote-desktop windows that read the cursor differently are
all unverified. The native check scripts in `tests/native_aircontrol_*_check.py` need a
camera and were not run.

The drawing smoothness of the practice cursor was reasoned from the frame timing and checked in the page's behavior tests only for its on-screen text; it was not measured on a live camera.
No physical face or camera was used; the numbers come from simulated noise
(white noise, a correlated sway, and isolated one-frame glitches). Whether real
glitches are one frame long, and whether the 1.5° gate and the 14 px widened hold
feel right, are unverified.
Real tracking noise differs by camera, lighting and person, so whether 8 px of
hold and the new slow-drift lag feel right needs a person to try it in practice
mode. If aiming feels sluggish, lower Head steadiness or Smoothing.
