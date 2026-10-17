# Head-first AirControl implementation plan

Execute sequentially with systematic debugging and TDD; no subagents. The user's
existing instruction to implement without further design check-ins applies.

**Goal:** Make Head & Face the fresh-install default and make ordinary clicks,
right/double clicks and dragging usable without requiring facial expressions.
Preserve explicit camera start, practice, input ownership and cleanup.

**Design:** Keep the existing MediaPipe provider. Add a desktop/ non-activating HUD
dwell action dock. Select an action, settle on a target, and execute once. Drag
uses a first dwell to hold and a second dwell after movement to drop. A separate
Release drag action, tracking loss and Pause always release input. Calibrated
expressions may optionally hold a drag. Use pixel-scaled jitter stabilization
after the existing adaptive filter, with visible dwell progress. Saved explicit
mode/smoothing choices remain intact; fresh profiles default to Head.

**References:** [eViacam](https://github.com/cmauri/eviacam) uses dwell with a click
type dock. [Gameface's design](https://developers.googleblog.com/en/project-gameface-makes-gaming-accessible-to-everyone/)
supports personalized expressions and smoothing. Implement our own logic; no
GPL source is copied and no unbenchmarked runtime replacement is introduced.

## Tasks

- [x] Reproduce missing head drag/actions and jitter with deterministic engine,
  service and browser tests. Make hand-specific fixtures explicitly Hand mode.
- [x] Add shared HUD geometry, dwell action/drag state, expression holds and
  pixel-scaled stabilization. Test action rearming, ambiguity and cleanup.
- [x] Add themed action dock, practice/drag feedback and native HUD progress.
  Cover desktop scaling, all themes, reduced motion and keyboard operation.
- [x] Run regressions and controlled scratch-window input checks; document
  measured results and remaining participating-user accuracy/comfort checks.
- [x] Launch through the latest-source shortcut and update the private repo.

Physical accuracy and comfort cannot be inferred from synthetic landmarks. Do
not start the camera without the user's explicit Start camera action in this
turn; the existing successful head motion report informs the requested tuning.
