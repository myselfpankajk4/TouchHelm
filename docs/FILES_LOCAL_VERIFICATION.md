# Files and local Wi-Fi verification — Test 8

The design was approved on 27 October 2026. Implementation and verification
continued on 28 October after a disconnected agent session. This document records
generated-data tests, not physical Android or live PC capture acceptance.

## Boundaries actually exercised

`tests/offline_files_check.py` starts the normal aiohttp server on an actual PC
LAN address with a temporary config and temporary file tree. It mocks native
mouse/keyboard, desktop-service providers, screen capture and audio acquisition.
The **production threaded MediaWorker**, aiortc, WebRTC negotiation, selected-peer
checks, codecs, file store and file HTTP transport run normally. Video frames and
audio samples are generated; no private PC file, screen or sound is captured.

`tests/offline_files_phone_check.cjs` opens actual Chrome at **393 × 850** CSS
pixels using ordinary LAN HTTP and asserts `isSecureContext === false`.
All nonlocal HTTP requests are rejected from the first navigation; local
data/blob resources do not count as network traffic. No Cloudflare helper starts.

The browser exercises Files navigation, quick folders/drives, current-folder
search, list selection, native video seeking, MP3 metadata/playback readiness,
PDF preview/open fallback, 2.56 MB chunked sends, byte-identical stored files,
numbered duplicate preservation, Chrome downloads, a new folder, destination
pagination beyond 200 folders, in-flight upload cancellation, and 320/393/980px
layouts. It receives generated PC video and audio through the production media
worker and checks inbound audio packets. Input reaches a mock native controller.

## Regression coverage

Temporary-file Python tests cover Unicode/empty files, chunk bounds and offsets,
ownership/concurrency, duplicate names, native directory replacement locks,
cleanup journals, cloud-only disabled metadata, invalid/traversing/device/ADS
names, stale file identity and unsafe active-content attachment handling.

HTTP tests cover one-use PIN-issued file tickets, cookie/CSRF binding, Range,
HEAD and 416, a full 1 MiB request body, cross-origin/rebinding rejection, native
permission/PIN/socket revocation, interrupted downloads and revocation during a
disk read. A delayed folder request cannot mutate after native revocation.
The phone cannot grant itself `files_enabled` through `/api/config`.

The independent review found four important issues: delayed-mutation revocation,
missing download interruption notification, destination pagination and silently
hidden cloud placeholders. Each was reproduced and fixed. Additional regression
checks cover failed reauthentication and same-PC Chrome selecting another actual
local NIC; an external phone still must match its actual paired IP.

Verified source results on 28 October:

- Full Python suite: **576 passed**, including a real Windows junction replacement
  with an unchanged hard-linked file identity, disk-full start and startup recovery.
- `npm test`: **122 passed, one optional skip**.
- Desktop/local-transport suite: **13 passed**, including optional visual capture.
- Existing phone behavior suite: **90/90 passed**.
- Production-worker offline file/media integration: all reported checks true;
  byte-exact files, no external HTTP, actual inbound audio packets and mock input.
- axe on Files: **zero violations in all 14 theme/appearance combinations**.

Further regressions pin cancellation before Chrome opens a request, bounded
Receive queues, stable Cancel keyboard focus during progress, a compact transfer
tray, permanent reauthentication revocation, and shutdown releasing active file
handles. Intermediate logs under `build/` are development artifacts, not claims
that every physical device passed. Installer evidence is added after building.

## Visual review

The inspected target is `docs/design/files-local-target.png` (853 × 1844 pixels,
approximately 393 × 850 CSS pixels). The implemented interface uses semantic DOM
and original SVG folder/file artwork, not a screenshot background. Actual Chrome
captures are under `build/files-*`. Search/sort, simpler file-row separators,
the existing mouse mark, all seven themes and accessible controls are deliberate
adaptations recorded in the approved design. No exact pixel-for-pixel claim is made.

## Remaining device acceptance

Physical Android Chrome still needs a participating user's test of native
downloads, PDF handling, actual Wi-Fi throughput, phone locking/backgrounding,
audible PC loopback and real Windows capture/control. Unsupported codecs use the
download/open fallback. A generated silent audio stream proves transport, not
speaker output. The 16 GiB limit is an implementation bound; a 16 GiB physical
Android transfer has not been tested. HTTP does not gain TLS protection simply
because it is on home Wi-Fi.
