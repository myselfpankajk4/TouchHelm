# Test 9 — folder access, PDFs and PC audio

Reported on 28 October 2026 after testing the local Files interface.

## Changes

- Downloads could fail as a whole when one ordinary file carried Windows
  extended attributes. `0x40000` means EA in stat/handle metadata, but
  RECALL_ON_OPEN in directory enumeration. The check now uses the metadata
  source correctly. Offline and recall-on-data-access items remain blocked,
  along with directory-enumerated recall-on-open placeholders. Directory
  leases, reparse restrictions, identity checks and no-recall handles remain.
  A child that loses access during enumeration is disabled individually.
- PDFs use one **Open PDF in Chrome** link to the existing authenticated
  endpoint and retain **Receive**. Removing the embedded viewer removes its
  extra Open control; file-cookie and PIN requirements have not been weakened.
- PC audio switches now request audible playback after host confirmation.
  Unmute is a fallback when Chrome blocks playback. Stale play callbacks cannot
  alter a replacement session or override a newer playback attempt.

Attribute definitions: [Microsoft file attributes](https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants).
Playback behavior: [Chrome autoplay policy](https://developer.chrome.com/blog/autoplay).

## Verification

The new regressions first reproduced the metadata exception, folder-wide
failure, duplicate PDF controls and muted confirmed-audio state. They pass
after the fixes. Metadata-only checks on this PC now list all six known folders
and both local drives, including Downloads; no personal file contents were read.

Local HTTP Chrome integration passes with external requests blocked. It checks
PDF authentication and bytes, byte-exact duplicate uploads/downloads, folder
creation, cancellation, local screen video and non-zero received audio energy
with playback unmuted after the Media switch is tapped. Generated media is used
instead of capturing the PC in this integration test.

A separate native Windows check played a brief generated 440 Hz WAV and detected
that tone through the actual WASAPI loopback and AudioNormalizer. Only detection
booleans were recorded; captured PC audio was not saved.

Physical Android speaker output and Chrome's device-specific PDF rendering still
need the user's acceptance test. The earlier Test 8 evidence remains recorded
separately in FILES_LOCAL_VERIFICATION.md.

Source verification:

- Full Python suite: **579 passed**. An initial concurrent run hit the existing
  restart-handoff fixture's 20 ms deadline; that module passed in isolation and
  the full suite then passed without concurrent browser load.
- Phone browser behavior: **93/93 passed**; the PDF layout was also captured and
  inspected at the mobile test viewport.
- `npm test`: **122 passed, one optional skip**.
- Desktop/local-network tests: **12 passed, one optional visual skip**.
- Independent read-only review found no blocking defects in the bugfix diff.

Installer and installed-copy results are added after the build completes.
