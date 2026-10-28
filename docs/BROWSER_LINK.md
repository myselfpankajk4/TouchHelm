# Historical: local encrypted browser pairing — Test 7

**Test 8 replaces this flow with local-only pairing and Files.** Public browser
pairing is no longer offered or started by the normal app. Use the current
[Local Wi-Fi guide](LOCAL_WIFI.md). The following is retained as Test 7 history.

On the desktop choose **Pair your phone → Browser link → Start browser link**.
Keep the PC and Android Chrome on the same local network. Internet is needed
only to load the phone interface and pair. Scan the QR, then enter the PC PIN.
No phone app, VPN, user CA certificate or Python installation is needed.
The installer bundles the pinned cloudflared helper; source builds automatically
download and hash-check it on the PC when this feature is requested.

Cloudflare serves the initial HTTPS page and bounded pairing messages. It never
receives the PIN, control commands, typed/focused text, settings or artwork via
an application control route. Those use an encrypted local WebRTC DataChannel.
Screen/audio and their signaling also stay local. The public helper/gateway shut
down once the direct channel connects. No STUN, TURN, router forwarding or
internet control fallback is configured. The selected peer must belong to a
private subnet of a local adapter, checked before accepting control and during
the session. Screen/audio retain their separate desktop permission.

The loaded phone document stays HTTPS and retains its secure context after the
temporary server closes; the phone is not navigated to an HTTP page. Screen/audio
also need **Pair your phone → Screen and audio access → Enable** on the PC.
Test 7 reports that permission separately from PIN and secure-transport errors.
An off desktop permission is not evidence of lost HTTPS. The phone's Media tab
now explains an off permission instead of silently turning its audio switch off.
The brand icon is embedded so delayed browser requests do not need the closed
origin. Generated video, video-plus-audio and audio-only RTP passed in Chrome
after shutdown with every later HTTP request blocked. Physical Android and live
capture on each PC still need device testing.

Plain HTTP remains available for basic local control, but cannot provide all
secure-context browser features such as motion sensors and wake lock. Browser
permissions, OS permissions and unsupported PC fields remain unchanged.

The QR includes a 256-bit pairing key and PC DTLS certificate fingerprint in its
fragment. The phone removes the fragment, verifies the PC fingerprint and sends
HMAC proofs bound to the stage, nonce and exact answer SDP. It never transmits the
QR key or authenticates control with a public HTTP cookie. Pairing expires after
120 seconds; choose **New QR code** if necessary. Local sessions last at most
30 minutes and retain the PC PIN/rate limit and capability checks. Stop, expiry,
loss of the local peer or host shutdown release input and end the session.
No tunnel starts automatically. Keep the loaded phone tab open: reloading or
reconnecting requires a fresh PC QR because its old public origin is stopped.
Existing connection preferences are preserved.

Only a separate random-port loopback gateway is forwarded. It validates the exact
assigned hostname and serves static assets plus challenge/offer/answer routes.
There is no public control WebSocket, PC info/config/artwork API, PIN endpoint,
certificate download, handoff, desktop preview or service worker. The normal
LAN app and native desktop bridge are not forwarded. Security/access settings
cannot be changed through the local phone RPC either.
The helper uses an isolated empty configuration and private environment; it does
not reuse a Cloudflare account, tunnel token or service installation.

Quick Tunnels are intended for testing, have changing hostnames and no uptime
guarantee. Temporary DNS failures were observed during verification. The desktop
withholds the QR until the public HTTPS path passes normal TLS verification.
Failure leaves a retry action rather than a stale ready link. A stable production
release needs a managed hostname/service and operational ownership.
[Cloudflare Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

The existing manually installed TouchHelm CA is not needed for this mode. On
Android, remove only that matching TouchHelm certificate under the user credential
settings; names vary by phone. Do not clear unrelated credentials. Banking-app
warnings depend on each app and may persist for other reasons. This feature does
not change Windows installer signing or remove SmartScreen warnings.

Trust limit: the PC, phone/browser and initially delivered page code must still
be trusted. A compromised page can act as the paired phone. This change removes
the ongoing public control service and readable relay traffic; it does not claim
to protect against a compromised endpoint or malicious initial hosting code.

Verified: proof/peer/framing security tests and all legacy route denials; shared
PIN/input cleanup; real Chrome with local aiortc and a mocked native host. After
the helper/gateway stopped, the browser blocked every HTTP request and still
completed PIN-authenticated typing packets, settings, artwork and theme changes.
The same test passed through normal trusted public HTTPS bootstrap, without a
certificate exception. Physical Android, banking apps and complete screen/audio
sessions still need user testing; native media transport/capture is unchanged.
