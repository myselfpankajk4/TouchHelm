# TouchHelm portable test build

For Windows 10/11 **x64**, using a standard signed-in user account. Windows 7/8,
32-bit Windows, native ARM64, Windows S mode, and enterprise application allowlists
are not supported by this test build. Windows must include its normal .NET
Framework 4.8 desktop components.

Download `TouchHelm-2.2.0-test-win-x64.exe` and double-click it. No separate Python,
pip, Node, WebView2, or camera package installation is needed. The first launch
verifies and extracts bundled files into `%LOCALAPPDATA%\TouchHelm\packages`.
Keep several GB of free disk space for extraction. Later launches reuse that
version's files. Keep the EXE wherever you prefer; settings live separately in
`%LOCALAPPDATA%\TouchHelm` and survive a new test version.

The EXE is **unsigned**. Windows may show unknown-publisher, SmartScreen,
antivirus, firewall, or camera-permission prompts. A single file does not remove
these protections. Check the download source and SHA-256 checksum; do not disable
Windows security to run it. Your organization may prevent unsigned apps entirely.
Allow private-network access only if you want to connect from your phone.

Open Chrome on your Android phone, connect to the same local network, and scan
the desktop QR code. Enter the PIN shown on your own PC. Fresh portable installs
generate their own PIN; this build contains no developer settings or credentials.
Basic phone control works locally. Trusted remote HTTPS still requires the
optional Tailscale setup/account on both devices. Screen casting and camera access
depend on Windows permissions, hardware and drivers.

Check trackpad clicks/dragging/scrolling, typing in both directions, automatic
typing-dock opening, Clear with Live on/off, disconnect/reconnect, all themes, and
camera practice. Different desktop controls expose different Windows accessibility
support; password fields and the Windows secure desktop are intentionally excluded.

For diagnostics, close the normal app and run the EXE with
`--self-test --report "C:\path\to\report.json"`. It checks native imports, models,
the bundled renderer and classic fallback without opening a camera or injecting
input. The report directory must exist. Normal startup errors go to
`%LOCALAPPDATA%\TouchHelm\desktop.log`; review logs before sharing them.

This is a prerelease. Automated checks on the build host do not establish clean-VM
compatibility or physical Android Chrome behavior. Report Windows version, target
PC app/control, phone Chrome version, and steps when something fails.

Bundled third-party packages retain their license/notice files; `dependencies.json`,
`redistributables.json`, and vendor signature evidence are inside each extracted
version directory. Fixed Version WebView2 receives updates through new TouchHelm
builds, so use current test releases. To remove the app, exit it, delete its EXE,
and remove `%LOCALAPPDATA%\TouchHelm` if you also want to erase settings and cached
versions. No administrator installation or automatic startup entry is added.
