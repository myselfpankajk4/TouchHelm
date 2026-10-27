# Files and fully local Wi-Fi — design for review

Status: proposed; product implementation has not started.

## Intent and selected approach

TouchHelm's Android Chrome interface gains a **Files** tab. A paired person can
browse their Windows PC, open supported files on their phone, send phone files
into a chosen PC folder, and receive PC files. Every normal connection, including
initial pairing, works without internet. Existing remote controls, PC screen
viewing/control and PC audio remain available on the local network.

The user explicitly selected **Local Wi-Fi only; remove internet pairing** on
27 October 2026. No Cloudflare, Tailscale, relay, public bootstrap, phone app or
manually trusted phone certificate is part of the new normal flow.

Approaches considered:

1. **Local browser HTTP with local WebRTC media (selected).** A PC LAN QR opens
   the complete phone interface. Authentication and file access use the local
   server; screen/audio use direct WebRTC. This meets offline first-launch and
   browser-only requirements. HTTP page delivery and ordinary control/file
   traffic are not end-to-end encrypted; home Wi-Fi is a deployment assumption,
   not a security guarantee.
2. **Trusted HTTPS bootstrap followed by local encrypted transport (rejected).**
   The current Test 7 model preserves secure browser APIs but needs internet to
   start or reload. The user expressly rejected retaining internet pairing.
3. **Native phone client or installed private CA (rejected).** Either changes
   the no-phone-install requirement; manual CAs already caused banking warnings.

The builder may retain legacy modules for compatibility/tests, but no reachable
UI, startup path or new package dependency may initiate internet pairing.

## Product scope

- Files is a first-class phone destination alongside the six existing tabs.
  Put it immediately after Trackpad so it is visible without hunting.
- Quick locations: actual available Desktop, Downloads, Documents, Pictures,
  Music and Videos known folders. Resolve Windows known folders, including
  redirected folders; do not assume every name exists below the home directory.
- This PC lists actual available local drives. Browsing follows ordinary
  Windows user access rights, without elevation. No synthetic file list ships.
  Reject mapped network drives/shares. Cloud-only OneDrive or other provider
  placeholders must not trigger an internet download: show that the file needs
  to be made available offline on the PC first. Already resident local files
  remain usable within the path/handle rules below.
- Folder view has breadcrumbs, Up, Refresh, search within this folder, name/type/
  date/size sort, and list/grid options. Large directories use bounded pages;
  search is bounded to the current folder, not a recursive whole-drive scan.
- Tap a folder to browse; tap a file to preview on the phone. **Never execute
  it on the PC.** Receive is explicit download/save to the phone. Multi-select
  queues individual downloads without silently making a huge archive.
- PDF uses Chrome's available PDF viewer/open action, images use a contained
  preview, and audio/video use native browser controls with seek support.
  Unsupported codecs/types offer Receive/Open in another phone app. Do not
  promise that every Windows video format will play in Android Chrome.
- Phone save dialogs and the final phone download location are controlled by
  Chrome/Android; do not claim arbitrary phone-folder write permission.
- Send to PC opens the phone's native file picker (multiple files), then an
  explicit destination picker; default to the currently browsed writable folder
  or Downloads. Show the destination before sending. Allow creation of a normal
  named subfolder so people can choose a useful destination without leaving Files.
- Transfer tray shows direction, filename, destination, completed/total bytes,
  progress and Cancel. Completed sends refresh the destination listing. Interrupted
  transfers show a retry action; do not claim completion on a broken connection.
- Existing files are never overwritten: allocate an available numbered filename
  atomically and report the final name. No delete, move, rename-existing,
  arbitrary command execution or Windows-permission editing in this scope.

## Desktop and local connection

- The primary pairing screen offers the local PC address, QR and PIN. Remove
  public browser-link/Tailscale download/setup actions and their status polling.
  Do not install/download or bundle cloudflared for the new release.
- Migrate a saved browser_link/tailscale preference to Local Wi-Fi; stop owned
  legacy helpers on upgrade/shutdown. Existing local CA files need not be deleted
  or uninstalled. Their removal is separate from this feature.
- Keep normal app startup free of network downloads. Existing installed PC
  media dependencies remain usable offline.
- A PC-side **File access** permission, initially off, allows browsing and
  sending/receiving for PIN-paired local phones. Display its scope clearly:
  files accessible to the current Windows user on local drives. One Enable action
  grants the requested session capability; do not prompt for each file.
- Screen/audio retain their separate PC permission. Enabling Files never enables
  screen capture or PC input, and enabling screen capture never grants Files.
- A PIN is required for Files and screen/audio. Switching off PIN or file access,
  disconnecting the owning phone, or stopping the PC server revokes file sessions
  and cancels active transfers. No permanent secret in a preview/download URL.
- Validate the real connection's local endpoint and peer against the selected
  LAN adapter's private subnet. Do not accept forwarded headers as proof of local
  origin. Check Host and Origin to prevent rebinding/cross-origin access. Reject
  public/relay/Tailscale routes for the normal local-only features.
- Browser notices accurately say **Local Wi-Fi**, not **secure** or **encrypted**
  for HTTP controls/files. No router forwarding or cloud fallback. Router client
  isolation or Windows firewall failure produces actionable reconnect guidance.

## Browser capability changes

- Hide Air Mouse and automatic screen-awake in the ordinary HTTP mode. Do not
  advertise unavailable controls. Touchpad movement still works. Explain the
  phone's screen-timeout setting in a short local-mode help note.
- Do not simply pass `secure=True` for plain HTTP. Adapt the media authority to
  distinguish authenticated, explicitly permitted local transport from trusted
  HTTPS. Preserve owner checks, rate limits, input release and permission gates.
- Receiving PC-generated screen/audio does not call phone getUserMedia. Use
  direct WebRTC with no STUN/TURN. Validate local media candidates and the actual
  nominated peer before live capture/transmission; fail closed if not verifiable.
  Media remains encrypted by WebRTC, while HTTP signaling/page delivery retains
  the limitations described above.
- Remove phone secure-pairing/CA/Tailscale handoff prompts from the local-only
  experience. Preserve themes, keyboard/text behavior and normal reconnects.

## Files service contract and boundaries

Use a dedicated files module behind the existing aiohttp server. Keep slow disk
work outside the input event loop. Do not put arbitrary paths into the general
control-command dispatcher or extend the old public gateway.

After existing WebSocket PIN authentication, mint a cryptographically random,
short-lived Files session tied to that exact live client and LAN peer. Bind
same-origin HTTP preview/download/upload authorization to that session with an
HttpOnly SameSite=Strict cookie exchanged by a one-use authenticated handshake.
Require an additional non-URL CSRF token for writes. Do not send the PIN as a
media URL, store file bodies in localStorage, or authorize Files using only the
existing `_http_authorized` header shortcut. Bound session count and lifetime;
recheck native permission, PIN generation and owning socket throughout transfers.

Representative operations: session exchange; locations/drives; bounded directory
listing; create subfolder; authorized read with HEAD and HTTP single-byte Range;
upload start/chunk/finish/cancel. The builder decides endpoint spelling and
internal data types. Keep raw paths out of the rendered address bar; breadcrumbs
and opaque entry IDs identify locations. Treat all names and metadata as data,
rendering text with safe DOM APIs.

Resolve and validate local paths server-side on every operation. No UNC/network
shares, device namespaces, ADS, reserved Windows names, relative traversal or
reparse-point escapes into a different location. Validate an upload's chosen
directory again at finalization. Existing-file writes are never allowed. Check
type, length, file identity and handles to avoid a link/junction replacement race;
use Windows handle/reparse protections as needed, rather than relying solely on
an earlier lexical `Path.resolve` check. Do not expose inaccessible/system-secret
locations by bypassing Windows checks. Permission errors are ordinary UI states.

Stream raw file chunks; never base64-buffer an entire file in a control packet or
phone memory. Use bounded upload chunks with verified offsets/length, incremental
disk writes, file-size/disk-space checks, bounded concurrent workers and a
temporary partial file. Delete incomplete app-owned partials on cancel, failure,
expiry and next-start recovery. Finish atomically without replacement. Limits and
retry behavior must be visible, documented, and covered by tests; no silent
truncation. Cap errors/logs without file bodies, PINs, secrets or private paths.

Use safe MIME allowlists. HTML, SVG, scripts and executables download as
attachments; never execute uploaded active content in TouchHelm's origin. Media
and PDF preview responses use correct Content-Type, nosniff, cache/privacy
headers and disposition. Range requests return correct 206/416/HEAD metadata
without reading the entire file, and stop on revocation or disconnect. A slow
disk or large transfer must not stall typing or pointer movement.

## Visual system and layout

Image target: `docs/design/files-local-target.png`, **853 by 1844 pixels**,
generated for this brief and inspected before implementation. Names, sizes and
transfer progress in the image are illustrative fixtures. Use approximately
393 by 850 CSS pixels for the matching mobile render; it is a design proposal
rather than a product screenshot.
The generated target omits the requested search/sort row and renders file rows
with more separate panel borders than desired. The implementation should add
accessible search/sort and simplify those row borders; these are explicit
corrections to the image, not a claim of exact screenshot reproduction. Use
original authored file-type glyphs rather than reproducing a vendor PDF logo.

Extend the existing seven themes, system typography, mouse mark and safe areas.
The Files material accent is a family of authored sculpted folder/file SVGs:
beveled fronts, paper inserts and restrained directional shadows. No icon-font,
remote font, CDN asset or emoji dependency. This is the one expressive element;
ordinary rows and controls stay quiet.

Light Glass target palette (map to semantic theme tokens in code): Cloud
`#F6F8FC`, Paper `#FFFFFF`, Ink `#17263A`, Slate `#58677C`, Folder blue
`#376BDB`, Local teal `#14675C`. Accent colors on decorative icon materials may
vary by file type. Maintain readable light/dark/increased-contrast themes.

Type: existing Segoe UI/platform system sans; Files heading 28/34 semibold,
section 18/24 semibold, filenames/actions 15/21, supporting 13/18. Text and
breadcrumbs align left. Numbers use tabular numerals; dates/sizes use Intl.

Phone layout, approximately 393 by 852 CSS pixels:

```text
TouchHelm                         PC connected
Files                              Local Wi-Fi
My PC
[ Send to PC                 ] [ Receive    ]
[ Downloads   3D icon ] [ Documents 3D icon ]
[ Pictures    3D icon ] [ Videos    3D icon ]
This PC / Downloads                  Up / View
Search this folder                         Sort
PDF  Travel guide.pdf                  actions
     PDF, size
MP3  Evening mix.mp3                    actions
MP4  Weekend.mp4                        actions
[ transfer name / destination / progress / X ]
Trackpad Files Presenter Media Keyboard Apps Remote
```

Quick access is a compact bento composition, not a page of metric cards. Folder
contents are a list by default, with optional grid. User filenames wrap safely.
Selection introduces a contextual Receive/count bar, without covering the list.
At narrow widths the seven navigation targets retain >=44px touch regions and
can scroll; selection scrolls into view and Files remains near the beginning.
At tablet/desktop widths, locations become a left sidebar and preview a right
pane; file content owns the center. The phone preview takes the full task area
with Back, filename, Receive and native media controls. Preserve browser Back
for folders/preview without discarding a transfer in progress.

Design critique: avoid a cloud-storage dashboard, artificial storage totals,
generic equal icon/title/text cards across the whole page, or heavy decoration
that reduces file density. The bento is only for destinations. Preserve clear
Send/Receive direction, breadcrumbs and the current PC destination at all times.

All interactive controls use semantic elements, visible keyboard focus, labelled
icons, >=44px targets and live progress/error feedback. Keep focus contained in
destination dialogs, return focus on close, respect reduced motion, and avoid
announcing progress every network chunk. Empty, loading, access-off, read-only,
disconnected, no-results, disk-full and unsupported-preview states explain an
action that is actually available.

## Acceptance and verification

1. With internet blocked from first page load, an Android Chrome-class client
   pairs using the PC LAN QR and PIN, browses, uploads, downloads, seeks media,
   and runs PC screen/audio. Record actual phone testing separately from desktop
   Chrome automation; do not claim physical Android verification without it.
2. Verify byte-identical uploads/downloads for empty, Unicode-named, duplicate,
   multipart/chunk-boundary and large files; bounded memory; correct Range/HEAD;
   seek and cancel/retry; no overwrite; cleanup after disconnect/permission revoke.
3. Negative tests cover unauthenticated/public/cross-origin requests, PIN change,
   stale sessions, traversal, UNC/device/ADS names, malicious HTML/SVG, replaced
   symlinks/junctions, denied folders, concurrent duplicates and disk-full.
4. Real synthetic video/audio transport and controls pass over local HTTP with
   no public helper, STUN, TURN or remote HTTP requests. No real private PC screen
   or files are captured for automated tests.
5. Render and exercise Files at 320/393px phone and wide tablet/desktop widths,
   light/dark themes, large text and reduced motion. Compare the main viewport to
   the saved image target, then inspect preview, chooser and transfer/error states.
   Run the requested fresh Web Interface Guidelines review on changed UI files.
6. Existing control, text synchronization, themes, AirControl and desktop native
   permission tests remain green. Adapt expectations narrowly for intentionally
   removed public pairing; preserve historical regression coverage where useful.
7. Packaging smoke checks verify the installed local QR, Files permission, no
   cloudflared payload/download and normal start/stop/uninstall. Building or
   publishing another installer is a subsequent release step, not evidence of
   browser implementation correctness.

## Boundaries and builder decisions

No automatic transcoding, recursive folder downloads, cloud storage, WAN remote
access, phone screen capture, delete/move existing PC files, or silent modification
of the phone's trust store. Windows installer signing remains a separate matter.

The builder chooses endpoint details, chunk/page sizes, bounded worker limits,
SVG geometry and exact adaptive layout within this contract. Proposed limits
must be explicit before claiming support for large files. The user has approved
the local-only approach; the written design and visual target are awaiting review.

Builder review: an independent review agent could not be started in this host.
A self-review tightened the contract for network drives/cloud placeholders,
phone download-location permissions, unsafe active previews, path replacement
races and the distinction between encrypted WebRTC and unencrypted HTTP.
There are no remaining product questions beyond approval of this written design.
