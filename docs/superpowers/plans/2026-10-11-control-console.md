# TouchHelm Control Console Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the coordinated task sequence and superpowers:dispatching-parallel-agents for independent Windows providers, native feedback, and phone UI files. User approved implementation without further design or plan check-ins.

**Goal:** Deliver the approved remote redesign and Windows context/app controls, keeping existing safe input and pairing behavior.

**Architecture:** Asynchronous DesktopServices supplies context and catalog commands, separate from native key/volume feedback. TouchHelmControls owns the new controls; app.js and web_server.py connect them over authenticated messages. Content-derived versioning keeps browsers current.

**Tech stack:** Python/aiohttp/Tkinter/ctypes, Windows PowerShell COM/WinRT, plain HTML/CSS/JavaScript, unittest/Node/Playwright.

**Spec:** ../specs/2026-10-11-control-console.md

## Global constraints

- Five phone tabs; Numpad inside Keyboard; Windows Start only in Keyboard.
- 44px touch targets and readable contrast across all five existing themes.
- Never fabricate playlist/presentation data; adapters report capabilities.
- Native actions remain mocked in tests. No unsolicited launches or real input during QA.
- Slow provider calls never block pointer traffic; only authenticated clients receive desktop state/catalogs.
- There is no Git repository; leave reviewable workspace files rather than attempting commits/worktrees.

## Review focus

- Multi-touch chords, sticky modifiers, pointer cancellation and disconnect cannot leave held keys.
- A failed or hung app/media provider cannot stall cursor traffic or turn the entire server offline.
- Catalog IDs cannot be forged into arbitrary executables, commands, or paths.
- Old service workers and HTTP caches must load the current build without erasing a draft.
- Timer reset/pause/background throttling cannot affect subsequent presentation commands.

## Task 1: Windows providers

Files: create server/desktop_services.py, server/desktop_bridge.ps1, tests/test_desktop_services.py. Interface is the DesktopServices contract in the spec.

- [x] Add failing tests for catalog ID validation, real launch-frequency sorting/persistence, explicit missing-provider states, and bounded helper failure.
- [x] Verify red, then implement lazy bridge/provider methods and a bounded local media catalog.
- [x] Probe only read-only snapshot/apps/media queries on this Windows machine; report actual provider availability.
- [x] Run focused tests and inspect helper cleanup.

Provider evidence: 15 focused tests passed; read-only Windows probe found 115 apps and no active media session/presenter. Native effects were mocked. Stable selection IDs, cancellation before queued native writes, and nonrecursive all-session snapshot metadata have focused regressions.

## Task 2: Native keys and desktop feedback

Files: modify server/windows_input.py; create server/osd_overlay.py and tests/test_native_controls.py. Existing native method signatures stay compatible.

- [x] Add failing tests for volume media-key dispatch, exact set feedback, brightness feedback, OEM punctuation/function/numpad mappings, and helper ownership cleanup.
- [x] Implement native flyout-triggering up/down/mute, focus-preserving feedback for absolute values/brightness, and correct physical key mapping.
- [x] Verify all native effects remain mocked in the tests.

## Task 3: Phone surfaces and independent controls

Files: modify web/index.html/web/ui.css; create web/controls.js and tests/controls_logic.test.cjs. Keep existing IDs for remote/timer/PIN/settings controls.

- [x] Add failing tests for true press/release and latched modifier chords, release-all safety, draft-preserving collapse, and safe search/catalog rendering.
- [x] Build the five-tab layout, spacious pad/expanding typing, context-first Presenter/Media, full Keyboard/Numpad, Apps and all interface methods in the spec.
- [x] Test new logic; leave full screenshots to the coordinated verification batch.

## Task 4: Server/client integration, timer, current builds

Files: modify server/web_server.py/web/app.js/web/sw.js/gui/app_window.py; create server/build_version.py; extend safe server/browser tests.

- [x] Add failing tests for unauthorized/forged commands, nonblocking queries, context delivery, timer reset/resume/deadline behavior, and version revalidation.
- [x] Integrate DesktopServices and TouchHelmControls with the spec's exact messages; preserve existing socket/config/draft protections.
- [x] Add content-derived build ID, no-store headers, QR version, browser version check/draft restoration, and service-worker cache bypass/update.
- [x] Use deadline-based local timer and verify reset with subsequent slide packets in the real DOM.

## Task 5: Verification and handoff

Files: update tests/test_web_client.cjs, tests/desktop_preview.py, README.md, BUGFIX_REPORT.md, DESIGN.md, PRODUCT.md and .impeccable/design.json.

- [x] Run full safe Python and JavaScript suites; adapt meaningful existing browser tests to Numpad inside Keyboard and Apps.
- [x] Inspect normal/minimum desktop and all phone tabs, populated dynamic states, reduced viewport and themes in one batch.
- [x] Fix observed material defects in one batch and run one confirmation; any unresolved issue is explicit.
- [x] Use fresh review as required by the design skill, then document actual capabilities and evidence.

Documentation complete: README.md and BUGFIX_REPORT.md describe actual provider/native capabilities and live-device limits; PRODUCT.md records approved behavior; DESIGN.md and .impeccable/design.json capture implemented tokens. Fresh verification passed 80 Python tests, 49 JavaScript tests, 38 real-DOM browser scenarios, and four transparent Tk pairing/settings previews. The explicit disclosure-chevron repair was included. Independent review disposition is ship: the initial review covered the approved interface and the final review confirmed the sole remaining disclosure repair resolved. A fresh reviewer spawn failed due to an unsupported harness default model, so an existing independent reviewer substituted. Context/detector automation was unavailable.
