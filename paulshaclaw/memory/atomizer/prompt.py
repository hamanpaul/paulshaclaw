from __future__ import annotations

from .splitter import Fragment


def build_prompt(skill_text: str, fragments: list[Fragment], known_projects: list[str]) -> str:
    parts = [
        skill_text,
        "",
        "## Known projects (choose exactly one per slice, or _unknown)",
        ", ".join(known_projects) if known_projects else "_unknown",
        "",
        "## Session fragments to atomize",
    ]
    for fragment in fragments:
        parts.extend(
            [
                f"[fragment {fragment.fragment_index}]",
                f"project: {fragment.project}",
                f"source_agent: {fragment.source_agent}",
                f"source_session: {fragment.source_session}",
                f"source_artifact: {fragment.source_artifact}",
                f"captured_at: {fragment.captured_at}",
                f"provenance.repo: {fragment.provenance.get('repo', '')}",
                f"provenance.commit: {fragment.provenance.get('commit', '')}",
                f"provenance.path: {fragment.provenance.get('path', '')}",
                fragment.body,
                "",
            ]
        )
    parts.extend(
        [
            "## Output",
            "Return ONLY the JSON array specified by the skill's output contract.",
        ]
    )
    return "\n".join(parts)
