# Compact desktop test version

User wants a materially smaller EXE and a desktop interface that feels like a
Windows application. They approved automatic first-run downloads, with no manual
Python/package installation. Preserve phone typing/Clear and existing features.

Measured Test1 compressed payload: WebView2 297.1 MiB, camera 115.8 MiB, main
runtime 109.1 MiB, app/models 10.0 MiB. Main opportunities are delivery changes,
not removing icons or source code.

Approach: compact EXE contains the core embedded Python/runtime, pip, Tk fallback,
application UI and locked dependency/model manifests. Reuse system Evergreen
WebView2; if absent, download and verify Microsoft's signed bootstrapper and run
its per-user silent installer. Prepare screen/audio and camera dependencies in
separate per-user component directories using public, hash-locked wheels and
verified public models. No private GitHub download credentials are required.

First-run setup displays progress, supports cancellation, retries incomplete
preparation, and marks components ready only after native checks. Later launches
reuse prepared components. Keep the existing offline Test1 available.

Desktop redesign proceeds independently in gui/web: compact shell/navigation,
QR/address/PIN together, concise advanced disclosures, native grouped settings,
and a clearer camera workspace. All themes, IDs, APIs and accessibility remain.

Verification: focused setup tests for missing/cached/damaged/cancelled components,
hash checks and trusted bootstrapper selection; actual first-run preparation with
core embedded Python; final EXE extraction/native/desktop/pairing checks; affected
browser/theme/accessibility checks and existing regression suites. Report physical
phone/clean-VM limits. Publish a new test prerelease without replacing Test1.

Completed: compact EXE 29.5 MiB (94.5% reduction), actual preparation/retry/cache
reuse, final native/desktop/API/PIN WebSocket smoke, and refreshed desktop across
themes. Review fixes cover cache damage and verification cancellation. Regression
counts: Python492, JavaScript118 with one optional skip, browser104/104. See
[verification](COMPACT_VERIFICATION.md) for exact artifact and test limits.
