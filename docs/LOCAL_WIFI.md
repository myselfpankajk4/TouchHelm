# Local Wi-Fi and Files

Connect the Windows PC and Android phone to the same home Wi-Fi. Open TouchHelm
on the PC, choose **Pair your phone**, scan its local QR in Chrome, and enter the
PC PIN. Pairing, reloading, controls, file transfers, PC screen and PC audio do
not use an internet service. No phone app, VPN or manually trusted certificate
is needed. Mobile data can be off; keep the local Wi-Fi connection on.

The QR opens the PC's private IP address. Windows Firewall must allow TouchHelm
on the private network. Guest-network client isolation can prevent a connection;
use the ordinary home network in that case. Public internet pairing was removed.
No STUN/TURN server, relay or router port-forwarding fallback is configured.

## Browse, preview and transfer

On the PC, open **Pair your phone → File access → Enable File access** once.
This grants PIN-paired local phones access to local files available to the
current Windows user. It does not bypass Windows permissions or elevate the app.
Switch **Settings → File access** off to revoke it. Screen/audio access is a
separate permission and never starts simply because Files is enabled.

On the phone, open **Files**:

- Choose an available quick folder, or **This PC** and a local drive. Folder
  names and drive availability come from Windows. Breadcrumbs return to earlier
  locations. Search looks in the current folder; Name/Newest/Type/Size changes
  the order. Show more files/folders continues a large listing.
- Tap a file to preview it on the phone. Images and supported audio/video have
  inline previews; media supports seeking. PDFs offer one **Open PDF in Chrome**
  action, opening a separate browser tab, plus **Receive** to save a copy. The
  embedded PDF viewer was removed because its extra Open control could lose the
  authenticated session on mobile. Browser codec/PDF support varies;
  **Receive** remains available for opening a file in another phone app.
  Executables, HTML, SVG and unsupported formats download rather than run in
  TouchHelm. Opening a file here never executes it on the PC.
  AAC/ADTS audio (`.aac` and `.adts`) is recognized as browser audio. Supported
  videos and audio can also open in a separate Chrome tab; the inline player
  pauses when you do this. Portrait video fits the visible phone area while
  preserving the full frame and native controls. Receive remains the fallback
  for a codec or AAC variant the phone cannot decode.
- Choose **Send to PC**, select files with Android's picker, choose a PC folder,
  then **Send here**. **New folder** can create a destination. Duplicates receive
  a numbered name; existing files are never overwritten.
- Choose a file's down-arrow, or select several file checkboxes and choose
  **Receive**. Chrome owns the phone's download permission, progress UI and save
  location. TouchHelm reports bytes sent to Chrome, not a claim that Android has
  saved them successfully. Chrome can ask permission for multiple downloads.
- Transfers show a mini progress strip by default. Tap it to expand file names,
  direction, detailed progress, cancellation, Retry and history; tap again to
  collapse. New progress does not open it automatically. The strip prioritizes
  an actively sending/receiving file over a delayed Chrome download. A retry
  starts the interrupted file again; there is no silent replay on reconnect.

Uploads use 1 MiB chunks and downloads use at most 256 KiB per disk read. Files
are not loaded as one large phone-memory blob. Limits are 16 GiB per file, 32
files per phone selection and pending phone queue, two active uploads per file
session (the interface sends sequentially), eight uploads globally, four preview/download responses per
session and eight globally. Receive requests also queue individually so Chrome
is not flooded with concurrent downloads. File sessions expire after 30 minutes; reconnect
before a long transfer if needed. Directory pages contain at most 200 entries;
a scan stops at 50,000 entries with a visible smaller-folder suggestion.

Cloud-only placeholders explain that they must be made available offline on the
PC first. TouchHelm does not hydrate them using internet. Network shares, device
paths, alternate streams and reparse-point redirects are not accepted. A folder
that Windows denies or that disappears must be selected again after recovery.
An unavailable entry no longer prevents the rest of its folder from loading.

## Listen to PC audio

Enable **Screen and audio access** on the PC, then switch on **PC audio** in
Media or Remote on the phone. Playback starts after the PC confirms the stream;
there is no routine second Unmute step. If Chrome blocks audible playback,
**Unmute** appears as a retry. The phone receives the current Windows output
device's loopback audio; that output must be playing something to hear sound.

## Connection properties

This mode serves the phone page, control commands and files over **local HTTP**.
They are not protected by TLS; home Wi-Fi is a deployment assumption, not an
end-to-end security guarantee. PC screen/audio are encrypted by WebRTC. The
server checks the actual LAN peer, destination Host and Origin, requires PIN
authentication, and keeps Files behind a separate native permission. File
cookies are short lived, HttpOnly and bound to the live authenticated socket;
writes also require a CSRF token. Native revocation or disconnect ends transfers.

Chrome may suspend the page when the phone locks or the app is backgrounded. Set a longer phone screen timeout if needed; this can interrupt
transfers/media. Return to Chrome and reconnect/retry.

No certificate is needed. If an older TouchHelm phone CA is still installed, remove only that
matching user certificate in the phone's credential settings.

See [verification and limits](FILES_LOCAL_VERIFICATION.md).
