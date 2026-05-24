"""Rule-based inbox bucket classifier for Stage 2 memory importer."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Mapping


def _lower_items(values: list[str]) -> list[str]:
    return [value.lower() for value in values if isinstance(value, str) and value]


def _basename(path: str) -> str:
    return PurePosixPath(path).name.lower()


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _touched_code_file(paths: list[str]) -> bool:
    code_suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".c", ".cc", ".cpp", ".h", ".hpp", ".go", ".rs", ".java")
    return any(path.endswith(code_suffixes) for path in paths)


def classify_session(session: Mapping[str, object]) -> str:
    filename = str(session.get("raw_payload_pointer") or "")
    touched_files = _lower_items(list(session.get("touched_files", [])))
    prompts = _lower_items(list(session.get("user_prompts", [])))
    referenced_artifacts = _lower_items(list(session.get("referenced_artifacts", [])))
    path_inputs = [filename.lower(), *touched_files]
    prompt_text = " ".join(prompts)

    for path in path_inputs:
        base = _basename(path)
        if (
            "docs/superpowers/plans/" in path
            or path.endswith("docs/plan.md")
            or path.endswith("docs/task.md")
            or path.endswith("docs/todo.md")
            or base in {"plan.md", "task.md", "todo.md"}
            or base.endswith("-plan.md")
        ):
            return "plans"
    if _has_any(prompt_text, ("/plan", "implementation plan", "實作計畫")):
        return "plans"

    for path in path_inputs:
        base = _basename(path)
        if (
            "docs/research/" in path
            or path.endswith("docs/spec.md")
            or base == "spec.md"
            or base.endswith("-design.md")
            or ("design" in base and base.endswith(".md"))
        ):
            return "research"
    if _has_any(prompt_text, ("/research", "research", "研究", "survey", "explore", "design doc")) and not _touched_code_file(touched_files):
        return "research"

    for path in [*path_inputs, *referenced_artifacts]:
        base = _basename(path)
        if (
            "reports/" in path
            or "evidence/" in path
            or "evidence" in base
            or "postmortem" in base
            or base.endswith("-report.md")
        ):
            return "reports"
    if _has_any(prompt_text, ("report", "summary", "postmortem", "review", "evidence")) or (
        "test" in prompt_text
        and _has_any(prompt_text, ("result", "results", "verification", "verify"))
        and _has_any(prompt_text, ("attach", "collect", "summarize", "archive"))
    ):
        return "reports"

    return "sessions"
