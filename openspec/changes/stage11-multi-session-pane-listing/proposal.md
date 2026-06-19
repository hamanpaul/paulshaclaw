## Why

The Stage 11 cockpit currently lists only panes from the tmux session that hosts the cockpit, so an operator cannot see or swap work panes from the rest of the local tmux fleet. This breaks the intended cockpit model: one operator surface should supervise all local tmux sessions while preserving the existing active-slot and return-to-cockpit semantics.

## What Changes

- Change cockpit pane discovery from session-local `tmux list-panes` to all-session `tmux list-panes -a`.
- Add session and window metadata to pane records so the work list can show `session:window` context and sort panes predictably.
- Scope active-slot detection to the cockpit's own tmux session so overlapping pane geometry in other sessions cannot be mistaken for the active slot.
- Keep the candidate list flat while including panes from every local tmux session except the cockpit pane itself.
- Preserve the existing `Enter` swap workflow and `LayoutActionService` API; tmux pane IDs remain the cross-session identity for `swap-pane`.
- Add hotkey help: short footer descriptions plus a `?` modal with the full binding table and multi-session behavior notes.
- Derive the cockpit session from the cockpit pane record during startup and fail with the existing missing-cockpit-pane error path when it cannot be found.

## Capabilities

### New Capabilities

- `stage11-operator-cockpit`: Defines the Stage 11 cockpit pane-listing, active-slot, cross-session swap, and hotkey help behavior.

### Modified Capabilities

- None. `openspec/specs/` does not currently contain an active Stage 11 spec; the archived Stage 11 baseline is used only as historical context.

## Impact

- **Affected code**:
  - `paulshaclaw/cockpit/models.py`
  - `paulshaclaw/cockpit/tmux.py`
  - `paulshaclaw/cockpit/store.py`
  - `paulshaclaw/cockpit/app.py`
  - `paulshaclaw/cockpit/help.py`
  - `paulshaclaw/cockpit/__main__.py`
- **Affected tests**:
  - `tests/test_stage11_operator_cockpit.py`
  - `tests/test_stage11_operator_cockpit_e2e.py`
- **Execution assumption**:
  - Implementation planning assumes `gpt-5.3-codex` as the primary agent model for code changes, test expansion, and review checkpoints.
- **Explicitly not impacted**:
  - `LayoutActionService` interfaces and implementation
  - Stage 1, Stage 3, Stage 9, and coordinator integration
  - `scripts/start.sh`
  - Any new goto or switch-client workflow
