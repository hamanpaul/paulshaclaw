## ADDED Requirements

### Requirement: JOBS displays producer execution identity with its source
The cockpit MUST preserve the typed `executor`, `model`, `job_id`, `card`, `identity_source`, and `execution_state` fields from Cortex workflow status rows in `in_flight`, `attention`, and `recent_done`. The JOBS panel SHALL show full literal executor and model strings in an expandable detail row for every grouping axis. It MUST distinguish actual execution, last execution, planned identity, and unavailable identity without inferring identity from persona or phase. Existing reason, next actions, and run identifiers MUST remain available.

#### Scenario: Blocked workflow retains last execution identity
- **WHEN** Cortex reports `identity_source=last-execution` and an exited executor/model
- **THEN** the detail MUST label the identity as 上次執行, preserve the execution state and binding identifiers, and MUST NOT claim that the executor is still running

#### Scenario: Planned and unavailable identity remain distinct
- **WHEN** a row reports planned identity or no dispatched identity
- **THEN** the panel MUST identify planned values as 預定／未派工 and display unavailable values as 未提供 rather than using the role as an executor

#### Scenario: Narrow panel and refresh retain literal identity
- **WHEN** a retry changes the executor/model or a long model includes markup-like characters
- **THEN** refreshing and expanding the row MUST show the new complete literal string without retaining the previous model

#### Scenario: Older or malformed snapshots are readable
- **WHEN** identity fields are absent, null, or have invalid types
- **THEN** the consumer MUST use empty typed defaults and show unavailable identity while preserving the existing workflow information
