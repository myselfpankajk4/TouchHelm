---
name: TouchHelm control console
description: A compact phone remote with large movement space, real desktop context, and tactile native controls.
colors:
  primary: "#72d8e6"
  primary-contrast: "#06131a"
  background: "#0b131b"
  card: "#121f2a"
  card-hover: "#203342"
  surface: "#1a2a37"
  text: "#eef7fa"
  text-muted: "#b4c8d2"
  text-dim: "#9fb8c6"
  border: "#344957"
  danger: "#ff8aa1"
  oled-background: "#000000"
  oled-primary: "#38bdf8"
  oled-muted: "#c0c0c8"
  matrix-background: "#050c08"
  matrix-primary: "#00ff66"
  matrix-muted: "#b2d9c2"
  nordic-background: "#0b1120"
  nordic-primary: "#60a5fa"
  nordic-muted: "#afc0d3"
  light-background: "#f8fafc"
  light-primary: "#1d4ed8"
  light-text: "#0f172a"
  light-muted: "#475569"
  light-danger: "#b91c1c"
  desktop-background: "#111722"
  desktop-card: "#192230"
  desktop-border: "#3b4b62"
  desktop-primary: "#86b7fb"
  desktop-text: "#f0f6fc"
  desktop-muted: "#b5c1d2"
typography:
  body:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    fontSize: "16px"
  context-title:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    fontSize: "25px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.5px"
  section-title:
    fontSize: "22px"
    fontWeight: 600
    letterSpacing: "-0.4px"
  action:
    fontSize: "14px"
    fontWeight: 600
  nav-label:
    fontSize: "11px"
    fontWeight: 500
rounded:
  key: "7px"
  control: "8px"
  field: "9px"
  dock: "12px"
  dialog: "15px"
  touch-surface: "16px"
spacing:
  key-gap: "4px"
  toolbar-gap: "6px"
  control-gap: "8px"
  page: "14px"
  section-gap: "16px"
  wide-page: "22px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-contrast}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
    typography: "{typography.action}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  touch-surface:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.touch-surface}"
  native-key:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.key}"
    height: "44px"
  native-key-held:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-contrast}"
    rounded: "{rounded.key}"
    height: "44px"
---

# Design System: TouchHelm

## Overview

The approved direction is a compact control console: slate surfaces, clear context, and precise accent states. Large usable movement space and readable task feedback take priority. The mouse mark and five themes preserve TouchHelm's identity; controls use system typography and native semantics.

This is an operating interface. The phone uses compact toolbars, contextual titles, and broad touch surfaces. The Tk desktop groups QR pairing, security, device status, and secondary activity in a restrained dark panel. Product flows and capabilities are recorded in PRODUCT.md; these tokens describe their visual expression.

## Colors

The frontmatter records actual values from `web/ui.css`, resolved over `web/style.css`, and desktop constants in `gui/app_window.py`. The phone CSS custom properties are the implementation source of truth. Cyber uses a pale cyan action accent on blue-black surfaces. OLED retains black and azure; Matrix green; Nordic slate and blue; Solarized Studio light surfaces and deep blue.

Primary indicates selected navigation, prominent actions, pressed keys, and focused controls. Main, muted, and dim text separate context from supporting labels without making essential information decorative. Danger marks destructive actions and persistent save failures. Alternate themes retain the same hierarchy and their own contrast color.

## Typography

Use Segoe UI followed by platform system sans fallbacks; no remote font dependency. Context titles carry the greatest emphasis, followed by section titles, body/control text, supporting labels, and compact navigation labels. Long app, deck, artist, and catalog names wrap. Timer and timeline values use tabular numerals. Avoid artificial uppercase telemetry or decorative type competing with a task.

## Layout

The phone shell follows the visual viewport and safe-area insets, with a maximum width of 980px. Header height is 56px; bottom navigation is 60px. Task pages scroll within the shell. The five destinations are Trackpad, Presenter, Media, Keyboard, and Apps; Keyboard contains its Numpad segment.

Trackpad uses a flexible movement surface, a slim 44px click strip, and a collapsed single-line typing dock. Expanded typing exposes actions and an auto-sized field up to 176px high. At viewport heights of 560px or below, hints shrink and the expanded dock suppresses the click strip to keep composition reachable.

At 700px width, Media becomes two columns and Apps uses a two-column catalog; Presenter and Keyboard cap content at 760px. Below 359px, header spacing tightens and nonessential latency text hides. Desktop starts at 880×700 with an 820×620 minimum; pairing and settings adapt within that window.

## Elevation & Depth

Tonal surfaces and thin borders establish depth. Movement surfaces, ordinary controls, dialogs, and transient feedback have no shadow in the console overrides. Transient feedback uses a solid card surface and state border near the top of the task area. The modal backdrop is a plain translucent black overlay without blur. Reduced-motion preference removes transitions and animation; navigation state transitions otherwise take 150ms.

## Shapes

Controls use gently rounded corners, with smaller radii for dense keys and larger radii for movement areas and dialogs. Keep the control silhouette compact and consistent. Laser space uses a dashed border to distinguish its task from pointer movement. Preserve a minimum 44px command target even where the visible glyph is smaller.

## Components

- **Buttons:** solid accent for primary actions, tonal secondary controls, quiet icon/text actions. Disabled remote controls use reduced opacity; held keys use the accent fill and contrast text. Focus-visible uses a 2px accent outline offset by 3px.
- **Navigation:** five equal destinations with icon and label. Selected state combines accent text, a tonal background, and semantic selection state.
- **Typing dock:** rounded bordered surface, compact at rest, expanding on focus. Send/Enter is primary; Clear and Done are secondary. Collapsing preserves the text.
- **Touch marker:** hidden at rest; a restrained accent circle appears only during active touch.
- **Disclosures:** Timer, extended keyboard groups, and shortcuts have explicit trailing chevrons that reverse when open. Preserve visible collapsed/open affordances alongside the 44px summary target.
- **Context and catalogs:** title/status precede commands; list rows use dividers, wrapping names, and secondary detail. Unknown values and empty/loading/error messages occupy real layout space.
- **Dialogs:** bounded 460px width and viewport-safe height; 44px close/action controls, labelled fields, contained focus, and return focus. PIN remains required until authentication succeeds.
- **Feedback:** transient status is distinct from socket status; unsaved settings have a persistent inline warning. Desktop Copy URL feedback stays inline; device rows and activity preserve stable identity and scrolling.

## Do's and Don'ts

- Do preserve movement space, 44px actions, readable contrast, visible focus, safe areas, and reduced motion in every theme.
- Do use real titles, capability messages, and explicit unknown values in context views.
- Do show press/latch and disabled states consistently; keep local drafts, navigation, and timer accessible offline.
- Don't expand decoration, glows, simulated telemetry, or empty cards at the expense of task controls.
- Don't manufacture slide counts, playlists, successful saves, or ready connection states.
- Don't introduce a second Windows Start button or move ordinary typing out of Trackpad.
