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

_PLACEHOLDER_PHRASES = ("(無內容)", "尚未收到您的具體需求", "目前尚未收到")
_BARE_PLACEHOLDERS = {"- (none)", "(none)", "(unknown)"}


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


@dataclass(frozen=True)
class NoiseVerdict:
    is_noise: bool
    reason: str


def classify_noise(frontmatter: Mapping[str, object], body: str) -> NoiseVerdict:
    """Classify a knowledge slice as noise using ONLY its body content.

    frontmatter is accepted for interface symmetry but intentionally unused so
    that untitled / no-project slices with real bodies are not mis-dropped.
    """
    del frontmatter
    stripped = body.strip()

    first_line = stripped.splitlines()[0].strip() if stripped else ""
    section = _STRUCTURAL_FIRST_LINE.get(first_line)
    if section is not None:
        return NoiseVerdict(True, f"structural-echo:{section}")

    if stripped in _BARE_PLACEHOLDERS or any(p in stripped for p in _PLACEHOLDER_PHRASES):
        return NoiseVerdict(True, "placeholder")

    if _is_hollow(stripped):
        return NoiseVerdict(True, "empty")

    return NoiseVerdict(False, "")
