# TouchHelm 2.1 — living controls

This release preserves the five tabs and seven theme families. The implementation contract is [TOUCHHELM_LIVING_PLAN.md](TOUCHHELM_LIVING_PLAN.md).

## Interaction changes

- Presenter navigation sizes with its container. Monitor selection and color choices precede the large framed pad. A compact Windows layered laser has cached alpha sprites, click-through hit testing and no foreground activation.
- One monotonic playback clock drives elapsed time, seek thumb, fill and accessible time. Provider positions are sampled from Windows `LastUpdatedTime`; an omitted playback rate advances at effective 1× while its metadata remains unknown. Selected-player snapshots share this normalization. Scrubbing owns the thumb until release; commands wait for readback and recover on rejection or timeout.
- Artwork reports `not_provided`, `available` or `read_error`. Authenticated bytes are normalized and decoded, valid covers are reused, and item changes clear old covers. No image is fabricated or scraped.
- Apps offer **Close window** only for verified windows, with a chooser for multiple windows. The bridge revalidates identity and posts normal `WM_CLOSE`. “Close requested” does not promise the window closed. A bounded refresh confirms disappearance or explains an open window, save prompt, refusal or unverifiable catalog. There is no force termination.
- Live typing defaults on unless the device saved an opt-out. Offline changes pause live transmission until explicit Send; reconnect and restored drafts send nothing automatically. Return/IME handling, draft dismissal and synchronization baselines remain intact.

## Four living themes

| Family | Idle and interaction scenes |
| --- | --- |
| Forest & Bloom | Varied flowers, growing frame vines, drifting petals and touch-bent foliage |
| Companion | Blinks, peripheral robot scenes, eyes following touch and state-aware expressions |
| Resonance | Decorative notes, plucked frame strings, native-key reactions and actual-playback record motion |
| Clay | Sculpted edge forms, pressed impressions and compressed/rebounding controls |

Rich is the default. Calm keeps brief stationary feedback; Off removes living effects. System reduced motion overrides spatial animation. The passive plane has eight recycled nodes: at most two idle actors and six touch actors. Continuous pointer work is admitted at no more than 30 updates per second. Input, scrolling, hidden state and view changes clear or suspend appropriate work. Text composition, focus rings, QR codes and PINs are protected; private textarea characters are never read for decoration.

The shared desktop runtime covers pairing, navigation, settings and outcome feedback. `/preview.html` shows actual phone/desktop components with simulated transport, including touch, held keys, seeking, missing artwork, close requests and private HTTPS readiness/permission/reconnect states. Preview controls never reach PC input.

## Private HTTPS without installing a local CA

1. In desktop **Pairing → Connection → Private Tailscale HTTPS**, use the Windows and Android installation links.
2. Sign in/connect both devices to the same tailnet. Enable MagicDNS and HTTPS certificates in Tailscale if your administrator requires it.
3. Refresh status, then choose **Enable private HTTPS**. TouchHelm enables a four-digit host PIN first if one is not already required.
4. Connect Tailscale on Android, scan the new `https://…ts.net:8443/` QR, and enter the host PIN. Verify Chrome shows a trusted secure context.
5. Disable this mode using the same desktop action. Only TouchHelm's verified owned endpoint is removed.

Serve proxies HTTPS 8443 privately to `127.0.0.1:8767`. Existing conflicting services are reported and preserved. No Funnel, public endpoint, automatic installer/login, trust-store mutation or phone-accessible setup privileges are used. Trusted proxy transport requires the dedicated loopback listener, loopback peer and configured hostname. Eight submitted invalid PINs within a minute trigger a global 60-second backoff, including peers sharing a loopback proxy. Tailnet access rules still determine which peers can reach the host.

HTTP 8765 and local-CA HTTPS 8766 remain explicit alternatives. Moving an existing phone to trusted HTTPS uses a single-use, 60-second transfer bound to the exact destination and fresh PIN authentication; it carries draft, baseline and device preferences without typing. A transient transfer failure can retry. An expired transfer requires returning to the previous connection.

Reference: [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve), [Windows media timeline](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessiontimelineproperties), [WM_CLOSE](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-close).

## Verification and remaining device acceptance

Safe automated regressions replace native input, close requests, provider commands and Tailscale CLI changes. Native smoke separately exercises only app-owned resources: cached laser colors without foreground activation, a scratch form whose first close is cancelled and second accepted, and the actual WebView2 shell's branding/QR/bridge/four panels with graceful shutdown.

The final verification counts, visual results and source-launcher evidence are recorded in [BUGFIX_REPORT.md](../BUGFIX_REPORT.md). No automated fixture is presented as a physical Android or supported-player test.

**Not performed on physical devices:** Android keyboard/IME, vibration, trusted Tailscale HTTPS and phone animation performance; supported live-player timeline/artwork and PowerPoint controls; 30-minute Tailscale WSS stability including background/resume and source restart. Tailscale is not installed/logged in on the verification PC. Complete these checks on connected target devices before declaring device acceptance.
