<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.1 -->
policy_version: 1.0.1

# Copilot Instructions for `paulshaclaw`

## Project snapshot

- This repository is a **docs-first design repo** for the `paulshaclaw` agent workflow system.
- The most important source files are the staged research docs under `docs/research/`.
- Read the architecture docs before making changes:
  - `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`
  - `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md`
  - `docs/research/04.stage4-persona-role-catalog-handoff-guardrails-research.md`
  - `docs/research/01.prompt-define-plan-build-verify-review-ship-resear.md`

## Big-picture architecture

- The system is organized as a staged lifecycle:
  - **Stage 0**: tool / naming cleanup and OpenSpec + Superpowers setup
  - **Stage 1**: `PaulShiaBro` daemon, TUI, Telegram bot, registry
  - **Stage 2**: `~/.agents/memory` as the memory substrate
  - **Stage 3**: slash-command lifecycle with artifacts and gates
  - **Stage 4**: persona contracts, handoff, and guardrails
  - **Stage 5+**: observability, security, and deployment hardening
- The operating model is **hub-and-spoke**:
  - one manager / orchestrator owns task authority
  - workers do bounded execution and return artifacts
  - avoid direct worker-to-worker mesh behavior unless a doc explicitly calls for it
- The lifecycle is **artifact-first and event-first**:
  - prompt text is not the source of truth
  - canonical state lives in artifacts and event logs
  - gate decisions should be based on files, schemas, and recorded events

## Key conventions

- Use the staged docs as the source of truth for scope, terminology, and phase boundaries.
- Preserve the existing naming system:
  - `paulshaclaw` for the repo
  - `PaulShiaBro` for the daemon/bot
  - `psc` for short CLI / env naming
  - `PoHsiaBro` for the font / glyph family
- Keep changes aligned with the repository’s path split:
  - `paulshaclaw/` for repo code and templates
  - `~/.agents/` for private runtime state and memory
  - `~/.config/paulshaclaw/` for secrets and machine-local config
- Treat `docs/spec.md`, `docs/plan.md`, `docs/roadmap.md`, `docs/test.md`, `docs/task.md`, and `docs/todo.md` as lifecycle artifacts with explicit phase roles.
- When adding or editing docs, prefer the existing zh-TW terminology and the repo’s stage numbering instead of inventing new labels.
- Persona work should follow the contract model from Stage 4:
  - persona = contract
  - agent instance = runtime execution
  - skill = reusable capability

## Tooling and commands

- No repository-local build, test, or lint commands are defined in this snapshot.
- If code or scripts are added later, document the canonical commands alongside the relevant stage or tool docs.

## Working notes

- `openspec` and `superpowers` are part of the intended workflow scaffold; keep related changes consistent with the stage docs.
- Favor small, staged edits that keep the lifecycle readable and replayable.

## v1.0.1 新增規則（issue 連結 / docs 對齊 / 語言）
> 本段於 policy 1.0.1 隨 R-17 / R-18 與語言規範新增。

- **R-17（PR↔issue，FAIL gate）**：PR body 引用 issue（`#N`）時必須為 closing-keyword 形式（`Closes` / `Fixes` / `Resolves #N`），merge 由 GitHub 原生自動關閉 issue 並留下 cross-reference；只引用不關閉時上 `policy-exempt:issue-link`。
- **R-18（docs 對齊，WARN，不擋 merge）**：`code_paths` 有變動但 `README.md` / `docs/**` 未同步時提醒；純內部變動可上 `policy-exempt:docs-sync`。
- **語言規範（checklist）**：依 repo 來源決定語言——`github.com/hamanpaul/*`、`github.com/paulc-arc/*` → zh-tw；arcadyan GitLab → en_US。涵蓋 PR 標題／內文與所有 comment。本 repo 屬 `hamanpaul` → zh-tw。
- **動工前（軟性，不打斷流程）**：若任務對應某 issue，`gh issue view <N>` 核對相關性後分支可命名 `feature/<N>-<slug>`，開 PR 於 body 寫 `Closes #N`；查無對應 issue 照常進行，不另開、不停。
- **Exemption 白名單新增**：`policy-exempt:issue-link`（R-17）、`policy-exempt:docs-sync`（R-18）。
