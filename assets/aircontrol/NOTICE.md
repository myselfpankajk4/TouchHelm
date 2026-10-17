# AirControl third-party assets

The unmodified MediaPipe Tasks model bundles in this directory are supplied by
Google / the MediaPipe Authors. `manifest.json` records the original versioned
download URLs, exact byte lengths and SHA-256 digests. TouchHelm verifies those
digests before copying the bundles into its isolated runtime.

- [Gesture Recognizer documentation and model card](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer)
- [Face Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
- [MediaPipe upstream project and license](https://github.com/google-ai-edge/mediapipe)

`APACHE-2.0.txt` preserves the upstream MediaPipe project's Apache 2.0 license;
TouchHelm does not relicense third-party components. Installed Python wheels retain
their own license files and metadata. The package lock is
`requirements-aircontrol.txt`; these dependencies do not enter the phone runtime.

The [SDK privacy notice](https://pypi.org/project/mediapipe/#privacy-notice) says
input processing happens on device while SDK performance/utilization metrics are
reported to Google. TouchHelm does not claim to disable that upstream behavior.
Camera images are not recorded or sent to TouchHelm phones. No face templates or
identity enrollment are created.
