# Generative themes

Release `TouchHelm-2.2.0-setup-win-x64.exe` (version `2.2.0`, unsigned).

## What changed

- Seven image/CSS themes were replaced by five: **Aurora** (default), **Bloom**, **Resonance**,
  **Constellation** and **Ink**. Each has light, dark and increased-contrast treatment.
- Aurora, Bloom, Resonance and Constellation render a full-screen WebGL1 fragment shader
  (`web/theme-scenes.js`, engine in `web/theme-gl.js`, canvas styles in `web/theme-gl.css`).
  Raw WebGL was kept over three.js: the themes are 2D shader fields, the app is offline and
  three.js would add roughly 600 KB for no benefit.
- The field reacts to touch position and timing: the trackpad, keys, buttons, sliders, tabs,
  the text box and player state. Typed text and input values are never read. The canvas
  ignores pointer events and is `aria-hidden`.
- Quality adapts: render scale drops when frames run long, stamp slots scale with the GPU's
  uniform budget (4/8/12), the loop idles when nothing is happening and stops while the page is
  hidden. System reduced motion renders one frozen frame; Effects Off and Ink use no GL.
- Legacy ids migrate: cyber/glass → Aurora dark, light → Aurora light, oled/nordic →
  Constellation dark, soft → Constellation light, matrix → Bloom dark, clay → Bloom light,
  companion → Resonance light.
- Removed: `web/theme-effects.*`, `web/themes/{clay,companion,glass,soft}.css`, bitmap theme
  backdrops and `assets/theme`. The installer now deletes these from an existing install.

## Verification

- `node --test` theme suites, including a browser test that compiles every scene in light and
  dark, reacts, pauses, freezes under reduced motion and tears down cleanly.
- Python suites that exercise themes, desktop preview, config validation and the installer.
- Looked at all five themes, light and dark, at phone width in the built-in browser; a drag
  produced a stamp.
- Installed build ran `TouchHelm.exe --self-test`: all checks true.

## Known gaps

- Shader performance was measured under software and desktop GL only. Check frame feel on a
  real phone; Calm or Off in Settings lowers the cost.
- `tests/test_web_client.cjs` "living visual matrix" and "Text sync and pairing guides" fail
  identically on the previous commit (selector ambiguity on the Pair button), so the theme
  matrix inside that test does not run to completion.
- The `--visual` batch in `tests/themes.test.cjs` still points at the removed
  `assets/theme/review` fixture.
