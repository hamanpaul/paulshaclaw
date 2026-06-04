## ADDED Requirements

### Requirement: Gate-protected atomize-skill optimization

Stage 2 SHALL provide a `paulshaclaw/memory/skillopt/` code module that refines the atomizer's `atomize-knowledge-slice.md` SKILL using a vendored copy of the `evolve` generic SkillOpt loop. The module MUST treat the SKILL as a trainable artifact and MUST only overwrite it when a candidate scores strictly higher than the baseline on the validation set and is a structurally valid skill; otherwise the original SKILL MUST remain unchanged. The vendored loop MUST preserve the upstream behavior (validation gate, fail-closed sanitized errors, pre-write backup to `skillopt-history/`, records limited to scores/counts/decision). The module MUST be a code module, not a skill, and MUST run as an offline CLI that is NOT wired into the dream loop in this change.

#### Scenario: Candidate that does not improve is rejected

- **WHEN** `psc memory skillopt run` produces a candidate whose mean validation score is not strictly greater than the baseline
- **THEN** `atomize-knowledge-slice.md` MUST remain byte-identical to its pre-run content
- **THEN** the run result reason MUST be `rejected: no improvement`

#### Scenario: Improving candidate is accepted with backup

- **WHEN** a candidate scores strictly higher than baseline on the validation set and is a valid skill
- **THEN** the prior skill MUST be backed up under `skillopt-history/<skill_stem>/<ts>.md` before the overwrite
- **THEN** `atomize-knowledge-slice.md` MUST be updated to the candidate
- **THEN** an append-only record limited to scores/counts/decision MUST be written to `runtime/ledger/skillopt.jsonl`

#### Scenario: Model failure leaves the skill unchanged

- **WHEN** the rollout (gemma4), optimizer (codex), or judge model times out or raises
- **THEN** the run MUST fail closed with reason `error`, returning no partial scores
- **THEN** `atomize-knowledge-slice.md` MUST remain unchanged

### Requirement: Reuse importer and atomizer without duplication

The SkillOpt module SHALL NOT re-implement session scanning or project resolution; it MUST consume importer-produced inbox fragments and the `project` value already present in their frontmatter. The atomize rollout MUST reuse the existing `build_prompt` + `LLMPromoter` by injecting the candidate `skill_text`, and MUST NOT fork a separate atomization splitter. Cross-folder-same-project identity MUST be taken from the importer's `project_resolver` (driven by `projects.yaml` roots/remotes) and MUST NOT be delegated to the LLM judge.

#### Scenario: Project comes from importer, not the judge

- **WHEN** the val_set builder assigns a project to a fragment
- **THEN** it MUST read the `project` field written by the importer
- **THEN** the LLM judge MUST NOT be asked to assign or correct the project

#### Scenario: Rollout injects the candidate skill

- **WHEN** the loop evaluates a candidate `skill_text`
- **THEN** that exact `skill_text` MUST be the skill passed into `build_prompt` for the atomize rollout

### Requirement: Project-stratified deterministic validation set with reference-only `~/notes`

The val_set builder SHALL stratify items by `project` and split each project's items into train/validation deterministically, such that identical inputs always yield identical splits (e.g. via a hash of `"<session_id>#<fragment_index>"`), with no wall-clock or random source. A project with fewer than the configured minimum sample size MUST contribute all its items to train and none to validation, and the downgrade MUST be logged. The `~/notes` Obsidian vault MUST be used read-only as reference exemplars (semantic content only, frontmatter ignored) supplied to the judge as a rubric; it MUST NOT be used as a paired gold target, MUST NOT be written, and `PersonalVault` MUST be excluded.

#### Scenario: Deterministic split is reproducible

- **WHEN** `build_valset` runs twice over the same inbox content
- **THEN** the train/validation partitions MUST be identical across runs

#### Scenario: Sparse project avoids noisy validation

- **WHEN** a project has fewer items than the configured minimum sample size
- **THEN** all of that project's items MUST go to train and none to validation
- **THEN** the downgrade MUST be logged

#### Scenario: `~/notes` is reference only

- **WHEN** the builder or judge accesses `~/notes`
- **THEN** access MUST be read-only and limited to semantic content used as judge rubric
- **THEN** `PersonalVault` MUST NOT be read
- **THEN** no run MUST treat a `~/notes` note as a 1:1 gold target

### Requirement: LLM judge scores atomization quality only

The validation gate SHALL score each rollout output with a hybrid of a deterministic structural score and an LLM judge, combined as a weighted sum that yields an absolute 0–1 score per output (preserving the generic loop's `score(output, gold)` contract). The structural score MUST be used for train-failure ranking. The judge MUST evaluate atomization quality only — slice granularity, concept boundary, one-concept-per-slice, and relation soundness — and MUST NOT evaluate project assignment.

#### Scenario: Structural score ranks train failures

- **WHEN** the loop selects failures from the train set
- **THEN** it MUST rank by the deterministic structural score (no LLM call required)

#### Scenario: Hybrid score gates validation

- **WHEN** the loop scores a candidate on the validation set
- **THEN** the score MUST combine structural and judge components into a single 0–1 value
- **THEN** the judge MUST NOT be prompted to assign or correct the project
