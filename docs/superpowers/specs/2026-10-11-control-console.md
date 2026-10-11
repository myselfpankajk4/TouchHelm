# TouchHelm control console

Approved in chat: implement the redesign without further design or plan check-ins.

The phone should feel like a working remote: most of Trackpad is usable movement space, typing expands only when needed, Presenter and Media show the real desktop context, keyboard chords act as held native keys, and Apps launches desktop programs. Existing pairing, themes, PIN protection, gestures, laser, volume, brightness, shortcuts, and drafts remain available.

## Phone layout

Five bottom tabs: Trackpad, Presenter, Media, Keyboard, Apps. Numpad becomes a segmented panel inside Keyboard. A compact header shows the connection and Settings; appearance, awake, and fullscreen actions remain available within Settings. Keep 44px touch targets, readable contrast, native focus, safe areas, and reduced motion. Retain the five themes, mouse mark, and system type; replace the previous roomy card layout with compact toolbars, contextual information, and purposeful control surfaces.

Trackpad uses a slim click strip and a single-line typing dock. Focus expands the dock to reveal Send/Enter, Clear, live sync, and an auto-sized typing field. A Done control returns focus to cursor movement and collapses typing while retaining a draft. The expanded field stays reachable above the phone keyboard.

Presenter shows app/deck title, slideshow status, current slide/count/title when available, compact slide tools, collapsible timer, and laser pad. Timer start/pause/reset are local and independent of network state. Use a deadline clock so background throttling does not stretch a running timer. Controls show connection failures instead of silently failing.

Media shows current player, title/artist/state, elapsed/duration where the player exposes them, a player selector, playback controls, compact volume/brightness rows, and a playable media list. Surface exact playlist availability. Windows media sessions supply broad current-playback support; extra adapters supply queue information where exposed. A local Music/Videos list offers selectable files when no application queue is available. Never fabricate a playlist or slide count.

Keyboard provides standard keys, function/navigation keys, letters, numbers, symbols and native numpad codes. Pointer press/release sends native keydown/keyup. Tap modifiers to latch for chords such as Ctrl+Shift+A; hold modifiers for simultaneous touch chords. Show held keys, provide Release all, and release on blur, cancellation, tab change, disconnect, and shutdown. Ordinary typing stays in Trackpad.

Apps lists Windows registered apps, supports search/refresh, and sorts running apps and actual TouchHelm launch frequency ahead of remaining alphabetical entries. Launches accept only catalog IDs; no remote shell commands or arbitrary paths.

## Desktop integration boundaries

Keep aiohttp, Tkinter, plain JavaScript, and the existing native input controller. New `DesktopServices` isolates Windows app, presentation, and media providers behind asynchronous methods. A persistent hidden PowerShell bridge may use Windows WinRT and COM without new package dependencies. All slow native queries and filesystem scans run away from the input event loop, with bounded deadlines and explicit unavailable states. Providers are lazy and close on server shutdown.

`DesktopServices` interface:
- `async snapshot() -> dict`: `{presentation: dict, media: dict}`.
- `async list_apps() -> list[dict]`: entries `{id, name, running, launches}`.
- `async launch_app(app_id: str) -> dict`: `{success, message}`.
- `async list_media() -> dict`: `{sessions: list, items: list, playlist_supported: bool, playlist_message: str}`.
- `async media_command(action: str, session_id: str = "", item_id: str = "") -> dict`: `{success, message, handled}`.
- `async presentation_command(action: str) -> dict`: `{success, message, handled}`. Rich PowerPoint control should avoid dependence on foreground focus; other presenters keep native shortcuts and window context.
- `async close()`: closes owned helper resources.

Presentation fields: `{available, app, title, active, slide, total, slide_title, message}`. Media fields: `{available, session_id, app, title, artist, album, status, position, duration, message}`. Missing numerical fields are null. Media items: `{id, title, subtitle, kind}` with kind describing queue/local/session.

Authenticated incoming WebSocket messages: `get_desktop_state`, `get_apps`, `launch_app {app_id}`, `get_media_library`, `play_media {item_id, session_id?}`. Existing `media` packets may include `session_id`. Responses: `desktop_state {presentation, media}`, `apps_sync {apps}`, `media_library {sessions, items, playlist_supported, playlist_message}`, `command_result {command, success, message}`. Authenticated broadcasts periodically update presentation/media state. Unknown or unauthorized commands must not query or launch anything.

`web/controls.js` defines `TouchHelmControls(client)`, with `setConnected(bool)`, `releaseKeys()`, `renderDesktopState(state)`, `renderApps(apps)`, `renderMediaLibrary(catalog)`, and `commandResult(result)`. It owns new keyboard, typing expansion, app search/list, and context rendering. `app.js` owns the socket, timer, existing controls, and invokes that interface.

Volume up/down/mute should use native media keys to trigger the Windows flyout. Absolute volume and brightness changes get a transient TouchHelm desktop indicator when Windows offers no public flyout trigger. No focus theft; feedback helpers are lazy and shut down cleanly. Native key mappings must cover OEM punctuation and function/numpad keys correctly.

## Always-current browser

Create a content-derived build ID, version the QR URL, serve HTML and mutable assets with cache revalidation/no-store, include the ID in the HTML and `/api/version`, and compare it on open/focus. Auto-refresh only when a differing server build is confirmed; retain drafts and avoid refresh loops. Service-worker fetches must bypass HTTP caching for live assets, update on registration, and retain offline fallbacks. A stale worker must still receive a current build URL. The desktop shortcut continues to launch source from D:/Mouse.

## Verification

No test may send real keys, click, launch apps, alter volume/brightness, or lock the PC. Mock native boundaries and temporary usage/config files; use real DOM and local HTTP/socket doubles for interactions. Read-only Windows provider probes may inspect installed apps/current sessions. Test modifier cancellation, server auth and ID validation, timer reset plus subsequent slide commands, build mismatch/draft retention, unsupported providers, and slow helper timeouts. Visual verification is one full matrix, one repair batch, and one confirmation, covering narrow phones, landscape, keyboard-reduced viewport, desktop, all five themes, and dynamic populated/empty/error states.
