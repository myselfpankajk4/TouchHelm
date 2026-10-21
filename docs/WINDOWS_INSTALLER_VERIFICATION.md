# Windows installer Test 3 verification

`TouchHelm-2.2.0-test3-setup-win-x64.exe` is **168,197,949 bytes (160.4 MiB)**,
69.9% smaller than the original 559,095,094-byte offline portable EXE. It contains
647,431,606 unpacked bytes (about 618 MiB), excluding an existing system browser.
SHA-256:

```
6592539c96307f19028043c610d6d03d3d2cdf2d92c8a7dec20cdb5c42508624
```

The installer bundles Python, screen/audio providers, isolated camera dependencies,
models and Microsoft's x64 OpenMP DLL. It uses system Evergreen WebView2 and only
prepares Microsoft's browser runtime if absent. The EXE remains unsigned.

Observed on the build host:

- All 495 Python regression tests pass. The three new installed-mode tests cover
  system-browser selection, isolation from external Python settings, and ensuring
  installed setup never enters the Python-package/model download path.
- The final installer successfully installs for the current user, registers the
  Installed apps entry and uninstaller, and creates desktop and Start Menu shortcuts
  with the correct targets. User and machine PATH remain unchanged. Windows Start
  discovers `TouchHelm.Desktop`.
- The exact final installed launcher passes all 20 native checks with PATH reduced
  to Windows directories and invalid PYTHONHOME/PYTHONPATH. These check bundled
  imports, camera model loading without camera access, actual WebView2 JavaScript,
  system browser selection and a real Tk fallback window.
- A separate check rejects network/package-install calls and succeeds with the
  existing Windows browser. It imports DXcam's actual capture acceleration extension
  and verifies that VCOMP140.DLL is loaded from TouchHelm's own runtime directory.
- Normal and delay-loaded PE imports across 177 core and 92 camera binaries have
  no missing non-OS Visual C++ runtime DLLs. The audit caught OpenMP previously
  supplied by this PC; the builder now extracts that pinned, hash-checked x64 DLL
  from a Microsoft-signed redistributable without executing its installer. The
  extracted DLL retains its valid Microsoft signature. Fresh and cached build
  extraction paths both pass.
- A compiled real-launcher/fake-host test reproduced the missing lifecycle guard,
  then verified protection during first-launch preparation and the entire host
  lifetime, including releasing the guard after exit. Final setup and uninstall
  both refuse changes while the guard exists and preserve the app entry/files.
- A preliminary installer uninstalled successfully, removed its app entry and
  shortcuts, and preserved existing user settings. The final guarded build is
  installed and running on the PC.
- Opening the final Start Menu shortcut with no Python in PATH opens a responsive
  native TouchHelm window from the installed runtime. The normal host serves its
  API, requires its PIN, and authenticates a WebSocket client without transmitting
  PC input. Reports contain booleans/counts, no pairing PIN or IPC credentials.
- Review found and resolved lifecycle protection gaps; re-review found no concrete
  remaining blocker. Whitespace verification passes.

Clean Windows VM, physical Android Chrome, missing-system-WebView2 installation,
full screen/audio streaming and real camera-control sessions were not exercised
in this pass. Existing system WebView2 was reused; missing-browser setup and
signature/cancellation paths have regression coverage. No system runtime was
uninstalled for testing. SmartScreen, Smart App Control and permission behavior
remain controlled by Windows and publisher trust; another compiler cannot remove
that trust requirement.
