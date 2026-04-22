from __future__ import annotations

from .models import PaneRecord


LIST_PANES_FORMAT = "\t".join(
    [
        "#{pane_id}",
        "#{pane_title}",
        "#{pane_current_command}",
        "#{pane_left}",
        "#{pane_top}",
        "#{pane_width}",
        "#{pane_height}",
        "#{pane_active}",
    ]
)


def parse_list_panes(raw: str) -> tuple[PaneRecord, ...]:
    panes: list[PaneRecord] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 7:
            pane_id, title, command, left, top, width, height = parts
            active = "0"
        elif len(parts) == 8:
            pane_id, title, command, left, top, width, height, active = parts
        else:
            # malformed line, skip
            continue
        panes.append(
            PaneRecord(
                pane_id=pane_id,
                title=title,
                command=command,
                left=int(left),
                top=int(top),
                width=int(width),
                height=int(height),
                active=active == "1",
                preview=(),
            )
        )
    return tuple(panes)
