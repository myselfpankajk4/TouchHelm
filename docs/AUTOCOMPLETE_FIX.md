# Inline autocomplete while typing from a phone

Test 4 (Windows version 2.2.0.4) addresses an unaccepted inline suggestion being
copied back into the phone's typing field. For example, after a phone sends `g`,
Chrome may show `google.com` with `oogle.com` selected. The phone should keep `g`
so the next character continues the user's intended text.

The focused Windows text helper now reports optional selection offsets, only
when a single TextPattern selection can be verified against the current field
value. Offsets use UTF-16 units after newline normalization. Unsupported or
inconsistent selection information is omitted.

The text service recognizes a selected suffix only when its unselected prefix
exactly matches a successful phone write to the same field. It returns that
typed prefix while retaining the revision of the actual, complete Windows value.
The next phone edit therefore still uses the existing compare-and-write guard.
Accepting the suggestion, a real PC edit, or changing fields restores normal
full-value synchronization. Empty writes never trigger suffix suppression.
Provider requests and this short-lived context are serialized across clients.
No contents are added to diagnostics or disk storage.

No Chrome autocomplete setting, recovery button or phone certificate change is
required. Providers without accessible selection information retain their prior
behavior; committed form autofill is distinct from a selected inline suggestion.

Verification on 26 October 2026:

- Three new assertions failed against the original service, reproducing immediate
  completion, delayed completion and a Unicode prefix being overwritten.
- All 499 Python regression tests pass after the fix, including seven focused
  text-sync tests and the authenticated text protocol tests.
- Browser logic tests: 118 pass, one existing test skipped, no failures.
- The real Windows PowerShell text bridge compiles and starts with the changed
  native helper.
- The owned Windows scratch-field check passes two-way edits, raw-revision
  preservation, repeated selected completion, accepted completion, stale-write
  rejection, password exclusion and read-only exclusion.
- The phone-sized browser/WebSocket/Windows scratch-field integration passes
  selected completion and acceptance alongside automatic typing-dock opening,
  stale-write recovery and PC/phone editing. Its Windows pipe teardown emitted a
  ConnectionResetError after all assertions passed; the command exited zero.
- Independent review found no concrete blocking issue; whitespace checks pass.

These checks use an owned scratch field to reproduce native selection behavior.
Physical Android Chrome and a history-populated desktop Chrome address bar were
not driven in this pass. Confirm the original scenario with the new build: type
several prefixes from the phone, continue typing while a suffix is highlighted,
accept a suggestion on the PC, and check that Clear and ordinary PC edits still
sync. No unrelated user field or browser history is used by these probes.

## Installed Test 4 build

The installer is 168,192,121 bytes (160.4 MiB), with SHA-256:

```
b2e8606bcd0d5390982a8e5376e1c4be2355924b9e57ed20886decb18714f244
```

At the owner's request, the old installation was checked before replacement;
its uninstaller was already absent. Test 4 was installed through the normal
desktop shell context. That context verified version 2.2.0.4 registration,
uninstaller, desktop and Start shortcuts, both fixed source hashes and preserved
settings. The installed launcher passed all 20 native runtime checks with only
Windows directories in PATH and invalid external Python environment settings.
The normal application window then opened and responded. Its source identity,
API, required PIN and authenticated WebSocket were checked without transmitting
PC input. The test installer remains unsigned.
