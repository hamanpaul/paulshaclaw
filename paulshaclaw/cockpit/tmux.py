from __future__ import annotations

from dataclasses import replace
from pathlib import Path
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
        "#{pane_current_path}",
        "#{host_short}",
    ]
)

_MINICOM_COM_RE = re.compile(r"COM(\d+)", re.IGNORECASE)
_MINICOM_DEVICE_RE = re.compile(r"-D\s+(\S+)")

# minicom 常經 wrapper（如 serialwrap-minicom，bash script）啟動，此時 tmux
# #{pane_current_command} 回報的是 shell 而非 minicom。這組 shell 名用來判斷
# 「值得對該 pane 的 tty 探一次 minicom」，把成本鎖在真正可能藏 minicom 的 pane。
_SHELL_COMMANDS = frozenset({"bash", "sh", "zsh", "dash", "ash", "fish"})


def parse_list_panes(raw: str) -> tuple[PaneRecord, ...]:
    panes: list[PaneRecord] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        pane_id, session_name, window_index, title, command, left, top, width, height = parts[:9]
        active = parts[9] if len(parts) >= 10 else "0"
        tty = parts[10] if len(parts) >= 11 else ""
        pane_current_path = parts[11] if len(parts) >= 12 else ""
        host_short = parts[12] if len(parts) >= 13 else ""
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
                pane_tty=tty,
                pane_current_path=pane_current_path,
                host_short=host_short,
            )
        )
    return tuple(panes)


def _bare_tty(tty: str) -> str:
    """tmux #{pane_tty} is like ``/dev/pts/2``; ``ps`` reports the bare ``pts/2``."""
    return tty[len("/dev/"):] if tty.startswith("/dev/") else tty


def _minicom_label_from_args(args: str) -> str | None:
    """Map a process argv line to a ``minicom COMx`` label, or ``None``.

    Match the minicom *binary* (argv0 basename == ``minicom``), NOT a bare
    ``"minicom"`` substring — so benign lines like ``man minicom``,
    ``vim .../serialwrap-minicom``, the ``serialwrap-minicom`` wrapper itself, or
    ``less minicom_COM0.log`` are not mistaken for a live minicom session. The COM
    identity lives in minicom's own argv (``-C .../mini_COM0_*.log`` / ``-D dev``)."""
    stripped = args.strip()
    if not stripped:
        return None
    argv0 = stripped.split(None, 1)[0].rsplit("/", 1)[-1]
    if argv0 != "minicom":
        return None
    matched = _MINICOM_COM_RE.search(args)
    if matched:
        return f"minicom COM{matched.group(1)}"
    device = _MINICOM_DEVICE_RE.search(args)
    if device:
        return f"minicom {device.group(1).rsplit('/', 1)[-1]}"
    return "minicom"


def _run_ps(argv: list[str]) -> str | None:
    """Bounded, decode-safe ``ps``; ``None`` on any failure/timeout.

    ``errors="replace"`` stops undecodable process arguments from raising
    ``UnicodeDecodeError`` up through the refresh path; the 1s timeout and the
    OSError/SubprocessError guard keep a slow/absent ``ps`` from blocking or crashing."""
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def _minicom_map() -> dict[str, str]:
    """One ``ps`` for the whole refresh → ``{bare-tty: "minicom COMx"}``.

    Replaces N per-pane ``ps`` calls (one per title-less shell pane) with a single
    process scan, so a refresh can't fan out into many synchronous forks — nor block
    the UI for seconds if several ttys are slow. First minicom per tty wins."""
    stdout = _run_ps(["ps", "-e", "-o", "tty=", "-o", "args="])
    if stdout is None:
        return {}
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        tty_name, args = parts
        if tty_name in ("?", "-"):
            continue
        label = _minicom_label_from_args(args)
        if label and tty_name not in result:
            result[tty_name] = label
    return result


def _minicom_summary(tty: str) -> str | None:
    """Per-pane fallback: derive ``minicom COMx`` from the minicom process on ``tty``.

    Prefer :func:`_minicom_map` (one ``ps`` for the whole refresh); this single-tty
    probe is the fallback for direct callers that have no precomputed map. Returns
    ``None`` for an empty tty without spawning ``ps``."""
    if not tty:
        return None
    stdout = _run_ps(["ps", "-t", _bare_tty(tty), "-o", "args="])
    if stdout is None:
        return None
    for line in stdout.splitlines():
        label = _minicom_label_from_args(line)
        if label:
            return label
    return None


def _lookup_minicom(tty: str, minicom_by_tty: dict[str, str] | None) -> str | None:
    """Resolve a minicom label for ``tty``: from the batch map when given, else probe."""
    if minicom_by_tty is not None:
        return minicom_by_tty.get(_bare_tty(tty)) if tty else None
    return _minicom_summary(tty)


def derive_summary(
    pane: PaneRecord, minicom_by_tty: dict[str, str] | None = None
) -> str:
    """A readable work-list label: the title when set, else a command fallback.

    minicom is often launched via a wrapper (e.g. ``serialwrap-minicom``), so tmux
    reports the pane command as a shell rather than ``minicom``; for title-less shell
    panes we consult the minicom-by-tty map (or a per-pane probe when no map is given)
    so the pane is still labeled by its COM port. Pass ``minicom_by_tty`` — the result
    of :func:`_minicom_map` — to avoid a per-pane ``ps`` on every refresh."""
    title = pane.title.strip()
    host_short = pane.host_short.strip()
    if title and title != host_short:
        return title
    if pane.command == "minicom" or pane.command in _SHELL_COMMANDS:
        label = _lookup_minicom(pane.pane_tty, minicom_by_tty)
        if label:
            return label
        if pane.command == "minicom":
            return "minicom"
    if pane.pane_current_path:
        return Path(pane.pane_current_path).name or "/"
    return f"[{pane.command}]" if pane.command else ""


class TmuxClient:
    def list_panes(self, *, cockpit_pane_id: str) -> tuple[PaneRecord, ...]:
        """List panes with a readable summary per pane.

        三層版面後 refresh 恆為一次 ``list-panes``（外加 title 缺失 minicom pane
        的小 ``ps``）；cockpit 不再抓任何 pane preview。``cockpit_pane_id`` 保留
        為 loader 契約參數（呼叫端以 keyword 傳入）。"""
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
        # One ``ps`` scan for the whole refresh, shared across all panes, so
        # wrapped-minicom detection can't fan out into a per-pane fork storm.
        minicom_by_tty = _minicom_map()
        _ = cockpit_pane_id
        return tuple(
            replace(
                pane,
                summary=derive_summary(pane, minicom_by_tty),
            )
            for pane in panes
        )
