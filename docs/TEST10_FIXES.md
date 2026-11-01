# Test 10 — compact transfers and phone media playback

Reported on 28 October 2026 after local phone/PC file-transfer testing.

## Changes and reproduced causes

- The current transfer row was outside the history disclosure, leaving its
  details permanently visible. All rows now live inside native `<details>`.
  The collapsed view is a compact label, percentage and progress bar; tapping
  reveals names, directions, controls and history. Updates preserve its open
  state and keyboard focus. Active transfers take priority over delayed Chrome
  downloads in the mini strip.
- Chrome's separate media document was blocked by the file response's
  `default-src 'none'` policy. A real Chrome popup reproduced the resulting CSP
  violation and broken player. Only inline audio/video responses now permit
  `media-src 'self'`; default sources and scripts remain denied, downloads and
  unsupported content retain the stricter policy, and cookie/PIN/Origin/LAN
  requirements are unchanged. Opening Chrome pauses the inline player.
- The portrait video extended roughly 60 px below its flex-shrunk preview body.
  Preventing body shrink fixed that crop, but short screens still placed
  controls below the navigation. Video now fits the visible area, preserving
  its frame with `object-fit: contain`. It recalculates for metadata, viewport
  changes, transfers and history expansion/collapse. Measurement starts from the
  CSS size so collapsing history restores the player. Opening a new preview
  resets the folder's scroll position; both player edges are tested.
- `.aac` was classified as an unsupported download. AAC/ADTS (`.aac`, `.adts`)
  now uses `audio/aac`, the audio preview and the Chrome-open link. Native phone
  codec limitations still use Receive as a fallback; this adds no transcoder,
  cloud service or mobile download.

Format references: [Chromium's AAC/ADTS mapping](https://chromium.googlesource.com/chromium/src/+/master/media/base/mime_util_internal.cc),
[Android supported audio formats](https://developer.android.com/media/platform/supported-formats).

## Verification

Regressions first failed for the permanent row, AAC classification, restrictive
media response, portrait crop, off-screen controls, retained folder scroll,
history-toggle resizing and delayed-download progress priority. Focused checks
pass after the fixes.

The local HTTP integration uses generated landscape/portrait H.264 MP4 and ADTS
AAC files, a real Chrome instance, authenticated file endpoints and blocked
external requests. It checks playback in both inline and separate Chrome
players, viewport/container bounds at 393×850, 320×568 and 844×390, previews from
a scrolled folder, transfers, cancellation and compact progress. Screenshots
were inspected, including the short portrait screen and active mini strip.
Saved examples: [mini transfer strip](design/files-transfer-mini.png) and
[short-screen portrait player](design/files-portrait-short.png).

Full Python verification: **581 passed**. `npm test`: **122 passed, one optional
skip**. A fresh read-only review found the delayed-download priority and
history-toggle cases; both received failing regressions and fixes. Its final
delta review found no remaining actionable issue.

Final browser behavior verification: **96/96 passed**. Local HTTP integration
passed every reported check, including video/AAC playback in separate Chrome
tabs and a collapsed transfer strip at most 72 px tall. Files accessibility:
**zero violations across all 14 theme/appearance combinations**. The reviewer
checked the final sizing and toggle corrections with no remaining actionable
finding.

## Installer verification

- File: `dist/TouchHelm-2.2.0-test10-setup-win-x64.exe`.
- Size: **168,241,922 bytes**; SHA-256:
  `b2c7ec2afd7816e9ff229d32d064a33a04df1a8187420494e2ec10ed52d944b6`.
  The finished installer matches its manifest.
- Exact packaged source/runtime: **37 Files/HTTP/local-mode tests passed**.
- Packaged launcher: **20 native self-test checks passed**, with only Windows
  on PATH and deliberately invalid Python environment paths. The bundled Python,
  camera models, WebView2 execution and Tk fallback work; no public pairing
  helper is included. Server and Files UI source hashes match the tested tree.

The normal desktop installer successfully upgraded the existing copy to
**2.2.0.10**. Windows registration, uninstaller and desktop/Start shortcuts are
present. The final pre-install settings file was preserved byte for byte.
Installed server and Files UI hashes match the tested sources. The reopened
window responds, and the installed-source identity, local API and
PIN-authenticated WebSocket checks all pass.

Physical Android Chrome codec/native-control acceptance still requires the
user's device test. This remains an unsigned test installer.
