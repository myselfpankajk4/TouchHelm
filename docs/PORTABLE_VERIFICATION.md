# Portable test release verification

Artifact: `TouchHelm-2.2.0-test-win-x64.exe`, 559,095,094 bytes (533.2 MiB).
Unpacked payload: 1,352,322,002 bytes. SHA-256:

```
36a61ac5771ff7469b31de0e523d57c90774599f56bd9bbc20dd505bc81c68ef
```

Build inputs: official embedded CPython 3.13.14 x64, Fixed Version WebView2
155.0.4283.62 x64, the project's pinned main/remote requirements, and the fully
hash-locked AirControl requirements and model manifest. Python and Microsoft
native entrypoint Authenticode signatures verified valid. The outer EXE is
unsigned and requests the current user's privileges, without elevation.

Observed checks on the build host:

- 478 Python tests passed, including eight portable regressions.
- 118 JavaScript tests passed; one optional DOM test skipped.
- 104/104 browser tests passed, including text recovery/Clear, accessibility,
  desktop themes, AirControl views, phone viewports and keyboard reflow.
- Final EXE first launch verified SHA-256 and extracted its own payload.
- Extracted runtime passed all 20 native import/model/renderer/Tk checks with a
  PATH containing only Windows system directories and isolated user settings.
  Installed WebView2 registry lookup was deliberately hidden from that process;
  bundled WebView2 executed JavaScript and the Tk fallback created a real window.
  Camera models loaded without opening a camera or injecting input.
- Normal EXE startup opened a responsive native TouchHelm window, served its
  phone host API, required a generated PIN and authenticated a WebSocket client.
  The packaged test host was stopped gracefully and the updated source app restored.
- Payload audit found no developer config, environment file, instance token,
  private key or log. Dependency certifi CA bundles are intentionally public.
- Fresh code review and `git diff --check` found no remaining blockers.

Review/smoke fixes included explicit pywebview runtime selection, Windows 10
AppContainer read/execute access only on public browser runtime files, the Tcl
zlib dependency, visible startup errors, and short logical cache paths that survive
Windows AppData redirection. Screenshot previews use synthetic device data.

Limits: no clean Windows VM or physical Android Chrome test was performed. No
claim is made that every Windows control exposes editable accessibility text, or
that Chrome permits the system keyboard to appear after asynchronous focus.
The native browser/UIA foreground probe skipped when Windows denied foreground
activation. No full camera tracking/capture or remote network session was exercised
by the portable smoke check. Windows security/permission prompts remain possible.
