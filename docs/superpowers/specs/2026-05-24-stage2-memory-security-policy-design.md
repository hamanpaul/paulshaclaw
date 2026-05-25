# Stage 2 Topic 8 — Memory Security Policy Design

## Context

Stage 2 memory is the `paulshaclaw` memory subsystem. Its runtime memory lives outside the repository under `~/.agents/memory/`; the repository owns the tools, contracts, specs, and staged skill scaffolds that operate on that memory. Topic 1 already defines the memory substrate layers (`raw`, `distilled`, `canonical`, `indexed`), and Topic 2 defines the Importer MVP that writes normalized session artifacts into `inbox/`.

Topic 8 is the cross-cutting security policy layer for the whole Stage 2 memory system. It is not owned by the importer, `paulsha-mem-moc`, retrieval, or dream mode. Instead, it defines the policy artifacts, boundary vocabulary, reference API, audit contract, and fail-mode rules every memory component must use when reading from or writing to memory.

The approved design intentionally treats `paulshaclaw` as the task / agent workflow toolset and treats `paulsha-mem-moc` as the Stage 2 component that will maintain the memory mechanism. `obs-auto-moc` concepts may be reimplemented as `paulsha-mem-moc`, but Topic 8 does not perform that rewrite.

## Goals / Non-Goals

**Goals:**

- Define a single Stage 2 memory security contract that all current and future memory components must obey.
- Establish boundary names and policy hook semantics using the existing Topic 1 layer model without redefining the memory tree.
- Provide a Python reference library, `paulshaclaw.memory.policy`, as the only supported way for components to run policy checks.
- Protect ingress with a two-stage redaction pipeline: hook-side cheap regex at `external_to_raw`, then importer-side gitleaks plus policy library at `raw_to_distilled`.
- Define classification tagging for distilled artifacts using `public` / `private` / `secret` levels and rule-based defaults.
- Record policy execution in both the session-level importer ledger and a rule-level append-only audit log without storing matched secret text.
- Support local policy overrides and policy dry-runs without committing personal or organization-specific rules to the repository.
- Add CI linting so new memory consumers cannot bypass the policy API silently.

**Non-Goals:**

- No publish guard implementation in this sub-spec. The repository stores memory tooling and contracts; real memory content remains under `~/.agents/memory/`. Future export, public skill publishing, or external sharing features must define their own egress guard using this policy layer.
- No execution of `distilled_to_canonical`, `canonical_to_indexed`, or `indexed_to_consumer` policies beyond schema and boundary placeholders. Those are owned by future `paulsha-mem-moc`, retrieval, and consumer sub-specs.
- No cross-language policy SDK. MVP assumes Python consumers.
- No ML / embedding classifier. Classification is rule-based YAML policy only.
- No emergency kill-switch. Operators can use audited local overrides; fail-closed boundaries must not silently degrade to unsafe behavior.
- No Stage 1 event bus integration. Topic 8 writes local audit JSONL; future observability may subscribe to it.

## Boundary Contract

Topic 8 reuses Topic 1's layer model and defines these canonical boundary identifiers:

| Boundary | Meaning | MVP execution |
|---|---|---|
| `external_to_raw` | CLI hook / watcher source enters transient queue material | Required: hook-side cheap regex redaction screening |
| `raw_to_distilled` | queue payload becomes normalized `inbox/` artifact | Required: importer gitleaks scan, line redaction, classification tagging |
| `distilled_to_canonical` | `inbox/` artifact is promoted into work-centric / knowledge memory | Deferred; policy schema must reserve this boundary |
| `canonical_to_indexed` | canonical memory becomes retrieval-ready index material | Deferred; policy schema must reserve this boundary |
| `indexed_to_consumer` | retrieval / wake-up / prompt assembly sends memory to a consumer, especially an LLM | Deferred; policy schema must reserve this boundary |

Policy rules attach to boundary identifiers, not to implementation details. Components are responsible for calling the policy API at the boundaries they own. Audit records always name the boundary so later debugging can answer "which security check ran, at which layer transition, under which effective policy hash?"

## Policy Artifacts

Repository defaults live under:

```text
paulshaclaw/memory/policy/
├── secrets.yaml
├── classification.yaml
└── boundaries.yaml
```

`secrets.yaml` defines:

- cheap regex rule IDs and patterns used by hooks;
- gitleaks enable / disable configuration for importer-side scans;
- detector names;
- redaction action, fixed to `line` for MVP;
- rule severity and human-readable descriptions.

`classification.yaml` defines:

- allowed levels: `public`, `private`, `secret`;
- project / path / git-remote default classification rules;
- unknown-project fallback;
- automatic downgrade rules such as "any artifact with redaction hits becomes `private`";
- manual / override precedence.

`boundaries.yaml` defines:

- all boundary identifiers;
- policy hooks required or deferred at each boundary;
- fail-mode (`fail_closed`, `fail_open_warn`);
- retry count and backoff for fail-closed checks;
- audit requirements.

Local overrides live at:

```text
~/.config/paulshaclaw/policy.override.yaml
```

Overrides may:

- disable specific rule IDs;
- disable rule IDs for specific sessions;
- append local regex rules;
- append local classification defaults;
- override default classification for specific project roots or remotes.

Overrides must never be committed to the repository because they can reveal personal, customer, or organization-specific vocabulary. The policy loader merges repository defaults with local overrides into an effective policy and computes `effective_policy_hash`. Ledger and audit records must include both `policy_version` and `effective_policy_hash`. Consumers that only support an older major policy version must fail closed rather than misread a new schema.

Override rule IDs, descriptions, and reasons must not contain secret values or original matched text. They may name project slugs, rule IDs, session references, and coarse human categories only.

## Redaction Contract

### Detector pipeline

At `external_to_raw`, hook scripts run only cheap regex rules. This stage catches obvious secrets with low overhead: GitHub PATs, OpenAI / Anthropic keys, AWS keys, JWTs, private key block markers, bearer tokens, and similar high-confidence tokens. Hooks must stay thin: no gitleaks, no canonical-memory writes, and no long-running analysis.

The hook writes the queue payload only after applying cheap-regex line redaction. The queue item is therefore a transient normalized capture, not a byte-for-byte raw session archive. Raw session ownership remains with the originating CLI session store.

At `raw_to_distilled`, the importer calls `paulshaclaw.memory.policy` to run the full policy. The importer runs gitleaks on the queued payload, merges any hook-side hit metadata, resolves overrides, applies redaction, and only then writes the distilled `inbox/` artifact.

If importer-side gitleaks finds a secret missed by hook regex, the importer must not archive the original queue file. It redacts the affected lines in memory, writes only the redacted distilled artifact, optionally archives only a redacted queue snapshot, and unlinks the original queue file after successful processing. This rule supersedes Topic 2's generic "archive queue payload" behavior for policy-hit items.

### Action

MVP redaction is line-level. Any line containing one or more hits is replaced with a placeholder:

```text
[REDACTED LINE: github_pat x1]
[REDACTED LINE: github_pat x1, bearer_token x1]
```

The memory system must not store the matched substring, original line, or raw secret in `inbox/`, ledger, audit log, quarantine, encrypted raw archive, `archive/queue/`, or `runtime/queue/_failed/`. Raw session storage remains the responsibility of the originating LLM CLI.

### Metadata

Importer ledger entries include session-level summary fields:

- `redaction_hits`
- `redaction_types`
- `redaction_stage` (`hook`, `importer`, or `both`)
- `policy_version`
- `effective_policy_hash`

Rule-level audit records include:

- `ts`
- `boundary`
- `component`
- `session_ref`
- `policy_version`
- `effective_policy_hash`
- `rule_id`
- `detector`
- `line_no`
- `action`

Audit records must not include matched values or original line text.

### Failure behavior

Redaction failures are fail-closed. If policy loading, override merging, regex execution, gitleaks execution, or hash calculation fails at a redaction boundary, the component retries according to `boundaries.yaml`. If retry is exhausted, the component writes only a failure stub to `~/.agents/memory/runtime/queue/_failed/` and unlinks the queue payload. The stub contains session reference, source tool, boundary, error class, timestamp, and policy version/hash if available; it must not contain the original payload or any conversation line. When the ledger is available, it records `policy-error`; no inbox artifact is written.

Because gitleaks is required for `raw_to_distilled`, `install.sh` must either install a pinned gitleaks binary / package or validate an existing configured binary before enabling importer processing. If gitleaks is enabled but missing or exits with an unexpected error, `raw_to_distilled` follows the fail-closed retry path above. Operators may only disable gitleaks through audited local override for explicit rule debugging; default policy keeps it enabled.

## Classification Contract

Classification levels:

| Level | Meaning | Required behavior |
|---|---|---|
| `public` | Suitable for future publish / sync / export if another sub-spec defines such egress | May flow through local memory pipeline, still subject to later boundary policy |
| `private` | Local-only memory; do not assume it may leave the machine or be included in all consumers | May flow inside local memory; consumers must respect their own boundary policy |
| `secret` | Material that should not exist in distilled or canonical memory | Must not enter indexed or consumer boundaries; if present after redaction, write forensic audit |

Default classification is rule-based:

- match `project_slug`, repository path, or git remote when available;
- unknown project defaults to `private`;
- any artifact with redaction hits defaults to `private`;
- `paulshaclaw` design / tooling sessions may default to `public`;
- local override can downgrade or upgrade defaults, with audit visibility.

Every distilled `inbox/` artifact must include:

- `classification_level`
- `classification_reason`
- `classification_policy_hash`
- `classification_source` (`default_rule`, `override`, or `manual`)

Future `paulsha-mem-moc` promotion must preserve or tighten classification:

- `secret` cannot enter canonical memory;
- `private` cannot automatically become `public`;
- `public` may be downgraded to `private`;
- manual and local override decisions have higher precedence than defaults.

Classification failures are fail-open with warning because missing tags are recoverable and do not directly leak secrets. If classification fails, the artifact is written as `classification_level: private`, ledger / audit record `classification-warning`, and replay can backfill later.

## Audit and Ledger Contract

Topic 8 writes both:

- session-level summaries in the existing Stage 2 importer ledger; and
- rule-level details in `~/.agents/memory/runtime/audit/policy.jsonl`.

The two streams share `session_ref`, `policy_version`, and `effective_policy_hash`. Ledger answers "what happened to this session?" Audit answers "what did this rule do across sessions?"

`policy.jsonl` is append-only for MVP. Rotation and janitor cleanup are deferred to dream / janitor sub-specs. Audit records are local-only and must avoid matched secret text. They may include rule IDs, detector names, line numbers, action names, boundary names, component names, and session references.

Ledger / audit write failures are policy execution failures. For fail-closed boundaries, the component must first prepare the sanitized output, then append audit and ledger records, then atomically publish the output. If audit append fails after retry, the output is not published, the component writes a failure stub, records `policy-error` in the ledger, and unlinks the queue payload.

If the ledger append itself fails after retry, the component cannot truthfully claim a ledger `policy-error` entry. In that case it must still fail closed: do not publish output, write a failure stub with `ledger_status: "unavailable"`, unlink the queue payload, and append a best-effort warning to `~/.agents/memory/log/policy.log`. For fail-open classification warnings, artifact publication may proceed, but the component must append a best-effort warning to `policy.log` if audit or ledger append fails.

## Override and Dry-Run

False positives are handled by local override plus dry-run, not by disabling the whole policy layer.

Supported override shapes:

- `disable_rules`
- `disable_rules_for_session`
- local regex rule append
- local classification rule append
- project default classification override

The CLI exposes:

```bash
psc memory dry-run-policy <session-id>
psc memory replay --session <session-id>
```

`dry-run-policy` must not write inbox artifacts. It prints rule ID, detector, line number, action, boundary, classification result, and effective policy hash. It does not print matched strings or original line text. If the operator needs to inspect raw content, they must open the originating CLI session store directly.

`replay` reruns importer logic for one session with the current effective policy. Override usage must be reflected in audit records and in the effective policy hash.

## Consumer Enforcement

`paulshaclaw.memory.policy` is the only supported API for policy execution. Memory consumers must not:

- parse policy YAML directly;
- implement their own regex detector outside the policy library;
- write audit records by hand;
- skip boundary calls for a boundary they own.

The repository must include CI lint that detects memory consumer source files and verifies they call the policy boundary API. A new consumer sub-spec must declare which boundaries it owns. If implementation code adds a memory consumer without a matching policy API call, CI fails.

The MVP lint can be Python-oriented and conservative. Cross-language enforcement is deferred until non-Python memory components exist.

## Fail Modes and Retry

`boundaries.yaml` declares fail mode by boundary / policy class:

- redaction at `external_to_raw` and `raw_to_distilled`: fail-closed with retry;
- classification stamping at `raw_to_distilled`: fail-open with warning and `private` fallback;
- future admission / consumer gates: fail-closed unless a later sub-spec justifies otherwise.

Failures that exhaust retry at fail-closed boundaries write only a metadata stub to `runtime/queue/_failed/`, unlink the queue payload, and write `policy-error` ledger metadata when the ledger is available. Fail-open warnings must still write audit records so later replay can find and repair them.

No kill-switch is part of MVP. Local override is the supported escape hatch and must remain auditable.

## Testing / Acceptance

Minimum acceptance coverage:

1. Regex detector sees an obvious token at `external_to_raw`; the resulting inbox artifact has a redacted line and does not contain the token.
2. Gitleaks sees a queued payload at `raw_to_distilled`; the inbox artifact has a redacted line.
3. Redacted imports write ledger fields `redaction_hits`, `redaction_types`, `redaction_stage`, `policy_version`, and `effective_policy_hash`.
4. `policy.jsonl` contains rule-level events without matched strings or original line text.
5. Detector failure retries; retry exhaustion writes only a metadata stub to `_failed/`, unlinks the queue payload, writes `policy-error` when the ledger is available, and does not write inbox.
6. Unknown project classification produces `private`.
7. Any redaction hit downgrades classification to `private`.
8. Override disabling a specific rule for a specific session makes dry-run show that rule as skipped and writes an override audit event.
9. A memory consumer that does not call the policy boundary API fails CI lint.
10. A policy major version unsupported by the consumer fails closed.
11. A gitleaks-only hit is redacted before any queue archive is written; `archive/queue/` and `_failed/` contain no original matched line.

## Open Questions

1. Should future `paulsha-mem-moc` promotion treat `private` as allowed in canonical memory, or should some project classes require `private` to remain only in `inbox/`?
2. Should audit rotation be owned by the dream / janitor sub-spec or by Topic 8 follow-up work?
