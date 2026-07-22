# stage11-operator-cockpit 差異規格（cockpit-three-layer）

## MODIFIED Requirements

### Requirement: Cockpit lists panes from all local tmux sessions
The Stage 11 cockpit SHALL enumerate panes from every local tmux session visible to the tmux server. Each pane record MUST include the pane ID, session name, window index, title, command, geometry, and active flag. The cockpit MUST NOT capture pane preview content: a periodic refresh tick SHALL consist of a single `list-panes` invocation (plus the bounded `ps` lookup for title-less minicom panes only).

#### Scenario: All-session pane scan includes session and window metadata
- **WHEN** the tmux server contains panes in sessions `main` and `work`
- **THEN** the cockpit pane scan MUST include panes from both sessions and MUST preserve each pane's `session_name` and `window_index`

#### Scenario: Refresh tick performs no preview capture
- **WHEN** a periodic refresh tick runs
- **THEN** the cockpit MUST NOT invoke `tmux capture-pane` for any pane

### Requirement: Candidate section includes all non-cockpit non-active panes
The Stage 11 cockpit SHALL list every pane in the cockpit session that is neither the cockpit pane nor the cockpit-session active slot as a candidate, sorted by `(session_name, window_index, pane_id)`. Panes in other sessions MUST still be enumerated（requirement「lists panes from all local tmux sessions」）and counted in the banner session summary, but MUST NOT appear as candidates（truth-up：#249「WORK 收斂自身 session」已出貨行為，原 spec 文字未同步）.

#### Scenario: Candidate section is scoped to the cockpit session
- **WHEN** the cockpit session `main` contains non-active candidate panes `%2` and `%3`, and session `work` contains pane `%7`
- **THEN** the candidate section MUST include `%2` and `%3` sorted by `(session_name, window_index, pane_id)` and MUST NOT include `%7`

### Requirement: Enter swaps selected pane with active slot across sessions
The Stage 11 cockpit SHALL provide exactly two equivalent swap triggers: pressing `Enter` on a selected candidate, and double-clicking a candidate row (see the double-click requirement). Both triggers MUST route through the same activation sequence: restore-before-swap pre-step (see the restore requirement), then the existing layout action service swap with the selected pane ID and active-slot pane ID, then a rebuild of cockpit state from a fresh tmux scan. Candidates are scoped to the cockpit session（見 candidate-section requirement）；the swap mechanism itself remains session-agnostic（pane id 定址）. The keyboard path MUST have a single action authority: the work-list widget's own `enter` binding delegates to the app swap action, and the app MUST NOT keep a duplicate `on_key` enter special-case.

#### Scenario: Selected candidate swaps into active slot
- **WHEN** the active slot is `%4`, the selected candidate is `%12`（cockpit session）, and the operator presses `Enter`
- **THEN** the cockpit MUST invoke a swap from `%12` to `%4` and MUST refresh pane state from tmux after the swap

#### Scenario: Enter triggers exactly one swap
- **WHEN** the work list is focused and the operator presses `Enter` once on a selected candidate
- **THEN** the layout action service MUST receive exactly one swap invocation

### Requirement: Cockpit provides footer and modal hotkey help
The Stage 11 cockpit SHALL provide short descriptions for visible bindings in the footer and SHALL bind `?` to a modal help screen. The modal MUST list the cockpit bindings — including `j`（JOBS 收合）and the double-click swap trigger — and explain the multi-session pane-listing and swap behavior. Pressing `Esc` in the modal MUST dismiss it.

#### Scenario: Question mark opens and escape dismisses help
- **WHEN** the cockpit is running and the operator presses `?`
- **THEN** the cockpit MUST show the help modal
- **WHEN** the operator presses `Esc` while the help modal is active
- **THEN** the cockpit MUST dismiss the help modal and return to the cockpit screen

#### Scenario: Help content covers new interactions
- **WHEN** the operator opens the help modal
- **THEN** the modal MUST describe the `j` JOBS toggle and the double-click swap trigger

## ADDED Requirements

### Requirement: Cockpit renders a three-layer vertical layout without a detail panel
The Stage 11 cockpit SHALL render, top to bottom: brand banner, WORK pane list, and JOBS panel. The cockpit MUST NOT render a `#pane-detail` widget. The WORK list SHALL flex to fill remaining height（`1fr`）with a minimum of 5 rows; the JOBS panel SHALL auto-size to content with a maximum height of 12 rows including its border.

#### Scenario: Three layers in order and no detail widget
- **WHEN** the cockpit mounts
- **THEN** the widget tree MUST contain banner, work list, and jobs panel in that vertical order and MUST NOT contain `#pane-detail`

#### Scenario: Small terminal preserves WORK minimum height
- **WHEN** the cockpit runs in an 80×15 terminal
- **THEN** the WORK list MUST retain at least 5 rows and the JOBS panel MUST be clipped from the bottom first

### Requirement: Double-click on a work-list candidate triggers the swap action
The Stage 11 cockpit SHALL treat two `ListView.Selected` events on the same candidate `pane_id` within 0.4 seconds as a double-click and MUST invoke the same swap action as `Enter`. Detection state SHALL be keyed by `pane_id`（not row index）with an injectable clock. The handler MUST ignore `Selected` events whose list view is not the work list（without touching gesture state）, and MUST treat a work-list click on the ACTIVE row or on an item without `pane_id` as gesture interruption（clearing the pending first click）. A successful swap trigger（any source）MUST clear the pending first click. The keyboard `enter` path MUST NOT emit `Selected`（the work-list widget overrides `action_select_cursor` to delegate directly to the swap action）.

#### Scenario: Double-click within threshold swaps
- **WHEN** the operator clicks candidate `%12` twice within 0.4 seconds
- **THEN** the cockpit MUST invoke the swap action for `%12` exactly once

#### Scenario: Slow second click does not swap
- **WHEN** the operator clicks candidate `%12` twice with more than 0.4 seconds between clicks
- **THEN** the cockpit MUST NOT invoke the swap action and MUST record the second click as a new first click

#### Scenario: Intervening ACTIVE-row click interrupts the gesture
- **WHEN** the operator clicks candidate `%12`, then the ACTIVE row, then candidate `%12` again, all within 0.4 seconds
- **THEN** the cockpit MUST NOT invoke the swap action and MUST treat the third click as a new first click

#### Scenario: Double-click on the ACTIVE row is a no-op
- **WHEN** the operator double-clicks the ACTIVE row
- **THEN** the cockpit MUST NOT invoke the swap action

### Requirement: Restore-before-swap bounds pane displacement
The Stage 11 cockpit SHALL maintain a single in-memory displacement record `(occupant_pane_id, displaced_pane_id)` and SHALL run every activation through the sequence: if a record exists and both panes are present in the latest snapshot, first swap the occupant back with the displaced pane（restore）; on restore success where the activation target equals the displaced pane, the activation is complete without a further swap; on restore failure the cockpit MUST clear the record, notify, and abort the activation without performing the main swap; if either recorded pane is absent the record is dropped silently. The main swap on success MUST set the record to the new pair; on failure the record stays cleared and the cockpit notifies. Every terminal outcome MUST be followed by a fresh tmux re-scan. The record MUST reset to empty on cockpit startup.

#### Scenario: Second activation restores the first displaced pane
- **WHEN** the operator activates `%12`（displacing `%4`）and then activates `%15`
- **THEN** the cockpit MUST first swap `%12` back with `%4` and then swap `%15` into the active slot, leaving at most one displaced pair

#### Scenario: Activating the displaced pane completes via restore only
- **WHEN** the displacement record is `(%12, %4)` and the operator activates `%4`
- **THEN** the cockpit MUST perform exactly one swap（the restore）, MUST NOT perform a self-swap, and MUST clear the record

#### Scenario: Restore failure aborts the activation
- **WHEN** the restore swap fails with an error
- **THEN** the cockpit MUST clear the record, notify the operator, MUST NOT perform the main swap, and the next activation MUST proceed as a plain swap

#### Scenario: Missing recorded pane drops the record
- **WHEN** either recorded pane is absent from the latest snapshot and the operator activates a candidate
- **THEN** the cockpit MUST drop the record without notification and perform the main swap directly

### Requirement: JOBS panel is collapsible
The Stage 11 cockpit SHALL bind `j` to toggle the JOBS panel between expanded（default）and collapsed. Collapsed height MUST be at most 3 rows and the border title MUST show `JOBS ▸ N slices` with `N` refreshed on every refresh tick. The toggle MUST be inert while a modal is open. The collapsed state SHALL be in-memory only and reset on restart.

#### Scenario: Toggle collapses and expands
- **WHEN** the operator presses `j` with the JOBS panel expanded
- **THEN** the JOBS panel MUST collapse to at most 3 rows showing `JOBS ▸ N slices`
- **WHEN** the operator presses `j` again
- **THEN** the JOBS panel MUST expand to auto height capped at 12 rows

#### Scenario: Toggle is blocked while a modal is open
- **WHEN** the help modal is open and the operator presses `j`
- **THEN** the JOBS panel state MUST NOT change
