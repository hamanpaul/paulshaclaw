## MODIFIED Requirements

### Requirement: Release launcher reuses the active Cortex manager

The release launcher MUST recognize a live Cortex manager whose kernel lock is
held at either the instance layout `~/.agents/control/cortex/manager.lock` or the
legacy flat layout `~/.agents/control/manager.lock`. A lock file that is absent or
not held MUST NOT be treated as a live manager. When either supported lock is held,
the launcher MUST NOT start its fallback manager daemon.

#### Scenario: Cortex instance lock prevents fallback startup

- **WHEN** the Cortex manager holds a kernel flock on
  `~/.agents/control/cortex/manager.lock`
- **THEN** release startup MUST report that Cortex manager is already running and
  MUST NOT spawn `paulsha_cortex.coordinator.manager_daemon`

#### Scenario: Stale instance lock does not count as live

- **WHEN** `~/.agents/control/cortex/manager.lock` exists but no process holds its
  kernel flock
- **THEN** the launcher MUST treat the manager as unavailable and MAY start its
  bounded fallback according to the existing contract

### Requirement: Release launcher supports the documented no-cockpit form

The `paulshaclaw` console entry point MUST accept both
`paulshaclaw --no-cockpit` and `paulshaclaw up --no-cockpit`. Both forms MUST call
the same foreground supervisor with `no_cockpit=True`. The launcher MUST retain
the existing implicit `up`, explicit `up`, `down`, and `status` behavior and MUST
NOT add lifecycle-state words as commands.

#### Scenario: Top-level no-cockpit uses the default up command

- **WHEN** an operator runs `paulshaclaw --no-cockpit`
- **THEN** the launcher MUST invoke the release supervisor with
  `no_cockpit=True`

#### Scenario: Explicit up remains compatible

- **WHEN** an operator runs `paulshaclaw up --no-cockpit`
- **THEN** the launcher MUST invoke the same release supervisor with
  `no_cockpit=True`
