"""Stage 2 knowledge noise classifier (#139 P2). Body-content only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

# importer/frontmatter.render_markdown 的結構段落 heading。
_STRUCTURAL_SECTIONS = (
    "CWD", "Source", "Prompts", "Touched files", "Referenced artifacts", "Summary",
)
_STRUCTURAL_FIRST_LINE = {f"## {name}": name for name in _STRUCTURAL_SECTIONS}

_HEADING_LINE = re.compile(r"^#{1,6}\s")
_LIST_ITEM = re.compile(r"^(?:[-*+]\s|\d+[.)]\s)")

_PLACEHOLDER_PHRASES = ("(無內容)", "尚未收到您的具體需求", "目前尚未收到")
_BARE_PLACEHOLDERS = {"- (none)", "(none)", "(unknown)"}
# A placeholder is deletion-grade noise only when the body *opens* with the
# boilerplate, not when a real note merely quotes it deeper in the text (#139
# finding 3). The importer's empty-session bodies all begin with the phrase.
_PLACEHOLDER_HEAD_WINDOW = 12


def _content_lines(stripped: str) -> list[str]:
    """Prose lines: non-blank lines that are neither markdown headings nor list items."""
    out: list[str] = []
    for line in stripped.splitlines():
        s = line.strip()
        if not s or _HEADING_LINE.match(s) or _LIST_ITEM.match(s):
            continue
        out.append(s)
    return out


def _is_hollow(stripped: str) -> bool:
    """True when nothing but markdown heading lines / blanks remains.

    Content-based (NOT a length threshold): covers真正空白與純標題片段
    （如 `# Session <uuid>`）。
    """
    for line in stripped.splitlines():
        s = line.strip()
        if s and not _HEADING_LINE.match(s):
            return False
    return True


def _structural_echo_section(stripped: str) -> str | None:
    """Return the structural section name iff the body is an importer-template echo.

    Requires the first line to be a structural heading AND the body to carry no
    substantial prose (≤1 prose line). Importer sections are a path / list / one
    short line; a real note that merely *starts* with `## Summary` but then has
    multiple prose lines is NOT an echo and must be kept (#139 finding 3).
    """
    first_line = stripped.splitlines()[0].strip() if stripped else ""
    section = _STRUCTURAL_FIRST_LINE.get(first_line)
    if section is None:
        return None
    if len(_content_lines(stripped)) > 1:
        return None
    return section


def _opens_with_placeholder(stripped: str) -> bool:
    if stripped in _BARE_PLACEHOLDERS:
        return True
    head = stripped[:_PLACEHOLDER_HEAD_WINDOW]
    return any(p in head for p in _PLACEHOLDER_PHRASES)


@dataclass(frozen=True)
class NoiseVerdict:
    is_noise: bool
    reason: str


def classify_noise(frontmatter: Mapping[str, object], body: str) -> NoiseVerdict:
    """Classify a knowledge slice as noise using ONLY its body content.

    frontmatter is accepted for interface symmetry but intentionally unused so
    that untitled / no-project slices with real bodies are not mis-dropped.
    Deletion-grade: each rule is shaped to avoid removing real knowledge (#139).
    """
    del frontmatter
    stripped = body.strip()

    section = _structural_echo_section(stripped)
    if section is not None:
        return NoiseVerdict(True, f"structural-echo:{section}")

    if _opens_with_placeholder(stripped):
        return NoiseVerdict(True, "placeholder")

    if _is_hollow(stripped):
        return NoiseVerdict(True, "empty")

    return NoiseVerdict(False, "")
