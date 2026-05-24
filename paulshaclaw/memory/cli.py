from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Sequence

from . import policy as memory_policy

BOUNDARY = "raw_to_distilled"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


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

    return parser


def _dry_run_policy(args: argparse.Namespace) -> int:
    payload = Path(args.payload_file).read_text(encoding="utf-8")
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
    payload = Path(args.payload_file).read_text(encoding="utf-8")
    policy = _load_policy(args.override)
    result = _check(payload, session_ref=args.session, project_slug=args.project, policy=policy)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_artifact(result), encoding="utf-8")
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


def _load_policy(override_path: str | None):
    return memory_policy.load_policy(override_path=override_path)


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
            f"classification_level: {classification.level}\n",
            f"classification_reason: {classification.reason}\n",
            f"classification_policy_hash: {classification.policy_hash}\n",
            f"classification_source: {classification.source}\n",
            "---\n\n",
            result.text,
        )
    )
