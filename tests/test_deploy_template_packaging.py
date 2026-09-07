"""Regression coverage for deploy template package-data parity."""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from paulshaclaw.deploy.planner import build_command_plan


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "paulshaclaw"
TEMPLATE_MARKER = "paulshaclaw/deploy/templates/"


def _run_build(source: Path, output_dir: Path, *build_targets: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(output_dir),
            *build_targets,
            str(source),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"build 失敗 (targets={build_targets}):\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )


def _source_template_paths() -> set[str]:
    return {
        path.relative_to(PACKAGE_ROOT / "deploy" / "templates").as_posix()
        for path in (PACKAGE_ROOT / "deploy" / "templates").rglob("*.tmpl")
        if path.is_file()
    }


def _archive_template_paths(names: list[str]) -> set[str]:
    return {
        name.split(TEMPLATE_MARKER, 1)[1]
        for name in names
        if TEMPLATE_MARKER in name and name.endswith(".tmpl")
    }


def _assert_wheel_contract(zf: zipfile.ZipFile) -> None:
    names = set(zf.namelist())
    assert "paulshaclaw/core/commands.json" in names
    assert "paulshaclaw/cockpit/cockpit.tcss" in names
    for module in ("lock", "services", "supervisor", "cli"):
        assert f"paulshaclaw/launcher/{module}.py" in names

    entry_points = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
    assert len(entry_points) == 1
    entry_point_text = zf.read(entry_points[0]).decode("utf-8")
    assert "psc = paulshaclaw.cli:main" in entry_point_text
    assert "paulshaclaw = paulshaclaw.launcher.cli:main" in entry_point_text


def _assert_sdist_contract(tf: tarfile.TarFile) -> None:
    names = tf.getnames()
    assert any(name.endswith("/paulshaclaw/core/commands.json") for name in names)
    assert any(name.endswith("/paulshaclaw/cockpit/cockpit.tcss") for name in names)
    for module in ("lock", "services", "supervisor", "cli"):
        assert any(name.endswith(f"/paulshaclaw/launcher/{module}.py") for name in names)

    pyproject_member = next(name for name in names if name.endswith("/pyproject.toml"))
    pyproject_text = tf.extractfile(pyproject_member).read().decode("utf-8")
    assert 'psc = "paulshaclaw.cli:main"' in pyproject_text
    assert 'paulshaclaw = "paulshaclaw.launcher.cli:main"' in pyproject_text


def test_source_sdist_and_rebuilt_wheel_ship_the_planner_templates(tmp_path: Path) -> None:
    """All build forms must carry exactly the source template set.

    This intentionally fails until deploy templates are declared as package data.
    Comparing paths (rather than a count or a fixed number) catches omissions,
    unexpected paths, empty package directories, and planner/source drift.
    """
    source_templates = _source_template_paths()
    assert source_templates, "source deploy template set must not be empty"
    planner_templates = {
        asset.template_relpath
        for asset in build_command_plan(
            "install", instance_name="packaging-test", root_dir="/srv/paulshaclaw"
        ).templates
    }
    assert planner_templates
    assert planner_templates <= source_templates

    source_dist = tmp_path / "source-dist"
    source_dist.mkdir()
    _run_build(REPO_ROOT, source_dist, "--wheel", "--sdist")
    source_wheel = next(source_dist.glob("*.whl"))
    source_sdist = next(source_dist.glob("*.tar.gz"))

    with zipfile.ZipFile(source_wheel) as zf:
        assert _archive_template_paths(zf.namelist()) == source_templates
        _assert_wheel_contract(zf)

    with tarfile.open(source_sdist, "r:gz") as tf:
        assert _archive_template_paths(tf.getnames()) == source_templates
        _assert_sdist_contract(tf)

        extracted_root = tmp_path / "sdist-source"
        extracted_root.mkdir()
        tf.extractall(extracted_root)

    extracted_project = next(path for path in extracted_root.iterdir() if path.is_dir())
    rebuilt_dist = tmp_path / "rebuilt-dist"
    rebuilt_dist.mkdir()
    _run_build(extracted_project, rebuilt_dist, "--wheel")
    rebuilt_wheel = next(rebuilt_dist.glob("*.whl"))

    with zipfile.ZipFile(rebuilt_wheel) as zf:
        assert _archive_template_paths(zf.namelist()) == source_templates
        _assert_wheel_contract(zf)
