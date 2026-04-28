## Context

Stage 11 already has a pane-first cockpit runtime under `paulshaclaw/cockpit/`. Its current tmux adapter calls `tmux list-panes` without `-a`, so the cockpit only sees panes in the tmux session that hosts the cockpit. Operators expect the cockpit to supervise the local tmux fleet, not only the current session.

Moving to `tmux list-panes -a` changes more than the command flag. The existing active-slot state machine uses pane geometry `(left, top)` as the active-slot anchor. Those coordinates are scoped per tmux session, so multiple sessions can have panes with the same anchor. The cockpit must therefore carry session identity through parsing, state construction, refresh, and display.

This design is derived from `docs/superpowers/specs/2026-04-28-stage11-multi-session-pane-listing-design.md`. Implementation planning assumes `gpt-5.3-codex` as the primary model for code edits and review checkpoints.

## Goals / Non-Goals

**Goals:**

- List panes from every local tmux session/window in the Stage 11 work list.
- Preserve the existing active-slot, selected-pane, and return-to-cockpit semantics.
- Keep active-slot detection scoped to the cockpit's own tmux session.
- Allow `Enter` swap to work across sessions through tmux pane IDs.
- Add operator hotkey help through footer descriptions and a `?` modal.
- Keep the implementation small and testable with focused unit and smoke coverage.

**Non-Goals:**

- Add a cross-session goto or `switch-client` action.
- Group panes by session in the UI.
- Change `LayoutActionService`, Stage 1, Stage 3, Stage 9, coordinator integration, or `scripts/start.sh`.
- Add new mutation actions beyond the existing `Enter` swap behavior.

## Decisions

### Decision 1: Enumerate panes with `tmux list-panes -a`

- **Choice:** Change `TmuxClient.list_panes()` to run `tmux list-panes -a -F <format>`.
- **Alternatives considered:** Run one `list-panes` command per session, or keep session-local enumeration and add a later aggregator.
- **Rationale:** `list-panes -a` is tmux's native all-session pane listing, keeps the adapter simple, and returns pane IDs that are already globally unique within the tmux server.

### Decision 2: Add `session_name` and `window_index` to `PaneRecord`

- **Choice:** Extend `PaneRecord` with `session_name: str` and `window_index: str`, and add `#{session_name}` / `#{window_index}` to the list-panes format.
- **Alternatives considered:** Parse session/window only for display, or derive it from pane IDs later.
- **Rationale:** Session identity is part of state correctness, not only presentation. The store needs it to disambiguate active-slot anchors, and the UI needs it for understandable labels. `window_index` remains a string so tmux base-index customization does not force numeric assumptions.

### Decision 3: Keep the active slot cockpit-session-local

- **Choice:** Derive `cockpit_session_name` from the cockpit pane record at startup and pass it into `CockpitState.from_panes()`, `choose_startup_slot()`, refresh reconciliation, and active/candidate section generation.
- **Alternatives considered:** Include session in the stored active-slot anchor, or pick the largest pane across all sessions.
- **Rationale:** The active slot represents the work pane in front of the cockpit operator. Selecting it from another session would make the cockpit's local layout semantics ambiguous. Session filtering preserves existing behavior while allowing the candidate list to span every session.

### Decision 4: Preserve flat candidate listing and existing swap service

- **Choice:** Keep one flat candidate section sorted by `(session_name, window_index, pane_id)` and leave `LayoutActionService.swap_selected_with_active()` unchanged.
- **Alternatives considered:** Add per-session headers, create a new cross-session swap API, or add goto behavior.
- **Rationale:** The expected scale is small enough that grouping adds UI churn without a clear benefit. `tmux swap-pane -s %X -d %Y` accepts pane IDs, and pane IDs are unique across the tmux server, so the existing service already supports cross-session swap.

### Decision 5: Add help without expanding control surface

- **Choice:** Add binding descriptions to existing controls, bind `?` to a `HelpModal`, and allow `Esc` to dismiss the modal.
- **Alternatives considered:** Add a command palette, inline onboarding text, or new quit/navigation bindings.
- **Rationale:** The operator needs discoverability for existing actions and the new all-session behavior. A footer plus modal addresses that without changing the cockpit's mutation surface.

## Risks / Trade-offs

- **[Pane geometry collisions across sessions]** -> Mitigation: carry `session_name` through the state model and filter active-slot comparisons to `cockpit_session_name`.
- **[All-session listing exposes more panes than expected]** -> Mitigation: label every pane with `session:window` and keep deterministic sorting.
- **[Cross-session swap could appear surprising]** -> Mitigation: keep swap confirmation on `Enter` only, do not add implicit focus/goto behavior, and document the behavior in help.
- **[Textual modal binding conflicts]** -> Mitigation: keep modal controls limited to `Esc` dismissal and avoid adding overlapping main-screen actions.
- **[Existing tests are tightly coupled to `PaneRecord` construction]** -> Mitigation: update fixtures and add targeted tests for parsing, state segmentation, help, and `__main__` startup derivation.

## Migration Plan

This change is an in-place Stage 11 behavior update with no data migration.

1. Extend the tmux parsing and pane model first, updating tests to include session/window fields.
2. Thread `cockpit_session_name` through state construction and refresh logic.
3. Update UI labels and help modal behavior.
4. Add unit and smoke tests for multi-session parsing, state segmentation, startup derivation, and help.
5. Run the Stage 11 focused test suite:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py tests/test_stage11_operator_cockpit_e2e.py -v
```

Rollback is limited to reverting the Stage 11 cockpit files and tests changed by this proposal. `LayoutActionService`, `scripts/start.sh`, and other stages remain untouched.

## Open Questions

- None. The source design fixes the key product decisions: flat list, no goto, active slot scoped to the cockpit session, and footer plus `?` modal help.
