"""Release 一致性 gate 與 release workflow 結構測試。

涵蓋：
- ``scripts/check-release-consistency.py`` 的不一致 FAIL 行為（VERSION / pyproject /
  CHANGELOG section / vX.Y.Z tag / source revision）。
- ``.github/workflows/release.yml`` 結構：tag 觸發、最小權限、一般 main push 不發布。
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check-release-consistency.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _run_checker(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--repo-root", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_repo(tmp_path: Path, version: str, changelog_sections: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    pyproject_text = textwrap.dedent(
        f"""\
        [project]
        name = "paulshaclaw"
        version = "{version}"
        """
    )
    (repo / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    body = "# Changelog\n\n"
    for section in changelog_sections:
        body += f"{section}\n\n- item\n\n"
    (repo / "CHANGELOG.md").write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@t"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


def test_version_file_matches_pyproject() -> None:
    """checker 不帶 --tag 時只檢查 VERSION/pyproject 一致。"""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", [])
        result = _run_checker(repo)
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_version_pyproject_mismatch_fails() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", [])
        # 故意改 VERSION 與 pyproject 不一致
        (repo / "VERSION").write_text("0.2.0\n", encoding="utf-8")
        result = _run_checker(repo)
        assert result.returncode == 1, result.stdout
        assert "VERSION(0.2.0) != pyproject.toml(0.1.0)" in result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_tag_mismatch_fails() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", ["## [0.1.0] - 2026-01-01"])
        result = _run_checker(repo, "--tag", "v0.2.0")
        assert result.returncode == 1, result.stdout
        assert "VERSION(0.1.0) != tag(0.2.0)" in result.stderr
        assert "pyproject.toml(0.1.0) != tag(0.2.0)" in result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_missing_changelog_section_fails() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        # 只有 Unreleased，沒有 [0.1.0] section
        repo = _make_repo(tmp, "0.1.0", ["## [Unreleased]"])
        result = _run_checker(repo, "--tag", "v0.1.0")
        assert result.returncode == 1, result.stdout
        assert "缺少 ## [0.1.0] release section" in result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_tag_not_at_head_fails() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", ["## [0.1.0] - 2026-01-01"])
        subprocess.run(
            ["git", "-C", str(repo), "tag", "v0.1.0"], check=True
        )
        # 在 tag 之後再 commit，使 tag 不指向 HEAD
        (repo / "extra.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "extra.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "extra"], check=True)
        result = _run_checker(repo, "--tag", "v0.1.0")
        assert result.returncode == 1, result.stdout
        assert "未指向 HEAD" in result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_all_consistent_passes() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", ["## [0.1.0] - 2026-01-01"])
        subprocess.run(["git", "-C", str(repo), "tag", "v0.1.0"], check=True)
        result = _run_checker(repo, "--tag", "v0.1.0")
        assert result.returncode == 0, result.stderr
        assert "@ v0.1.0" in result.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_annotated_tag_at_head_passes() -> None:
    """annotated / signed tag 也必須被視為指向 HEAD。

    `git rev-parse refs/tags/<tag>` 對 annotated tag 解析出的是 tag object SHA
    而非 commit，少了 `^{commit}` 會把正確的 release tag 誤判成 source revision
    不一致——正式 release 慣例上就是打 annotated（甚至 signed）tag。
    """
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", ["## [0.1.0] - 2026-01-01"])
        subprocess.run(
            ["git", "-C", str(repo), "tag", "-a", "v0.1.0", "-m", "release 0.1.0"],
            check=True,
        )
        result = _run_checker(repo, "--tag", "v0.1.0")
        assert result.returncode == 0, result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_extract_notes_outputs_section_body() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(
            tmp,
            "0.1.0",
            ["## [Unreleased]", "## [0.1.0] - 2026-01-01"],
        )
        # 讓 0.1.0 section 有可區分內容
        body = "# Changelog\n\n## [Unreleased]\n\n- unreleased item\n\n## [0.1.0] - 2026-01-01\n\n- released item\n\n## [0.0.1]\n\n- old\n"
        (repo / "CHANGELOG.md").write_text(body, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--repo-root", str(repo), "--extract-notes", "0.1.0"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "- released item" in result.stdout
        assert "- unreleased item" not in result.stdout
        assert "- old" not in result.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_extract_notes_missing_section_fails() -> None:
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        repo = _make_repo(tmp, "0.1.0", ["## [Unreleased]"])
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--repo-root", str(repo), "--extract-notes", "9.9.9"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "9.9.9" in result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- workflow 結構測試 ---


def _load_workflow() -> dict:
    assert WORKFLOW.exists(), f"release workflow 不存在：{WORKFLOW}"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_release_workflow_triggered_by_tag_only() -> None:
    """release workflow 由 vX.Y.Z tag 觸發；一般 main push 不會發布正式版本。"""
    wf = _load_workflow()
    on = wf.get("on") or wf.get(True)  # yaml 可能把 'on' parse 成 True
    assert isinstance(on, dict), on
    push = on.get("push", {})
    tags = push.get("tags", [])
    assert tags == ["v*"], f"push.tags 應為 ['v*']，實際 {tags}"
    branches = push.get("branches")
    # 不得在 push.branches 觸發（否則 main push 會發布）
    assert not branches, f"不得以 push.branches 觸發 release，實際 {branches}"


def test_release_workflow_has_workflow_dispatch_dry_run() -> None:
    """提供 workflow_dispatch 入口供本機／手動 dry-run。"""
    wf = _load_workflow()
    on = wf.get("on") or wf.get(True)
    assert isinstance(on, dict), on
    assert on.get("workflow_dispatch") is not None, "缺少 workflow_dispatch 入口"


def test_release_workflow_minimal_permissions() -> None:
    """權限最小化：只宣告 contents:write（建立 release 必要）。"""
    wf = _load_workflow()
    perms = wf.get("permissions", {})
    assert perms == {"contents": "write"}, f"權限應為 contents:write，實際 {perms}"


def test_release_workflow_runs_version_consistency_gate() -> None:
    """workflow 必須在 build 前呼叫 consistency checker。"""
    wf = _load_workflow()
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "check-release-consistency.py" in text, "workflow 未呼叫 consistency checker"
    assert "python -m build" in text, "workflow 未使用 python -m build"
    assert "gh release create" in text, "workflow 未建立 GitHub Release"
    # fail-closed：不得以 --force 覆寫既有 release
    assert "release create --force" not in text, text