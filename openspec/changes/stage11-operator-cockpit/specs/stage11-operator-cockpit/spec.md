## ADDED Requirements

### Requirement: Stage 11 cockpit startup and active slot selection
The system SHALL provide a Stage 11 operator cockpit that runs in its own tmux pane and selects one dedicated active slot at startup. The active slot MUST be chosen from the largest non-cockpit pane visible to the cockpit at startup. The cockpit pane itself MUST be excluded from active-slot selection even when it is tied for largest pane size.

#### Scenario: Largest non-cockpit pane becomes active slot
- **WHEN** the cockpit starts in pane `%0` and visible panes `%1`, `%2`, and `%4` are non-cockpit candidates, with `%4` being the largest non-cockpit pane
- **THEN** the cockpit MUST record `%4` as the active slot and MUST NOT select `%0`

### Requirement: Work list enumerates all non-cockpit panes
The Stage 11 cockpit SHALL display a work list containing every non-cockpit pane visible to the tmux session. The active slot MUST appear in a dedicated `ACTIVE` section, and all other non-cockpit panes MUST appear in a separate candidate section. The cockpit pane itself MUST NOT appear in either section.

#### Scenario: Active pane is segmented from other candidates
- **WHEN** the cockpit has identified `%4` as the active slot and the remaining visible non-cockpit panes are `%1`, `%2`, and `%3`
- **THEN** the work list MUST show `%4` in the `ACTIVE` section and MUST show `%1`, `%2`, and `%3` in the candidate section

### Requirement: Enter swaps the selected pane with the active slot
The Stage 11 cockpit SHALL treat work-list navigation as selection only and SHALL trigger layout mutation only when the operator confirms with `Enter`. On `Enter`, the cockpit MUST swap the selected candidate pane with the active slot using tmux layout actions, and MUST then reconcile its state against a fresh tmux scan instead of relying on predicted local state.

#### Scenario: Enter swaps selected candidate into active slot
- **WHEN** the active slot is `%4`, the selected candidate is `%1`, and the operator presses `Enter`
- **THEN** the cockpit MUST invoke a swap between `%1` and `%4` and MUST rebuild its pane state from a fresh tmux scan after the swap

### Requirement: Swap defaults focus to the new active pane
After a successful swap, the Stage 11 cockpit SHALL default operator focus to the pane that has just been swapped into the active slot. The cockpit MUST also provide an explicit mechanism for returning focus to the cockpit pane.

#### Scenario: Focus moves to swapped-in active pane
- **WHEN** pane `%1` is swapped into the active slot previously occupied by `%4`
- **THEN** the operator focus MUST move to `%1` by default and the cockpit MUST preserve a way to return to the cockpit pane

### Requirement: Pane detail and global jobs use hybrid data sources
The Stage 11 cockpit SHALL source pane existence, size, command, title, and snapshot information from live tmux state. The cockpit SHALL source job and trace data primarily from Stage 3 lifecycle artifacts, coordinator state, and registry metadata. If job mapping is incomplete, the cockpit MUST continue to display pane state and MUST mark missing job data explicitly as degraded, unknown, unmapped, or no artifact.

#### Scenario: Pane state remains available when job mapping is incomplete
- **WHEN** a visible pane exists in tmux but no matching lifecycle or coordinator artifact can be resolved for it
- **THEN** the cockpit MUST still display the pane in the work list and pane detail view, and MUST mark the job-related area as degraded or unmapped

### Requirement: Active slot loss enters degraded state
If the active slot disappears after startup, the Stage 11 cockpit SHALL enter a degraded state instead of silently choosing a replacement pane. In degraded state, the cockpit MUST clearly indicate that the active slot has been lost and MUST require explicit operator action or restart before active-slot-dependent swap behavior resumes.

#### Scenario: Lost active slot does not silently reassign
- **WHEN** the pane recorded as the active slot is destroyed or no longer visible to tmux during a cockpit session
- **THEN** the cockpit MUST enter degraded state, MUST indicate that the active slot is lost, and MUST NOT automatically assign a new active slot
