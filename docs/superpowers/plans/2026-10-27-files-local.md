# Files and local-only Wi-Fi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PC file browsing, phone previews and bidirectional transfers while removing internet from pairing and media.

**Architecture:** A dedicated filesystem service owns safe local handles, bounded I/O and transfer sessions. An aiohttp adapter binds that service to a PIN-authenticated live phone over the actual LAN connection. The existing phone shell gains Files and native browser media previews; PC screen/audio use verified direct local WebRTC.

**Tech Stack:** Python 3.13, aiohttp, Windows filesystem handles, existing aiortc, plain HTML/CSS/JavaScript and local SVG icons. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-27-files-local-design.md` (approved 27 October 2026).

## Global constraints

- Local Wi-Fi only; no reachable internet-pairing startup/UI or cloudflared payload.
- File access initially off, PIN mandatory, explicit native permission, live-client revocation.
- Ordinary HTTP is not advertised as encrypted; screen/audio retain WebRTC encryption.
- No overwrite, PC execution, existing-file deletion, UNC/network files or cloud hydration.
- Preserve seven themes, local assets, keyboard/text sync, native permissions and >=44px targets.
- No dependency, phone certificate, app, internet or remote asset required at runtime.

## Review focus

- Directory replaced during upload: native ancestor handles deny replacement; finish cannot escape.
- Browser-native media requests cannot attach custom headers: same-origin HttpOnly cookie session, CSRF writes, live owner checks.
- Phone disconnects during a large file: bounded chunks, cancel/retry and cleanup; no fake completion.
- Unsupported codecs/PDF support: explicit download/open fallback without a blank dead-end preview.
- Ordinary LAN HTTP has no secure-context APIs: no gyro/wake-lock prompt; media receive must work without getUserMedia.

## Task 1: Local filesystem engine

Files: create `server/file_store.py`, `server/file_handles.py`, `tests/test_file_store.py`.

Interfaces: `FileStore(roots=None, temporary=None)`, `locations()`, `listing(id, query='', sort='name', offset=0)`, `open_read(id)`, `mkdir(parent,name)`, `begin(owner,parent,name,size)`, `append(owner,id,offset,data)`, `finish(owner,id)`, `cancel(owner,id)`, `revoke(owner)`; all synchronous, caller dispatches through bounded worker pool.

- [ ] Add failing real temporary-file tests: Unicode/empty/duplicate files, pagination/search, byte-exact chunks, invalid offsets, cancel, revocation, file size, traversal/device/ADS/reserved names, unsafe previews, replacement links and denied cloud placeholders.
- [ ] Run `python -m unittest tests.test_file_store` and observe missing implementation.
- [ ] Implement native guarded handles, known folders/local drives, opaque identities, MIME allowlist, upload chunks <=1 MiB, <=16 GiB per file, <=2 active uploads per owner, <=200 entries/page, bounded scan <=50,000 entries with explicit limit error. Session scope <=8192 file identities; paginate without stale arbitrary paths.
- [ ] Run file-store tests green and commit.

## Task 2: Authenticated local file HTTP

Files: create `server/local_network.py`, `server/file_http.py`, `tests/test_file_http.py`; modify `server/web_server.py`, `server/config.py`, `gui/webview_window.py`.

Interfaces: `FileHTTP(server,store)` with `routes(app)`, `ticket(client)`, `revoke(client)`, `close()`; `local_request(request)` validates real socket/Host/subnet; file session exchange uses a 30s one-use ticket delivered after WS auth, HttpOnly SameSite=Strict path-scoped cookie and CSRF header for writes. Sessions expire after 30min and revoke with PIN/access/socket changes.

- [ ] Write failing integration tests for ticket exchange, Range/HEAD/416, attachment types, duplicate upload, cross-origin/public/unauthenticated access, PIN/access revocation and in-flight disconnect.
- [ ] Observe red, implement narrow JSON routes plus streamed content with 256 KiB read buffers; upload requests bounded at 1 MiB; disk workers max2; transfers/files clients bounded.
- [ ] Add `files_enabled` native-only bool config permission, disable on no PIN, and live revoke hooks. Do not expose permission updates through phone settings.
- [ ] Run file HTTP/store and existing server tests; commit.

## Task 3: Offline local pairing and PC media

Files: modify `server/web_server.py`, `server/remote_service.py`, `server/remote_media.py`, `gui/webview_window.py`, `gui/web/desktop.js`, `gui/web/index.html`, `packaging/build_installer.py`; tests `tests/test_offline_local.py`, existing narrow expectations.

- [ ] Write failing tests for explicit verified-LAN media capability, public/foreign origin denial, disabled internet pairing, startup ignoring old Tailscale/CA preference and cloudflared-free packaging.
- [ ] Observe red; route media authority using distinct local capability, no forged secure flag; media worker verifies nominated ICE peer on the authenticated LAN and guards capture/audio until verified.
- [ ] Remove normal public/Tailscale setup actions and API calls; migrate desktop to local QR. Keep historical helper modules/tests unexposed. Add PC Files permission UI.
- [ ] Run local/media/server/native-shell regressions green and commit.

## Task 4: Files browser UI

Files: create `web/files.js`, `web/files.css`, local `web/icons/files/*.svg`; modify `web/index.html`, `web/app.js`, `web/experience.js`, `web/sw.js`; tests `tests/files_logic.test.cjs`, browser tests.

- [ ] Add failing UI tests for tab/auth session, quick folders/drives/breadcrumbs, search/sort/pages, selection/Receive, destination picker/new folder, progress/cancel/retry, preview/download fallback and browser Back.
- [ ] Observe red; build approved image direction with semantic controls, safe text rendering, sculpted authored icons, all theme tokens, 320/393/wide layouts. Use native video/audio/iframe PDF and bounded HTTP upload chunks; never whole-file buffers.
- [ ] Hide gyro/wake-lock in HTTP; remove secure pairing/handoff prompts; preserve existing controls and navigation.
- [ ] Run JS tests and local browser interactions; compare actual screenshots to target and fix material differences; commit.

## Task 5: Offline integration, review and handoff

Files: create `tests/offline_files_check.py`, `tests/offline_files_phone_check.cjs`, `docs/FILES_LOCAL_VERIFICATION.md`; update `PRODUCT.md`, `DESIGN.md`, `docs/BROWSER_LINK.md`, `docs/WINDOWS_INSTALLER.md`.

- [ ] Run real local HTTP + Chrome synthetic file/media tests with nonlocal HTTP blocked from first load; assert video/audio-only, controls, transfers, native previews, seek and no public helper. Capture 320/393/wide, light/dark, loading/off/empty/error/progress states using fixtures only.
- [ ] Run full Python and JS suites plus existing interaction tests; fetch Web Interface Guidelines and review changed UI code. Fix meaningful failures once supported by regression tests.
- [ ] Request fresh whole-branch review if available, fix material findings, document physical Android/native capture limits honestly. Update spec status, ledger and task checkboxes.
- [ ] Commit tested source and documentation. Do not publish a new installer or replace the user's installed copy as part of this source implementation unless subsequently requested.

## Execution record

Approval authorizes implementation in this session. Native execution on the existing
`codex/portable-test-release` branch preserves the prior test-release context. No
additional design/plan permission round is needed. Save durable progress in
`build/files-local-progress.md` (ignored), recording tests and rulings after tasks.
