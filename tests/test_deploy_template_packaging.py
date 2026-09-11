"""Regression coverage for deploy template package-data parity."""

from __future__ import annotations

import contextlib
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
    resolve_install_path,
    run_install,
    run_upgrade,
)
from paulshaclaw.deploy import planner


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
PACKAGE_ROOT = REPO_ROOT / "paulshaclaw"
TEMPLATE_MARKER = "paulshaclaw/deploy/templates/"


def _load_artifact_checker():
    module_path = REPO_ROOT / "scripts" / "check-release-artifacts.py"
    spec = importlib.util.spec_from_file_location("release_artifact_checker", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_deploy_main(argv: list[str]) -> tuple[int, str, str]:
    from io import StringIO

    from paulshaclaw.deploy.__main__ import main

    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exit_code = main(argv)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _stub_install_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._ensure_linger_enabled",
        lambda: "enabled",
    )
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._run_daemon_reload",
        lambda: "ran",
    )


def _assert_footer_report(
    payload: dict[str, object],
    *,
    mode: str,
    fragments: tuple[str, ...],
) -> None:
    assert "detected_agents" in payload
    assert "footer_selection" in payload
    selection = payload["footer_selection"]
    assert isinstance(selection, dict)
    assert selection.get("mode") == mode
    selection_text = json.dumps(selection, ensure_ascii=False)
    for fragment in fragments:
        assert fragment in selection_text


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


def test_source_checker_distinguishes_empty_dirs_from_non_template_files(tmp_path: Path) -> None:
    checker = _load_artifact_checker()
    source_root = tmp_path / "source"
    shutil.copytree(REPO_ROOT / "paulshaclaw", source_root / "paulshaclaw")
    shutil.copy(REPO_ROOT / "VERSION", source_root / "VERSION")
    template_root = source_root / "paulshaclaw" / "deploy" / "templates"

    notes_dir = template_root / "notes"
    notes_dir.mkdir()
    (notes_dir / "README.md").write_text("template notes\n", encoding="utf-8")
    assert checker._source_template_paths(source_root)

    (template_root / "empty").mkdir()
    with pytest.raises(checker.ArtifactCheckError, match="empty"):
        checker._source_template_paths(source_root)


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


@pytest.mark.parametrize(
    ("footer", "expected_fragments"),
    [
        ("copilot:haman:arc", ("copilot", "haman", "arc")),
        ("none", ("none",)),
    ],
)
def test_install_apply_reports_explicit_footer_selection(
    monkeypatch,
    tmp_path: Path,
    footer: str,
    expected_fragments: tuple[str, ...],
) -> None:
    _stub_install_side_effects(monkeypatch)

    exit_code, stdout, stderr = _run_deploy_main(
        [
            "install",
            "--apply",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            "--home-dir",
            str(tmp_path / "home"),
            "--footer",
            footer,
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    _assert_footer_report(payload, mode="flag", fragments=expected_fragments)


def test_install_apply_skips_footer_selection_without_tty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _stub_install_side_effects(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    exit_code, stdout, stderr = _run_deploy_main(
        [
            "install",
            "--apply",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            "--home-dir",
            str(tmp_path / "home"),
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    _assert_footer_report(payload, mode="skipped", fragments=("no-tty",))


def test_install_plan_only_reports_skipped_footer_selection() -> None:
    exit_code, stdout, stderr = _run_deploy_main(
        [
            "install",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    _assert_footer_report(payload, mode="skipped", fragments=("plan-only",))


def test_status_and_uninstall_apply_ignore_missing_templates(monkeypatch, tmp_path: Path, capsys) -> None:
    template_root = _template_checkout_without_last_asset(tmp_path)
    monkeypatch.setattr(planner, "TEMPLATE_ROOT", template_root)
    monkeypatch.setattr("paulshaclaw.deploy.installer._disable_service_units", lambda plan: [])
    monkeypatch.setattr("paulshaclaw.deploy.installer._stop_service_units", lambda plan: [])
    monkeypatch.setattr("paulshaclaw.deploy.installer._run_daemon_reload", lambda: [])

    from paulshaclaw.deploy.__main__ import main

    home_dir = tmp_path / "home"
    common_args = [
        "--instance",
        "demo-agent",
        "--root-dir",
        "/srv/paulshaclaw",
        "--home-dir",
        str(home_dir),
    ]

    assert main(["status", *common_args]) == 0
    assert capsys.readouterr().out.strip() == "{}"

    assert main(["uninstall", *common_args, "--apply"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "uninstall"
    assert payload["status"] == "ok"


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
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)
    install = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", str(wheel)],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    home_dir = tmp_path / "installed-home"
    no_host_tools = tmp_path / "no-host-tools"
    no_host_tools.mkdir()
    env = clean_env.copy()
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
    _assert_footer_report(payload, mode="skipped", fragments=())
    expected_plan = build_command_plan(
        "install", instance_name="wheel-agent", root_dir="/srv/paulshaclaw"
    )
    expected_files = {
        str(resolve_install_path(asset, home_dir=home_dir)) for asset in expected_plan.templates
    }
    assert set(payload["applied_files"]) == expected_files
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
    assert record["version"] == REPO_VERSION
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
