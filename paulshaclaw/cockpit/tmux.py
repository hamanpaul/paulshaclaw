from __future__ import annotations

import re
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
        "#{pane_tty}",
    ]
)

_MINICOM_COM_RE = re.compile(r"COM(\d+)", re.IGNORECASE)
_MINICOM_DEVICE_RE = re.compile(r"-D\s+(\S+)")


def parse_list_panes(raw: str) -> tuple[PaneRecord, ...]:
    panes: list[PaneRecord] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        tty = ""
        if len(parts) == 11:
            (pane_id, session_name, window_index, title, command,
             left, top, width, height, active, tty) = parts
        elif len(parts) == 10:
            pane_id, session_name, window_index, title, command, left, top, width, height, active = parts
        elif len(parts) == 9:
            pane_id, session_name, window_index, title, command, left, top, width, height = parts
            active = "0"
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
                pane_tty=tty,
            )
        )
    return tuple(panes)


def _minicom_summary(tty: str) -> str | None:
    """Derive a label like ``minicom COM0`` from the minicom process on ``tty``.

    minicom doesn't set a pane title, so the only place the COM identity lives is
    its argv (``-C .../mini_COM0_*.log`` / ``-D <device>``). Read it with a
    bounded, short-timeout ``ps`` so this stays cheap on every refresh."""
    if not tty:
        return None
    # tmux #{pane_tty} is like "/dev/pts/2"; `ps -t` wants the bare tty name
    # ("pts/2"), so strip the /dev/ prefix to keep the lookup portable.
    tty_name = tty[len("/dev/"):] if tty.startswith("/dev/") else tty
    try:
        completed = subprocess.run(
            ["ps", "-t", tty_name, "-o", "args="],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in completed.stdout.splitlines():
        if "minicom" not in line:
            continue
        matched = _MINICOM_COM_RE.search(line)
        if matched:
            return f"minicom COM{matched.group(1)}"
        device = _MINICOM_DEVICE_RE.search(line)
        if device:
            return f"minicom {device.group(1).rsplit('/', 1)[-1]}"
        return "minicom"
    return None


def derive_summary(pane: PaneRecord) -> str:
    """A readable work-list label: the title when set, else a command fallback."""
    if pane.title.strip():
        return pane.title
    if pane.command == "minicom":
        return _minicom_summary(pane.pane_tty) or "minicom"
    return f"[{pane.command}]" if pane.command else ""


class TmuxClient:
    def list_panes(
        self, *, cockpit_pane_id: str, capture_previews: bool = True
    ) -> tuple[PaneRecord, ...]:
        """List panes with a readable summary per pane.

        ``capture_previews=False`` skips the per-pane ``capture-pane`` calls so a
        periodic UI refresh stays cheap (one ``list-panes`` plus a tiny ``ps``
        only for title-less minicom panes); the detail view captures the selected
        pane's preview on demand instead."""
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
        enriched: list[PaneRecord] = []
        for pane in panes:
            preview = ()
            if capture_previews and pane.pane_id != cockpit_pane_id:
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
                    pane_tty=pane.pane_tty,
                    summary=derive_summary(pane),
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
