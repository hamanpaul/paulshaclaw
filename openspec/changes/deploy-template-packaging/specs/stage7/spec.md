## MODIFIED Requirements

### Requirement: Stage 7 deploy templates are complete release assets

The Stage 7 deploy template catalog MUST be packaged as data in the `paulshaclaw` wheel and
sdist. Source, source sdist, and a wheel rebuilt from that sdist MUST expose the same non-empty
relative template path set, and that set MUST cover every template selected by the planner.

#### Scenario: All build forms preserve the planner template set

- **WHEN** a candidate source tree is built as a wheel and sdist, and the sdist is rebuilt as a
  wheel
- **THEN** each artifact's deploy template relative-path set MUST equal the non-empty source set
- **THEN** the planner-selected assets MUST be a subset of that source set

### Requirement: Artifact verification is shared and fail-closed

Release and pull-request artifact gates MUST invoke the same checker for wheel and sdist content.
The checker MUST reject missing or unexpected assets, duplicate or non-template template members,
genuinely empty template directories, forbidden template strings, unreadable files, corrupt
archives, and missing archive paths with a non-zero result.

#### Scenario: Template packaging drift blocks the gate

- **WHEN** an artifact omits a template, adds an unexpected path, or contains an empty template
  directory
- **THEN** the shared checker MUST report the failing asset and exit non-zero

## ADDED Requirements

### Requirement: Install and upgrade preflight precedes host mutation

`install` and `upgrade` MUST read and render every required template before any host-side file
write, checkpoint creation, `loginctl`, or `systemctl` operation. A template preflight failure MUST
return exit 1 and one JSON report containing `status=failed`, instance/root context, failed assets,
and an actionable message. Artifact checksum failures MUST retain exit 2.

#### Scenario: Missing final template leaves no partial install

- **WHEN** the last planner-selected template is missing during install or upgrade preflight
- **THEN** the command MUST return exit 1 with one failure JSON report
- **THEN** it MUST NOT write deployment files, an install record, a checkpoint, or systemd state

#### Scenario: Plan-only uses the same failure contract

- **WHEN** plan-only install or upgrade cannot read a required template
- **THEN** it MUST return the same exit-1 JSON contract, while status and uninstall remain usable

### Requirement: Installed-wheel acceptance is isolated from the checkout

Packaging acceptance MUST install the candidate wheel into a clean virtual environment and invoke
deploy from outside the checkout with checkout `PYTHONPATH` removed. The report MUST validate
applied files, permissions, install-record version and checksum, and MUST mark unavailable systemd
as skipped or on-host-only rather than claiming service startup.

#### Scenario: Clean installed wheel performs deploy install

- **WHEN** a clean venv runs `python -m paulshaclaw.deploy install --apply --verify` outside the
  repository
- **THEN** the loaded module MUST come from the venv, deploy output MUST be valid JSON, and the
  install record MUST contain the requested version and artifact SHA

### Requirement: Packaging test tooling is present before pytest

The PR test workflow and local preflight MUST install the `build` frontend in the same operator
runtime before running pytest, because packaging acceptance tests invoke `python -m build`.

#### Scenario: Preflight can execute packaging acceptance

- **WHEN** the declared pytest gate starts in CI or through `scripts/preflight-tests.sh`
- **THEN** `python -m build` MUST be available to the test subprocesses before collection reaches
  the packaging acceptance tests
