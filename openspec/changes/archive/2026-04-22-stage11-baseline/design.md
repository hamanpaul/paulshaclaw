## Context

Stage 1 currently owns the smallest possible runtime baseline for the project: config loading, daemon command routing, Telegram authorization, and a deterministic text renderer for pane/task listing. That baseline is intentionally simple and does not provide a real interactive terminal UI. The project now needs a separate stage for an operator-facing cockpit that can treat the tmux layout as the real workspace, observe pane state in real time, and perform one safe layout mutation: swapping a selected pane into a dedicated active work slot.

The clarified constraints from brainstorming are:

- This work MUST be a new stage and MUST NOT expand Stage 1 scope.
- The cockpit pane itself is part of the tmux environment and must exclude itself from candidate panes.
- The active work slot is chosen once at startup from the largest non-cockpit pane and remains stable unless explicitly lost.
- The MVP is read-mostly and must not absorb broader control actions such as send-message, adopt/release, or resize.
- Pane state comes from tmux truth, while job state comes primarily from Stage 3 / coordinator / registry artifacts with best-effort fallback.

## Goals / Non-Goals

**Goals:**
- Introduce Stage 11 as a dedicated operator cockpit stage.
- Provide a pane-first interactive UI with four stable areas: active slot, work list, selected pane detail, and global jobs.
- Support `Enter`-triggered swap of a selected pane with the active slot, followed by full reconciliation against tmux truth.
- Keep Stage 11 resilient when artifact data is incomplete.
- Keep Stage 11 isolated from Stage 1 and Stage 3 ownership boundaries.

**Non-Goals:**
- Changing Stage 1 canonical behavior or replacing the Stage 1 renderer.
- Redefining Stage 3 lifecycle, trace, or coordinator schemas.
- Implementing send message, interrupt, resize, rename, adopt/release, or approval workflows in MVP.
- Supporting multiple active slots in MVP.

## Decisions

### Decision 1: Stage 11 is a separate runtime stage

- **Choice:** Create a new Stage 11 instead of extending Stage 1.
- **Alternatives considered:**
  - Extend Stage 1 `tui` into an interactive UI.
  - Treat the cockpit as a Stage 3 sub-feature because it reads lifecycle state.
- **Rationale:** Stage 1 was intentionally archived as a minimal baseline. Expanding it would blur the existing contract and create spec churn in a stage that already serves as an upstream dependency. Stage 3 owns lifecycle truth, but the cockpit is not a lifecycle engine; it is an operator control plane that consumes lifecycle outputs.

### Decision 2: Use a pane-first Textual cockpit

- **Choice:** Implement the cockpit as a `Textual` application.
- **Alternatives considered:**
  - `prompt_toolkit` for a lighter semi-interactive console.
  - raw `curses` or tmux-native shell glue.
- **Rationale:** The cockpit needs multiple stable panels, keyboard-driven focus, future mouse support, and a clear separation between UI and external actions. `Textual` fits the multi-panel operator console model better than `prompt_toolkit`, and it avoids the state-management fragility that a tmux-script-heavy approach would introduce.

### Decision 3: Split runtime into UI, store, and adapters/services

- **Choice:** Use three layers: Textual UI, cockpit store/state, and adapters/services.
- **Alternatives considered:**
  - Put tmux commands and artifact parsing directly inside UI widgets.
  - Build a single monolithic cockpit module for the MVP.
- **Rationale:** The cockpit must reconcile two different truths: live tmux state and artifact-derived job state. A separate store and adapters layer makes it easier to test active-slot selection, swap reconciliation, and degraded behavior without binding tests directly to UI widgets.

### Decision 4: Active slot is selected once and does not drift

- **Choice:** Determine the active slot at startup from the largest non-cockpit pane and keep it fixed unless lost.
- **Alternatives considered:**
  - Recompute the largest pane after every layout change.
  - Let the currently focused pane define the active slot.
- **Rationale:** The cockpit is meant to coordinate a dedicated work window, not continuously chase layout size changes. Dynamic recomputation would make swap behavior harder to predict and would break the operator mental model of a stable active work slot.

### Decision 5: Hybrid data sourcing with tmux as pane truth

- **Choice:** Pane state comes from live tmux scanning; job state comes primarily from Stage 3 / coordinator / registry artifacts, with best-effort fallback.
- **Alternatives considered:**
  - Require Stage 3 artifacts to be complete before Stage 11 can run.
  - Make registry or coordinator the canonical source for pane identity as well.
- **Rationale:** The cockpit must remain usable even when artifact coverage is incomplete. tmux is the only authoritative source for pane existence, size, and content. Artifact sources remain important for jobs and traces, but they cannot be allowed to block basic pane orchestration.

### Decision 6: The only MVP mutation is `swap`

- **Choice:** Restrict MVP control actions to swapping the selected pane with the active slot on `Enter`.
- **Alternatives considered:**
  - Include send-message and interrupt in the first cut.
  - Allow direct pane focus/follow without swap.
- **Rationale:** This keeps the first implementation small, testable, and aligned with the clarified need: content switching inside the tmux layout. Broader controls add concurrency and safety concerns that are better deferred to later iterations.

## Risks / Trade-offs

- **[Textual increases runtime dependency surface]** -> Mitigation: keep UI dependencies isolated to Stage 11 and avoid leaking them into Stage 1 or Stage 3.
- **[Pane-to-job mapping may be incomplete or noisy]** -> Mitigation: make degraded and unmapped states explicit in the UI instead of silently guessing.
- **[Swap may drift from real layout if UI predicts state locally]** -> Mitigation: force a tmux re-scan after every mutation and rebuild observed state from external truth.
- **[Active slot can disappear mid-session]** -> Mitigation: enter an explicit degraded state and require operator intervention instead of silently reassigning.
- **[Future requests may push Stage 11 into a broad control shell]** -> Mitigation: keep MVP contract narrowly scoped and treat new control actions as follow-up requirements.

## Migration Plan

There is no migration of existing Stage 1 or Stage 3 behavior. Stage 11 is additive.

Implementation rollout:

1. Add Stage 11 runtime modules and tests alongside existing stages.
2. Keep Stage 11 launch separate from Stage 1 daemon startup.
3. Validate against tmux-backed end-to-end scenarios before treating the cockpit as the preferred operator surface.

Rollback strategy:

- Disable or remove Stage 11 entry points without touching Stage 1 or Stage 3 artifacts.
- Because Stage 11 is additive and non-canonical, rollback does not require data migration.

## Open Questions

- What should the Stage 11 entry command and package path be (`python -m ...`, `psc cockpit`, or both)?
- Should the first implementation persist cockpit-local preferences such as "return to cockpit after swap," or keep them in-memory only?
