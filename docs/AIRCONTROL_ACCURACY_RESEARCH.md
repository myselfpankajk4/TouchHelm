# AirControl accuracy and default-gesture research (2.2.1)

Why: AirControl felt unreliable. Changing gesture bindings only touches a small
part of the problem. The larger problem was where the click lands. This note
records what was looked at, what was changed, what was measured, and what has
**not** been verified on a real camera.

## Findings that drove the changes

1. **The cursor followed the fingertip of the pinching finger.** Closing a
   pinch moves the index tip by several centimetres, so the pointer moved
   while the click was being made. The engine froze the pointer at the moment
   the pinch was *recognised*, which is already after the movement. Measured
   effect: about 81-96 px between where the user aimed and where the click
   landed, on a 1080p screen, even with a perfectly still hand.
2. **Gesture recognition lags the gesture.** A smile, wink or pinch is only
   reported after it has crossed a threshold, so the click used the pointer
   position from the end of the gesture, not the start. Head mode suffers most
   because a smile moves the head a little.
3. **Too many defaults.** Thumb and face gestures fire by accident (Midas touch:
   Jacob, 1990, "What you look at is what you get"). Every default binding is
   a chance for a false click.

## Decisions

| Area | Decision | Reason |
|---|---|---|
| Hand pointer | Use the centre of the four knuckles (landmarks 5, 9, 13, 17) | Does not move when the thumb and index pinch, so closing a pinch cannot move the cursor |
| Click anchor | Pin the click to where the pointer was about 150 ms before recognition (`HAND_LOOKBACK`, `HEAD_LOOKBACK`), from a 0.5 s trail | Recognition lag; capped by tests so it cannot grow unnoticed |
| Filter | Keep the existing One Euro filter (Casiez, Roussel and Vogel, CHI 2012) | It already trades jitter for lag by speed. A separate speed-gain curve was not added: it would stack on top and was not shown to help |
| Pinch | Keep hysteresis (`pinch_close` .25, `pinch_open` .4) | Stops flicker at the threshold |
| Defaults | Pinch = left press/drag, middle pinch = right click, two fingers = scroll, closed fist = pause, open palm = resume | The small set that has no false-trigger problem when a hand is simply in view |
| Everything else | Thumbs and face gestures kept, default off, under "More gestures (advanced)" | Customisation kept, accidents removed |
| Saved profiles | `TUNING` 2 -> 3. Hand bounds are reset to the default range once | The pointer moved from fingertip to knuckles, so old calibrated bounds no longer match. Users with saved hand profiles should re-run Quick setup |

Prior art consulted by name: Google MediaPipe (Gesture Recognizer and Face
Landmarker, the models TouchHelm already uses), Google Project Gameface
(head and face gestures as a mouse), Windows Eye Control and head-pointer
dwell, Apple AssistiveTouch pinch and clench gestures, and open-source
gesture-mouse projects. Their general approach (pointer from a stable point,
dwell or a simple pinch for click, a short list of defaults, smoothing
adapted to speed) matches the decisions above.

## Measurements

Reproduce with `python tests/aircontrol_accuracy_benchmark.py`; the unit tests
are in `tests/test_aircontrol_pointer_accuracy.py`. Error is pixels at button
down versus the cursor position when the gesture started, on a 1080p screen,
12 seeds.

| Pointer / anchor | fps | still: mean px | still: worst px | moving 0.12/s: mean px | moving: worst px |
|---|---|---|---|---|---|
| fingertip pointer, one-frame anchor (2.2.0) | 15 | 80.9 | 88.6 | 92.2 | 104.2 |
| fingertip pointer, one-frame anchor (2.2.0) | 30 | 85.6 | 115.7 | 96.4 | 130.5 |
| knuckle-centre pointer, one-frame anchor | 15 | 0.0 | 0.0 | 44.4 | 52.8 |
| knuckle-centre pointer, one-frame anchor | 30 | 0.1 | 1.2 | 46.5 | 57.5 |
| knuckle-centre pointer + lookback anchor (2.2.1) | 15 | 0.0 | 0.0 | 22.6 | 29.1 |
| knuckle-centre pointer + lookback anchor (2.2.1) | 30 | 0.0 | 0.6 | 5.2 | 22.8 |

| Head smile click: pose shift while smiling | one-frame anchor mean / worst px | lookback anchor (2.2.1) mean / worst px |
|---|---|---|
| 1.5 deg | 2.2 / 6.4 | 0.1 / 1.2 |
| 3 deg | 27.6 / 36.4 | 0.8 / 4.6 |
| 6 deg | 120.6 / 129.5 | 12.5 / 25.2 |

## What these numbers are not

- **Synthetic data.** The streams are generated, with assumed pose-shift sizes
  and an assumed 0.2 s pinch-close time. They prove the engine no longer adds
  this error and that the fix is correct for the modelled motion. They do not
  predict real-world error.
- **Not verified on a real camera.** No real webcam, real hand or real head
  was used. Still to check by hand: click accuracy on small targets in hand
  and head mode, a moving-hand click, that the knuckle pointer feels natural
  and reaches screen edges with Quick setup, that the lookback does not feel
  like the click "snapping back" at very low frame rates, and head-mode smile
  clicks. If 150 ms feels wrong, the two lookback constants in
  `server/aircontrol/engine.py` are the only values to tune.
- **Not looked up or confirmed:** Windows Eye Control's default dwell time,
  Apple Vision Pro guidance, Project Gameface's default bindings, MediaPipe
  calculator option names, head-pointer dwell radius studies, and
  Kalman-filter-specific evidence. None of the decisions rely on them.
