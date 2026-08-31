## MODIFIED Requirements

### Requirement: Release wheel contains launcher runtime data

The built `paulshaclaw` wheel MUST contain every immutable data file required by
the release launcher and Stage 1 command routing, including
`paulshaclaw/core/commands.json`. Release verification MUST inspect the built
wheel or a clean installation; importing from the repository source tree MUST NOT
be accepted as evidence of package completeness.

#### Scenario: Built wheel contains the command registry

- **WHEN** the project builds a wheel from the candidate source revision
- **THEN** the wheel archive MUST contain
  `paulshaclaw/core/commands.json`

### Requirement: Installed launcher starts from arbitrary directories

The pipx-installed `paulshaclaw` executable MUST start without relying on the
repository current working directory or a repository-injected module path. Final
acceptance MUST run the installed executable from at least two non-repository
directories, observe ready state, terminate it, and verify that owned child
processes and the release start lock are cleaned up.

#### Scenario: Installed no-cockpit startup is self-contained

- **WHEN** an operator starts `paulshaclaw --no-cockpit` from `/tmp`
- **THEN** startup MUST pass command-registry and Cortex readiness boundaries
  using installed files, and termination MUST leave no owned child or stale start
  lock

#### Scenario: Bare installed command starts the cockpit

- **WHEN** an operator starts bare `paulshaclaw` in a controlled tmux pane whose
  current directory is outside the repository
- **THEN** the installed release launcher MUST reach cockpit ready state and MUST
  cleanly stop when the operator terminates it
