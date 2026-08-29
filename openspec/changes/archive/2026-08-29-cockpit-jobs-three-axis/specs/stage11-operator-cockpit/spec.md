## ADDED Requirements

### Requirement: JOBS panel ingests workflow-run status without losing legacy slice compatibility
The Stage 11 cockpit SHALL ingest JOBS data from both legacy slice-style manager status entries and the
workflow-run status plane. When a manager entry lacks `slice_id`, `id`, `name`, or `title` but carries
`work_id` or `run_id`, the cockpit MUST still surface the row. For workflow-run rows the cockpit MUST
preserve `repo`, `current_phase`, `run_id`, and the human-readable `blocking_reason.detail` when present.
The cockpit SHALL continue to accept legacy `slice` entries unchanged. `status.not_claimable` entries MUST
surface as a synthetic `未認領` phase, and a missing `not_claimable` key MUST be treated as an empty list.

#### Scenario: workflow-run rows without legacy identifiers are still shown
- **WHEN** manager status `in_flight` or `attention` contains `workflow_run` entries with `work_id`,
  `current_phase`, `run_id`, and `blocking_reason`, but without `slice_id`, `id`, `name`, or `title`
- **THEN** the JOBS panel MUST render those entries instead of dropping them
- **AND** the rendered reason MUST prefer `blocking_reason.detail` over machine `reason` when both are present

#### Scenario: not_claimable rows become an unclaimed phase
- **WHEN** manager status includes `not_claimable` items with `work_id` and `next_step_hint`
- **THEN** the JOBS panel MUST render them as phase `未認領`
- **AND** absence of the `not_claimable` key MUST NOT fail rendering

### Requirement: JOBS panel groups work on project, stage, and agent axes
The Stage 11 cockpit SHALL provide three JOBS grouping axes: `project`, `stage`, and `agent`. Pressing `g`
MUST cycle them in the order `project → stage → agent → project`, and the JOBS border subtitle MUST show
`[by <axis>]` for the active axis. The project axis SHALL group by repo, the stage axis by `current_phase`,
and the agent axis by the derived persona mapping (`claim` / `ship` → manager, `define` / `plan` → planner,
`build` → builder, `verify` / `review` → reviewer). Group sorting MUST surface human-actionable or in-flight
work before `claim` backlog, `recent_done`, and `未認領` rows. Expansion state MUST be preserved per axis
within the running cockpit session.

#### Scenario: operator cycles axes without losing per-axis expansion
- **WHEN** the operator presses `g` three times while the JOBS panel is open
- **THEN** the cockpit MUST cycle the subtitle through `[by stage]`, `[by agent]`, and back to `[by project]`
- **AND** groups expanded on one axis MUST still be expanded when the operator returns to that axis

#### Scenario: claim backlog stays below active pipeline work
- **WHEN** the JOBS data contains in-flight rows, `claim` rows, `recent_done` rows, and `未認領` rows
- **THEN** groups containing human-actionable or in-line pipeline work MUST sort before claim backlog
- **AND** `recent_done` groups MUST sort below active pipeline work
- **AND** `未認領` groups MUST sort last

#### Scenario: project axis keeps recent_done rows inside their repo group
- **WHEN** workflow-run rows and legacy `recent_done` rows from the same repo appear together on the project axis
- **THEN** the cockpit MUST keep those `recent_done` rows inside the repo group instead of splitting them into
  standalone `wf-*` groups

### Requirement: JOBS rows show semantic counts and safe detail lines
The Stage 11 cockpit SHALL render the JOBS border title as `JOBS · N 件` with non-zero suffix counts for
`在管線`, `待認領`, and `不可認領`. JOBS tree rows that carry actionable detail MUST keep that detail in child
rows, but those detail rows MUST be collapsed by default to preserve the 12-line viewport. Workflow-run detail
rows MUST show the available `next_actions` and `run_id` instead of emitting a `cortex slice-action` command
that lacks fail-closed parameters. A `claim` row awaiting dispatch MUST state `尚未派工`.

#### Scenario: workflow-run detail avoids invalid slice-action commands
- **WHEN** a `workflow_run` row is `needs_human` and carries `next_actions=["retry-build","abandon"]` plus
  `run_id="run-xyz"`
- **THEN** its detail row MUST include `retry-build|abandon` and `run-xyz`
- **AND** the detail row MUST NOT render a `cortex slice-action` command

#### Scenario: needs-human detail rows start collapsed
- **WHEN** a group or row with actionable detail is mounted in the JOBS tree
- **THEN** the detail child MUST exist
- **AND** that detail child MUST be collapsed until the operator expands it

#### Scenario: claim rows identify undispatched work
- **WHEN** a `claim` row requires human attention before a run exists
- **THEN** its detail MUST state `尚未派工`
- **AND** the cockpit MUST NOT render a workflow action command for that row
