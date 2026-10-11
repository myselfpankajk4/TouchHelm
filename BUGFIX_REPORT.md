# TouchHelm bug fixes

The desktop app, server, and phone page were audited together. The approved 11 October 2026 control console has five tabs: Trackpad, Presenter, Media, Keyboard, and Apps. Numpad is inside Keyboard; the five appearance themes and existing pairing/input safeguards remain.

## Requested changes

- Windows Start now appears once, in the Keyboard tab.
- The complete typing panel (text field, Send, Clear, live keystroke sync) is on Trackpad.

## Other verified repairs

- Live typing handles paste, autocorrect, selection replacement, multi-character deletion, and IME composition. Offline Send retains the draft; switching typing modes avoids duplicate text.
- Double tapping sends two clicks instead of three. Slow two-finger scrolling no longer opens a context menu when fingers lift.
- Reconnecting ignores obsolete sockets and cancels duplicate retries. Selecting a different server also directs settings requests to it.
- Connecting a phone loads the PC's settings without overwriting them with old phone defaults.
- Settings changes propagate between desktop and phone controls. Both sensitivity sliders cover the same range.
- Phone controls fit narrow screens, landscape, and a reduced viewport representing an open keyboard. Unsupported fullscreen and screen-awake APIs no longer throw or show false success.
- The service worker caches the assets actually referenced by the page and only deletes its own obsolete caches.
- The existing optional PIN now gates both remote input and settings; public responses omit the PIN. Invalid settings and malformed WebSocket packets cannot poison configuration or disconnect a healthy session.
- Held keys and buttons are released on disconnect or shutdown. Unicode input preserves supplementary characters, Windows hotkeys use their required flags, and the laser starts with the requested color.
- Desktop startup waits for server readiness, reports failures, and cleans up partial resources. Shutdown closes the server loop; tray callbacks run on the Tk thread, a failed tray remains recoverable from the taskbar, and discovery closes sockets and joins workers.

## UI and UX refresh

- Desktop pairing now leads with a readable QR code, selectable address, and inline Copy URL feedback. Connected devices show Ready or PIN required, with a dash for unknown latency. Recent activity stays secondary and retains the reader's scroll position.
- Desktop settings are grouped into Pointer, Scrolling, and Presentation. The content fits the settings viewport, and the pairing card adapts at the minimum window size so security details remain visible.
- Phone controls use quieter surfaces, clearer labels, larger touch targets, readable text across all five themes, and a bounded layout on desktop browsers. The typing panel remains on Trackpad, and Windows Start remains exclusive to Keyboard.
- Send and Clear restore typing focus. Send becomes Enter in live mode to describe its actual behavior. Offline drafts remain editable, while remote controls show that they are unavailable.
- Theme, Settings, and PIN dialogs contain keyboard focus. Theme and Settings support Escape and return focus to their trigger. PIN remains required until authentication succeeds.
- Failed settings saves no longer falsely report a disconnected PC. A persistent warning identifies unsaved settings; transient messages expire. Older responses and successful updates to unrelated settings cannot erase an unsaved edit.
- Switching PCs retains the draft but clears the old PC's sent-text history, preventing accidental backspaces on the new PC.

## Approved control console

- Trackpad now devotes its main area to movement. A slim typing dock expands on focus; Done collapses it and retains its draft.
- Presenter and Media put current desktop context before controls. The timer uses a local deadline, with pause/reset independent of presentation packets and connection state.
- Keyboard supports native press/release, simultaneous touch chords, latched modifiers, held-key feedback, Release all, and a segmented native Numpad. Cancellation and disconnect cleanup release held inputs.
- Apps supports catalog search/refresh and validated-ID launching. Ranking uses successful TouchHelm launch requests persisted in `.touchhelm_usage.json`, with heuristic visible process/window matching for running state. Launch requests are not proof that the destination app finished opening.
- The lazy hidden PowerShell provider supplies broad Windows media-session metadata and selected-player commands. Windows Media Player exposes an actual queue only where a running instance registers its COM object; current sessions and bounded local Music/Videos files provide other selectable items. The combined displayed list is limited to 200.
- PowerPoint supplies rich deck/slide/slideshow metadata and direct COM commands. Supported browser/PDF presenter windows expose window context and native keyboard fallback; slide numbers/counts remain unknown when unavailable.
- Queue/session identities remain stable across reorder; disappeared selections fail instead of controlling a different item. Snapshot metadata lists all current players without recursive references. A canceled queued request is checked after bridge-lock acquisition and before writing a native command.
- Busy-provider commands return an explicit failed `command_result` so an app row cannot remain stuck on Opening. The volume monitor's initial and polling reads run off the input event loop, keeping slow native reads from delaying pointer packets.
- Native volume up/down/mute request the Windows flyout. Absolute volume and brightness use a transient TouchHelm indicator without focus theft. Monitor brightness support depends on hardware/driver capabilities.
- Content-derived build IDs version QR URLs and phone assets. Confirmed server build changes reload the phone while preserving drafts. Existing Python hosts must still be restarted after source changes; the desktop shortcut launches current source.

## TouchHelm rename

The desktop window/tray, browser/PWA, Android package/theme, native feedback, launcher, internal classes/protocol identifiers, and documentation now use TouchHelm. The desktop shortcut is TouchHelm (Latest). Existing browser preferences and update drafts migrate from the former storage prefix; the worker cleans up its former cache prefix. Local launch history was retained under `.touchhelm_usage.json`.

After the rename, fresh verification passed 80 Python tests, 50 JavaScript tests, and 38 browser scenarios, plus desktop previews and Python/PowerShell/Android-resource syntax checks. `npm ci` and the portable test tooling were verified. Local configuration, history, virtual environments, dependencies, and generated QA captures are excluded from Git.

## Verification

### Icon restoration and shortcut repair

Restored local SVG icons across the phone's trackpad controls, presenter commands, timer, media controls/library, keyboard keys and editing shortcuts, Windows shortcuts, and typing dock. The original mouse mark is visible in the phone header and now matches the desktop header, window, tray, and shortcut. Send/Enter and Start/Pause update their label and glyph without deleting the icon.

Fresh verification passed 82 Python tests, 51 JavaScript tests, and the 39-scenario browser matrix. Four desktop fixture previews were rendered. The final catalog alignment adjustment received a focused confirmation across six viewport sizes and all five themes. Tests substitute native effects; this does not claim a physical phone or live media/presentation smoke test.

The local TouchHelm (Latest) shortcut now has normal window style and the app's ICO asset. Launching it produced a visible, non-minimized desktop window and a listening host; a read-only HTTP check confirmed the updated logo/icon HTML with `Cache-Control: no-store`. It continues to run source from `D:/Mouse/run.bat`. A running host must be closed before relaunching Python changes.

### Previous redesign verification

The earlier redesign verification passed **80/80 safe Python tests, 49/49 JavaScript tests, and 38/38 real-DOM browser scenarios**, including the final explicit disclosure-chevron repair. Focused provider coverage includes actual PowerShell functions with mocked session/queue objects and mocked native mutation boundaries. The initial independent review matched the approved interface except for disclosures. The final scored review covered that sole repair: resolved, remaining findings clear, disposition **ship**.

The fresh browser matrix passed narrow-phone, landscape, keyboard-reduced, and desktop-browser checks at 320×568, 360×640, 390×844, 844×390, 390×420, and 1440×900, with all five themes, populated metadata, and offline/PIN/settings-error screens. Empty/missing metadata and unavailable providers were covered by logic/provider tests, not an empty-context screenshot. Transparent Tk previews passed for pairing/settings at normal 880×700 and minimum 820×620 sizes, producing four images. Fresh artifacts are saved under `tests/artifacts`.

Python compilation and PowerShell syntax parsing passed. The existing desktop shortcut was read and verified to target `D:/Mouse/run.bat` with working directory `D:/Mouse`.

Spawning a fresh reviewer failed because the harness default model was unsupported; an existing independent reviewer substituted. Impeccable context/detector automation was unavailable and did not run; design records were checked directly against the implementation.

Safe Python regressions:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_build_version tests.test_desktop_regressions tests.test_native_controls tests.test_desktop_services tests.test_server_regressions -q
```

JavaScript regressions (Node.js required):

```powershell
node --test tests/web_logic.test.cjs tests/service_worker.test.cjs tests/browser_ux_logic.test.cjs tests/controls_logic.test.cjs
node tests/test_web_client.cjs
```

The browser runner uses an existing Playwright/Chromium installation. Its `PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` environment variables can override the bundled defaults.

Browser checks run against real DOM events and local HTTP with a controlled WebSocket transport. Keyboard appearance is represented by viewport resizing. Native Windows input and overlay effects are substituted in automated tests, so they never type, click, change volume, or lock the user's PC. Physical phone gestures and actual desktop input still need a device smoke check.

A read-only Windows provider probe found 115 registered apps, zero active media sessions, no supported active presenter, and no local media items. It did not launch an app, play media, send a key, or change volume/brightness. Physical Windows flyout/TouchHelm indicator behavior, live-player metadata/playback, and a live PowerPoint deck have not been smoke-tested. Running-app heuristics may match generic names incorrectly.

Use `node tests/test_web_client.cjs --visual` to refresh browser screenshots, or `--filter="name fragment"` to run only matching checks. `python tests/desktop_preview.py` captures a transparent, non-activating desktop preview with temporary configuration and no tray, networking, or remote input.

`test_touchhelm.py` is an older manual end-to-end script that injects real input, launches the GUI, and includes the Lock PC shortcut. It is not part of these safe regression commands.
