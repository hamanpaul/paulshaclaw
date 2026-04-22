## Why

Stage 1 currently provides only a deterministic text renderer for pane and task listing, which is sufficient as a baseline surface but does not satisfy the project's expectation for a true interactive terminal UI. The project now needs a separate stage that treats the tmux layout itself as the operator-facing workspace and provides a controlled cockpit for observing panes, switching active work content, and correlating pane state with lifecycle and coordinator data.

This change is needed now because the interaction model has been clarified during brainstorming: the cockpit must be its own stage, must not expand Stage 1 scope, and must support a read-mostly MVP centered on active-slot swapping inside the tmux environment.

## What Changes

- Add a new Stage 11 dedicated to an interactive operator cockpit instead of extending Stage 1.
- Define a pane-first terminal UI that treats the tmux layout as the real UI surface and uses one pane as the cockpit control plane.
- Introduce an `active slot` model selected at startup from the largest non-cockpit pane and kept stable for the lifetime of the cockpit session.
- Support a read-mostly MVP with four UI areas: active slot, work list, selected pane detail, and global job summary.
- Support one controlled layout mutation in MVP: swapping the selected pane with the active slot on `Enter`, then reconciling against real tmux state.
- Define a hybrid data model where pane state comes from live tmux scanning and job state comes primarily from Stage 3 / coordinator / registry artifacts with best-effort fallback.

## Capabilities

### New Capabilities
- `stage11-operator-cockpit`: Covers the Stage 11 interactive cockpit contract, including active-slot selection, work-list behavior, swap interaction, hybrid data sourcing, degraded behavior, and validation expectations.

### Modified Capabilities
- None.

## Impact

- Affected code:
  - New Stage 11 runtime modules for UI, tmux adapter, artifact adapter, and layout action service
  - New tests for unit, integration, and tmux-backed end-to-end behavior
- Affected systems:
  - tmux pane fleet observation and layout orchestration
  - Stage 3 lifecycle / coordinator / registry artifact consumption
- Dependencies:
  - New terminal UI runtime dependency for the cockpit implementation (`Textual` is the recommended design choice)
- Explicitly not impacted:
  - Stage 1 canonical runtime behavior
  - Stage 3 ownership of lifecycle, trace, and job artifacts
