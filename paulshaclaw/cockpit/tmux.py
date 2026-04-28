from __future__ import annotations

import subprocess

from .models import PaneRecord


LIST_PANES_FORMAT = "\t".join(
    [
        "#{pane_id}",
        "#{session_name}",
        "#{window_index}",
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
        if len(parts) == 9:
            pane_id, session_name, window_index, title, command, left, top, width, height = parts
            active = "0"
        elif len(parts) == 10:
            pane_id, session_name, window_index, title, command, left, top, width, height, active = parts
        else:
            continue
        try:
            left_value = int(left)
            top_value = int(top)
            width_value = int(width)
            height_value = int(height)
        except ValueError:
            continue
        panes.append(
            PaneRecord(
                pane_id=pane_id,
                session_name=session_name,
                window_index=window_index,
                title=title,
                command=command,
                left=left_value,
                top=top_value,
                width=width_value,
                height=height_value,
                active=active == "1",
                preview=(),
            )
        )
    return tuple(panes)


class TmuxClient:
    def __init__(self, session_name: str | None = None) -> None:
        self.session_name = session_name

    def list_panes(self, *, cockpit_pane_id: str) -> tuple[PaneRecord, ...]:
        try:
            completed = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", LIST_PANES_FORMAT],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ()
        panes = parse_list_panes(completed.stdout)
        if self.session_name:
            panes = tuple(pane for pane in panes if pane.session_name == self.session_name)
        enriched: list[PaneRecord] = []
        for pane in panes:
            preview = ()
            if pane.pane_id != cockpit_pane_id:
                try:
                    preview = self.capture_preview(pane.pane_id)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    preview = ()
            enriched.append(
                PaneRecord(
                    pane_id=pane.pane_id,
                    session_name=pane.session_name,
                    window_index=pane.window_index,
                    title=pane.title,
                    command=pane.command,
                    left=pane.left,
                    top=pane.top,
                    width=pane.width,
                    height=pane.height,
                    active=pane.active,
                    preview=preview,
                )
            )
        return tuple(enriched)

    def capture_preview(self, pane_id: str, *, lines: int = 20) -> tuple[str, ...]:
        completed = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return tuple(line.rstrip() for line in completed.stdout.splitlines() if line.strip())
