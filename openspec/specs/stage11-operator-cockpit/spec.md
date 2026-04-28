## ADDED Requirements

### Requirement: Cockpit lists panes from all local tmux sessions
The Stage 11 cockpit SHALL enumerate panes from every local tmux session visible to the tmux server. Each pane record MUST include the pane ID, session name, window index, title, command, geometry, active flag, and preview data needed by the existing cockpit UI.

#### Scenario: All-session pane scan includes session and window metadata
- **WHEN** the tmux server contains panes in sessions `main` and `work`
- **THEN** the cockpit pane scan MUST include panes from both sessions and MUST preserve each pane's `session_name` and `window_index`

### Requirement: Work list remains flat and identifies pane origin
The Stage 11 cockpit SHALL display a flat work list rather than grouping panes by session. Every visible pane label MUST include the `session:window` prefix, pane ID, and pane title so an operator can identify where the pane came from.

#### Scenario: Candidate list shows session-window context
- **WHEN** the candidate list contains pane `%12` from session `work`, window index `2`, with title `pytest`
- **THEN** the cockpit MUST render a candidate label containing `work:2 %12 pytest`

### Requirement: Active slot selection is scoped to the cockpit session
The Stage 11 cockpit SHALL derive the cockpit session from the cockpit pane record at startup. Startup active-slot selection MUST exclude the cockpit pane itself and MUST choose only from panes whose `session_name` matches the cockpit session.

#### Scenario: Larger pane in another session is not selected as active slot
- **WHEN** the cockpit pane is in session `main`, pane `%9` in session `work` is larger than every `main` session candidate, and pane `%4` is the largest non-cockpit pane in session `main`
- **THEN** the cockpit MUST select `%4` as the active slot and MUST NOT select `%9`

### Requirement: Active-slot refresh ignores matching geometry in other sessions
The Stage 11 cockpit SHALL reconcile active-slot existence only against panes in the cockpit session. A pane in another session with the same geometry as the active-slot anchor MUST NOT be treated as the active slot.

#### Scenario: Other-session anchor collision does not preserve active slot
- **WHEN** the active-slot anchor was recorded from session `main` and pane `%20` in session `work` has the same left/top geometry after refresh
- **THEN** the cockpit MUST NOT treat `%20` as the active slot for session `main`

### Requirement: Candidate section includes all non-cockpit non-active panes
The Stage 11 cockpit SHALL list every non-cockpit pane that is not the cockpit-session active slot as a candidate. Candidate panes MUST include panes from other sessions and non-active-slot panes from the cockpit session, sorted by `(session_name, window_index, pane_id)`.

#### Scenario: Candidate section spans sessions with deterministic ordering
- **WHEN** panes `%3`, `%7`, and `%2` are candidates across sessions `alpha` and `beta`
- **THEN** the candidate section MUST include all three panes sorted by session name, window index, and pane ID

### Requirement: Enter swaps selected pane with active slot across sessions
The Stage 11 cockpit SHALL keep `Enter` as the only swap trigger. When the operator presses `Enter` on a selected candidate, the cockpit MUST call the existing layout action service with the selected pane ID and active-slot pane ID, then rebuild cockpit state from a fresh tmux scan.

#### Scenario: Selected pane from another session swaps into active slot
- **WHEN** the active slot is `%4` in session `main`, the selected candidate is `%12` in session `work`, and the operator presses `Enter`
- **THEN** the cockpit MUST invoke a swap from `%12` to `%4` and MUST refresh pane state from tmux after the swap

### Requirement: Startup fails when cockpit pane cannot identify its session
The Stage 11 cockpit SHALL preserve the existing missing-cockpit-pane startup failure behavior. If the cockpit pane ID cannot be found in the all-session pane scan, startup MUST print the existing error path and exit with status `1`.

#### Scenario: Missing cockpit pane keeps existing failure path
- **WHEN** the cockpit starts with cockpit pane ID `%0` and the all-session tmux scan contains no pane `%0`
- **THEN** the cockpit MUST exit with status `1` and MUST NOT guess a cockpit session

### Requirement: Cockpit provides footer and modal hotkey help
The Stage 11 cockpit SHALL provide short descriptions for visible bindings in the footer and SHALL bind `?` to a modal help screen. The modal MUST list the cockpit bindings and explain the multi-session pane-listing and swap behavior. Pressing `Esc` in the modal MUST dismiss it.

#### Scenario: Question mark opens and escape dismisses help
- **WHEN** the cockpit is running and the operator presses `?`
- **THEN** the cockpit MUST show the help modal
- **WHEN** the operator presses `Esc` while the help modal is active
- **THEN** the cockpit MUST dismiss the help modal and return to the cockpit screen
