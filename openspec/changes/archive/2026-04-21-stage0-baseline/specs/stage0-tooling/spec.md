## ADDED Requirements

### Requirement: Tool rename matrix

Stage 0 MUST maintain a canonical tool rename matrix at `openspec/specs/stage0/tool-matrix.md` that records, for every project-tuned skill/tool, the old name, target name, source repo, final placement, Claude Code support status, and tracking link for the rename/refine work. The matrix MUST cover the six Stage 0 rename targets identified in research 05 §8 (`picoclaw-ops-companion` → `ops-companion`, `obs-auto-moc` → `paulsha-memory`, `codex-lesson`, `codex-project-insights`, `session-health`, `coordinator`). The matrix MUST also declare the sync-back gate that governs when a locally tuned skill is allowed to be pushed back to `hamanpaul/custom-skills`.

#### Scenario: Rename matrix completeness

- **WHEN** a reviewer reads `openspec/specs/stage0/tool-matrix.md`
- **THEN** the B-section table MUST list all six rename targets, each with non-empty values in the 舊名 / 目標名 / 來源 repo / 最終落點 / Claude Code 支援狀態 / tracking columns

#### Scenario: Sync-back gate declared

- **WHEN** a reviewer reads the D-section of the tool-matrix
- **THEN** the document MUST state that any skill synced back to `hamanpaul/custom-skills` MUST first pass its owning stage's tests and retain test evidence

### Requirement: External reference manifest

Stage 0 MUST pin every external reference repo used for reading/comparison at `openspec/specs/stage0/ref-manifest.yaml`. The manifest MUST enumerate each repo's name, GitHub slug, local path under `ref/`, stage dependencies, pin commit SHA, and status. It MUST also declare `tracked_in_git: false` and `runtime_source: false` so that `ref/` never participates in runtime load paths.

#### Scenario: Five repos pinned

- **WHEN** a reviewer parses `openspec/specs/stage0/ref-manifest.yaml`
- **THEN** the `repos` array MUST contain at least the five baseline entries (`custom-claw-tools`, `custom-skills`, `max`, `serialwrap`, `testpilot`), each with a non-empty `pin` commit SHA

#### Scenario: Ref is not runtime

- **WHEN** a reviewer parses the manifest's `policy` block
- **THEN** `tracked_in_git` MUST be `false` and `runtime_source` MUST be `false`

### Requirement: Worktree helper script

Stage 0 MUST provide `scripts/using-git-worktrees.sh` that manages per-stage worktrees under `/home/paul_chen/prj_pri/paulshaclaw-worktrees/<workstream>/` and the matching `wt/<workstream>` branch. The helper MUST cover four branching paths — (a) remote-tracking branch missing, (b) stale remote ref auto-pruned, (c) local branch already exists, (d) fresh branch creation — and MUST use distinct non-zero exit codes for the recoverable failure cases so that callers can distinguish them.

#### Scenario: Stale remote ref is auto-pruned

- **WHEN** a caller invokes the helper with a workstream whose remote ref no longer exists upstream
- **THEN** the helper MUST remove the stale remote ref and continue branch creation without operator intervention

#### Scenario: Pre-existing local branch is reused

- **WHEN** a caller invokes the helper for a workstream that already has a local `wt/<workstream>` branch and worktree
- **THEN** the helper MUST reuse the existing branch and exit successfully rather than duplicating worktree entries

### Requirement: Ref sync script

Stage 0 MUST provide `scripts/sync-ref.sh` that reads `openspec/specs/stage0/ref-manifest.yaml` and performs shallow clones of each enumerated repo at the declared `pin` commit into the declared local path. The script MUST be idempotent — re-running it on an already-synced workspace MUST NOT delete or re-download unchanged repos.

#### Scenario: Manifest drives clone targets

- **WHEN** the operator runs `scripts/sync-ref.sh` on a clean workspace
- **THEN** the script MUST clone exactly the repos listed in the manifest's `repos` block into the paths declared by each entry's `path` field

### Requirement: Stage 0 regression harness

Stage 0 MUST ship `scripts/test-stage0-tooling-foundation.sh` as the executable acceptance for research 05 §8 Stage 0. The harness MUST run a fixed catalogue of checks that collectively verify (a) the opsx slash-command prompt dual source stays drift-free, (b) the `wt/<workstream>` remote branches declared in the parallel plan all exist, and (c) the worktree helper's four branching paths each produce the expected exit code. Every check MUST exit zero for the harness to report PASS.

#### Scenario: Harness catches opsx prompt drift

- **WHEN** `.claude/commands/opsx/<name>.md` and `.github/prompts/opsx-<name>.prompt.md` diverge in body content
- **THEN** the harness MUST fail with a non-zero exit and an error identifying the drifting file pair

#### Scenario: Harness validates worktree helper paths

- **WHEN** the harness runs against a workspace that exercises all four worktree helper paths
- **THEN** the harness MUST assert that each path emits its expected exit code and MUST fail if any exit code diverges

### Requirement: Docs layout convention

Stage 0 MUST publish `openspec/specs/conventions/docs-layout.md` that fixes the writing roles of each documentation root: `docs/research/` (raw exploration), `docs/superpowers/specs/` (design drafts), `docs/superpowers/plans/` (executable plans), `docs/superpowers/workstreams/` (per-workstream plan/task/todo), `docs/ops/` (operations runbooks), `openspec/specs/` (canonical stage specs), and `openspec/changes/` (change proposals and archives). Contributors MUST treat this file as the authority for where new documents are created.

#### Scenario: Convention lists all six roles

- **WHEN** a reviewer reads `openspec/specs/conventions/docs-layout.md`
- **THEN** the document MUST describe the role of each of the seven documentation roots listed above

### Requirement: opsx slash command dual source

Stage 0 MUST keep the `opsx` slash-command surface available from both `.claude/commands/opsx/<name>.md` (Claude Code) and `.github/prompts/opsx-<name>.prompt.md` (GitHub Copilot). For each command — at minimum `opsx:new` and `opsx:ff` — the body content of the two files MUST remain byte-equivalent modulo the front-matter required by each host. A drift between the two sources MUST be detectable by the Stage 0 regression harness.

#### Scenario: Both hosts expose opsx:new and opsx:ff

- **WHEN** a reviewer inspects `.claude/commands/opsx/` and `.github/prompts/`
- **THEN** both directories MUST contain definitions for `opsx:new` and `opsx:ff`

#### Scenario: Drift is caught by harness

- **WHEN** one of the two sources is edited without updating the other
- **THEN** the Stage 0 regression harness MUST report a non-zero exit identifying the drifting command

### Requirement: AGENTS and CLAUDE single entry point

Stage 0 MUST keep a single canonical agent-workflow entry point. `AGENTS.md` is the source of truth; `CLAUDE.md` MUST be a symlink that points to `AGENTS.md`. Editing instructions for agents MUST NOT be duplicated across the two files.

#### Scenario: CLAUDE.md resolves via symlink

- **WHEN** a reviewer runs `readlink CLAUDE.md` at the repo root
- **THEN** the output MUST resolve to `AGENTS.md`

### Requirement: Workstream artefact convention

Stage 0 MUST fix the workstream directory shape at `docs/superpowers/workstreams/<workstream>/`. Each workstream MUST contain `plan.md`, `task.md`, and `todo.md`. `plan.md` MUST include the writing-plans sections `## Scope`, `## Steps`, `## Relevant files`, `## Verification`, `## Decisions`; `todo.md` MUST include the short-iteration sections `## Current Sprint`, `## Blockers`, `## Evidence / Links`, `## Handoff Notes`. The `stage0-tooling-foundation` workstream MUST additionally carry its own evidence files under `evidence/` as the reference example.

#### Scenario: Workstream skeleton is complete

- **WHEN** a reviewer lists `docs/superpowers/workstreams/stage0-tooling-foundation/`
- **THEN** the directory MUST contain `plan.md`, `task.md`, `todo.md`, and a non-empty `evidence/` directory

#### Scenario: Plan structure matches writing-plans

- **WHEN** a reviewer opens any workstream `plan.md`
- **THEN** the file MUST contain headings `## Scope`, `## Steps`, `## Relevant files`, `## Verification`, and `## Decisions`
