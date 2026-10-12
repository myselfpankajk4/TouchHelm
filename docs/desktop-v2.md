# TouchHelm v2 desktop and secure pairing

The default desktop is a pywebview EdgeChromium window. Python still owns the host server, native controllers, tray and shutdown. The phone interface remains separate from the privileged desktop bridge.

**v2.1:** Pairing now has explicit HTTP, local-certificate HTTPS and private Tailscale HTTPS modes. Tailscale avoids manually installing TouchHelm's CA, while still requiring installation/login on both devices and a host PIN. It serves private HTTPS 8443 over a dedicated loopback backend on 8767. Existing Serve conflicts are preserved. [Setup, living effects and current verification](LIVING_CONTROLS.md).

## Launch and rollback

Run `run.bat` from the project checkout. It changes to its own folder and launches that folder’s `main.py`, so it reads the saved source rather than a packaged copy. An isolated worktree can use the parent workspace’s `.venv`; its source and assets still come from the worktree. The launcher checks that Python runs and installs missing desktop dependencies into the selected workspace environment.

The selected environment currently contains pywebview **6.2.1** and cryptography **50.0.2**, matching `requirements.txt`. EdgeChromium also needs a working Windows WebView2 runtime and .NET environment; successful Python imports do not prove that a native window can open.

- `run.bat`: themed EdgeChromium desktop.
- `run.bat --classic-ui`: existing Tk desktop rollback.
- `run.bat --headless`: terminal host with no desktop window.
- `python main.py --port 8765 --pin 1234`: existing command-line overrides.

A per-user, per-Windows-session named mutex identifies the owning host. A launch with the same source, desktop mode, port and PIN policy asks that host to restore its window. Changed source, desktop mode or startup policy requests graceful shutdown, waits for mutex release, then starts the new host. Only a startup-policy hash enters protected IPC; the PIN is not sent in plaintext. This hash is an identity marker, not an authentication secret. Concurrent launchers recheck the current owner and authenticated IPC record. They never terminate an unrelated process or force-kill a host. If shutdown or authenticated activation cannot complete within the bounded wait, the launcher reports the failure.

Source identity includes Python, browser, desktop and launcher source. Configuration changes made in the desktop are persisted through the existing configuration manager and sent to connected phones. A successful disk save followed by failed phone notification is reported as saved with a warning to restart the host.

## Desktop architecture

`gui/webview_window.py` serves an allowlisted set of GUI, shared theme and brand assets on an ephemeral **127.0.0.1-only** listener. It rejects unexpected Host headers and path traversal. It exposes no HTTP native-command endpoint. The owned page URL includes a random session token; every native API command verifies that token and that the window still displays the exact owned page. Commands are rejected during closing or after navigation away from that page.

The shell has Pairing, Devices, Settings and Diagnostics pages. Pairing includes matching URL and QR codes for HTTP or enabled HTTPS, explicit PIN status and manual certificate instructions. Devices show authenticated state and measured latency only when available. Activity is bounded to 1,000 entries and scrolling respects someone reading older entries. Settings use atomic configuration validation with inline errors. The theme picker shares the phone’s seven themes while saving desktop appearance preferences independently in the user’s TouchHelm folder.

The original mouse, wheel and laser-dot mark appears in the header, native icon and tray. Minimize uses the taskbar until the tray is ready; a tray failure restores the window. Closing the desktop stops its assets and tray, then the owning main process stops the discovery beacon and awaits server cleanup before releasing the instance.

## Optional Android HTTPS setup

HTTP defaults to port 8765. HTTPS is optional and defaults to port 8766. Choose **Enable HTTPS** on the desktop Pairing page to request certificate preparation and an additional HTTPS listener. Turning HTTPS off stops that listener. TouchHelm never automatically adds certificates to Windows or Android trust stores.

1. Open the PC’s HTTP phone interface and choose **Settings → Secure pairing**. Download `TouchHelm-CA.crt`; the current PIN is required when PIN protection is enabled.
2. Compare the downloaded certificate’s SHA-256 fingerprint with the fingerprint on the locally owned desktop.
3. In Android Settings, search for **Install a certificate**, choose **CA certificate**, and select the downloaded file. Menu names vary by phone. Only install it when you control this PC.
4. Open the desktop’s HTTPS URL or QR code, authenticate again as required, and check Chrome’s connection security. Trust installation and secure-context hardware permissions need a real Android check.
5. Remove the TouchHelm CA from Android user credentials when you no longer use this PC.

The manager stores the private CA and server keys under `%LOCALAPPDATA%\TouchHelm\certificates`, outside HTTP assets and Git. Windows protection replaces their DACL with current-user access; an ACL failure aborts preparation. The stable local CA signs a renewable LAN/loopback SAN certificate. A changed LAN address renews the leaf while keeping the CA trusted on the phone. Incomplete or invalid CA files are rejected rather than silently replacing the trusted identity. Public API data includes the certificate, fingerprint, expiry and trust guide, never private-key paths or key material.

## Safe evidence and native smoke check

The desktop suites include `test_secure_pairing`, `test_instance_control`, `test_webview_shell` and `test_desktop_regressions`; the final full Python run passed **163 tests**. These cover certificate identity/SAN renewal, ACL failure boundaries, strict bridge authorization, settings errors, HTTPS rollback, preference persistence, asset isolation, bounded logs, restart races, shutdown boundaries, CLI override identity, runtime-asset build identity and classic lifecycle regressions. Native Windows ACL, mutex, IPC sockets, GUI and input effects are mocked in those suites. Temporary certificate/config files are confined to test directories. Python metadata and safe imports confirm the pinned packages.

Browser preview uses `render_preview_html('/preview/desktop/')` and an explicitly labeled sample fixture with a real encoded sample QR. `window.TouchHelmDesktopPreview.setState(name)` supports ready, disconnected, loading and unavailable states. This route has no native bridge. Browser preview confirms rendered HTML/CSS behavior, not the actual WebView2 backend or Windows taskbar.

After native launch is authorized, use this bounded smoke check:

1. Record only the relevant current Python process executable, command line and window title, then launch this checkout’s `run.bat`. Confirm one owned TouchHelm host and one visible desktop; do not send phone input.
2. Verify the actual window/taskbar icon, header brand and Pairing page. Compare the displayed host address with Diagnostics. Check all four desktop pages and theme switching without operating PC input controls.
3. Launch the same checkout again. Confirm restoration and no duplicate owned host. To test changed-source handoff, make an authorized harmless source change and launch again; confirm the old owned PID exits and one new PID appears. Never kill another process to make the check pass.
4. Close the owned window normally. Confirm its tray, asset listener and host listener close and a subsequent launch succeeds. Inspect only the known host PID/window and expected ports.
5. If HTTPS testing is separately authorized, enable it explicitly, inspect current-user-only ACLs on the known certificate directory, and follow the Android steps above. Disabling HTTPS must leave the HTTP host usable. Trust installation is a manual user action.

The root integration smoke subsequently opened the actual WebView2 desktop: brand image, QR, bridge, shared stylesheet and all four pages loaded without overflow or an error message, followed by normal window shutdown. A separate real launcher smoke restored the same build and gracefully restarted changed source; the old and replacement hosts exited normally. Temporary certificates passed a real Python TLS connection with CA/hostname verification and authenticated single-use handoff; key-folder protection ran on Windows. No trust store was modified. Tray recovery, Android trust/HTTPS and physical phone effects remain separate checks. Native OSD/input, PowerPoint and media effects were not exercised.
