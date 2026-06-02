from __future__ import annotations

from .splitter import Fragment


def build_prompt(skill_text: str, fragments: list[Fragment], known_projects: list[str]) -> str:
    sections = [skill_text.rstrip("\n")]
    if known_projects:
        sections.append("\n".join(known_projects))
    if fragments:
        sections.append(
            "\n\n".join(
                f"[fragment {fragment.fragment_index}]\n{fragment.body}"
                for fragment in fragments
            )
        )
    return "\n\n".join(sections)
