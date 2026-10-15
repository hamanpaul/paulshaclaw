from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from paulshaclaw_deploy.docker_transport import (
    DockerTransport,
    InfrastructureError,
    TransportBase,
)


def test_docker_transport_subclass_and_properties() -> None:
    dt = DockerTransport(image="ubuntu:24.04")
    assert isinstance(dt, TransportBase)
    assert dt.transport_type == "docker"
    assert dt.is_connected is False
    assert dt.container_id is None


@patch("subprocess.run")
def test_docker_transport_lifecycle(mock_run: MagicMock) -> None:
    # 1. connect
    mock_run.return_value = MagicMock(returncode=0, stdout="cid-12345678\n", stderr="")
    dt = DockerTransport(image="ubuntu:24.04")
    dt.connect()

    assert dt.is_connected is True
    assert dt.container_id == "cid-12345678"
    mock_run.assert_called_with(
        [
            "docker",
            "run",
            "-d",
            "--name",
            dt.container_name,
            "--label",
            f"paulshaclaw.deploy-run={dt._ownership}",
            "--user",
            "1000",
            "ubuntu:24.04",
            "tail",
            "-f",
            "/dev/null",
        ],
        stdout=-1,
        stderr=-1,
        text=True,
        check=False,
        timeout=120,
    )

    # 2. execute
    mock_run.return_value = MagicMock(returncode=0, stdout="test-output\n", stderr="")
    result = dt.execute("echo test")
    assert result["returncode"] == 0
    assert result["stdout"] == "test-output\n"

    # 3. disconnect / teardown
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    dt.disconnect()
    assert dt.is_connected is False
    assert dt.container_id is None
    assert dt.last_container_id == "cid-12345678"
    assert dt.cleanup_attempted is True
    assert dt._cleanup_done is True
    mock_run.assert_called_with(
        ["docker", "rm", "-f", "cid-12345678"],
        stdout=-1,
        stderr=-1,
        text=True,
        check=False,
        timeout=30,
    )


def test_docker_transport_enforces_digest_network_and_read_only_mount(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    digest = "sha256:" + ("a" * 64)
    dt = DockerTransport(
        image="ubuntu:24.04",
        image_digest=digest,
        uid=1000,
        network="none",
        volumes=[(str(artifact_dir), "/testpilot/artifacts", "ro")],
    )
    assert dt.build_run_command() == [
        "docker",
        "run",
        "-d",
        "--name",
        dt.container_name,
        "--label",
        f"paulshaclaw.deploy-run={dt._ownership}",
        "--user",
        "1000",
        "--network",
        "none",
        "-v",
        f"{artifact_dir}:/testpilot/artifacts:ro",
        f"ubuntu:24.04@{digest}",
        "tail",
        "-f",
        "/dev/null",
    ]

    with pytest.raises(ValueError, match="read-only"):
        DockerTransport(volumes=[(str(artifact_dir), "/testpilot/artifacts", "rw")]).build_run_command()


@patch("subprocess.run", side_effect=PermissionError("docker socket unavailable"))
def test_docker_transport_reports_docker_unavailable(mock_run: MagicMock) -> None:
    with pytest.raises(InfrastructureError, match="Docker run unavailable"):
        DockerTransport().connect()
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_docker_transport_timeout_keeps_evidence_and_cleans_up(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="cid-timeout\n", stderr=""),
        subprocess.TimeoutExpired(
            cmd=["docker", "exec"],
            timeout=3,
            output=b"partial stdout",
            stderr=b"partial stderr",
        ),
        MagicMock(returncode=0, stdout="", stderr=""),
    ]
    dt = DockerTransport(image="ubuntu:24.04")
    dt.connect()
    result = dt.execute("sleep 10", timeout=3)
    dt.disconnect()

    assert result["timed_out"] is True
    assert result["infrastructure_error"] is True
    assert result["stdout"] == "partial stdout"
    assert dt.last_container_id == "cid-timeout"
    assert dt.cleanup_attempted is True
    assert dt.cleanup_done is True


@patch("subprocess.run")
def test_docker_transport_cleanup_error_is_reported(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="cid-cleanup-error\n", stderr=""),
        MagicMock(returncode=1, stdout="", stderr="permission denied"),
    ]
    dt = DockerTransport(image="ubuntu:24.04")
    dt.connect()
    dt.disconnect()

    assert dt.last_container_id == "cid-cleanup-error"
    assert dt.cleanup_attempted is True
    assert dt.cleanup_done is False
    assert dt.cleanup_error == "permission denied"


@patch("subprocess.run")
def test_docker_transport_execute_as_sets_explicit_user(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="cid-root\n", stderr=""),
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="", stderr=""),
    ]
    dt = DockerTransport(image="ubuntu:24.04")
    dt.connect()
    dt.execute_as("id -u", user=0)
    dt.disconnect()

    exec_call = mock_run.call_args_list[1]
    assert exec_call.args[0][0:5] == ["docker", "exec", "-i", "--user", "0"]


def test_cleanup_timeout_can_be_retried_without_forgetting_owned_container():
    with patch('subprocess.run') as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, 'owned-container\n', ''),
            subprocess.TimeoutExpired(['docker', 'rm'], 30),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        transport = DockerTransport()
        transport.connect()
        transport.disconnect()
        assert transport.container_id == 'owned-container'
        assert transport.cleanup_error
        transport.disconnect()
        assert transport.cleanup_done is True
        assert transport.container_id is None


def test_run_timeout_recovers_only_container_with_our_ownership_label():
    with patch('subprocess.run') as run:
        transport = DockerTransport()
        run.side_effect = [
            subprocess.TimeoutExpired(['docker', 'run'], 120),
            subprocess.CompletedProcess([], 0, 'owned-id ' + getattr(transport, '_ownership', '') + '\n', ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        with pytest.raises(InfrastructureError):
            transport.connect()
        assert transport.cleanup_done is True
        assert transport.last_container_id == 'owned-id'
