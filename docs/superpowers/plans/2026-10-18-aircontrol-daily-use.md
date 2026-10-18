# AirControl Daily-Use Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AirControl comfortable for daily hands-free use and understandable to new users through a focused desktop workspace, safe head scrolling, useful practice, and measurable verification.

**Architecture:** Retain the isolated camera worker, pure gesture engine, service-owned native input, and plain JavaScript desktop. Add focused practice/metrics modules; expose authoritative readiness, exercise, and scroll state through the existing owned desktop bridge. Native HUD drawing and hit testing continue to share geometry.

**Tech Stack:** Windows x64, project Python 3.13 environment, MediaPipe/OpenCV isolated runtime, WebView2, HTML/CSS/JavaScript, unittest, Node tests, Playwright, pinned axe accessibility tooling.

**Spec:** [Approved design](../specs/2026-10-18-aircontrol-daily-use-design.md).

## Global Constraints

- Camera start and Enable remain distinct actions.
- Retain the 250 ms freshness watchdog and explicit Resume after stable reacquisition.
- Combined continues to require both sources for PC control.
- No phone endpoint is added; desktop commands remain owned-window-only.
- Preserve seven themes, the mouse mark, Segoe UI/system typography, and saved profile choices.
- At 820×620, the movement area begins in the first viewport and exposes at least 240 px of usable height.
- Verify 820×620, 1120×800, 1440×900, both appearances, all seven themes, and 200% zoom/reflow.
- Main text meets 4.5:1 contrast; large text meets 3:1; controls have at least 44×44 CSS px targets.
- Head scroll emits at most one `dy=+2` or `dy=-2` event per 150 ms after the configured dwell; no catch-up or momentum.
- Keep rolling latency data to 600 samples and completed exercise results to 100.
- Practice causes no native input, speech, input ownership, or native overlay effects.
- Export no images, landmarks, expression samples, window titles, field contents, device identifiers, or file-system paths.
- Do not replace the tracker, introduce a frontend framework, or alter phone/Remote protocols.
- Synthetic motion measurements do not establish physical recognition accuracy or comfort.

## Review Focus

1. Rapid repeated Enter Scroll / Done / Enable commands must not repeat input or bypass lifecycle checks (Tasks 1–3).
2. A resize or stale viewport during a drag must not count a miss or evaluate against mismatched target geometry (Tasks 4–5).
3. An expression held through scroll exit must not become a click/drag before relaxing (Tasks 2–3).
4. Negative monitor origins and monitor changes must preserve HUD hit testing and release scrolling safely (Task 3).
5. Empty/nonfinite metrics and hostile report fields must remain bounded, honest, and free of sensitive data (Task 6).

## File responsibilities

| Files | Responsibility |
| --- | --- |
| `server/aircontrol/service.py` | Readiness, lifecycle, event dispatch, practice/metrics integration |
| `server/aircontrol/engine.py` | Pure pointing and head-scroll state/repeat |
| `server/aircontrol/hud.py`, `overlay.py`, `overlay_native.cs` | Shared native targets and non-activating virtual cursor |
| New `server/aircontrol/practice.py` | Pure task geometry, completion, and bounded results |
| New `server/aircontrol/metrics.py` | Pure rolling measurements and sanitized reports |
| `gui/web/index.html`, `aircontrol.css`, `desktop.css`, `aircontrol.js` | Workspace, guidance, rendering, bridge binding |
| New `gui/web/aircontrol-view.js` | Pure view-state derivation, exported to browser and Node tests |
| `gui/webview_window.py` | Explicit local asset allowlist and trusted report build label |
| New `tests/aircontrol_view.test.cjs`, Python regression files below | Component contracts and lifecycle tests |
| `tests/test_web_client.cjs`, package files | Browser behavior, accessibility, visual matrix |
| New `tests/aircontrol_replay.py`, `tests/test_aircontrol_replay.py` | Repeatable synthetic motion evidence |

Existing `profiles.py` and `worker.py` retain their contracts. If an implementation needs to change those contracts, reassess against the approved spec before expanding scope.

## Task 1: Authoritative readiness and a protected baseline

**Files:** Modify `server/aircontrol/service.py`; test `tests/test_aircontrol_service.py`. Preserve the existing reliability work in `docs/AIRCONTROL.md`, `docs/AIRCONTROL_RELIABILITY_REVIEW.md`, `gui/web/aircontrol.js`, `server/aircontrol/engine.py`, `server/aircontrol/expressions.py`, `server/aircontrol/service.py`, `tests/test_aircontrol_engine.py`, `tests/test_aircontrol_expressions.py`, `tests/test_aircontrol_head_service.py`, and `tests/test_web_client.cjs`.

**Interfaces:** Add `AirControlService.activation_readiness(*, now=None) -> dict` returning `{ready: bool, code: str, message: str}`; expose as snapshot `activation`. Codes: `camera_off`, `already_active`, `calibration_required`, `practice_required`, `tracking_required`, `steady_required`, `release_gesture`, `monitor_required`, `ready`. This helper uses local state only. Command Enable additionally rechecks the current Windows desktop and live monitor geometry.

- [ ] **Step 1 — Record the baseline.** Review the existing reliability diff, run the baseline commands in Task 8, and commit only those previously approved changes with `fix: preserve AirControl release position and expression evidence`. Keep the committed spec and this plan intact; do not reset or stash away the local work.
- [ ] **Step 2 — Add failing tests** in `AirServiceTests` for each readiness code, freshness at 250/251 ms, still-held practice gestures, and readiness reads causing no acquire/display/input calls. Add `test_repeated_enable_cannot_reacquire_active_session` with two sequential Enable requests and one acquisition total.

```python
self.service.worker = None
result = self.service.activation_readiness(now=10.)
self.assertFalse(result['ready'])
self.assertEqual(result['code'], 'camera_off')
self.acquire.assert_not_awaited()
```

- [ ] **Step 3 — Verify RED.** Run `$env:PYTHONPATH='tests'; .\.venv\Scripts\python.exe -m unittest test_aircontrol_service -v`; new tests must fail for the missing readiness contract.
- [ ] **Step 4 — Implement** the helper in `service.py`; use it in the snapshot and Enable command. Keep unlocked-desktop and asynchronous monitor revalidation at the command boundary. Reject Enable unless the lifecycle is practicing and input is not already owned. Render-time readiness must not save a profile or touch hardware.
- [ ] **Step 5 — Verify GREEN** with the same command and the head-service regressions. Commit the scoped files with `feat: expose authoritative AirControl activation readiness`.

## Task 2: Pure head-scroll state and timing

**Files:** Modify `server/aircontrol/engine.py`; create `tests/test_aircontrol_scroll.py`.

**Interfaces:** Add `GestureEngine.head_scroll: bool` and `set_head_scroll(enabled: bool) -> list[dict]`. It releases a held button when necessary, cancels pending gesture/dwell confirmation, and consumes dwell on exit. `step()` continues updating `point`, but emits no desktop pointer/button/expression actions in scroll mode. It recognizes `scroll_up`, `scroll_down`, `scroll_done`, `pause`, and `stop` HUD targets. Reset/loss clears the mode and repeat state.

- [ ] **Step 1 — Add failing engine tests** using the existing `face(t, ...)` fixture from `test_aircontrol_head_actions`: dwell for 900 ms, repeat at 150 ms, no repeats before the deadline, no catch-up after a gap, immediate stop on target departure, fresh dwell on direction change, release on entry, and no click/button/pointer actions while scrolling. Assert non-Head modes reject entry.

```python
e = GestureEngine(default_profile(mode='head'))
e.set_head_scroll(True)
e.hud_regions = [{'action':'scroll_up','rect':[.4,.4,.6,.6]}]
e.step(face(0.))
events = e.step(face(.9))
self.assertEqual([x for x in events if x['kind']=='scroll'],
                 [{'kind':'scroll','dy':2}])
self.assertFalse(any(x['kind'] in ('pointer','button','action') for x in events))
```

- [ ] **Step 2 — Verify RED.** Run `$env:PYTHONPATH='tests'; .\.venv\Scripts\python.exe -m unittest test_aircontrol_scroll -v`.
- [ ] **Step 3 — Implement** the pure state branch after valid point calculation and before ordinary gestures/dwell. Use observation timestamps, at most one repeat per accepted sample, and no timer/thread. A timestamp gap greater than 250 ms clears an incomplete direction dwell/repeat even if a caller bypasses the service watchdog.
- [ ] **Step 4 — Add the held-expression exit regression.** Hold a calibrated smile through Done, dwell duration, and neutral release; assert zero click/drag until it relaxes and is deliberately reasserted. Verify the new test fails before adding the needed rearm state, then passes.
- [ ] **Step 5 — Verify GREEN** for engine, head actions, filters, expressions, and scroll tests. Commit with `feat: add exclusive head-scroll engine mode`.

## Task 3: Service, native dock, and escape integration

**Files:** Modify `service.py`, `hud.py`, `overlay.py`, `overlay_native.cs`; create `tests/test_aircontrol_scroll_service.py`; extend `tests/test_aircontrol_overlay.py`, `tests/test_aircontrol_head_service.py`.

**Interfaces:** Add guarded commands `head_scroll`, `scroll_up`, `scroll_down`, `scroll_done`. Direction commands issue one small step only; engine observation processing owns dwell/repeat. Add snapshot `head_scroll`. Preserve `HEAD_ACTIONS` and add `HEAD_SCROLL_ACTIONS` for these four names. Extend `layout(display, *, active=False, head=False, dragging=False, scrolling=False)` and `regions(display, *, active=False, scrolling=False)`. Add `practice_regions(viewport, *, scrolling=False) -> list[dict]` with normalized target rectangles for in-stage controls, shared by practice rendering and engine hit testing.

- [ ] **Step 1 — Add failing lifecycle tests:** Head-only and calibrated guards; active/practice entry; one native drag release; repeat routes only scroll; direction commands outside scroll are rejected; duplicate entry is harmless. Cover Pause, Stop, Recenter, practice transition, stale frame, required-source loss, worker failure, locked desktop, physical takeover, and monitor removal. Assert each clears the submode and input.
- [ ] **Step 2 — Add geometry tests:** every visible action is hit-testable at its drawn center with a negative monitor origin; Up/Down/Done are at least 44 px native targets; practice targets fit a 160×160 minimum validated viewport; a monitor change cannot retain repeat. Run the Task 2 and new service/overlay test modules and observe RED.
- [ ] **Step 3 — Implement** service guards and snapshot state. Release native buttons before entering scroll; preserve the physical cursor position as the takeover anchor in active mode. During active scrolling, permit only scroll and HUD navigation/escape proposals at the final dispatch boundary. No automatic dictation. Practice uses only in-stage regions and never opens a native overlay. Command and observation paths must share the same scroll adapter limits.
- [ ] **Step 4 — Implement** the expanded shared dock geometry, allowlisted callbacks, and native virtual cursor while scrolling. Up/Down/Done replace the click selector during scrolling; Pause/Stop remain. Keep the existing non-activation styles. Native timers render only; they never repeat scroll.
- [ ] **Step 5 — Verify GREEN** for all AirControl Python tests and the existing owned-HUD compile/inspection check where available. No webcam or unguarded Windows input is required. Commit with `feat: integrate safe head scrolling with the desktop and HUD`.

## Task 4: Practice exercises with authoritative hit testing

**Files:** Create `server/aircontrol/practice.py`, `tests/test_aircontrol_practice.py`; modify `service.py`, `tests/test_aircontrol_service.py`, `tests/test_webview_shell.py`.

**Interfaces:** `PracticeSession()` exposes `set_viewport(width:int, height:int, revision:int=0)`, `start(name:str, at:float)`, `consume(events:list[dict], point:tuple|None, at:float)`, `interrupt(at:float)`, `resume(at:float)`, `clear_history()`, and `snapshot(at:float)->dict`. Names are `free`, `click`, `drag`, `scroll`. Snapshot includes `name`, `status`, `viewport_revision`, `targets`, `target_index`, `misses`, `successes`, `elapsed_ms`, `document_position`, `goal`, `accepted_clicks`, and `results`. Targets have normalized `x`, `y`, `width`, `height`; results are capped at 100.

Add commands `practice_viewport` with `{width,height,revision}`, `practice_start` with `{name}`, `practice_reset`, `practice_pause`, `practice_resume`; expose snapshot `practice`. Revisions are integers in [0, 2147483647]; ignore an older revision and reject changed dimensions under an already accepted revision. Starting an exercise while active first uses the existing practice transition, including input release/ownership return; it cannot retain native ownership.

- [ ] **Step 1 — Add failing pure tests:** three click targets; off-target miss; drag source-to-destination and premature release; scroll goal completion; pause time excluded; tracking interruption cancels a held attempt; resize restarts the attempt without a miss; completion counted once; 101 results retain only the newest 100. Reject nonfinite values, booleans, and viewport dimensions outside 160–8192.

```python
p = PracticeSession()
p.set_viewport(640, 480)
p.start('click', 0.)
p.consume([{'kind':'action','action':'left_click'}], (.25,.5), 1.)
self.assertEqual(p.snapshot(1.)['successes'], 1)
self.assertEqual(p.snapshot(1.)['target_index'], 1)
```

- [ ] **Step 2 — Verify RED.** Run `$env:PYTHONPATH='tests'; .\.venv\Scripts\python.exe -m unittest test_aircontrol_practice -v`.
- [ ] **Step 3 — Implement** the pure evaluator. Use click centers `(.25,.5)`, `(.75,.5)`, `(.5,.25)`, clamped for a 16 px inset around at least 64 px targets. Drag uses source `(.25,.5)` and destination `(.75,.5)`. Scroll position starts at 0 with goal .75; each `dy` changes position by `-dy*.04`, clamped to [0,1]. A pinch tap qualifies as a click on release only if held at most .5 s and moved at most 12 stage pixels. Right clicks do not complete left-click targets.
- [ ] **Step 4 — Add failing integration tests** for all commands, stale viewport updates, invalid lifecycle, bridge ownership checks, and zero native mouse/keyboard/wheel/speech/overlay/acquire effects during exercises. Preserve free-practice activation; a successful exercise click contributes to readiness, a miss does not. Implement service integration and ensure resize revisions apply atomically before the next observation is scored.
- [ ] **Step 5 — Verify GREEN** for practice/service/scroll/WebView-shell tests. Commit with `feat: add safe click drag and scroll practice exercises`.

## Task 5: Focused frontend and guided setup

**Files:** Modify `gui/web/index.html`, `aircontrol.css`, `desktop.css`, `aircontrol.js`, `gui/webview_window.py`, `tests/test_web_client.cjs`, `tests/test_webview_shell.py`, `package.json`; create `gui/web/aircontrol-view.js`, `tests/aircontrol_view.test.cjs`.

**Interfaces:** Export `deriveAirView(snapshot, draft) -> {step, primary, status, modeSummary, instruction, scrolling}` as `window.TouchHelmAirView.derive` and CommonJS `derive`. `step` is `camera`, `calibrate`, `practice`, or `enable`; `primary` has `action`, `label`, `disabled`. Consume the service `activation`, `practice`, and `head_scroll` contracts from Tasks 1–4. Rendering must not change service state or saved settings.

- [ ] **Step 1 — Add failing view/browser tests** for setup step derivation, one relevant primary action, readiness reasons, active-versus-practice status, held gestures, tab keyboard semantics, scroll controls, real practice targets, command failure retention, and inspecting Practice without stopping active control. Starting an exercise explicitly returns ownership. Add the new unit file to `npm test`.
- [ ] **Step 2 — Add failing bounds tests:** at 820×620, the stage begins within the viewport and at least 240 px remains visible below the session bar; Pause/Stop do not overlap it. Check single-column reflow at a 410 CSS px effective width and 200% text scaling. Assert all in-stage targets match service rectangles after resize. Run `npm test` and `node tests/test_web_client.cjs --behavior-only '--filter=AirControl'` and observe the new failures.
- [ ] **Step 3 — Implement** the pure view helper, explicit local asset allowlist entry, script ordering, and preview server file mapping. Test the real asset resolver so preview-only success cannot conceal an owned-shell 404. Retain all DOM IDs used by bridge behavior, changing their placement deliberately rather than duplicating controls.
- [ ] **Step 4 — Build** the spec layout: compact persistent session bar; stage-first workspace; contextual inspector; Session/Practice/Personal settings/Diagnostics tabs; setup-only progression; optional expression settings; folded advanced controls; compact chooser. Change setup explicitly stops the session and exposes camera/monitor/mode choices before a fresh Start/Calibrate/Practice flow; changing a selection alone must not restart capture. Keep theme variables, system type, 4/8/12/16/24 px spacing, visible focus, reduced motion, and 44 px controls. Remove promotional eyebrows and oversized competing gesture decoration from this surface.
- [ ] **Step 5 — Wire** practice viewport updates through a ResizeObserver with coalescing and a revision token. Do not score old geometry while an updated viewport is pending. Announce meaningful status changes only, avoid rerendering focused form controls per frame, and preserve dirty drafts on polling. Preview fixtures explicitly simulate the new states without native commands.
- [ ] **Step 6 — Verify GREEN** with units, owned-shell tests, and AirControl browser checks. Capture the minimum and normal desktop layouts in one inspection batch, fix the observed issues in one batch, and confirm once. Commit with `feat: redesign AirControl around a focused daily workspace`.

## Task 6: Bounded diagnostics and sanitized report export

**Files:** Create `server/aircontrol/metrics.py`, `tests/test_aircontrol_metrics.py`; modify `service.py`, `gui/webview_window.py`, `gui/web/aircontrol.js`, `gui/web/index.html`, `tests/test_webview_shell.py`, `tests/test_web_client.cjs`.

**Interfaces:** `SessionMetrics(latencies=None)` reuses the service's existing latency deque when supplied. Methods: `observe(*, at:float, tracked:bool, capture_fps=None, inference_ms=None, frame_age_ms=None)`, `record_latency(value:float)`, `reset(at:float)`, `snapshot(at:float)->dict`, and `report(*, at:float, mode:str, display_size:list[int], results:list[dict], build_id:str)->dict`. Snapshot labels the 600-sample latency window and exposes `latency_sample_count`, `median_latency_ms`, `p95_latency_ms`, `tracking_interruptions`, `duration_seconds`, and existing measured rate fields. P95 uses nearest rank `ceil(.95*n)-1` on sorted finite samples.

Add `reset_measurements` and `export_report` commands. The owned DesktopAPI supplies the running app's trusted `build_id` for export, replacing any renderer-provided value. The report envelope is `{version:1, build, mode, display_size, duration_seconds, metrics, exercises}` and is built through an explicit field allowlist.

- [ ] **Step 1 — Add failing tests** for empty windows returning null, literal samples 1–100 giving median 50.5/p95 95, 601 samples retaining 600, interruption counted once per tracked-to-lost transition, nonfinite/negative input rejected or omitted, reset preserving calibration/sequence/exercise progress, and report results capped at 100. Inject paths/titles/landmarks/arbitrary nested keys and assert none survive export. Run the new metrics tests and observe RED.
- [ ] **Step 2 — Implement** pure metrics without timers, hardware reads, or I/O. Integrate accepted observations, native pointer latency, tracking loss/watchdog, and lifecycle reset without counting startup as an interruption. Replace the existing latency append with `record_latency`, rather than writing twice to the shared deque. No unbounded history or per-frame disk writes. Compute percentiles from the bounded window on snapshot; do not claim lifetime percentiles.
- [ ] **Step 3 — Add failing bridge/browser tests** for an unowned export refusal, overriding a forged build label, null metric display, explicit download, and reset leaving the camera/calibration unchanged. Implement trusted build injection, service allowlisting, and JSON Blob download with URL cleanup. No automatic export/upload and no camera/field information.
- [ ] **Step 4 — Verify GREEN** for metrics, service, WebView-shell, and AirControl browser checks. Confirm export parses and contains only the documented envelope. Commit with `feat: add bounded AirControl diagnostics and private reports`.

## Task 7: Motion replay and automated accessibility checks

**Files:** Create `tests/aircontrol_replay.py`, `tests/test_aircontrol_replay.py`, `docs/THIRD_PARTY_DEVELOPMENT.md`; modify `tests/test_web_client.cjs`, `package.json`, `package-lock.json`.

**Interfaces:** `run_replay(*, engine_factory, fps:int, size:tuple[int,int], scenario:str)->dict` reports `jitter_rms_px`, `step_90_ms`, `actions`, `button_downs`, `button_ups`, and `samples`. CLI `python tests/aircontrol_replay.py --output <path>` writes a synthetic-only report. Scenarios are `stationary`, `jitter`, `step`, `conflict`, `loss`, `edges` at 10/15/30 observations per second and HD/4K scales.

- [ ] **Step 1 — Add failing replay tests** with independently known coordinate traces, exact action counts, first-invalid-observation release, endpoint reachability, and bounded comparison of 90% step response. Save the pre-feature baseline after Task 1 and use exactly the same fixtures/settings for comparison; import its engine from a separate temporary source snapshot, never move this checkout's HEAD.
- [ ] **Step 2 — Implement** replay generation and measurement. Include fixture seed, settings, build label, and sample dimensions in the report; no camera/model/native imports. Verify no new unintended actions and no step-response worsening beyond one observation interval. Record measured jitter values without requiring an invented percentage improvement.
- [ ] **Step 3 — Resolve and pin the accessibility dev dependency** at execution time:

```powershell
$axeVersion = npm view @axe-core/playwright version
npm install --save-dev --save-exact "@axe-core/playwright@$axeVersion"
```

Record the installed versions and upstream license references in the development notice. Do not add this library to runtime HTML or serve `node_modules`.

- [ ] **Step 4 — Add a failing browser accessibility check** for camera-off, calibrating, practicing, active, paused, tracking-lost, scrolling, and unavailable states in the default theme; cover all seven themes/both appearances in practice. Scan the active AirControl surface with axe. Assert no unresolved critical/serious findings, and independently check contrast, 44 px targets, tab names/associations, focus, live announcements, and reduced motion. Fix actual product findings rather than adding broad exclusions.
- [ ] **Step 5 — Verify GREEN** with replay units/CLI, `npm test`, and `node tests/test_web_client.cjs --visual '--filter=AirControl'`. Complete one batched inspection/correction/confirmation cycle for any new accessibility/layout changes. Commit with `test: benchmark AirControl motion and accessibility`.

## Task 8: Whole-product verification and delivery evidence

**Files:** Update `PRODUCT.md`, `DESIGN.md`, `docs/AIRCONTROL.md`, `docs/AIRCONTROL_VERIFICATION.md`, `docs/AIRCONTROL_RELIABILITY_REVIEW.md`; create `docs/AIRCONTROL_DAILY_USE_RELEASE.md`.

**Interfaces:** Documentation reflects the delivered snapshot/command names and actual measurements; it does not add new product behavior. The release note separates implementation, automated evidence, and physical acceptance.

- [ ] **Step 1 — Run the complete suites** and inspect exit codes/results:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
npm test
node tests/test_web_client.cjs --behavior-only
node tests/test_web_client.cjs --visual '--filter=AirControl'
.\.venv\Scripts\python.exe tests/aircontrol_replay.py --output .tmp/aircontrol-daily-use-replay.json
git diff --check
```

The known sandbox can block Store Python, temporary ACL checks, and the browser's local server. Use approved command escalation for those environmental restrictions; do not weaken app authentication or camera/input guards. Do not run the legacy root `test_touchhelm.py` against real user apps; it intentionally sends native input.

- [ ] **Step 2 — Review** the full change against every acceptance item, including phone retained drafts, Remote view/audio, ownership, saved modes, model checksums, session stop/recovery, and report privacy. Request one independent review when a compatible reviewer is available. If delegation still fails on its configured model, disclose that limitation and perform a direct review; do not report an independent review that did not occur.
- [ ] **Step 3 — Document physical acceptance** as a 30-minute participating-user checklist: explicit Start/Enable, click/drag/scroll tasks, ordinary blink rejection, personal expressions, pause/resume, occlusion/reacquisition, physical takeover, and available camera unplug/reconnect. Collect only the sanitized report and comfort feedback. Do not start the webcam automatically; mark all scenarios not performed as unverified.
- [ ] **Step 4 — Update** the product/design/help documents and release evidence with actual test counts, replay results, screenshots inspected, deviations, and outstanding physical checks. No unsupported recognition-accuracy or camera-FPS claims. Keep the original brand/theme direction and explain the practice-versus-active distinction.
- [ ] **Step 5 — Commit** scoped release documentation with `docs: record AirControl daily-use verification`. Report the code delivered and automated results separately from physical readiness. External publishing, merging, and tracker replacement are outside this plan.

## Plan self-review and execution handoff

Coverage: setup/readiness (1,5); scroll exclusivity and native recovery (2,3);
task-based practice (4,5); visual system and navigation (5); metrics/privacy (6);
replay/accessibility (7); full regression and participating-user evidence (8).
Each Review Focus condition has an explicit owning test. New interfaces are
introduced before their consumers; no persistent profile format change is needed.

Recommended execution: Native in the current checkout, sequentially. These tasks
share the service/engine/frontend contracts and the checkout contains approved
reliability work. A single implementer avoids overlapping state changes; use one
whole-change reviewer at the end if the tool can launch it. User review of this
plan and execution-method selection are required before implementation.
