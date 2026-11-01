# Desktop Fluent review

## Design plan, before implementation

TouchHelm is a Windows control center: pairing should lead with the actual QR,
and AirControl should lead with its live movement/practice stage. The surrounding
chrome should feel like a calm Windows 11 utility.

- Palette reference (Glass dark): Midnight `#0b1929`, Panel `#12283b`, Control
  `#1a344a`, Ice `#eef8fc`, Mist `#b0c8d8`, Signal `#8cdef4`. All seven existing
  theme palettes remain authoritative; desktop layers and strokes derive from
  their semantic tokens rather than replacing their colors.
- Type: Segoe UI Variable, then Segoe UI/system sans. 28px page title, 18px
  section title, 14px body/control text, 12px supporting context. Left aligned.
- Layout: compact app header over a quiet navigation rail and one inset workspace.
  Selected navigation uses a short vertical accent marker. Pairing puts a large
  real QR and address together, with setup guidance beside it. AirControl keeps
  persistent escape actions above the dominant stage and a narrow coaching rail.

```text
mouse mark / TouchHelm                 host status / tray / mode
navigation       | inset workspace
selected marker  | title / useful context
                 | QR + address       | selected setup guide
                 | PIN / security     | supporting actions
```

Self-review against the brief: avoid a marketing hero, generic metric cards,
decorative gradients, repeated panel shadows, or a whole-screen redesign. The
distinctive elements are TouchHelm's mouse mark, real pairing QR and interactive
AirControl stage. Use Windows-like layering, restrained 6/10/12px radii and short
action feedback; retain 44px targets, visible focus, reduced motion and all theme
choices. Consolidate the duplicated desktop CSS instead of adding another layer
of contradictory overrides.

## Implementation and self-review

The app header and navigation now share a calm base layer, around a single inset
workspace. Theme-derived strokes replace the repeated strong card outlines;
panel/control radii distinguish their roles. The original mouse mark remains.
Pairing has a named QR area, with its address/actions and security directly below
or alongside at narrow widths. An unavailable QR retains the actual setup state.
AirControl retains its dominant stage, persistent escape controls and narrow
coaching rail. Its tabs use short selection markers. The chooser has quieter
artwork wells and no decorative diagonal arrows or looping hover animation.

The desktop stylesheet was consolidated into base/component/responsive rules.
Scoped geometry wins over shared material rules, while all seven semantic theme
palettes and their high-contrast values remain available. Review removed the
decorative navigation backdrop to keep the rail useful and quiet.

## Verification

- Existing isolated browser preview suite: 19 desktop/AirControl behavior,
  interaction, layout and scaling checks passed. The accessibility check initially
  caught a transient contrast problem during immediate light-to-dark theme
  changes: background interpolation lagged behind text color. Background color
  interpolation was removed; the isolated accessibility rerun passed, covering
  session states and all seven themes in both appearances.
- Final focused visual rerun passed 3/3: selected HTTPS pairing guides, keyboard
  tabs/200% equivalent reflow, and the AirControl theme/scaling matrix (820×620,
  1120×800 and 1440×900). Targets remain at least 44px and no page overflow was
  reported. Reduced-motion checks passed.
- Inspected generated pairing, chooser, AirControl session/head-action and narrow
  reflow screenshots. Final light/dark Glass snapshots use the same preview harness.
- `git diff --check` passed for the changed desktop sources and this review.

The preview uses sample connection data and no live webcam or native input.
Actual QR generation, camera recognition and packaged WebView2 startup are not
established by these UI checks. No protocol/runtime or phone files were changed.
