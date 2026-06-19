from __future__ import annotations

from paulshaclaw.core.config import AppConfig


def render_pane_task_view(config: AppConfig) -> str:
    lines = [
        "pane | title   | task         | status",
        "-----+---------+--------------+--------",
    ]
    for assignment in config.pane_assignments:
        lines.append(
            f"{assignment.pane_id:<4} | "
            f"{assignment.title:<7} | "
            f"{assignment.task_id:<12} | "
            f"{assignment.status}"
        )
    return "\n".join(lines)
