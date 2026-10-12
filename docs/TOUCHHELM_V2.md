# TouchHelm v2 implementation contract

The user approved implementation on 12 October 2026. Android Chrome is primary. Deliver all five milestones without further design check-ins; physical checks remain explicitly separate from mocked regressions.

## Behaviors

1. Trackpad dominates. Expanded composer collapses and blurs on first pad contact, consumes that entire contact without PC input, preserves draft. Return inserts newline, buffered default, explicit Send and Ctrl+Enter shortcut. Live mode has PC Enter action and enter/shift_enter newline preference, correct IME/autocorrect/paste/emoji baseline. Optional pinch zoom locks interpretation; retain two-finger XY scrolling, drag, sensor calibration and settings.
2. Presenter compact context then reachable Previous/Next, large laser with display selection, then show controls, independent timer, optional preview/notes drawer. On-demand PowerPoint current/next previews, notes, slide navigation; honest unavailable states. Fallback must verify presentation target focus. Release laser on every interruption.
3. Media Now Playing: actual artwork/title/artist/album/player/timing, supplementary details, stateful Play/Pause, supported seek and +/-10s, local elapsed interpolation while confirmed Playing, capability-gated shuffle/repeat/rate/stop/track actions, readback after commands. Only genuine provider queue, no local folder scans or generic session-as-playlist. Volume/brightness unknown if readback missing.
4. Keyboard native held/sticky modifiers, F1-F24 and Numpad retained, chord composer/favorites, controlled repeat, cleanup on interruptions. Windows Start only Keyboard.
5. Apps actual shell icons, exact verified window identity, pinned then running then TouchHelm frequency then alpha. Hold/overflow menu Open, Focus (window chooser), Pin, Details. Scroll/cancel suppress menu; hold release cannot launch. No close/kill.

## Shared interfaces

Provider service: media_command(action, session_id='', item_id='', value=None); presentation_command(action, slide=None); presentation_details(); displays(); app_action(app_id,action,window_id=''). service.assets.get(asset_id)->PNG bytes|None. App entries icon_id,pinned,windows:[{id,title}]. Media adds capabilities {play,pause,next,prev,stop,seek,shuffle,repeat,rate}, artwork_id, playback_rate, shuffle, repeat, min_seek/max_seek relative seconds, updated_at UTC seconds. Presentation details current/next objects with artwork_id/title/index, notes string, slides index/title list, capabilities and message.

HTTP assets are opaque IDs, existing auth headers, no arbitrary paths or PIN URLs. Slow providers/asset normalization off input loop. Validate finite action values and current catalog/window/session IDs. Preserve old command shapes, add text newline_mode enter/shift_enter and provider numeric values.

Themes: bloom,resonance,companion,clay,glass,soft,ink. Full materials, illustrations, icon presentation and state/motion across every phone tab and desktop. Original brand mark remains recognizable, real app branding untouched. window.TouchHelmThemes registry/migrate/apply/mountPicker/updateContext/setInteractionActive. Local device preferences appearance light/dark/system, motion, contrast. Migrate cyber/oled=>glass dark, matrix=>bloom dark, nordic=>soft dark, light=>clay light. Active theme assets only, pause while html.interaction-active/hidden, reduced-motion/increased contrast, accessible Ink fallback. No fake audio waveform.

Haptics centralized, trusted activation/capability/return-status/throttle/cancel, explicit Test vibration, visible feedback fallback, physical Android evidence before claiming hardware works.

Desktop pywebview EdgeChromium shared theme shell; Python server/native/tray/headless retained, --classic-ui rollback. Native privileged bridge only owned window with token. QR/pairing/settings/devices/activity/diagnostics, original icons, graceful lifecycle. Single-instance restore matching build, graceful restart changed source, no unrelated process termination.

Optional SecurePairingManager local CA and SAN certificate, LOCALAPPDATA/TouchHelm/certificates private-key ACL, public fingerprint/certificate and manual Android trust guide, no automatic trust-store changes. HTTP8765 plus HTTPS8766, HTTPS QR/WSS, renew LAN SAN changes, explicit expiring one-use in-memory draft/preference transfer between origins, recheck auth. Secure context checks for wake-lock/motion. Private keys never HTTP assets or Git.

## Execution milestones and acceptance

- M1 interactions, layout, haptic diagnostics, stateful media and absent unsupported queue.
- M2 actual provider artwork/media/actions/app icons/menus/presentation details and focus guards.
- M3 secure pairing, shared desktop/theme foundation, migration and reliable launcher.
- M4 all seven themes and browsable real-interface preview board, clearly labeled fixtures.
- M5 safe regressions plus physical-device checklist, documentation/screenshots and private GitHub updates.

Meaningful RED/GREEN regressions for reported defects and native provider/security boundaries. Visual matrix 320x568,360x640,390x844,landscape,keyboard-reduced,desktop; all themes light/dark/reduced/high contrast, offline/loading/unavailable/held/menu states. Inspect once in batch; one fix batch and one confirmation. 44px targets, 4.5:1 body/3:1 graphical contrast, visible focus. No stuck native state. No fake library/waveform/readback. Native input is mocked in automated tests. Actual phone, PowerPoint and player smoke tests may need user-operated devices and must remain disclosed if unavailable.

No live desktop streaming, true audio analysis, arbitrary browser slide introspection, or application force termination.

## Implementation and evidence

Milestones 1–4 are implemented. Release documentation, preview board and repository integration comprise milestone 5. Physical acceptance remains separate from software verification.

- Browser regressions reproduce multiline Return, first-contact dismissal, Presenter hierarchy, timer isolation, stateful playback, unavailable queues/players/hardware, native key cleanup, gesture locking, app holds and authenticated certificate transfer. Phone layouts cover 320×568, 360×640, 390×844, landscape, keyboard-reduced height and desktop.
- The shared theme board uses the actual interfaces with simulated data. Seven theme families cover every phone tab and desktop page. Fourteen light/dark variants passed the rendered text-contrast audit after correcting light selected-tab labels. Ink remains the asset-load fallback. Theme artwork provenance is recorded in `assets/theme/provenance.json`.
- Windows provider fixtures cover finite values/capabilities, stale session/window rejection, real queues only, bounded asset normalization, on-demand PowerPoint details and guarded presentation fallback. Current/next exports use a bounded ten-second thumbnail cache; notes are read on demand.
- Read-only probes on this PC found 109 registered apps, 90 extracted icons in the initial bounded batch, five verified windows and one 2560×1440 display. Volume and brightness readback succeeded. No actual launch/focus/playback/input or hardware setter was used for those probes.
- An actual WebView2 smoke loaded the brand image, QR, native bridge, Glass theme and all four desktop pages, with no page overflow or desktop error message. It closed normally. Content capture used the owned WebView2 renderer; README previews remain explicitly synthetic.
- A real source-launcher smoke restored the same build, then restarted after a temporary source marker changed. Old and replacement hosts exited normally; the marker was removed. No native input was sent.
- Real temporary local certificates passed Python CA/hostname verification and authenticated, single-use TLS draft handoff. Windows key-directory protection executed successfully. No Windows or Android trust store was changed.

Remaining device acceptance: Android keyboard/IME and physical vibration; Android CA installation and trusted secure context; phone theme performance; live supported-player seeking/readback and PowerPoint navigation/notes/preview behavior. Automated tests mock those native effects. A successful API request is never described as a physical success.

### Manual device checklist

1. Pair Android Chrome using the current QR. Type two lines, paste emoji and use IME; confirm each character reaches the target once. Touch the pad to dismiss typing, confirm the draft remains, and confirm that contact performs no PC input.
2. Choose Test vibration and confirm a physical pulse. Test with vibration disabled too; visible press feedback must remain usable.
3. With PowerPoint open, start/pause/reset/finish the timer while using Previous/Next and laser. Check the selected monitor, current/next thumbnails, notes and a slide jump. Move focus to an unrelated window and confirm fallback refuses input.
4. With a supported player open, select it explicitly. Check artwork, Play/Pause state, seek bounds, ±10 seconds and the options it advertises. Close that player; it must become unavailable without targeting another player.
5. Hold an app, scroll through apps and cancel a hold. Use Open/Focus/Pin/Details and a multi-window chooser. Hold native keys, change tabs or background Chrome; no key, mouse button or laser may remain held.
6. Follow the desktop HTTPS guide, compare the CA fingerprint, install Android trust manually, then scan the HTTPS QR. Reauthenticate and transfer a draft once. Check Chrome reports a trusted secure context before testing keep-awake/motion.
7. Use all seven themes in light/dark and reduced motion, including the smallest screen and the phone keyboard open. Check labels, focus, touch targets and response time on the actual phone.
