from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE11_TODO = REPO_ROOT / "docs" / "superpowers" / "workstreams" / "stage11-operator-cockpit" / "todo.md"
CLOSEOUT_TODO = REPO_ROOT / "docs" / "superpowers" / "workstreams" / "cockpit-jobs-three-axis-closeout" / "todo.md"
OPENSPEC_TASKS = REPO_ROOT / "openspec" / "changes" / "cockpit-jobs-three-axis-closeout" / "tasks.md"


def _read_required(path: Path) -> str:
    assert path.exists(), f"closeout tracking artifact is missing: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _contains_any(haystack: str, *needles: str) -> bool:
    lowered = haystack.lower()
    return any(needle in haystack or needle.lower() in lowered for needle in needles)


def test_stage11_closeout_todo_records_issue_322_and_pr_329_statuses() -> None:
    text = _read_required(STAGE11_TODO)
    lines = [line.strip() for line in text.splitlines() if "#322" in line or "#329" in line]

    assert any("#329" in line for line in lines), "stage11 closeout todo must mention merged PR #329"
    assert _contains_any(
        "\n".join(line for line in lines if "#329" in line),
        "merged",
        "merge",
        "已合併",
        "合併",
    ), "stage11 closeout todo must record that PR #329 is merged"

    assert any("#322" in line for line in lines), "stage11 closeout todo must mention closed issue #322"
    assert _contains_any(
        "\n".join(line for line in lines if "#322" in line),
        "closed",
        "close",
        "已關閉",
        "關閉",
    ), "stage11 closeout todo must record that issue #322 is closed"


def test_closeout_workstream_keeps_dedicated_tracking_files() -> None:
    closeout_todo = _read_required(CLOSEOUT_TODO)
    openspec_tasks = _read_required(OPENSPEC_TASKS)

    assert _contains_any(
        closeout_todo,
        "#330",
        "cockpit-jobs-three-axis-closeout",
        "three-axis closeout",
    ), "closeout todo must track issue #330 / closeout work item"
    assert _contains_any(
        openspec_tasks,
        "RED",
        "#330",
        "cockpit-jobs-three-axis-closeout",
    ), "OpenSpec tasks must keep the closeout change tracked"
