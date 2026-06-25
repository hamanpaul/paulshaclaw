from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import policy as memory_policy
from .moc import frontmatter_io as _fio
from .moc import moc_builder as _moc_builder
from .noise import classify_noise

BOUNDARY = "raw_to_distilled"


class PayloadReadError(Exception):
    """Raised when a payload file cannot be read as UTF-8 text."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PayloadReadError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    memory = subparsers.add_parser("memory")
    memory_subparsers = memory.add_subparsers(dest="memory_command", required=True)

    dry_run = memory_subparsers.add_parser("dry-run-policy")
    dry_run.add_argument("session_id")
    dry_run.add_argument("--payload-file", required=True)
    dry_run.add_argument("--project", default="_unknown")
    dry_run.add_argument("--override")
    dry_run.set_defaults(func=_dry_run_policy)

    replay = memory_subparsers.add_parser("replay")
    replay.add_argument("--session", required=True)
    replay.add_argument("--payload-file", required=True)
    replay.add_argument("--out", required=True)
    replay.add_argument("--project", default="_unknown")
    replay.add_argument("--override")
    replay.set_defaults(func=_replay)

    janitor = memory_subparsers.add_parser("janitor")
    janitor_subparsers = janitor.add_subparsers(dest="janitor_command", required=True)
    scan = janitor_subparsers.add_parser("scan")
    scan.add_argument("--memory-root", required=True)
    scan.add_argument("--knowledge-root", default=None)
    scan.add_argument("--now", default=None)
    scan.add_argument("--override", default=None)
    scan.add_argument("--dry-run", action="store_true")
    scan.set_defaults(func=_janitor_scan)

    atomize = memory_subparsers.add_parser("atomize")
    atomize.add_argument("--memory-root", required=True)
    atomize.add_argument("--now", default=None)
    atomize.add_argument("--override", default=None)
    atomize.add_argument("--promoter", choices=["identity", "llm"], default=None)
    atomize.add_argument("--agent-command", default=None)
    atomize.add_argument(
        "--instruction-root", action="append", default=None,
        help="agent-instruction doc root/file; when given, drops doc-fragment slices "
             "(verbatim instruction-doc sections) at produce time. Repeatable.")
    atomize.add_argument("--dry-run", action="store_true")
    atomize.set_defaults(func=_atomize)

    dream = memory_subparsers.add_parser("dream")
    dream_subparsers = dream.add_subparsers(dest="dream_command", required=True)
    dream_run = dream_subparsers.add_parser("run")
    dream_run.add_argument("--memory-root", required=True)
    dream_run.add_argument("--now", default=None)
    dream_run.add_argument("--dry-run", action="store_true")
    dream_run.add_argument("--require-idle", action="store_true")
    dream_run.add_argument("--max-load", type=float, default=1.0)
    dream_run.add_argument("--promoter", choices=["identity", "llm"], default=None)
    dream_run.add_argument("--agent-command", default=None)
    dream_run.set_defaults(func=_dream)
    dream_status = dream_subparsers.add_parser("status")
    dream_status.add_argument("--memory-root", required=True)
    dream_status.set_defaults(func=_dream)

    skillopt = memory_subparsers.add_parser("skillopt")
    skillopt_subparsers = skillopt.add_subparsers(dest="skillopt_command", required=True)
    skillopt_run = skillopt_subparsers.add_parser("run")
    skillopt_run.add_argument("--memory-root", default=str(Path.home() / ".agents" / "memory"))
    skillopt_run.add_argument("--reference-root", default=str(Path.home() / "notes"))
    skillopt_run.add_argument("--skill-path", default=None)
    skillopt_run.add_argument("--budget", type=int, default=1)
    skillopt_run.add_argument("--dry-run", action="store_true")
    skillopt_run.add_argument("--now", default=None)
    skillopt_run.set_defaults(func=_skillopt)

    bundle_p = memory_subparsers.add_parser("bundle")
    bundle_p.add_argument("--memory-root", required=True)
    bundle_p.add_argument("--project", default=None)
    bundle_p.add_argument("--tag", action="append", default=None)
    bundle_p.add_argument("--entity", default=None)
    bundle_p.add_argument("--include-decayed", action="store_true")
    bundle_p.add_argument("--out", required=True)
    bundle_p.add_argument("--now", default=None)
    bundle_p.set_defaults(func=_bundle)

    search_p = memory_subparsers.add_parser("search")
    search_p.add_argument("query")
    search_p.add_argument("--memory-root", required=True)
    search_p.add_argument("--project", default=None)
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--include-decayed", action="store_true")
    search_p.set_defaults(func=_search)

    wakeup_p = memory_subparsers.add_parser("wakeup")
    wakeup_p.add_argument("--memory-root", default=str(Path.home() / ".agents" / "memory"))
    wakeup_p.add_argument("--project", default=None)
    wakeup_p.add_argument("--cwd", default=None)
    wakeup_p.add_argument("--k", type=int, default=8)
    wakeup_p.add_argument("--char-budget", type=int, default=8000)
    wakeup_p.add_argument("--now", default=None)
    wakeup_p.set_defaults(func=_wakeup)

    syncback = memory_subparsers.add_parser("syncback")
    syncback_subparsers = syncback.add_subparsers(dest="syncback_command", required=True)
    syncback_check = syncback_subparsers.add_parser("check")
    syncback_check.add_argument("--repo-root", default=".")
    syncback_check.add_argument("--no-run-tests", action="store_true")
    syncback_check.add_argument("--json", action="store_true")
    syncback_check.add_argument("--now", default=None)
    syncback_check.set_defaults(func=_syncback)

    knowledge = memory_subparsers.add_parser("knowledge")
    knowledge_subparsers = knowledge.add_subparsers(dest="knowledge_command", required=True)
    prune = knowledge_subparsers.add_parser("prune-noise")
    prune.add_argument("--memory-root", required=True)
    prune.add_argument("--now", default=None)
    prune.add_argument(
        "--instruction-root", action="append", default=None,
        help="agent-instruction doc root/file (CLAUDE.md/AGENTS.md/GEMINI.md). Repeatable. "
             "When given, enables doc-fragment pruning against that corpus; omit to disable.")
    prune.add_argument(
        "--project", action="append", default=None,
        help="restrict pruning to these project(s). Repeatable; omit to scan all projects.")
    group = prune.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    prune.set_defaults(func=_prune_noise)

    retitle = knowledge_subparsers.add_parser("retitle-untitled")
    retitle.add_argument("--memory-root", required=True)
    retitle.add_argument("--now", default=None)
    retitle.add_argument(
        "--instruction-root", action="append", default=None,
        help="agent-instruction doc root/file; builds the doc-fragment guard corpus so "
             "instruction fragments are skipped (left for prune-noise) instead of retitled.")
    retitle.add_argument("--agent-command", default=None,
                         help="override the title-distillation command (default: gemma4 wrapper).")
    retitle.add_argument(
        "--project", action="append", default=None,
        help="restrict retitling to these project(s). Repeatable; omit to scan all projects.")
    rgroup = retitle.add_mutually_exclusive_group()
    rgroup.add_argument("--dry-run", action="store_true")
    rgroup.add_argument("--apply", action="store_true")
    retitle.set_defaults(func=_retitle_untitled)

    usage_p = memory_subparsers.add_parser("usage")
    usage_p.add_argument("--memory-root", required=True)
    usage_p.add_argument("--since", default=None)
    usage_p.add_argument("--json", action="store_true")
    usage_p.set_defaults(func=_memory_usage)

    return parser


def _dry_run_policy(args: argparse.Namespace) -> int:
    payload = _read_payload(args.payload_file)
    policy = _load_policy(args.override)
    result = _check(payload, session_ref=args.session_id, project_slug=args.project, policy=policy)
    summary = _summary(
        result,
        skipped_overrides=_skipped_overrides(
            payload,
            policy=policy,
            session_ref=args.session_id,
            boundary=BOUNDARY,
        ),
        override_path=args.override,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


def _replay(args: argparse.Namespace) -> int:
    payload = _read_payload(args.payload_file)
    policy = _load_policy(args.override)
    result = _check(payload, session_ref=args.session, project_slug=args.project, policy=policy)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_artifact(result), encoding="utf-8")
    _append_replay_audit(result, session_ref=args.session, audit_path=_replay_audit_path(out))
    summary = _summary(
        result,
        skipped_overrides=_skipped_overrides(
            payload,
            policy=policy,
            session_ref=args.session,
            boundary=BOUNDARY,
        ),
        override_path=args.override,
    )
    summary["out"] = str(out)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _janitor_scan(args: argparse.Namespace) -> int:
    from .janitor import cli as janitor_cli
    return janitor_cli.run(args)


def _atomize(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .atomizer.cli import run as atomize_run

    if args.now is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return atomize_run(args)


def _dream(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .dream.cli import run as dream_run

    if getattr(args, "now", None) is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return dream_run(args)


def _skillopt(args: argparse.Namespace) -> int:
    from .skillopt import cli as skillopt_cli

    return skillopt_cli.run(args)


def _bundle(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .replay.cli import run as bundle_run

    if args.now is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return bundle_run(args)


def _search(args: argparse.Namespace) -> int:
    from .moc.cli import run as search_run

    return search_run(args)


def _wakeup(args: argparse.Namespace) -> int:
    from .wakeup import cli as wakeup_cli

    return wakeup_cli.run(args)


def _syncback(args: argparse.Namespace) -> int:
    from .syncback import cli as syncback_cli

    return syncback_cli.run(args)


def _write_manifest(manifest: Path, rows: list[dict]) -> None:
    # Atomic replace so the manifest is never left half-written (#139 finding 2).
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(manifest)


def _prune_noise(args: argparse.Namespace) -> int:
    from .instruction_corpus import corpus_for_roots

    root = Path(args.memory_root)
    now = (args.now or datetime.now(timezone.utc).isoformat()).replace("+00:00", "Z")
    apply = bool(getattr(args, "apply", False))
    corpus = corpus_for_roots(getattr(args, "instruction_root", None))
    projects = getattr(args, "project", None)
    knowledge = root / "knowledge"

    # Phase 1: scan + classify only. No deletes yet — build the full candidate list.
    rows: list[dict] = []
    for path in sorted(knowledge.rglob("*.md")):
        if path.name.endswith("-moc.md"):
            continue
        try:
            fm, body = _fio.read(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            # Unreadable/non-UTF-8 slice: cannot classify, so never delete it. When a
            # project filter is set we cannot confirm scope, so skip rather than record.
            if projects:
                continue
            rows.append({"slice_id": "", "project": "", "path": str(path),
                         "reason": "unreadable", "status": "error", "error": str(exc)})
            continue
        if fm.get("memory_layer") != "knowledge":
            continue
        if projects and str(fm.get("project", "")) not in projects:
            continue
        verdict = classify_noise(fm, body, doc_corpus=corpus)
        if not verdict.is_noise:
            continue
        rows.append({"slice_id": str(fm.get("slice_id", "")), "project": str(fm.get("project", "")),
                     "path": str(path), "reason": verdict.reason,
                     "status": "planned" if apply else "dry-run"})

    ledger_dir = root / "runtime" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    safe_now = now.replace(":", "")  # strip ':' for filesystem-safe filename; Z-normalized so no '+'
    manifest = ledger_dir / f"prune-{safe_now}.jsonl"

    # Phase 2: persist the planned manifest BEFORE any unlink, so a later failure can
    # never leave deletes without a durable audit record (#139 finding 2).
    _write_manifest(manifest, rows)

    # Phase 3: delete, updating each row's status, then atomically rewrite the manifest.
    if apply:
        deleted = False
        for row in rows:
            if row["status"] != "planned":
                continue
            try:
                Path(row["path"]).unlink()
                row["status"] = "deleted"
                deleted = True
            except OSError as exc:
                row["status"] = "error"
                row["error"] = str(exc)
        _write_manifest(manifest, rows)
        if deleted:
            _moc_builder.build_mocs(root, now=now)

    stats = Counter(r["reason"] for r in rows)
    print(json.dumps({"scanned_noise": len(rows), "applied": apply, "by_reason": dict(stats),
                      "manifest": str(manifest)}, ensure_ascii=False))
    return 0


def _retitle_untitled(args: argparse.Namespace) -> int:
    from . import retitle as retitle_mod
    from .importer.title import generate_atom_title

    from .instruction_corpus import corpus_for_roots

    root = Path(args.memory_root)
    now = (args.now or datetime.now(timezone.utc).isoformat()).replace("+00:00", "Z")
    apply = bool(getattr(args, "apply", False))
    corpus = corpus_for_roots(getattr(args, "instruction_root", None))

    command = getattr(args, "agent_command", None)
    title_kwargs = {"command": tuple(command.split())} if command else {}

    def distill(body: str):
        title, _source = generate_atom_title(body, **title_kwargs)
        return title

    summary = retitle_mod.retitle_untitled(
        root, now=now, apply=apply, distill=distill, doc_corpus=corpus,
        projects=getattr(args, "project", None))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def _memory_usage(args: argparse.Namespace) -> int:
    from collections import defaultdict

    ledger = Path(args.memory_root) / "runtime" / "ledger" / "memory_usage.jsonl"
    rows = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.since and str(e.get("ts", "")) < args.since:
                continue
            rows.append(e)

    agg = defaultdict(lambda: {"offered_count": 0, "cited_count": 0, "matched_count": 0, "last_used": ""})
    for e in rows:
        ts = str(e.get("ts", ""))
        for sid in e.get("offered", []):
            agg[sid]["offered_count"] += 1
        for sid in e.get("cited", []):
            agg[sid]["cited_count"] += 1
            if ts > agg[sid]["last_used"]:
                agg[sid]["last_used"] = ts
        for sid in e.get("matched", []):
            agg[sid]["matched_count"] += 1
            if ts > agg[sid]["last_used"]:
                agg[sid]["last_used"] = ts

    slices = [{"slice_id": sid, **v} for sid, v in agg.items()]
    slices.sort(key=lambda s: (s["cited_count"], s["matched_count"]), reverse=True)
    never_used = sum(
        1 for s in slices
        if s["offered_count"] > 0 and s["cited_count"] == 0 and s["matched_count"] == 0
    )
    n = len(rows)
    total_cited = sum(len(e.get("cited", [])) for e in rows)
    total_matched = sum(len(e.get("matched", [])) for e in rows)
    summary = {
        "sessions": n, "slices": len(slices), "never_used": never_used,
        "avg_cited_per_session": round(total_cited / n, 3) if n else 0.0,
        "avg_matched_per_session": round(total_matched / n, 3) if n else 0.0,
    }
    report = {"summary": summary, "slices": slices}

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"sessions={summary['sessions']} slices={summary['slices']} "
              f"never_used={summary['never_used']} "
              f"avg_cited/session={summary['avg_cited_per_session']} "
              f"avg_matched/session={summary['avg_matched_per_session']}")
        for s in slices[:30]:
            print(f"  {s['slice_id']}  offered={s['offered_count']} cited={s['cited_count']} "
                  f"matched={s['matched_count']} last_used={s['last_used']}")
    return 0


def _load_policy(override_path: str | None):
    if override_path is None:
        return memory_policy.load_policy()
    return memory_policy.load_policy(override_path=override_path)


def _read_payload(payload_file: str) -> str:
    path = Path(payload_file)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PayloadReadError(f"cannot read payload file {path!s}: {exc}") from None
    except OSError as exc:
        raise PayloadReadError(f"cannot read payload file {path!s}: {exc}") from None


def _check(text: str, *, session_ref: str, project_slug: str, policy):
    return memory_policy.check_boundary(
        BOUNDARY,
        text,
        project_slug=project_slug,
        session_ref=session_ref,
        policy=policy,
    )


def _summary(result, *, skipped_overrides: list[dict[str, object]], override_path: str | None) -> dict[str, object]:
    metadata = dict(result.ledger_metadata)
    metadata.update(
        {
            "boundary": BOUNDARY,
            "hits": [_hit_summary(hit, BOUNDARY) for hit in result.hits],
            "policy_version": result.policy.policy_version,
            "effective_policy_hash": result.policy.effective_policy_hash,
            "skipped_overrides": skipped_overrides,
            "override_path": str(override_path) if override_path else None,
        }
    )
    return metadata


def _hit_summary(hit, boundary: str) -> dict[str, object]:
    return {
        "rule_id": hit.rule_id,
        "detector": hit.detector,
        "line_no": hit.line_no,
        "action": hit.action,
        "boundary": boundary,
    }


def _skipped_overrides(text: str, *, policy, session_ref: str, boundary: str) -> list[dict[str, object]]:
    skipped: list[dict[str, object]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule in policy.secret_rules.values():
            if rule.detector != "regex" or not memory_policy.is_rule_disabled(policy, rule.rule_id, session_ref):
                continue
            if re.search(rule.pattern, line):
                skipped.append(
                    {
                        "rule_id": rule.rule_id,
                        "detector": rule.detector,
                        "line_no": line_no,
                        "action": "skipped",
                        "boundary": boundary,
                    }
                )
    return skipped


def _artifact(result) -> str:
    classification = result.classification
    return "".join(
        (
            "---\n",
            f"classification_level: {_yaml_scalar(classification.level)}\n",
            f"classification_reason: {_yaml_scalar(classification.reason)}\n",
            f"classification_policy_hash: {_yaml_scalar(classification.policy_hash)}\n",
            f"classification_source: {_yaml_scalar(classification.source)}\n",
            "---\n\n",
            result.text,
        )
    )


def _yaml_scalar(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
        or ": " in value
        or "#" in value
    ):
        return json.dumps(value)
    return value


def _append_replay_audit(result, *, session_ref: str, audit_path: Path) -> None:
    boundary_policy = result.policy.boundaries.get(BOUNDARY)
    if boundary_policy is None or not boundary_policy.audit_required:
        return
    memory_policy.append_policy_audits(
        audit_path,
        memory_policy.build_policy_audit_events(
            boundary=BOUNDARY,
            component=str(result.ledger_metadata["redaction_stage"]),
            session_ref=session_ref,
            policy=result.policy,
            hits=result.hits,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())


def _replay_audit_path(out: Path) -> Path:
    return out.with_name(f"{out.stem}.policy-audit.jsonl")
