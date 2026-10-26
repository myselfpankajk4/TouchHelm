# Certificate-free browser pairing — Test 5

On the desktop choose **Pair your phone → Browser link → Start browser link**.
Keep the PC and Android Chrome online. Scan the QR, then enter the PC PIN.
No phone app, VPN, user CA certificate or Python installation is needed.
The installer bundles the pinned cloudflared helper; source builds automatically
download and hash-check it on the PC when this feature is requested.

Control commands, typed text, focused PC text and ordinary UI metadata travel
through Cloudflare, which terminates TLS. This is not end-to-end encryption from
phone to PC. Screen/audio retain the existing direct, host-only WebRTC route;
both devices must share a reachable local network. Screen/audio access remains
a separate desktop permission, and starts only after a phone request.

Plain HTTP remains available for basic local control, but cannot provide all
secure-context browser features such as motion sensors and wake lock. Browser
permissions, OS permissions and unsupported PC fields remain unchanged.

The optional test link expires after 30 minutes. Its QR capability expires after
120 seconds, is single-use, and rotates after exchange. Choose **New QR code**
if needed. Refreshing an already paired browser uses its Secure, HttpOnly,
SameSite=Strict cookie. The existing PC PIN and rate limit still apply.
Stop link, helper exit, expiry or host shutdown revoke sessions and release input.
No tunnel starts automatically. Existing connection preferences are preserved.

Only a separate random-port loopback gateway is forwarded. It validates the exact
assigned hostname, gates APIs/WebSocket behind the QR capability, and denies
certificate downloads, handoffs, desktop previews, service workers and private
configuration/source files. The normal LAN app and native desktop bridge are
not forwarded. Security/access settings cannot be changed through the relay.
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

Verified: offline manager/gateway tests; native bridge/PIN/cleanup regressions;
desktop loading, recovery, settings, QR controls and responsive layouts; real
public HTTPS/WSS and actual headless Chrome pairing/PIN/cookie refresh against a
synthetic host, with normal TLS verification and no native PC input. Physical
Android, banking apps and screen/audio over the public signaling route still
need the user's test. The media transport itself is unchanged.
