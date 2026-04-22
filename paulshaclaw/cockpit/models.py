from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotAnchor:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class PaneRecord:
    pane_id: str
    title: str
    command: str
    left: int
    top: int
    width: int
    height: int
    active: bool
    preview: tuple[str, ...]

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def anchor(self) -> SlotAnchor:
        return SlotAnchor(
            left=self.left,
            top=self.top,
            width=self.width,
            height=self.height,
        )


@dataclass(frozen=True)
class JobSummary:
    source: str
    status: str
    trace_id: str | None
    pane_id: str | None
    scope: str | None


@dataclass(frozen=True)
class PaneDetail:
    pane: PaneRecord
    jobs: tuple[JobSummary, ...]
    degraded_reason: str | None
