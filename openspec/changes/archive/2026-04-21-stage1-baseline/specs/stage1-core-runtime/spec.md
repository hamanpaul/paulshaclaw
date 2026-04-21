## ADDED Requirements

### Requirement: Daemon status command

The PaulShiaBro daemon SHALL expose a `/status` command that returns a JSON object describing the current runtime snapshot. The JSON payload MUST contain exactly the keys `ok`, `daemon`, `project`, `pane_count`, and `allowed_user_count`. `ok` MUST be boolean; `daemon` and `project` MUST be strings derived from the loaded config; `pane_count` MUST be the integer length of the configured pane assignments; `allowed_user_count` MUST be the integer length of the Telegram authorization whitelist.

#### Scenario: Status returns configured snapshot

- **WHEN** a caller invokes `/status` on a daemon loaded with a config that declares a `daemon_name`, `default_project`, three pane assignments, and two allowed user ids
- **THEN** the returned JSON MUST satisfy `{"ok": true, "daemon": <daemon_name>, "project": <default_project>, "pane_count": 3, "allowed_user_count": 2}`

### Requirement: Daemon dispatch command

The daemon SHALL expose a `/dispatch <task_id>` command that forwards to the coordinator seam and returns a JSON object containing exactly the keys `ok`, `job_id`, `phase`, and `scope`. The `phase` MUST equal the configured `coordinator.phase`. The `scope` MUST equal the supplied `task_id`. The payload passed to the coordinator MUST be the configured `coordinator.default_payload` with a `task_id` key added. A `/dispatch` without a `task_id` MUST raise an error before any coordinator call.

#### Scenario: Dispatch forwards task to coordinator

- **WHEN** a caller invokes `/dispatch job-42` on a daemon whose config declares `coordinator.phase = "build"` and `coordinator.default_payload = {"project": "paulshaclaw"}`
- **THEN** the coordinator MUST be called once with `phase="build"`, `scope="job-42"`, and `payload={"project": "paulshaclaw", "task_id": "job-42"}`; and the returned JSON MUST contain `ok=true`, `phase="build"`, and `scope="job-42"`

#### Scenario: Dispatch rejects missing task id

- **WHEN** a caller invokes `/dispatch ` (empty task id)
- **THEN** the daemon MUST raise a validation error and MUST NOT call the coordinator

### Requirement: Config loader precedence

The config loader SHALL resolve the config file path using a fixed precedence: the explicit `--config` CLI flag first, then the `PSC_STAGE1_CONFIG` environment variable, and finally a validation error if neither is provided. The loader MUST parse JSON, reject non-object payloads, and MUST validate that the top-level object contains `daemon_name`, `default_project`, `coordinator`, and `pane_assignments`. Missing required fields MUST produce an error that names the missing field path.

#### Scenario: Explicit flag overrides environment

- **WHEN** both `--config /path/a.json` is passed AND `PSC_STAGE1_CONFIG=/path/b.json` is set in the environment
- **THEN** the loader MUST read `/path/a.json` and MUST NOT read `/path/b.json`

#### Scenario: Environment fallback when flag absent

- **WHEN** `--config` is not passed AND `PSC_STAGE1_CONFIG=/path/c.json` is set
- **THEN** the loader MUST read `/path/c.json`

#### Scenario: Missing required field is reported

- **WHEN** the loaded JSON lacks the `pane_assignments` key
- **THEN** the loader MUST raise a validation error whose message contains `config.pane_assignments`

### Requirement: Coordinator seam

The daemon runtime SHALL define a `CoordinatorClient` Protocol that exposes exactly one method: `create_job(*, phase: str, scope: str, payload: dict) -> dict`. The runtime MUST ship a default `LocalCoordinator` implementation that returns a dict containing `job_id`, `phase`, `scope`, and the echoed `payload`. Consumers (Stage 3, etc.) MUST be able to inject an alternative `CoordinatorClient` via the daemon constructor without modifying daemon source code.

#### Scenario: Custom coordinator is honored

- **WHEN** a caller constructs the daemon with a custom `CoordinatorClient` that records every call
- **THEN** invoking `/dispatch` MUST route through the custom coordinator and MUST NOT fall back to `LocalCoordinator`

### Requirement: CLI entry point

The daemon SHALL be invocable as a CLI via `python -m paulshaclaw.core.daemon --config <path> --command <command>`. The CLI MUST print the JSON result to stdout on success with exit code 0. On a validation error, a missing file, or an unsupported command, the CLI MUST print the error message to stderr and exit with code 1; no Python traceback MUST leak to stderr.

#### Scenario: Success prints JSON to stdout

- **WHEN** the CLI is invoked with a valid `--config` and `--command /status`
- **THEN** stdout MUST contain a JSON line matching the `/status` shape and the process MUST exit 0

#### Scenario: Invalid command exits cleanly

- **WHEN** the CLI is invoked with `--command /unknown`
- **THEN** stderr MUST contain a short error message (no Python traceback) and the process MUST exit 1

### Requirement: Telegram authorization gate

The Telegram bot router SHALL reject inbound commands whose user id is not present in `config.allowed_user_ids`, returning a refusal message and MUST NOT invoke the daemon. For authorized user ids, the router MUST forward the normalized command to the daemon and surface the daemon response (success) or the daemon's validation error (failure) to the caller.

#### Scenario: Unauthorized user is rejected

- **WHEN** a Telegram update arrives from user id `9999` while `allowed_user_ids = (1001,)`
- **THEN** the router MUST return a refusal message identifying the user as unauthorized, and the daemon's `handle_command` MUST NOT be called

#### Scenario: Authorized user is routed

- **WHEN** a Telegram update arrives from user id `1001` with text `/status` while `allowed_user_ids = (1001,)`
- **THEN** the router MUST call the daemon's `handle_command("/status")` exactly once and MUST surface the returned snapshot to the caller

### Requirement: TUI pane and task listing

The TUI SHALL render a view listing every configured pane assignment and its current task id and status. The renderer MUST be deterministic for a given config (stable ordering, no hidden state). The renderer MUST NOT require a real tmux session — it operates over the `PaneAssignment` tuples from the loaded config.

#### Scenario: Renderer enumerates configured panes

- **WHEN** the TUI view is rendered for a config with pane assignments `[{id:"0", title:"stage1", task:"T-1", status:"active"}, {id:"1", title:"stage2", task:"T-2", status:"idle"}]`
- **THEN** the rendered output MUST contain both pane ids, both titles, both task ids, and both status values, with the two panes appearing in the configured order

### Requirement: Sample config schema

The repository SHALL provide `config/paulshaclaw-stage1.sample.json` as a loadable sample that validates against the config loader contract. The sample MUST declare all required top-level fields (`daemon_name`, `default_project`, `coordinator`, `pane_assignments`) and MUST parse successfully via `load_config` without further modification.

#### Scenario: Sample config loads

- **WHEN** a caller invokes `load_config(config_path="config/paulshaclaw-stage1.sample.json")`
- **THEN** the call MUST return an `AppConfig` instance with non-empty `daemon_name`, `default_project`, and at least one `pane_assignments` entry

### Requirement: Smoke test harness

Stage 1 SHALL ship a smoke test suite at `tests/test_stage1_smoke.py` that collectively exercises: config loader happy path, config loader env fallback, config loader missing-field rejection, daemon `/status`, daemon `/dispatch` (with a fake coordinator to assert call args), TUI pane listing, Telegram router authorized route, Telegram router unauthorized rejection, Telegram router invalid-command surface, CLI success path, CLI clean-error path, and CLI env-config path. All cases MUST be executable via `python -m unittest discover -s tests` and MUST exit with zero failures.

#### Scenario: Smoke suite passes on merged main

- **WHEN** an operator runs `python -m unittest discover -s tests -v` from the repo root on main
- **THEN** the suite MUST report all Stage 1 smoke cases as `ok` and exit zero
