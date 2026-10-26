# TouchHelm Windows installer — Test 6

Use `TouchHelm-2.2.0-test6-setup-win-x64.exe` for a normal installation on Windows
10/11 x64. Run setup and choose Install. It installs for the current Windows user,
creates Start Menu and desktop shortcuts (desktop selected by default), and adds
TouchHelm to Settings → Apps → Installed apps with an uninstaller. The application
opens from the finish page. No administrator account is normally required.

Python, screen/audio libraries, the isolated camera runtime, and camera models
are included, along with the Microsoft OpenMP DLL required by screen capture.
There is no Python or C++ installer, pip, manual requirements step, or
PATH/environment-variable change. The launcher uses the private runtime beside
the app. A separately installed Python is neither used nor required. Upgrades
use the same app entry and preserve settings under LocalAppData\TouchHelm.
Uninstall removes application files and shortcuts; settings are retained.
Test 4 prevents a selected inline autocomplete suffix from replacing an ongoing
phone edit. For example, Chrome can suggest `google.com` after the phone sends
`g`, while the phone keeps `g`. Accepting that suggestion on the PC syncs the
full address. Other PC edits continue to sync automatically. No Chrome setting
or extra recovery button is needed. Fields without accessible selection metadata
retain the existing synchronization behavior.
If TouchHelm is running, choose Exit from its tray menu before updating or
uninstalling. Windows setup checks the running-app guard to prevent removing
files while the host is active.

The desktop uses Microsoft's Evergreen WebView2 already present on most current
Windows installations. If missing, setup downloads Microsoft's bootstrapper,
verifies its Microsoft signature, and runs it silently. That step needs internet;
managed-PC policies may prevent it. It also retries automatically when opening
TouchHelm. No screen/audio/camera packages or models are downloaded on first launch.
An offline PC must already have WebView2; Test 1 includes a private browser if that
is essential. Windows firewall and camera permissions remain controlled by Windows.

This test build is unsigned. A normal installer and a native launcher do not
establish publisher trust. SmartScreen/Smart App Control can warn or block it.
Do not disable Windows security or install an untrusted certificate to hide that
warning. Trusted signing requires a verified signing identity; Microsoft Store
MSIX distribution is a separate route that uses Microsoft's signing. Newly signed
direct downloads may still need reputation. See Microsoft's official guidance:
https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options

The [Windows trust research](WINDOWS_TRUST_RESEARCH.md) compares MSI, direct
signing and Store MSIX distribution, with TouchHelm-specific migration and
verification requirements. Renaming or repackaging the unsigned installer as an
MSI does not establish publisher trust.

## Build

Prepare `build/portable-stage` using the existing offline builder, then run:

```
.venv\Scripts\python.exe packaging\build_installer.py --iscc path\to\ISCC.exe
```

The builder copies an allowlist of current app sources and verified feature
runtimes into a fresh stage, checks models and private-file exclusions, compiles
the installed launcher, then uses Inno Setup's solid LZMA2 compression. It excludes
the private browser and package installers; all native dependency licenses remain
with their distributions. The file size and SHA-256 are in
`dist/installer-build-manifest.json` and `dist/SHA256SUMS-test6.txt`.

## Verification

`TouchHelm.exe --self-test --report C:\existing-folder\report.json` checks imports,
both bundled runtimes, model integrity, actual WebView2 JavaScript execution, and
the Tk fallback without opening a camera or sending PC input. It uses the same
installed launcher as the shortcuts. Build-host checks do not substitute for a
clean Windows VM or a physical Android Chrome test.

Test 6 uses temporary browser-only HTTPS for pairing and then closes its public helper. All PIN/control/text/settings/artwork traffic uses an encrypted local DataChannel; screen/audio also stay local. There is no public control API or relay fallback. The verified helper and Apache license remain bundled. Keep the phone tab open and scan a fresh QR after reload or disconnect. See [Browser link setup and limits](BROWSER_LINK.md).
