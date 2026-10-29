# TouchHelm product context

Current release 2.2.2: local Wi-Fi only, including first page load and pairing. Seven
phone tabs are Trackpad, Files, Presenter, Media, Keyboard, Apps and Remote.
Files provides local drive/known-folder browsing, supported browser previews,
Send to PC with an explicit destination and Receive through Chrome downloads.
A separate, initially-off PC File access permission and PIN are required.
Transfers are bounded, cancellable, revoke with the live client, and never
overwrite existing files. Ordinary controls/files use local HTTP; screen/audio
use direct encrypted WebRTC with verified local peers. See docs/LOCAL_WIFI.md and docs/FILES_LOCAL_VERIFICATION.md.
The earlier release notes below describe the evolution of the retained modules.

TouchHelm lets a person use a phone browser as a Windows remote. Primary tasks are pairing, pointer movement, typing, presentation/media controls, native key chords and registered apps. Python owns the server and WebView2 desktop shell, with a Tk rollback option. The phone uses plain HTML/CSS/JavaScript served by aiohttp.

The phone is typically held in one hand while attention stays on the PC or presentation. Keep movement space large, commands easy to reach, and context readable at a glance. The desktop's first task is pairing: QR code, address, copy/open actions, and security state belong together. Device status and activity support that task without replacing it.

Approved 12 October 2026: five phone tabs — Trackpad, Presenter, Media, Keyboard, Apps — with Numpad inside Keyboard and Windows Start only in Keyboard. First pad contact collapses the typing dock without discarding a draft or sending input. Live typing defaults on; offline edits require explicit Send after reconnect. Presenter and Media show actual provider context and missing capabilities. Apps use verified window identities; normal Close window preserves the application's save prompts.

Preserve five themes (Aurora, Bloom, Resonance, Constellation, Ink), the mouse mark, original app branding, system typography, native focus behavior, 44px targets and safe areas. Aurora, Bloom, Resonance and Constellation render a generative WebGL field that reacts to where and when the user touches, types and presses (position and timing only, never typed text) with Rich/Calm/Off preferences; Ink stays plain. System reduced motion wins; decoration cannot obscure controls or capture input. Drafts, navigation, themes and timer stay usable offline. Remote actions require a ready authenticated link; save errors must not pretend the socket disconnected.

Provider differences are product truth: PowerPoint exposes rich deck state and direct controls; other supported presenter windows may expose only a title and keyboard fallback. Windows media sessions expose playback metadata where supported, while queue access is adapter-specific. Never invent a playlist, slide count, elapsed value, running certainty, or successful command.

Preserve authentication revocation, PIN backoff, held-input cleanup, catalog validation, bounded slow work and owned-helper shutdown. Pairing is local HTTP with a host PIN; the server validates the selected peer against local private adapter subnets and failed or disconnected transport releases input. The source launcher restores matching builds and gracefully restarts changed source; versioned browser assets refresh while preserving drafts and synchronization baselines.

The sixth Remote tab supports screen control/viewing and a shared audio-only mode
available from Media. One controller owns both PC-audio toggles; listening alone
creates no screen capture or input lease. Fullscreen requests landscape where the
browser allows it and retains exit/Stop controls. New generated PINs use four ASCII
digits; actual wrong guesses remain rate limited. Multiline phone Return defaults
to Shift+Enter on the PC, with an explicit PC Enter action.

The four generative themes render GLSL fragment shaders (`web/theme-scenes.js`, `web/theme-gl.js`); there are no bitmap theme backdrops. Existing logos and provider artwork remain.

Trackpad's device-local Two-way PC text setting follows supported focused editable
Windows controls through an isolated, bounded UI Automation helper. It requires a
host PIN and active Trackpad/Live typing. Password and read-only fields are
excluded. Editable PC focus automatically expands and focuses the typing dock;
ordinary snapshots do not reopen a dismissed dock. Edits revalidate field identity
and revision, automatically merge independent edits, and follow PC text for
overlapping changes or a new field. No manual relink button is required. Lost
write acknowledgements are reconciled using the requesting client's committed
write ID. Field contents are never broadcast. See docs/PAIRING.md for pairing and limits.

AirControl adds a desktop Phone/AirControl chooser and explicit webcam start.
Hand, Head & Face and Combined modes share calibration, non-injecting practice,
validated profiles and native HUD/tray escape controls. Enabling transfers input
ownership and demotes an existing Remote Control stream to View without stopping
video/audio. Phone drafts remain local until explicit Send. Camera/inference use
an isolated checksum-locked Windows/Python 3.13 runtime; no phone camera endpoint
or face identity enrollment is provided. Speech uses guarded Windows Win+H and
separate Voice Access guidance. Physical tracking/speech acceptance is recorded
separately from synthetic/mock regressions in docs/AIRCONTROL_VERIFICATION.md.

Head & Face is now the fresh-profile default; explicit saved modes remain.
Its dwell action dock supports left/right/double clicks and a two-dwell drag/drop
without facial calibration. The shared native HUD geometry routes head dwell on
its controls without injecting desktop clicks. Calibrated expressions may hold a
drag. Physical-pixel steadiness and dwell radius are adjustable; interruption
releases app-owned input. Camera starts only through the explicit user action.

The daily-use AirControl workspace puts the movement area before setup details,
with persistent session/escape controls and service-derived activation guidance.
Session, Practice, Personal settings and Diagnostics separate the user's tasks.
Click/drag/scroll exercises use authoritative simulated events and validated stage
geometry; starting a task from active control explicitly returns ownership.
Head-only scrolling holds the Windows cursor at its entry position and uses a
virtual cursor for Up/Down/Done. All interruption paths cancel scrolling. Session
reports contain bounded, allowlisted measurements, no camera/field data, and are
exported only on request. See docs/AIRCONTROL_DAILY_USE_RELEASE.md for evidence
and the still-pending participating-user camera acceptance.
