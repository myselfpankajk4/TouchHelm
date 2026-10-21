# Compact Test 2 verification

`TouchHelm-2.2.0-test2-compact-win-x64.exe`: **30,958,009 bytes (29.5 MiB)**.
Test 1: 559,095,094 bytes (533.2 MiB). Reduction: **94.5%**.
Unpacked compact core: 72,197,536 bytes. SHA-256:

```
cc1b6935997a379a880b5d9c6a8170a948eb4ebeee7704e30c175203d0a59bd4
```

Size is reduced by reusing system Evergreen WebView2 and automatically preparing
feature components on first launch. It is a smaller initial download, not a claim
that the eventual native runtimes occupy only 29.5 MiB. The core includes Python,
the app, pip and Tk. No requirements are manually installed by testers. Feature
wheels/models come from public sources and are hash locked, without private GitHub
credentials. Microsoft's bootstrapper is signature-verified before execution.

Observed on the build host:

- 492 Python regressions, 118 JavaScript checks and 104/104 browser checks pass.
  One optional JavaScript DOM test is skipped.
- Real first-run preparation with the compact embedded Python downloaded public
  models/wheels, verified hashes, loaded screen/audio providers and checked camera
  models without opening a camera or injecting input. A DNS interruption exposed
  retry cleanup/error handling issues; regression tests and a successful retry
  cover their fixes.
- Final compact EXE verified/extracted its payload, reused prepared components and
  passed all 20 native import/model/WebView2 JavaScript/Tk checks with developer
  tools absent from PATH and isolated settings.
- A repeated setup check deliberately rejected network and package-install calls;
  intact prepared components were reused successfully. Missing/truncated native
  files and absent inventory invalidate cache readiness and trigger preparation.
- Normal final-EXE startup opened a responsive native TouchHelm window, served its
  API, required a PIN and authenticated a WebSocket client. The test host was
  stopped gracefully and the updated development app reopened.
- Installed Evergreen WebView2 was detected/reused. The actual Microsoft bootstrapper
  was downloaded and its Authenticode publisher/signature verified. Missing-runtime
  installation and invalid-signature/cancellation paths have focused mocked tests;
  the existing system runtime was not uninstalled to exercise a real clean install.
- Fresh review corrections include native-cache health inventory and cancellation
  during signature verification. Regression and independent re-review pass.
- Desktop QR/address/Copy/Open/PIN fit at 1120×800 and 820×620 across all seven
  themes/both appearances. Five desktop pages were inspected across those themes
  and sizes, with no layout clipping/overflow or small action targets. Glass light
  and dark have no serious/critical Axe issues on the redesigned pages.

Preview screenshots use a reserved documentation IP and synthetic PIN/device data.
See [desktop design review](DESKTOP_REDESIGN_V2.md) for visual evidence and constraints.
No clean Windows VM or physical Android Chrome test was performed. Full camera
tracking and a remote screen/audio session were not exercised by these smoke tests.
The EXE remains unsigned; Windows publisher/security/permission prompts can appear.
Optional Tailscale setup/account and hardware/Windows permission limits still apply.
