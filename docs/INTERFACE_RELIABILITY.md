# TouchHelm interface and typing repair

Design brief: a phone held in one hand controls a Windows PC. Preserve the seven
materials, local preferences, real provider state and large movement area. Repair
two-way typing without replaying saved drafts or editing a newly focused app.

## Design direction

The control surface is the distinctive object. Keep the surrounding navigation
quiet; use grouped controls rather than a dashboard of interchangeable cards.

Reference palette (the existing materials remain authoritative): deep blue
`#0b1929`, panel `#12283b`, control `#1a344a`, text `#eef8fc`, muted
`#b0c8d8`, action `#8cdef4`. Segoe UI/system typography remains local and fast;
25px task titles, 16px body/input, 13px controls, 12px supporting text. Numeric
readouts use tabular figures. All reading and form content is left aligned.

Two layouts considered:

```text
Chosen: movement first           Rejected: always-open editor
+----------------------+         +----------------------+
| Brand   Connection   |         | Brand   Connection   |
| Trackpad             |         | Type + settings      |
|                      |         | Large editor         |
|    Movement area     |         | Sync settings        |
|                      |         | Small movement area  |
| Mouse controls       |         | Mouse controls       |
| Type + sync status   |         | Navigation           |
| Navigation           |         +----------------------+
+----------------------+
```

The chosen layout keeps typing expandable and its status visible when collapsed.
Presenter prioritizes the current deck and next slide. Media groups playback and
system levels. Keyboard uses physical-key hierarchy. Apps uses searchable rows.
Remote mode choices become columns only where there is space. Desktop pairs a
quiet navigation rail with a clear task heading and grouped form sections.

Self-review: preserve the product's system font and theme-specific character;
avoid adding a new decorative palette or marketing hero. Spend visual emphasis
on the touch surface and primary action. Use borders for input/control boundaries,
spacing for section grouping, and focus rings for keyboard location.

## Confirmed defects

- Temporary loss of an editable PC target left clean text permanently conflicted.
- A write acknowledgement during IME composition did not advance the revision.
- Explicit Send from a paused linked draft left live typing paused and could
  press Enter unexpectedly.
- Hiding or switching away discarded the field guard while retaining its native
  diff baseline.
- An initial read timeout disabled otherwise available native typing.
- A read racing phone input retained the draft without offering PC-text recovery.
- The focusable trackpad did not have keyboard movement/click alternatives.

Regression checks cover each transition, preserve concurrent drafts, and keep
password/read-only fields excluded. Verification results are recorded after QA.

## Verification — 20 October 2026

- Python discovery: 469 passed.
- JavaScript unit suites: 99 passed, one optional browser-DOM test skipped.
- Browser interaction suite: 82 existing scenarios passed. Three new text recovery
  scenarios passed; eight focused text scenarios were repeated after final review.
- Visual/contrast/target checks: all seven themes, both appearances, six phone and
  desktop viewport sizes; desktop pairing, settings, devices and diagnostics.
- AirControl desktop scaling and accessibility matrices passed, including seven
  themes and both appearances.
- Windows scratch field: PC readback, phone multiline/emoji write, stale revision
  rejection, password exclusion and read-only exclusion passed.
- Independent code review found a repeated-suspension edge case. A regression
  reproduced it; the fix and clean/dirty lifecycle checks pass. Re-review found no
  remaining blockers. `git diff --check` passed.

Fresh Web Interface Guidelines were fetched from the Vercel source and applied to
the edited surfaces. Focus states, labelled controls, reduced motion, safe areas,
local font loading and 44px targets were retained. Added skip links and keyboard
trackpad input; gave the app mark intrinsic dimensions and bounded typing to the
protocol's 10,000-character limit.

Physical phone keyboard/network testing and compatibility with every Windows app
were not performed. Two-way reading still requires a host PIN and a supported,
editable, non-protected field. Native fallback remains available for unsupported
fields; concurrent or uncertain drafts require explicit recovery.

## Follow-up: automatic focused-field typing

The user reported that manual recovery still blocked normal use and asked for the
phone typing area to open when a PC field is selected. This supersedes the manual
conflict recovery described above.

- Removed Use PC text. Ordinary reads, rejected revisions, temporary focus loss
  and write timeouts automatically reconcile against current PC text.
- Independent edits merge as bounded Unicode-aware diff hunks. Overlapping edits
  and major rewrites follow the PC. A newly selected field always supplies its
  own text; edits from the previous field are not replayed into it.
- The host reports a committed write ID only to its requesting client and only
  for that field. Recovery can distinguish a committed edit from an unsent edit,
  preventing duplicate text after a dropped acknowledgement.
- PC field detection expands/focuses the typing dock once per focus transition.
  A remote mouse click requests a fresh read. Done remains respected until a new
  focus transition or click. Open settings retain focus. Mobile Chrome controls
  whether asynchronous focus also displays its system keyboard.
- Live-off buffered Send automatically retries a stale revision or timeout without
  sending Enter to another field. PC reading still honors the device opt-out.
- Active pages check the source build every 15 seconds, pausing update checks
  during composition and in-flight writes.

Follow-up verification: 470 Python tests and 111 JavaScript tests passed, with one
optional JavaScript DOM test skipped. The 24 focused text tests include failure
recovery, concurrent edits, IME, automatic opening and lost acknowledgements.
The native browser/WS/UIA probe is opt-in at
`node tests/native_text_browser_check.cjs`. This run explicitly skipped that probe
because Windows refused foreground activation of its owned scratch form. It did
not verify physical Android Chrome keyboard behavior.

Clear follow-up: Clear now writes an empty value to the linked PC field instead
of resetting only the phone baseline. It waits behind in-flight reads/writes,
retries the same field after revision rejection, and cancels on a different field.
Typing after Clear is retained; Live-off typing remains buffered. Seven new
regression cases and a browser button-click scenario cover the change. JavaScript
suite: 118 passed, one optional DOM test skipped.

Release verification: the complete browser suite now passes 104/104, Python
478/478, and JavaScript 118 with one optional skip. The compact trackpad layout
retains its movement area across all five tested phone viewports. See
[portable verification](PORTABLE_VERIFICATION.md) for the final EXE smoke evidence
and the [desktop review](DESKTOP_FLUENT_REVIEW.md) for Fluent design decisions.
