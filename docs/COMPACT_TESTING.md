# TouchHelm compact test build

For Windows 10/11 x64 with the standard .NET Framework desktop components.
Open `TouchHelm-2.2.0-test2-compact-win-x64.exe`. Python, the core app and its setup
engine are included; testers do not install Python, pip or requirements manually.

**Keep the PC online for the first launch.** TouchHelm automatically prepares
screen/audio controls and isolated camera dependencies/models in your user profile.
It reuses installed Evergreen WebView2, or runs Microsoft's verified per-user
bootstrapper if that runtime is missing. Progress appears during preparation.
Downloads come from public PyPI, Google model storage and Microsoft; private
GitHub access is not needed after someone shares the EXE with you.

The initial file is smaller because feature runtimes are downloaded once. This
does not remove their eventual disk footprint or first-run download cost. Expect
roughly 200–250 MiB of feature downloads, plus WebView2 if missing. Leave several
GB free. Once preparation finishes, ordinary local use can run offline. Optional
Tailscale remote access still requires its normal account/setup on both devices.

If preparation fails, check internet access and reopen the same EXE. Verified
components and pip's download cache are reused. Cancelling setup never opens a
camera or injects input. The camera starts only after you choose Start camera.
Settings remain in `%LOCALAPPDATA%\TouchHelm`; components are reused across UI
updates with unchanged dependency locks. Removing that folder erases settings,
prepared components, and cached versions.

The EXE is unsigned. Windows publisher, SmartScreen, firewall, antivirus or camera
permission prompts may appear. Check the source/checksum and don't disable Windows
security. Managed PCs can block unsigned apps or browser-runtime installation.
An offline full build remains available as Test1.

Use Android Chrome on the same local network, scan the desktop QR and enter the
PIN displayed on your own PC. Check trackpad, automatic typing sync, linked-field
Clear with Live on/off, themes, pairing and camera practice. Password fields and
the Windows secure desktop remain excluded. Chrome decides whether asynchronous
focus may display its system keyboard.

`--self-test --report "C:\existing-folder\report.json"` checks prepared runtimes,
camera models, renderer JavaScript and the classic fallback without opening a
camera or sending PC input. First-run preparation still requires internet when
components are missing. Review local logs before sharing them. Build-host checks
do not establish clean-VM or physical Android compatibility.
