"""Deterministic Stage 2 frontmatter and Markdown rendering."""

from __future__ import annotations

from .adapters.base import NormalizedSession


_BUCKET_TO_ARTIFACT = {
    "sessions": "session",
    "session": "session",
    "plans": "plan",
    "plan": "plan",
    "research": "research",
    "reports": "report",
    "report": "report",
}


def _value(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ")


def _required_value(value: object, default: str = "_unknown") -> str:
    rendered = _value(value)
    return rendered if rendered else default


def _artifact_name(classifier_bucket: str | None) -> str:
    if not classifier_bucket:
        return "session"
    return _BUCKET_TO_ARTIFACT.get(classifier_bucket, classifier_bucket.rstrip("s") or "session")


def _bullet_list(items: list[str]) -> list[str]:
    if not items:
        return ["- (none)"]
    return [f"- {item}" for item in items]


def _prompt_list(items: list[str]) -> list[str]:
    if not items:
        return ["- (none)"]
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]


def render_markdown(
    session: NormalizedSession,
    *,
    project: str = "_unknown",
    classifier_bucket: str | None = "session",
    captured_at: str | None = None,
    memory_layer: str = "inbox",
) -> str:
    source_artifact = _artifact_name(classifier_bucket)
    captured = captured_at or session.get("ended_at") or session.get("started_at") or ""
    lines = [
        "---",
        f"memory_layer: {_value(memory_layer)}",
        f"project: {_value(project or '_unknown')}",
        f"source_agent: {_value(session.get('tool'))}",
        f"source_session: {_value(session.get('session_id'))}",
        f"source_artifact: {_value(source_artifact)}",
        f"captured_at: {_value(captured)}",
        "provenance:",
        f"  repo: {_required_value(session.get('repo'))}",
        f"  commit: {_required_value(session.get('commit'))}",
        f"  path: {_required_value(session.get('raw_payload_pointer'))}",
        "---",
        "",
        f"# Session {_value(session.get('session_id'))}",
        "",
        "## Source",
        f"- Tool: {_value(session.get('tool'))}",
        f"- Session: {_value(session.get('session_id'))}",
        f"- Raw payload: {_value(session.get('raw_payload_pointer'))}",
        "",
        "## CWD",
        _value(session.get("cwd")) or "(unknown)",
        "",
        "## Touched files",
        *_bullet_list(session.get("touched_files", [])),
        "",
        "## Referenced artifacts",
        *_bullet_list(session.get("referenced_artifacts", [])),
        "",
        "## Prompts",
        *_prompt_list(session.get("user_prompts", [])),
        "",
    ]
    return "\n".join(lines)
