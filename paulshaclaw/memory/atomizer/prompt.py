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
        parts.extend([f"[fragment {fragment.fragment_index}]", fragment.body, ""])
    parts.extend(
        [
            "## Output",
            "Return ONLY the JSON array specified by the skill's output contract.",
        ]
    )
    return "\n".join(parts)
