"""Regression coverage for deploy template package-data parity."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from paulshaclaw.deploy import (
    build_command_plan,
    run_install,
    run_upgrade,
)
from paulshaclaw.deploy import planner


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "paulshaclaw"
TEMPLATE_MARKER = "paulshaclaw/deploy/templates/"


def _load_artifact_checker():
    module_path = REPO_ROOT / "scripts" / "check-release-artifacts.py"
    spec = importlib.util.spec_from_file_location("release_artifact_checker", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    _load_artifact_checker().check_artifacts(
        wheel=source_wheel,
        sdist=source_sdist,
        source_root=REPO_ROOT,
    )


def test_shared_artifact_checker_fails_closed_for_missing_or_corrupt_archive(tmp_path: Path) -> None:
    checker = _load_artifact_checker()
    missing = tmp_path / "missing.whl"
    with pytest.raises(checker.ArtifactCheckError, match="file does not exist"):
        checker.check_artifacts(wheel=missing, sdist=missing, source_root=REPO_ROOT)

    corrupt = tmp_path / "corrupt.whl"
    corrupt.write_bytes(b"not a zip archive")
    with pytest.raises(checker.ArtifactCheckError, match="unable to open archive"):
        checker.check_artifacts(wheel=corrupt, sdist=corrupt, source_root=REPO_ROOT)


def _template_checkout_without_last_asset(tmp_path: Path) -> Path:
    template_root = tmp_path / "templates"
    source_root = REPO_ROOT / "paulshaclaw" / "deploy" / "templates"
    shutil.copytree(source_root, template_root)
    last = sorted(template_root.rglob("*.tmpl"))[-1]
    last.unlink()
    return template_root


def test_install_template_preflight_has_no_partial_write_record_or_systemd(monkeypatch, tmp_path: Path) -> None:
    template_root = _template_checkout_without_last_asset(tmp_path)
    monkeypatch.setattr(planner, "TEMPLATE_ROOT", template_root)
    calls: list[str] = []
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._ensure_linger_enabled",
        lambda: calls.append("loginctl") or "enabled",
    )
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._run_daemon_reload",
        lambda: calls.append("systemctl") or "ran",
    )

    home_dir = tmp_path / "home"
    report, exit_code = run_install(
        instance_name="demo-agent",
        root_dir="/srv/paulshaclaw",
        apply=True,
        verify=False,
        home_dir=home_dir,
    )

    assert exit_code == 1
    assert report["status"] == "failed"
    assert report["failed_assets"] == ["state/config/__INSTANCE__.state.json.tmpl"]
    assert report["template_preflight"]["status"] == "failed"
    assert "未寫入" in report["actionable_message"]
    assert calls == []
    assert not home_dir.exists()


def test_upgrade_template_preflight_runs_before_checkpoint(monkeypatch, tmp_path: Path) -> None:
    template_root = _template_checkout_without_last_asset(tmp_path)
    monkeypatch.setattr(planner, "TEMPLATE_ROOT", template_root)
    home_dir = tmp_path / "home"

    report, exit_code = run_upgrade(
        instance_name="demo-agent",
        root_dir="/srv/paulshaclaw",
        apply=True,
        verify=True,
        home_dir=home_dir,
    )

    assert exit_code == 1
    assert report["status"] == "failed"
    assert not (home_dir / ".agents" / "deploy-checkpoints").exists()


def test_plan_only_install_template_failure_is_one_json_report(monkeypatch, tmp_path: Path, capsys) -> None:
    template_root = _template_checkout_without_last_asset(tmp_path)
    monkeypatch.setattr(planner, "TEMPLATE_ROOT", template_root)
    from paulshaclaw.deploy.__main__ import main

    exit_code = main(
        [
            "install",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["status"] == "failed"
    assert payload["failed_assets"] == ["state/config/__INSTANCE__.state.json.tmpl"]


def test_post_preflight_io_failure_reports_written_files_without_atomicity_claim(monkeypatch, tmp_path: Path) -> None:
    home_dir = tmp_path / "home"
    original_write_text = Path.write_text
    template_writes = 0

    def fail_on_second_deploy_write(path: Path, data: str, *args, **kwargs):
        nonlocal template_writes
        if str(path).startswith(str(home_dir)):
            template_writes += 1
            if template_writes == 2:
                raise OSError("simulated disk full")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_on_second_deploy_write)
    report, exit_code = run_install(
        instance_name="demo-agent",
        root_dir="/srv/paulshaclaw",
        apply=True,
        verify=False,
        home_dir=home_dir,
    )

    assert exit_code == 1
    assert report["status"] == "failed"
    assert len(report["applied_files"]) == 1
    assert report["mutation"]["atomic"] is False
    assert report["mutation"]["written_files"] == report["applied_files"]
    assert not (home_dir / ".agents" / "state" / "config" / "demo-agent.install-record.json").exists()


def test_clean_venv_runs_deploy_from_installed_wheel_outside_checkout(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheel-dist"
    wheel_dir.mkdir()
    _run_build(REPO_ROOT, wheel_dir, "--wheel")
    wheel = next(wheel_dir.glob("*.whl"))
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    venv_python = venv_dir / "bin" / "python"
    install = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    home_dir = tmp_path / "installed-home"
    no_host_tools = tmp_path / "no-host-tools"
    no_host_tools.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update({"PATH": str(no_host_tools), "HOME": str(home_dir)})
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    completed = subprocess.run(
        [
            str(venv_python),
            "-m",
            "paulshaclaw.deploy",
            "install",
            "--apply",
            "--verify",
            "--instance",
            "wheel-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            "--home-dir",
            str(home_dir),
            "--version",
            "0.2.7",
            "--artifact",
            str(wheel),
            "--artifact-sha256",
            wheel_sha256,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert len(payload["applied_files"]) == 8
    assert payload["artifact"]["sha256"] == wheel_sha256
    assert payload["verification"]["systemd"]["status"] == "on-host-only"
    assert payload["verification"]["systemd"].get("service_started") is not True

    state_dir = home_dir / ".agents" / "state" / "config"
    secret_dir = home_dir / ".config" / "paulshaclaw"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o750
    assert stat.S_IMODE((state_dir / "wheel-agent.state.json").stat().st_mode) == 0o640
    assert stat.S_IMODE(secret_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((secret_dir / "wheel-agent.secret.env").stat().st_mode) == 0o600
    record = json.loads((state_dir / "wheel-agent.install-record.json").read_text(encoding="utf-8"))
    assert record["version"] == "0.2.7"
    assert record["artifact_sha256"] == wheel_sha256

    module = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import paulshaclaw.deploy as d; print(d.__file__)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert module.returncode == 0, module.stderr
    loaded_path = Path(module.stdout.strip()).resolve()
    assert str(loaded_path).startswith(str(venv_dir.resolve()))
    assert not str(loaded_path).startswith(str(REPO_ROOT.resolve()))
