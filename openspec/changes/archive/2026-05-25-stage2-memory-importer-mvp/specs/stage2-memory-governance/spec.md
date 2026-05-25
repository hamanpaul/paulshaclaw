## ADDED Requirements

### Requirement: Canonical agent memory tree

Stage 2 SHALL provision `~/.agents/memory/` as the canonical agent memory substrate, fully disjoint from any Obsidian vault (`~/notes/`). The tree MUST contain `inbox/{sessions,plans,research,reports}/<tool>/<YYYY-MM-DD>/`, `work-centric/`, `knowledge/`, `runtime/{queue,queue/_failed,locks,ledger,indexes}/`, `log/`, `hooks/`, and `archive/queue/<YYYY-MM>/`. Directory mode MUST be 0700. `work-centric/`, `knowledge/`, and `runtime/indexes/` MUST be created as empty placeholders in this MVP; only `inbox/`, `runtime/queue*`, `runtime/locks`, `runtime/ledger`, `log/`, `hooks/`, and `archive/queue/` are write targets in this change.

#### Scenario: Install creates the canonical tree

- **WHEN** an operator runs `~/.agents/memory/hooks/install.sh --tree-only`
- **THEN** all directories listed above MUST exist with mode 0700
- **THEN** placeholder subtrees MUST contain a `.gitkeep` file but no other content
- **THEN** `~/notes/` MUST NOT be touched

#### Scenario: Memory tree is disjoint from Obsidian vault

- **WHEN** any importer or hook component executes
- **THEN** it MUST NOT read from or write to `~/notes/`
- **THEN** all reads and writes MUST be confined to `~/.agents/memory/` and repo-local fixture/history inputs

### Requirement: Hook-based session ingestion for three CLIs

Stage 2 SHALL provide native hook integrations for Claude Code (`SessionEnd`), Codex CLI (`Stop` and `SubagentStop`), and GitHub Copilot CLI (`sessionEnd`). Hook scripts MUST be thin: they MUST write the raw payload to `~/.agents/memory/runtime/queue/<tool>__<session-id>.json` via atomic rename and fire-and-forget invoke `paulshaclaw.memory.importer.cli ingest --queue-item <path>`. Hook scripts MUST tag every payload with a `capture_scope` of `session_end`, `turn`, or `subagent`. Hook scripts MUST NOT raise to the host CLI; any failure MUST be logged to `~/.agents/memory/log/hooks.log` and the script MUST exit zero.

#### Scenario: Claude SessionEnd writes a queue payload

- **WHEN** an authorized operator finishes a Claude Code session
- **THEN** `~/.agents/memory/runtime/queue/claude-code__<sid>.json` MUST appear within the hook timeout
- **THEN** the payload MUST include `capture_scope: "session_end"`
- **THEN** `~/.agents/memory/log/hooks.log` MUST NOT contain an ERROR entry for that session

#### Scenario: Codex Stop is treated as turn snapshot

- **WHEN** Codex CLI fires `Stop` mid-session
- **THEN** the hook MUST write a queue payload with `capture_scope: "turn"` and `ended_at: null`
- **THEN** the hook MUST NOT treat the event as session termination

#### Scenario: Copilot sessionEnd renames camelCase keys

- **WHEN** Copilot CLI fires `sessionEnd` with payload keys `sessionId`, `timestamp`, `cwd`, `reason`
- **THEN** the hook MUST normalize `sessionId` to `session_id`
- **THEN** the hook MUST supplement missing transcript fields by reading `~/.copilot/history-session-state/session_<sid>_*.json`

#### Scenario: Hook venv-pinned Python is independent of user PATH

- **WHEN** `install.sh` completes
- **THEN** all hook config files MUST invoke `~/.agents/memory/hooks/.venv/bin/python`
- **THEN** no hook config MAY invoke `python3` or `/usr/bin/env python3`

### Requirement: Content-hash and completeness idempotency

Stage 2 SHALL deduplicate session imports using `idempotency_key = "<source_agent>:<source_session>"`. The importer MUST compute `content_hash = sha256(canonical_json((session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))))` and `completeness = (scope_rank, turn_count, len(touched_files), len(user_prompts))` where `scope_rank` maps `{turn:0, subagent:0, session_end:1, watcher_final:2}`. For each incoming payload, after acquiring a `flock` on `runtime/locks/<key>.lock`, the importer MUST compare against the last ledger record for that key and resolve to exactly one of these statuses: `written` (first time), `hash-duplicate` (same hash), `updated` (strict tuple `completeness > recorded.completeness`), or `stale-skip` (otherwise). Every decision MUST append a record to `~/.agents/memory/runtime/ledger/import.jsonl`.

#### Scenario: First write produces written

- **WHEN** the importer processes a queue payload for a new idempotency key
- **THEN** the importer MUST write the inbox file
- **THEN** the ledger MUST receive an entry with `status: "written"`

#### Scenario: Identical hash short-circuits to hash-duplicate

- **WHEN** the importer processes a payload whose `content_hash` matches the most recent ledger entry for the same key
- **THEN** the importer MUST NOT rewrite the inbox file
- **THEN** the ledger MUST receive an entry with `status: "hash-duplicate"`

#### Scenario: Higher completeness yields updated

- **WHEN** the importer processes a payload whose `completeness` is strictly greater (per Python tuple ordering) than the recorded entry
- **THEN** the importer MUST overwrite the inbox file
- **THEN** the ledger MUST receive an entry with `status: "updated"` including `from_completeness` and `to_completeness` fields

#### Scenario: Lower or equal completeness yields stale-skip

- **WHEN** the importer processes a payload whose `completeness` is not strictly greater than the recorded entry and whose hash differs
- **THEN** the importer MUST NOT rewrite the inbox file
- **THEN** the ledger MUST receive an entry with `status: "stale-skip"`

### Requirement: Project identity resolution with longest-prefix

Stage 2 SHALL resolve each session payload to a project identity using `~/.agents/config/projects.yaml`. Resolution MUST attempt, in order: (1) longest-prefix match of payload `cwd` against any project's `roots`; (2) longest-prefix match of explicit git toplevel against `roots`; (3) normalized match of remote URLs against `remotes`. If no rule hits, the importer MUST set `project: _unknown` and continue without raising. On alias collision, the first definition in `projects.yaml` wins and a WARN entry MUST be appended to `importer.log`.

#### Scenario: Monorepo child wins over parent

- **WHEN** `projects.yaml` declares both `monorepo` with root `/repo` and `monorepo-web` with root `/repo/web`, and the payload `cwd` is `/repo/web/src`
- **THEN** the resolver MUST return `monorepo-web`

#### Scenario: Unknown project does not block ingestion

- **WHEN** the resolver finds no matching root or remote
- **THEN** the importer MUST set `project: _unknown` and proceed
- **THEN** no exception MAY be raised

### Requirement: Frontmatter contract for inbox entries

Stage 2 SHALL produce every inbox markdown file with a YAML frontmatter block whose required fields match `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md` lines 220–234, aligned with Stage 3 frontmatter. The MVP MUST NOT introduce new frontmatter fields beyond that contract. Missing best-effort fields MUST appear as empty strings or empty arrays, never as `null` or as missing keys.

#### Scenario: Lint passes on full corpus-compatible fixtures

- **WHEN** an operator runs `paulshaclaw/memory/lint/frontmatter_lint.py` over importer output produced from the repo-local fixture set
- **THEN** the lint MUST report zero failures

#### Scenario: Missing fields degrade gracefully

- **WHEN** an adapter receives a payload missing `touched_files` or `user_prompts`
- **THEN** the resulting markdown MUST contain empty list sections rather than raising
- **THEN** the importer MUST NOT raise
