# TouchHelm desktop redesign V2

## Plan before implementation

The previous pass retained website structure: two large welcome cards, a tall QR
card with its PIN below the fold, and a competing trusted-setup card. Fluent-like
radii did not fix that hierarchy. This pass changes the information architecture
to a compact Windows utility and keeps pairing's three real objects together.

Reference palette (Glass dark; derived from each active theme): Window `#0b1929`,
Group `#12283b`, Control `#1a344a`, Text `#eef8fc`, Secondary `#b0c8d8`, Accent
`#8cdef4`. Seven themes and both appearances stay authoritative. Neutral layers
use the active theme's background/panel values; accent is reserved for a primary
action, selection or live control state.

Type: Segoe UI Variable Text/Display with Segoe UI and system fallbacks. Page
titles 26–28px, group titles 16px, controls/body 13–14px, supporting text 12px.
Spacing: 4/8/12/16/24/32px. Windows-like 6px controls, 10px grouped surfaces.

```text
compact app title / host state                         tray / change mode
navigation | Pair your phone
           | connection mode
           | [real QR]   phone address / copy / open
           |             pairing PIN / security state
           | > trusted HTTPS or selected setup instructions
```

Welcome becomes a task list with two large, clearly described mode rows. Settings
become grouped, aligned label/control rows; devices remain a real table with
activity subordinate. At narrower desktop widths the navigation becomes an icon
rail, giving QR/address/PIN and AirControl more room. AirControl uses a compact
session bar, small workflow breadcrumb, broad stage and a quiet action column.

Pre-build critique: “more cards” would repeat the failed direction. Use one
primary pairing group, disclosures for advanced setup, and content-led native
rows elsewhere. Keep the QR, PIN and stage truthful, all IDs/features intact,
44px targets, visible focus and reduced-motion behavior. Do not interpolate
theme backgrounds independently of text because that creates transient contrast
failures during appearance changes.

## Implementation and critique

Pairing is now one horizontal task group: a real QR on the left, address/actions
and an aligned PIN/security row on the right. The default trusted-HTTPS offer is
a quiet closed disclosure. Selected HTTPS modes expose their main actions, with
long installation instructions in separate disclosures. All original buttons,
IDs, guides and setup states remain available.

The welcome screen is a native task list with two mode rows and compact original
artwork, rather than two equal presentation cards. A Home destination and an
accessible, labelled icon rail make navigation consistent. Settings use aligned
label/control rows in native groups. Device identity remains the primary table,
with activity in a subordinate log. AirControl shares the same shell, uses a
compact workflow breadcrumb, an uncluttered stage sized for the available window,
and legible two-column dwell actions. Its escape controls remain persistent.

Visual review removed repeated PIN instructions from the main visual hierarchy
by aligning the PIN beside its security label, and reduced the stage height so
camera permissions/recenter/dictation actions remain visible at 1120×800. It
also fixed the empty-stage camera icon's inherited 20px height. No camera imagery
or invented device state was used for the visual design.

## Verification

- Existing isolated preview tests: 4/4 initial desktop/navigation/target-size
  checks passed; the full AirControl selection passed 18/18, including all seven
  themes, both appearances, keyboard reflow, reduced motion and accessibility.
- An injected preview-only review using the existing test harness checked Home,
  Pairing, Devices, Settings and Diagnostics at 820×620 and 1120×800 across all
  14 theme/appearance combinations: no horizontal overflow, clipped controls or
  sub-44px action targets. Axe found no serious/critical issues on those five
  redesigned pages in Glass light/dark. Evidence: `tests/artifacts/desktop-v2-review.json`.
- A real QR generated for the reserved documentation address
  `http://192.0.2.10:8765/` and synthetic PIN `2468` were supplied only to the
  browser fixture. QR, address, Copy, Open and PIN bounds passed above-fold checks
  at both target sizes for every theme/appearance. The trusted disclosure was
  exercised and its setup action remained reachable. Evidence:
  `tests/artifacts/desktop-v2-fold.json`.
- Inspected dark/light pairing at both sizes, welcome, settings, devices and
  AirControl screenshots. Representative images:
  `tests/artifacts/desktop-v2-dark-pairing-1120.png`,
  `tests/artifacts/desktop-v2-dark-pairing-820.png`,
  `tests/artifacts/desktop-v2-light-pairing-820.png`,
  `tests/artifacts/desktop-v2-dark-home.png`,
  `tests/artifacts/desktop-v2-dark-settings.png`,
  `tests/artifacts/desktop-v2-dark-aircontrol.png`.

These checks use isolated synthetic browser data. Native camera/input behavior,
real pairing/network state and packaged WebView2 startup are outside this UI
verification. Existing long saved pairing passwords can wrap and require more
vertical space than the default four-digit PIN. No native app was launched; no
phone, runtime, packaging, protocol, dependency or existing test files were edited.
