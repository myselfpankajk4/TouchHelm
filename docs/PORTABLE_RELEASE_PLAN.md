# Portable Windows test release

Goal: share one EXE with Windows 10/11 x64 testers who have no Python, pip,
Node, camera packages, or WebView2 installation. Preserve browser phone controls,
automatic two-way typing, Clear, and optional desktop features.

User decision: no signing setup; prepare an unsigned portable test EXE. Windows
SmartScreen, publisher, firewall, antivirus, and camera permission prompts cannot
be guaranteed absent. Do not disable or circumvent them.

Architecture: an asInvoker .NET Framework launcher contains a SHA-256 checked ZIP.
It expands once into a per-user version directory, then runs bundled embedded
CPython. Include an isolated camera Python, checksum-locked models, Fixed Version
WebView2, Tk fallback, and runtime package licenses. Store settings outside the
version directory. Copy application assets by allowlist; never developer settings,
credentials, history, virtual environments, or repository metadata.

Tasks and evidence:

- [x] Portable path/config/camera integration with focused regression tests.
- [x] Repeatable runtime build and launcher with safe extraction and error UI.
- [x] Windows 11 inspired desktop polish; preserve all themes and controls.
- [x] Build EXE, verify payload, run embedded dependency/model/renderer smoke tests.
- [x] Run application regression suites and review the final changes.
- [x] Report artifact size, tested scope, and unsigned limitations before push.
- [x] Commit and push a test branch; publish a GitHub prerelease with EXE/checksums.

Verification limits: this host is not a clean Windows VM or a physical Android
phone. Report simulations and unattended browser/native checks precisely. The
repository is private; friends need repository access to download a private
release, or the owner can share the EXE directly. Do not change repository visibility.

Ruling: preserve the existing working changes in place on a new test branch rather
than create another checkout; those changes are the release's required input.

Review corrections: explicitly configure pywebview's runtime setting in addition
to Microsoft's environment variable; grant AppContainer read/execute only on the
public WebView2 directory; ship Tcl's zlib1.dll dependency; keep certifi's public CA
bundle while rejecting private-key inputs; surface nonzero/early startup failures.
Staged restricted-PATH smoke passed all 20 import/model/renderer/Tk checks with
installed WebView2 discovery disabled. Final EXE extraction smoke also passed.
Normal packaged desktop startup opened a responsive native window, served its API,
and accepted PIN-authenticated WebSocket pairing. The source host was restored.

Final relocation correction: keep logical absolute paths under Windows Store
AppData redirection and use a 16-character cache-directory prefix; the complete
SHA-256 still verifies the archive and ready marker. This avoids native import
failure when physical redirection expands a module path past the legacy limit.
The regression was observed failing before the correction and passing afterward.

Published [v2.2.0-test.1](https://github.com/myselfpankajk4/TouchHelm/releases/tag/v2.2.0-test.1)
with five assets. GitHub's computed EXE digest and size match the tested local
artifact. Code is on `codex/portable-test-release` with draft PR #1 targeting main.
