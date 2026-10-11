# TouchHelm product context

TouchHelm lets a person use a phone browser as a local Windows remote. Primary tasks are pairing with the desktop host, moving the pointer, typing text, navigating a presentation, controlling media, entering key chords, and opening installed apps. The desktop host is a Python/Tkinter source application; the phone interface is plain HTML/CSS/JavaScript served by aiohttp.

The phone is typically held in one hand while attention stays on the PC or presentation. Keep movement space large, commands easy to reach, and context readable at a glance. The desktop's first task is pairing: QR code, address, copy/open actions, and security state belong together. Device status and activity support that task without replacing it.

Approved 11 October 2026: five phone tabs — Trackpad, Presenter, Media, Keyboard, Apps — with Numpad inside Keyboard and Windows Start only in Keyboard. Text composition stays in Trackpad's compact expanding dock. Done collapses it without discarding a draft. Presenter and Media show actual provider context, with explicit missing values and capability messages. Apps accepts registered catalog IDs and ranks actual successful TouchHelm launch requests; running flags are heuristic.

Preserve five themes, the mouse mark, system typography, native keyboard/focus behavior, 44px command targets, safe areas, and reduced motion. Operate mode governs the remote and desktop control panel: usable controls and clear feedback take priority over decoration. Keep local drafts, navigation, themes, and timer usable without a connection. Remote actions require a ready authenticated link, and a settings-save error must not pretend the socket disconnected.

Provider differences are product truth: PowerPoint exposes rich deck state and direct controls; other supported presenter windows may expose only a title and keyboard fallback. Windows media sessions expose playback metadata where supported, while queue access is adapter-specific. Never invent a playlist, slide count, elapsed value, running certainty, or successful command.

Use the existing optional PIN and preserve authentication revocation, held-input cleanup, catalog validation, bounded slow work, and owned-helper shutdown. This is a local-network application, not a remote shell or an Internet deployment service. Source updates require restarting an existing Python host; versioned browser assets then help the phone load its current build while retaining drafts.
