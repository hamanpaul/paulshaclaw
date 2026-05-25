# Stage 2 Memory Security Policy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 2 Topic 8 memory security policy MVP: policy artifacts, policy API, ingress redaction, classification tagging, audit/ledger metadata, dry-run/replay helpers, CI lint, and OpenSpec/README follow-through.

**Architecture:** Add a focused `paulshaclaw.memory.policy` package that owns policy loading, override merge, effective hash, detectors, boundary checks, classification, audit, and safe failure stubs. Keep importer/hook integration as thin adapter functions because Topic 2 importer runtime does not exist yet; the API and tests define the contract future importer code must call. Preserve docs-first boundaries: real memory content stays under `~/.agents/memory/`; repository files contain only tooling, defaults, specs, tests, and plans.

**Tech Stack:** Python standard library (`dataclasses`, `json`, `hashlib`, `re`, `subprocess`, `pathlib`, `unittest`, `tempfile`), YAML via PyYAML if available with a JSON-compatible fallback parser for default policy fixtures, shell scripts for Stage 2 integration check.

---

## Chunk 1: Policy Defaults, Loader, and Hash

### Task 1: Add default policy artifacts

**Files:**
- Create: `paulshaclaw/memory/__init__.py`
- Create: `paulshaclaw/memory/policy/secrets.yaml`
- Create: `paulshaclaw/memory/policy/classification.yaml`
- Create: `paulshaclaw/memory/policy/boundaries.yaml`
- Create: `paulshaclaw/memory/policy/models.py`
- Create: `paulshaclaw/memory/policy/loader.py`
- Create: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing policy artifact tests**

Create the test scaffold first:

```python
from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def load_policy(testcase: unittest.TestCase):
    try:
        return importlib.import_module("paulshaclaw.memory.policy")
    except ModuleNotFoundError as exc:
        testcase.fail(f"memory policy module missing: {exc}")


class PolicyLoaderTests(unittest.TestCase):
    ...
```

Add `PolicyLoaderTests.test_load_defaults_lists_required_boundaries_and_rules`:

```python
def test_load_defaults_lists_required_boundaries_and_rules(self):
    mod = load_policy(self)
    policy = mod.load_default_policy()
    self.assertEqual(policy.policy_version, "0.1.0")
    self.assertIn("external_to_raw", policy.boundaries)
    self.assertIn("raw_to_distilled", policy.boundaries)
    self.assertIn("github_pat", policy.secret_rules)
    self.assertEqual(policy.classification.unknown_project_default, "private")
```

- [ ] **Step 2: Run the failing test**

Run: `python3 -m unittest tests.test_stage2_memory_policy.PolicyLoaderTests.test_load_defaults_lists_required_boundaries_and_rules -v`

Expected: FAIL with `ModuleNotFoundError` or missing `load_default_policy`.

- [ ] **Step 3: Create default YAML files**

Use JSON-compatible YAML so the loader can parse with either PyYAML or `json`:

`secrets.yaml`:

```yaml
{
  "policy_version": "0.1.0",
  "gitleaks": {"enabled": true, "binary": "gitleaks"},
  "rules": [
    {"id": "github_pat", "detector": "regex", "pattern": "(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})", "severity": "high", "description": "GitHub token"},
    {"id": "openai_key", "detector": "regex", "pattern": "sk-[A-Za-z0-9_-]{16,}", "severity": "high", "description": "OpenAI-like API key"},
    {"id": "anthropic_key", "detector": "regex", "pattern": "sk-ant-[A-Za-z0-9_-]{16,}", "severity": "high", "description": "Anthropic API key"},
    {"id": "aws_access_key", "detector": "regex", "pattern": "AKIA[0-9A-Z]{16}", "severity": "high", "description": "AWS access key"},
    {"id": "bearer_token", "detector": "regex", "pattern": "(?i)Authorization:\\s*Bearer\\s+\\S+", "severity": "high", "description": "Bearer token"},
    {"id": "jwt", "detector": "regex", "pattern": "eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+", "severity": "high", "description": "JWT"},
    {"id": "private_key_marker", "detector": "regex", "pattern": "-----BEGIN [A-Z ]*PRIVATE KEY-----", "severity": "high", "description": "Private key block"}
  ],
  "redaction": {"action": "line"}
}
```

`classification.yaml`:

```yaml
{
  "policy_version": "0.1.0",
  "levels": ["public", "private", "secret"],
  "unknown_project_default": "private",
  "redaction_hit_default": "private",
  "manual_precedence": true,
  "project_defaults": [
    {"project": "paulshaclaw", "level": "public", "reason": "tooling design repo", "roots": ["paulshaclaw"], "remotes": ["hamanpaul/paulshaclaw"]}
  ]
}
```

`boundaries.yaml`:

```yaml
{
  "policy_version": "0.1.0",
  "boundaries": [
    {"id": "external_to_raw", "status": "mandatory", "hooks": [{"name": "regex_redaction", "fail_mode": "fail_closed"}], "retry_count": 3, "retry_backoff_ms": 50, "audit_required": true},
    {"id": "raw_to_distilled", "status": "mandatory", "hooks": [{"name": "regex_redaction", "fail_mode": "fail_closed"}, {"name": "gitleaks_redaction", "fail_mode": "fail_closed"}, {"name": "classification", "fail_mode": "fail_open_warn"}], "retry_count": 3, "retry_backoff_ms": 50, "audit_required": true},
    {"id": "distilled_to_canonical", "status": "deferred", "hooks": [], "retry_count": 3, "retry_backoff_ms": 50, "audit_required": true},
    {"id": "canonical_to_indexed", "status": "deferred", "hooks": [], "retry_count": 3, "retry_backoff_ms": 50, "audit_required": true},
    {"id": "indexed_to_consumer", "status": "deferred", "hooks": [], "retry_count": 3, "retry_backoff_ms": 50, "audit_required": true}
  ]
}
```

- [ ] **Step 4: Implement minimal loader and data classes in focused modules**

Create `models.py` with:

```python
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

SUPPORTED_POLICY_MAJOR = "0"

@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    detector: str
    pattern: str
    severity: str
    description: str

@dataclass(frozen=True)
class BoundaryPolicy:
    boundary_id: str
    status: str
    hooks: Mapping[str, str]  # hook name -> fail mode
    retry_count: int
    retry_backoff_ms: int
    audit_required: bool

@dataclass(frozen=True)
class ProjectDefault:
    project: str
    level: str
    reason: str
    roots: tuple[str, ...]
    remotes: tuple[str, ...]

@dataclass(frozen=True)
class ClassificationPolicy:
    levels: tuple[str, ...]
    unknown_project_default: str
    redaction_hit_default: str
    manual_precedence: bool
    project_defaults: Mapping[str, ProjectDefault]

@dataclass(frozen=True)
class EffectivePolicy:
    policy_version: str
    secret_rules: Mapping[str, SecretRule]
    boundaries: Mapping[str, BoundaryPolicy]
    classification: ClassificationPolicy
    disabled_rules: frozenset[str]
    disabled_rules_for_session: Mapping[str, frozenset[str]]
    effective_policy_hash: str
```

Create `loader.py` with `load_default_policy()`, `load_policy(default_dir=None, override_path=None)`, and `_read_mapping(path)` using PyYAML when installed and `json.loads` otherwise. Keep `__init__.py` as a re-export surface only so later redaction/audit modules do not make one oversized file.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_stage2_memory_policy.PolicyLoaderTests.test_load_defaults_lists_required_boundaries_and_rules -v`

Expected: PASS.

### Task 2: Add override merge, effective hash, and major-version fail-closed

**Files:**
- Create: `paulshaclaw/memory/policy/redaction.py`
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing tests for override hash and unsupported major**

Add:

```python
def test_local_override_changes_effective_hash_and_disables_session_rule(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        override = Path(tmp) / "policy.override.yaml"
        override.write_text('{"disable_rules_for_session": {"session-a": ["github_pat"]}}', encoding="utf-8")
        base = mod.load_policy(override_path=None)
        overridden = mod.load_policy(override_path=override)
    self.assertNotEqual(base.effective_policy_hash, overridden.effective_policy_hash)
    self.assertIn("github_pat", overridden.disabled_rules_for_session["session-a"])

def test_override_supports_global_disable_local_regex_and_project_default(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        override = Path(tmp) / "policy.override.yaml"
        override.write_text(json.dumps({
            "disable_rules": ["jwt"],
            "append_regex_rules": [{"id": "local_customer", "detector": "regex", "pattern": "ACME-INTERNAL-[0-9]+", "severity": "medium", "description": "local customer marker"}],
            "project_defaults": [{"project": "personal-notes", "level": "private", "reason": "local override"}]
        }), encoding="utf-8")
        policy = mod.load_policy(override_path=override)
    self.assertIn("jwt", policy.disabled_rules)
    self.assertIn("local_customer", policy.secret_rules)
    self.assertEqual(policy.classification.project_defaults["personal-notes"].level, "private")
    self.assertEqual(policy.classification.project_defaults["personal-notes"].reason, "local override")

def test_project_default_override_keeps_roots_and_remotes(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        override = Path(tmp) / "policy.override.yaml"
        override.write_text(json.dumps({
            "project_defaults": [{"project": "client", "level": "private", "reason": "client local", "roots": ["/work/client"], "remotes": ["git@example/client.git"]}]
        }), encoding="utf-8")
        policy = mod.load_policy(override_path=override)
    default = policy.classification.project_defaults["client"]
    self.assertEqual(default.roots, ("/work/client",))
    self.assertEqual(default.remotes, ("git@example/client.git",))

def test_unsupported_major_version_fails_closed(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        policy_dir = Path(tmp)
        (policy_dir / "secrets.yaml").write_text('{"policy_version":"9.0.0","gitleaks":{"enabled":true},"rules":[]}', encoding="utf-8")
        (policy_dir / "classification.yaml").write_text('{"policy_version":"9.0.0","levels":["public","private","secret"],"unknown_project_default":"private","redaction_hit_default":"private","project_defaults":[]}', encoding="utf-8")
        (policy_dir / "boundaries.yaml").write_text('{"policy_version":"9.0.0","boundaries":[]}', encoding="utf-8")
        with self.assertRaises(mod.PolicyVersionError):
            mod.load_policy(default_dir=policy_dir)
```

- [ ] **Step 2: Run the failing tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.PolicyLoaderTests -v`

Expected: first test fails because override merge is missing; second fails because `PolicyVersionError` is missing.

- [ ] **Step 3: Implement override and hash**

Implement in `loader.py`. `load_policy()` must use explicit `override_path` when provided; when `override_path` is omitted it may read the default `~/.config/paulshaclaw/policy.override.yaml` if present, but tests should pass `override_path=None` to force no local override for deterministic baseline.

```python
class PolicyError(RuntimeError): ...
class PolicyVersionError(PolicyError): ...

def is_rule_disabled(policy: EffectivePolicy, rule_id: str, session_ref: str | None) -> bool:
    return rule_id in policy.disabled_rules or (
        session_ref is not None and rule_id in policy.disabled_rules_for_session.get(session_ref, frozenset())
    )
```

Hash canonical JSON containing defaults and override-derived values; do not include file paths.

- [ ] **Step 4: Run loader tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.PolicyLoaderTests -v`

Expected: PASS.

---

## Chunk 2: Redaction, Classification, Audit, and Fail-Closed Output

### Task 3: Implement regex redaction with line-level placeholders

**Files:**
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing redaction tests**

Add:

```python
def test_regex_redacts_entire_lines_and_reports_hits_without_secret_text(self):
    mod = load_policy(self)
    policy = mod.load_policy()
    text = "safe line\nAuthorization: Bearer sk-prod-secret-token\nnext line\n"
    result = mod.redact_lines(text, policy=policy, session_ref="session-a", boundary="external_to_raw")
    self.assertIn("safe line", result.text)
    self.assertIn("[REDACTED LINE:", result.text)
    self.assertNotIn("sk-prod-secret-token", result.text)
    self.assertEqual(result.hit_count, 1)
    self.assertEqual(result.stage, "hook")
    self.assertEqual(result.hits[0].line_no, 2)
```

- [ ] **Step 2: Run failing test**

Run: `python3 -m unittest tests.test_stage2_memory_policy.RedactionTests.test_regex_redacts_entire_lines_and_reports_hits_without_secret_text -v`

Expected: FAIL because `redact_lines` is missing.

- [ ] **Step 3: Implement hit and redaction types**

Add:

```python
@dataclass(frozen=True)
class PolicyHit:
    rule_id: str
    detector: str
    line_no: int
    action: str

@dataclass(frozen=True)
class RedactionResult:
    text: str
    hits: tuple[PolicyHit, ...]
    stage: str
    effective_policy_hash: str
    @property
    def hit_count(self) -> int: ...
```

Implement `redact_lines(text, *, policy, session_ref, boundary, extra_hits=())` by splitting lines with `keepends=True`, grouping hits by line, replacing whole lines with `[REDACTED LINE: rule xN]\n`, and never storing match text.

- [ ] **Step 4: Run redaction test**

Run: `python3 -m unittest tests.test_stage2_memory_policy.RedactionTests -v`

Expected: PASS.

### Task 4: Add gitleaks wrapper with injectable runner

**Files:**
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing gitleaks tests**

Add:

```python
def test_gitleaks_json_hits_are_converted_to_policy_hits(self):
    mod = load_policy(self)
    report = [{"RuleID": "generic-api-key", "StartLine": 3}]
    hits = mod.parse_gitleaks_report(json.dumps(report))
    self.assertEqual(hits[0].rule_id, "generic-api-key")
    self.assertEqual(hits[0].detector, "gitleaks")
    self.assertEqual(hits[0].line_no, 3)

def test_gitleaks_failure_raises_policy_error(self):
    mod = load_policy(self)
    def failing_runner(*_args, **_kwargs):
        raise FileNotFoundError("gitleaks")
    with self.assertRaises(mod.PolicyExecutionError):
        mod.run_gitleaks("content", runner=failing_runner)
```

Add the gitleaks-only boundary case required by the spec:

```python
def test_raw_to_distilled_gitleaks_only_hit_is_redacted(self):
    mod = load_policy(self)
    text = "safe\nsecret value that regex does not catch\n"
    def runner(*_args, **_kwargs):
        return mod.CompletedGitleaks(1, json.dumps([{"RuleID": "generic-api-key", "StartLine": 2}]), "")
    result = mod.check_boundary("raw_to_distilled", text, project_slug="_unknown", session_ref="s1", gitleaks_runner=runner)
    self.assertIn("[REDACTED LINE: generic-api-key x1]", result.text)
    self.assertNotIn("secret value", result.text)
```

- [ ] **Step 2: Run failing tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.GitleaksTests -v`

Expected: FAIL because parser/wrapper are missing.

- [ ] **Step 3: Implement parser and runner**

Implement `parse_gitleaks_report(report_text)` and `run_gitleaks(text, *, binary="gitleaks", runner=subprocess.run)`. In the real runner path, write input and report under a `TemporaryDirectory()` outside `~/.agents/memory/`, invoke `gitleaks detect --no-git --source <tmp-input> --report-format json --report-path <tmp-report>`, read the report, and let the temporary directory cleanup delete both files. Unit tests must use the injectable runner and must not persist the input payload. Treat exit code `0` as no findings, `1` as findings, and any other code / missing binary as `PolicyExecutionError`.

- [ ] **Step 4: Run gitleaks tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.GitleaksTests -v`

Expected: PASS.

### Task 5: Implement classification and audit writer

**Files:**
- Create: `paulshaclaw/memory/policy/classification.py`
- Create: `paulshaclaw/memory/policy/audit.py`
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing classification and audit tests**

Add:

```python
def test_unknown_project_defaults_private_and_redaction_hit_downgrades(self):
    mod = load_policy(self)
    policy = mod.load_policy()
    no_hit = mod.classify_artifact(policy=policy, project_slug="_unknown", redaction_hits=())
    self.assertEqual(no_hit.level, "private")
    hit = mod.classify_artifact(policy=policy, project_slug="paulshaclaw", redaction_hits=(mod.PolicyHit("github_pat", "regex", 1, "redact"),))
    self.assertEqual(hit.level, "private")

def test_audit_writer_omits_secret_text(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy.jsonl"
        event = mod.PolicyAuditEvent(boundary="external_to_raw", component="hook", session_ref="s1", policy_version="0.1.0", effective_policy_hash="hash", rule_id="github_pat", detector="regex", line_no=2, action="redact")
        mod.append_policy_audit(path, event)
        content = path.read_text(encoding="utf-8")
    record = json.loads(content)
    for field in ("ts", "boundary", "component", "session_ref", "policy_version", "effective_policy_hash", "rule_id", "detector", "line_no", "action"):
        self.assertIn(field, record)
    self.assertEqual(record["component"], "hook")
    self.assertEqual(record["session_ref"], "s1")
    self.assertEqual(record["detector"], "regex")
    self.assertEqual(record["action"], "redact")
    self.assertNotIn("ghp_", content)

def test_audit_event_rejects_raw_text_fields(self):
    mod = load_policy(self)
    with self.assertRaises(TypeError):
        mod.PolicyAuditEvent(boundary="external_to_raw", component="hook", session_ref="s1", policy_version="0.1.0", effective_policy_hash="hash", rule_id="github_pat", detector="regex", line_no=2, action="redact", raw_line="ghp_secret")
```

- [ ] **Step 2: Run failing tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.ClassificationAndAuditTests -v`

Expected: FAIL because classification/audit APIs are missing.

- [ ] **Step 3: Implement classification result and audit JSONL**

Add `ClassificationResult`, `PolicyAuditEvent`, `classify_artifact()`, and `append_policy_audit()`. Keep audit fields explicit; reject any extra payload body field.

- [ ] **Step 4: Run classification/audit tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.ClassificationAndAuditTests -v`

Expected: PASS.

### Task 6: Implement boundary check and safe failure stubs

**Files:**
- Create: `paulshaclaw/memory/policy/boundary.py`
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy.py`

- [ ] **Step 1: Write failing boundary/failure tests**

Add:

```python
def test_raw_to_distilled_boundary_returns_redacted_text_classification_and_metadata(self):
    mod = load_policy(self)
    result = mod.check_boundary("raw_to_distilled", "token=ghp_1234567890abcdefghijklmnopqrstuv", project_slug="paulshaclaw", session_ref="s1", gitleaks_runner=lambda *_a, **_k: mod.CompletedGitleaks(0, "[]", ""))
    self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuv", result.text)
    self.assertEqual(result.classification.level, "private")
    self.assertEqual(result.ledger_metadata["redaction_hits"], 1)
    self.assertIn("github_pat", result.ledger_metadata["redaction_types"])
    self.assertIn(result.ledger_metadata["redaction_stage"], {"importer", "both"})
    self.assertEqual(result.ledger_metadata["policy_version"], result.policy.policy_version)
    self.assertEqual(result.ledger_metadata["effective_policy_hash"], result.policy.effective_policy_hash)

def test_failure_stub_contains_metadata_only(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        stub = mod.write_failure_stub(Path(tmp), session_ref="s1", source_tool="codex", boundary="raw_to_distilled", error_class="PolicyExecutionError", policy_version="0.1.0", effective_policy_hash="hash", ledger_available=False)
        text = stub.read_text(encoding="utf-8")
    self.assertIn("ledger_status", text)
    self.assertNotIn("conversation", text)
    self.assertNotIn("ghp_", text)

def test_fail_closed_retry_exhaustion_writes_stub_unlinks_queue_and_publishes_no_inbox(self):
    mod = load_policy(self)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        queue = root / "queue.json"
        inbox = root / "inbox.md"
        queue.write_text("secret=ghp_1234567890abcdefghijklmnopqrstuv", encoding="utf-8")
        result = mod.handle_policy_failure(queue_path=queue, failed_dir=root / "_failed", inbox_path=inbox, session_ref="s1", source_tool="codex", boundary="raw_to_distilled", error=mod.PolicyExecutionError("boom"), policy=mod.load_policy(), ledger_available=True)
        self.assertFalse(queue.exists())
        self.assertFalse(inbox.exists())
        self.assertTrue(result.stub_path.exists())
        self.assertNotIn("ghp_", result.stub_path.read_text(encoding="utf-8"))

def test_boundary_retries_gitleaks_failure_before_stub(self):
    mod = load_policy(self)
    calls = []
    def failing_runner(*_args, **_kwargs):
        calls.append("call")
        raise FileNotFoundError("gitleaks")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        queue = root / "queue.json"
        inbox = root / "inbox.md"
        queue.write_text("safe text", encoding="utf-8")
        result = mod.process_queue_with_policy(queue_path=queue, inbox_path=inbox, failed_dir=root / "_failed", boundary="raw_to_distilled", project_slug="_unknown", session_ref="s1", source_tool="codex", gitleaks_runner=failing_runner)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.status, "policy-error")
        self.assertFalse(queue.exists())
        self.assertFalse(inbox.exists())
        self.assertTrue(result.stub_path.exists())
        self.assertNotIn("safe text", result.stub_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run failing tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.BoundaryTests -v`

Expected: FAIL because boundary API and stub writer are missing.

- [ ] **Step 3: Implement boundary result and failure stubs**

Implement `check_boundary(boundary, text, *, project_slug, session_ref, policy=None, gitleaks_runner=None)` for MVP boundaries. `external_to_raw` runs regex only. `raw_to_distilled` runs regex + gitleaks, redacts line hits, classifies, and returns `ledger_metadata` with `redaction_hits`, `redaction_types`, `redaction_stage`, `policy_version`, `effective_policy_hash`, and classification fields. Implement `process_queue_with_policy(...)` as the retry-owning wrapper that reads the queue, calls `check_boundary()` up to the boundary retry count, publishes sanitized output only after success, and calls `handle_policy_failure(...)` after exhaustion. Implement `write_failure_stub(failed_dir, ...)` and `handle_policy_failure(...)` writing JSON metadata only, unlinking the queue payload, and never publishing inbox output on fail-closed paths.

- [ ] **Step 4: Run boundary tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy.BoundaryTests -v`

Expected: PASS.

---

## Chunk 3: CLI Helpers, Consumer Lint, Docs, and OpenSpec Completion

### Task 7: Add dry-run and replay CLI surface

**Files:**
- Create: `paulshaclaw/memory/cli.py`
- Create: `paulshaclaw/memory/__main__.py`
- Modify: `paulshaclaw/memory/policy/__init__.py`
- Test: `tests/test_stage2_memory_policy_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add subprocess tests that run:

```bash
python3 -m paulshaclaw.memory memory dry-run-policy s1 --payload-file payload.txt --project paulshaclaw
python3 -m paulshaclaw.memory memory replay --session s1 --payload-file payload.txt --project paulshaclaw --out inbox.md
```

This mirrors the future `psc memory ...` shape even though the repository has no top-level `psc` entrypoint yet. Assert dry-run prints JSON with `rule_id`, `detector`, `line_no`, `action`, `boundary`, `classification_level`, `effective_policy_hash`, and skipped override entries when applicable. Assert dry-run does not create `out` or any inbox file and does not print the matched secret or the original line text. Assert replay calls the same boundary API, writes redacted output and classification metadata to `out`, and includes effective-hash / override visibility in the JSON summary.

- [ ] **Step 2: Run failing CLI tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy_cli -v`

Expected: FAIL because module CLI is missing.

- [ ] **Step 3: Implement CLI**

Use `argparse` with `prog="psc"` and subcommands:

```text
memory dry-run-policy <session-id> --payload-file <path> [--project <slug>]
memory replay --session <session-id> --payload-file <path> --out <path> [--project <slug>]
```

Print JSON summaries. Do not print matched text. Replay uses `policy.check_boundary("raw_to_distilled", ...)` as the importer-logic stand-in until Topic 2 runtime exists, writes a minimal markdown artifact with YAML-like frontmatter keys from the spec and the redacted body, and reports audit/effective-hash metadata.

- [ ] **Step 4: Run CLI tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy_cli -v`

Expected: PASS.

### Task 8: Add policy consumer lint

**Files:**
- Create: `paulshaclaw/memory/lint/__init__.py`
- Create: `paulshaclaw/memory/lint/policy_consumer_lint.py`
- Test: `tests/test_stage2_memory_policy_lint.py`

- [ ] **Step 1: Write failing lint tests**

Define the MVP consumer marker convention: a Python memory consumer is any `.py` file outside `paulshaclaw/memory/policy/` and tests that contains `# memory-consumer` or writes to memory path strings (`inbox/`, `work-centric/`, `knowledge/`, `runtime/index`). Create temp consumer files:

```python
GOOD = 'from paulshaclaw.memory import policy\n# memory-consumer\n\ndef write_memory():\n    policy.check_boundary("raw_to_distilled", "safe", project_slug="_unknown", session_ref="s")\n'
BAD = '# memory-consumer\ndef write_memory():\n    open("inbox.md", "w").write("unsafe")\n'
IMPORT_ONLY_BAD = 'from paulshaclaw.memory import policy\n# memory-consumer\ndef write_memory():\n    open("inbox.md", "w").write("unsafe")\n'
```

Assert lint returns `0` for GOOD and non-zero for BAD and IMPORT_ONLY_BAD when scanning a temp directory.

- [ ] **Step 2: Run failing lint tests**

Run: `python3 -m unittest tests.test_stage2_memory_policy_lint -v`

Expected: FAIL because lint module is missing.

- [ ] **Step 3: Implement conservative lint**

Scan `.py` files. Flag files matching the marker convention unless they contain an actual `check_boundary(` call from the policy API. Importing policy alone is not sufficient. Ignore the policy package and tests.

- [ ] **Step 4: Wire lint into Stage 2 integration check**

Modify `paulshaclaw/memory/tests/stage2_integration_check.sh` to run `python3 -m paulshaclaw.memory.lint.policy_consumer_lint paulshaclaw`.

- [ ] **Step 5: Run lint tests and integration check**

Run:

```bash
python3 -m unittest tests.test_stage2_memory_policy_lint -v
bash paulshaclaw/memory/tests/stage2_integration_check.sh
```

Expected: PASS.

### Task 9: Wire docs and OpenSpec task evidence

**Files:**
- Modify: `README.md`
- Modify: `openspec/changes/stage2-memory-security-policy/tasks.md`
- Modify: `openspec/specs/stage2-memory-governance/spec.md`

- [ ] **Step 1: Confirm README paths exist**

Run:

```bash
test -f docs/superpowers/specs/2026-05-24-stage2-memory-security-policy-design.md
test -d openspec/changes/stage2-memory-security-policy
grep -Fq 'stage2-memory-security-policy' README.md
```

Expected: all commands exit 0.

- [ ] **Step 2: Mark OpenSpec task checklist complete after code/tests pass**

Edit `openspec/changes/stage2-memory-security-policy/tasks.md` from `- [ ]` to `- [x]` only for actually completed tasks. Add verification summary with exact commands and outcomes.

- [ ] **Step 3: Run documentation/path verification**

Run:

```bash
test -f docs/superpowers/specs/2026-05-24-stage2-memory-security-policy-design.md
grep -Fq 'Memory Security Policy' README.md
```

Expected: all commands exit 0.

### Task 10: Final verification, review, archive, policy check, commit, push, PR

**Files:**
- All changed files

- [ ] **Step 1: Run focused Topic 8 tests**

Run:

```bash
python3 -m unittest tests.test_stage2_memory_policy tests.test_stage2_memory_policy_cli tests.test_stage2_memory_policy_lint -v
```

Expected: all Topic 8 tests PASS.

- [ ] **Step 2: Run repository tests and document baseline caveat**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: either all pass or only the known worktree-specific `test_paulshaclaw_self_snapshot_matches_known_state` baseline failure remains. If additional failures appear, fix them before continuing.

- [ ] **Step 3: Request code review**

Invoke `requesting-code-review` and address blocking findings. Do not merge or PR before blocking findings are fixed or explicitly documented as false positives.

- [ ] **Step 4: Run policy check**

Run the repository's policy check if available:

```bash
if command -v policy_check >/dev/null 2>&1; then
  policy_check --repo "$(pwd)"
elif python3 -c 'import policy_check' 2>/dev/null; then
  python3 -m policy_check --repo "$(pwd)"
else
  echo "policy_check unavailable"
fi
```

Expected: PASS or explicit `policy_check unavailable`. If unavailable, document command absence and use focused tests + code review as evidence.

- [ ] **Step 5: Archive the OpenSpec change**

Invoke `openspec-archive-change` after tests and code review. If the OpenSpec CLI is still unavailable, manually mirror the repository-standard archive directory structure, merge the change requirements into `openspec/specs/stage2-memory-governance/spec.md`, remove or move the active change, and update README links from active change path to archive path. Verify:

```bash
test -d openspec/changes/archive
! test -d openspec/changes/stage2-memory-security-policy
grep -Fq 'Stage 2 memory policy boundary contract' openspec/specs/stage2-memory-governance/spec.md
grep -Fq 'openspec/changes/archive/' README.md
! grep -Fq './openspec/changes/stage2-memory-security-policy/' README.md
archive_path="$(grep -o 'openspec/changes/archive/[^)]*stage2-memory-security-policy[^)]*' README.md | head -1)"
test -n "$archive_path"
test -e "$archive_path"
```

Expected: all archive invariants pass.

- [ ] **Step 6: Commit**

Run:

```bash
git status --short
git add README.md docs/superpowers/specs/ docs/superpowers/plans/ openspec/ paulshaclaw/memory/ tests/
git commit -m "feat(stage2): add memory security policy

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Expected: commit succeeds on branch `stage2-memory-security-policy`.

- [ ] **Step 7: Push and open PR**

Run:

```bash
git branch --show-current
test "$(git branch --show-current)" = "stage2-memory-security-policy"
git push -u origin stage2-memory-security-policy
gh pr create --fill --base main --head stage2-memory-security-policy
```

Expected: branch pushed and PR URL printed.
