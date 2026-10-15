## ADDED Requirements

### Requirement: Missing authority remains unknown in job projections
The cockpit SHALL preserve supplied submitted, running, blocked, failed and completed states.
Absent, blank, null or non-text state fields MUST render as unknown rather than infer running
from in_flight/slices membership or success from recent_done membership. Recent failures MUST
remain distinguishable from successful completions. An archived lifecycle marker MUST remain
visible alongside its independent gate outcome; recent_done history MUST NOT count as live work.

#### Scenario: Missing state is not promoted to execution or completion
- **WHEN** an in_flight, workflow_run, slices or recent_done item has no usable state
- **THEN** its state and visible status SHALL remain unknown with neutral styling

#### Scenario: Archived failed work remains historical failure
- **WHEN** a recent_done item carries a failed gate outcome or archived run_status
- **THEN** the projection SHALL preserve failure or archived respectively, retaining both when supplied
- **AND** it SHALL exclude that historical row from the active job count
