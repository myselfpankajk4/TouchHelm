# Media after HTTPS bootstrap shutdown — Test 7

Reported symptom: screen/audio sharing unavailable after the internet pairing
tunnel closes. Investigation found the installed `remote_enabled` setting false
while PIN and HTTPS were enabled. The media authority returned a combined error
mentioning both desktop permission and HTTPS. The Media audio toggle also reset
to off with generic copy, hiding the real permission requirement.

Test 7 keeps every PIN/secure-transport/desktop-access gate. It reports each failed
requirement separately, gives the Media tab a visible desktop permission recovery
message, and labels desktop screen/audio access On/Off outside its disclosure.
General installs retain the existing explicit PC opt-in. No stream starts merely
because a user pairs.

A new opt-in probe uses the real phone UI, aiortc, generated 640×360 video and
silent audio tracks, with all native PC input/services mocked. It uses trusted
public HTTPS to pair, confirms the page remains HTTPS and `isSecureContext=true`
after helper/gateway shutdown, then aborts every later HTTP request. It verified:

- Received/decoded screen video frames over local WebRTC.
- Received audio RTP alongside video.
- Stopped the screen and started a separate audio-only session with no video.
- Continued authenticated control after those media operations.
- No script errors, no live PC capture/input and no public control fallback.

The probe also caught a delayed `/icons/icon.svg` browser request. The bootstrap
now embeds that bundled icon in the page. The final media probe passed with zero
HTTP requests after pairing. An initial probe assertion was corrected to bind its
audio stats to the current peer/session instead of accepting stale peer stats;
that was a test synchronization issue, not evidence of media losing HTTPS.

Regression evidence: the incorrect permission/HTTPS error and silent Media
toggle were both observed failing before fixes. The new gateway icon test also
failed before embedding. Full Python suite: 541 passed; existing JavaScript unit
tests: 122 passed, one skip; local transport tests: 3 passed; browser interactions:
89/89 passed; desktop pairing: 9 passed, optional capture skipped. Physical Android/UPI behavior,
native device capture and external network/firewall conditions remain device
tests; generated media does not establish those hardware results.

Normal-desktop upgrade to 2.2.0.7 passed. For this user's explicitly requested
sharing use, screen/audio access was enabled with the required PIN retained; an
exact comparison confirmed every other config value was preserved. The live host
confirmed the updated source, local API, required PIN, authenticated connection
and enabled media flag. Twenty installed-runtime checks, the responsive window,
Windows uninstall entry and desktop/Start shortcuts passed. No stream was opened
by the installation smoke test.

Published installer: `TouchHelm-2.2.0-test7-setup-win-x64.exe`, 181,697,876 bytes.
Local and GitHub SHA-256 both match
`33a5ee0fd590d99edf44194df6d798c821297717d5fb488e5e34522dfb010f8f`.
