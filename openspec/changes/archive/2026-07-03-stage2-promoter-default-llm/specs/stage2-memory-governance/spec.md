## ADDED Requirements

### Requirement: Atomizer default promoter is LLM distillation

Stage 2 SHALL ship the atomizer with `promoter: llm` as the packaged default (`paulshaclaw/memory/atomizer/atomizer.yaml`). Any CLI path invoked without an explicit `--promoter` flag (`memory atomize`, `memory dream run`) MUST resolve to the LLM promoter and MUST NOT construct an `IdentityPromoter`. The identity promoter MUST remain available as an explicit `--promoter identity` option for tests and offline deterministic runs. The code-level fallback for configs that omit the `promoter` key entirely MUST remain `identity` (fail-safe: a stripped-down config never silently upgrades into spawning an external LLM call).

#### Scenario: Packaged config default resolves to llm

- **WHEN** `atomizer.config.load_config(override_path=None)` loads the packaged `atomizer.yaml`
- **THEN** the resulting `AtomizerConfig.default_promoter` MUST equal `"llm"`

#### Scenario: CLI without --promoter builds the LLM promoter

- **WHEN** `atomizer.cli._build_promoter` is called with `args.promoter = None` against the packaged config
- **THEN** the returned promoter MUST be an `LLMPromoter` instance
- **THEN** it MUST NOT be an `IdentityPromoter` instance

#### Scenario: Explicit identity flag is still honored

- **WHEN** `atomizer.cli._build_promoter` is called with `args.promoter = "identity"`
- **THEN** the returned promoter MUST be an `IdentityPromoter` instance

#### Scenario: Config omitting the promoter key fails safe to identity

- **WHEN** `load_config` reads a config file that contains no `promoter` key
- **THEN** `default_promoter` MUST resolve to `"identity"`
- **THEN** no LLM agent process MAY be spawned as a side effect of loading configuration

### Requirement: Scheduled dream templates pin the LLM promoter

The repo-shipped schedule templates (`paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh` and `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service`) SHALL pin `--promoter llm` explicitly, matching the production dream loop (`scripts/start.sh`). Each template MUST carry a comment documenting the identity promoter's boilerplate-output risk: identity copies importer template fragments 1:1 into knowledge slices and the noise gate only drops part of that boilerplate.

#### Scenario: Wrapper pins llm

- **WHEN** an operator inspects `dream-idle-wrapper.sh`
- **THEN** its `memory dream run` invocation MUST contain `--promoter llm`
- **THEN** it MUST NOT contain `--promoter identity`
- **THEN** a comment MUST explain the identity boilerplate risk

#### Scenario: Systemd service pins llm

- **WHEN** an operator inspects `paulsha-memory-dream.service`
- **THEN** its `ExecStart` MUST contain `--promoter llm`
- **THEN** it MUST NOT contain `--promoter identity`

#### Scenario: Enabling the systemd timer does not reintroduce identity promotion

- **WHEN** the (currently uninstalled) systemd timer/service pair is enabled without modification
- **THEN** every scheduled dream run MUST use the LLM promoter
