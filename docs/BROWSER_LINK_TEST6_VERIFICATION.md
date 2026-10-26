# Test 6 local-control verification — 26 October 2026

The ongoing Test 5 relay control transport is replaced. The temporary public
origin serves phone assets and HMAC-bound pairing only. PC controls, PIN, settings
and artwork have no public route; they use a private-subnet-validated DTLS peer.
See [transport setup and trust limits](BROWSER_LINK.md).

Verified against synthetic native boundaries, with no live PC input or capture:

- 539 Python regressions passed. This includes retained legacy endpoint denial
  tests, additive HMAC/nonce/exact-SDP/replay tests, selected-peer subnet checks,
  candidate filtering, framing limits and input cleanup after command failure.
- 122 existing JavaScript unit passes, one existing skip; 3 new transport logic
  tests passed. Existing browser interaction suite: 88/88 passed.
- Desktop pairing: 9 passed, optional screenshot check skipped. Local-connected
  state keeps Stop visible and removes stale public QR/address actions.
- Actual Chrome/aiortc control passed both a local bootstrap fixture and a real
  trusted public HTTPS bootstrap. No certificate bypass was used in the public
  test. The QR fragment was removed, the PC fingerprint checked, and PIN auth
  completed over the encrypted data channel.
- After the public helper/gateway stopped, Chrome aborted every subsequent HTTP
  request. Typing packets reached only the native mock; settings and 180 KB of
  synthetic artwork arrived through the local channel. A security-setting change
  was rejected. Material switching used its prepared stylesheet blob.
- There were no later HTTP requests, no script errors and no relay fallback on
  disconnect. The helper and gateway were both confirmed stopped. Startup
  cancellation, QR readiness and normal LAN-client preservation passed.

The version-bound nominated-ICE-pair inspection is intentionally fail-closed.
There is no STUN/TURN or automatic public control fallback. Initial page/browser
and PC trust still matter; this is not an independent audit or a claim of safety
against compromised endpoints/hosting. Local HTTP and other advanced connection
modes retain their existing properties when explicitly selected.

Physical Android permissions, complete live screen/audio sessions, banking apps
and clean-machine installation still need user/device testing. Keep the already
loaded phone page open; refresh/reconnect requires a new QR after the temporary
origin has closed.

Normal Windows desktop upgrade to 2.2.0.6 also passed: uninstall registration,
desktop/Start shortcuts, preserved settings, matching updated server sources,
responsive window, 20 bundled-runtime/model/UI checks with system Python absent
and invalid Python environment variables, and the running host's source identity,
local API and required-PIN authentication. No live-PC public link was opened by
these smoke checks.

Installer: `TouchHelm-2.2.0-test6-setup-win-x64.exe`, 181,698,959 bytes (173.3 MiB).
GitHub's uploaded digest matches local SHA-256:
`53024fd5128180c521fd1c96d1954510b7ad3b88b931a86f9d830391de7e75a7`.
