## ADDED Requirements

### Requirement: Session-start wake-up injection

Stage 2 SHALL provide a `paulshaclaw/memory/wakeup/` code module that builds a per-project wake-up brief and injects it at session start. The brief MUST consist of the project's MOC primer (the T7 `knowledge/<project>-moc.md` body) followed by the most recent K active knowledge slices rendered as compact pointers (title, a one-line summary, and an Obsidian wikilink). Recency MUST be derived from the lifecycle ledger's `last_event_ts` and filtered to active records via the retrieval set; the builder MUST be deterministic given its inputs (no wall-clock inside the builder) and MUST be read-only (no knowledge or ledger writes). The brief MUST be bounded by a character budget, reserving the recent-K block before the MOC and truncating only the MOC tail. Injection MUST use each CLI's additional-context channel: Claude `SessionStart`, Copilot `sessionStart`; Codex reuses Claude's hook. Injection MUST be fail-open: any error yields an empty brief, is logged, and exits zero without blocking session start.

#### Scenario: Brief surfaces project map and recent activity

- **WHEN** `psc memory wakeup --project <p>` runs and project `<p>` has a MOC and active slices
- **THEN** the output MUST contain the MOC primer and the most recent active slices, newest first
- **THEN** each recent entry MUST include a one-line summary and an Obsidian wikilink

#### Scenario: Unknown or empty project injects nothing

- **WHEN** the resolved project is `_unknown`, or the project has no MOC and no active slices
- **THEN** the brief MUST be empty and the hook MUST exit zero without injecting

#### Scenario: Session-start hook fails open

- **WHEN** the wake-up builder raises or input is malformed at session start
- **THEN** the hook MUST emit a valid empty-context payload, log the error, and exit zero
- **THEN** session start MUST NOT be blocked

#### Scenario: Brief respects the character budget

- **WHEN** the MOC body exceeds the remaining budget
- **THEN** the recent-K block MUST be preserved and only the MOC tail truncated with a truncation marker
- **THEN** the total brief length MUST NOT exceed the configured character budget

### Requirement: Pre-compaction session capture

Stage 2 SHALL provide PreCompact hooks (Claude `PreCompact`, Copilot `preCompact`) that snapshot the current session into the existing importer before compaction, tagging the snapshot with `capture_scope="pre_compact"`. The importer's scope ranking MUST treat `pre_compact` as a turn-level snapshot (rank 0) so that a later `session_end` or `watcher_final` capture supersedes it through the existing idempotency engine, without extending any schema. Pre-compaction capture MUST NOT perform atomization (deferred to dream) and MUST be fail-open: any error is logged and exits zero without blocking compaction.

#### Scenario: PreCompact writes a pre_compact snapshot

- **WHEN** compaction is triggered and a PreCompact hook fires with a session payload
- **THEN** a queue payload tagged `capture_scope: "pre_compact"` MUST be written and the importer triggered

#### Scenario: pre_compact is superseded by a more complete capture

- **WHEN** a `session_end` or `watcher_final` capture for the same session arrives after a `pre_compact` snapshot
- **THEN** the existing idempotency engine MUST treat the later capture as more complete (higher scope rank)

#### Scenario: PreCompact never blocks compaction

- **WHEN** the PreCompact hook errors or receives malformed input
- **THEN** it MUST log the error and exit zero
- **THEN** compaction MUST proceed unblocked
