"""Docker transport used by the paulshaclaw TestPilot plugin.

The transport deliberately owns only containers that it created.  Inputs are
converted into one ``docker run`` command, and every test step is a separate
``docker exec`` invocation so that exit status, output and timeout information
remain independently observable.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from testpilot.api import TransportBase


log = logging.getLogger(__name__)


class InfrastructureError(RuntimeError):
    """An unavailable or unusable Docker environment."""


class DockerTransport(TransportBase):
    """Execute TestPilot steps in one isolated Docker container."""

    def __init__(
        self,
        image: str = "ubuntu:24.04",
        container_name: str | None = None,
        uid: int | None = 1000,
        network: str | None = None,
        volumes: list[tuple[str, str, str]] | None = None,
        image_digest: str | None = None,
        user: str | None = "testuser",
    ) -> None:
        self._ownership = uuid.uuid4().hex
        self.image = image
        self.container_name = container_name or f"testpilot-paulshaclaw-{uuid.uuid4().hex[:8]}"
        self.uid = uid
        self.user = user
        self.network = network
        self.volumes = list(volumes or [])
        self.image_digest = image_digest
        self._container_id: str | None = None
        self._last_container_id: str | None = None
        self._connected = False
        self._cleanup_done = False
        self._cleanup_attempted = False
        self._cleanup_error: str | None = None

    @property
    def transport_type(self) -> str:
        return "docker"

    @property
    def container_id(self) -> str | None:
        return self._container_id

    @property
    def last_container_id(self) -> str | None:
        """Return the most recent container ID, including after cleanup."""
        return self._last_container_id

    @property
    def cleanup_done(self) -> bool:
        """Whether the owned container was removed successfully."""
        return self._cleanup_done

    @property
    def cleanup_attempted(self) -> bool:
        """Whether cleanup was attempted for an owned container."""
        return self._cleanup_attempted

    @property
    def cleanup_error(self) -> str | None:
        return self._cleanup_error

    @property
    def is_connected(self) -> bool:
        return self._connected and self._container_id is not None

    def _image_reference(self) -> str:
        if not self.image_digest:
            return self.image

        digest = str(self.image_digest).strip()
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError("image_digest must be a sha256 digest")
        if "@" in self.image:
            if self.image.endswith(f"@{digest}"):
                return self.image
            raise ValueError("image already contains a different digest")
        return f"{self.image}@{digest}"

    @staticmethod
    def _validate_volume(host_path: str, container_path: str, mode: str) -> None:
        host = Path(host_path).expanduser()
        home = Path.home().resolve()
        resolved = host.resolve(strict=False)
        forbidden_names = {".ssh", ".aws", ".gnupg", "docker.sock"}
        if resolved == home:
            raise ValueError("mounting the host HOME is forbidden")
        if any(part in forbidden_names for part in resolved.parts):
            raise ValueError("mounting host secrets or Docker socket is forbidden")
        if "systemd" in resolved.parts:
            raise ValueError("mounting a systemd path is forbidden")
        if not container_path.startswith("/") or "\n" in container_path or "\r" in container_path:
            raise ValueError("container mount path must be an absolute safe path")
        if mode not in {"ro", "ro,z", "ro,Z"}:
            raise ValueError("TestPilot artifact mounts must be read-only")

    def build_run_command(self) -> list[str]:
        """Build the complete, auditable ``docker run`` argv."""
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "--label",
            f"paulshaclaw.deploy-run={self._ownership}",
        ]

        if self.uid is not None:
            cmd.extend(["--user", str(self.uid)])
        elif self.user:
            cmd.extend(["--user", self.user])

        if self.network:
            cmd.extend(["--network", self.network])

        for host_path, container_path, mode in self.volumes:
            self._validate_volume(host_path, container_path, mode)
            cmd.extend(["-v", f"{host_path}:{container_path}:{mode}"])

        cmd.extend([
            self._image_reference(),
            "tail",
            "-f",
            "/dev/null",
        ])
        return cmd

    def connect(self, **kwargs: Any) -> None:
        """Start the owned container, reporting Docker failures as infra errors."""
        del kwargs
        if self.is_connected:
            return

        cmd = self.build_run_command()
        log.info("Starting docker container: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._recover_timed_out_start()
            raise InfrastructureError(f"Docker run unavailable: {type(exc).__name__}") from exc

        if proc.returncode != 0:
            detail = str(proc.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            raise InfrastructureError(f"Failed to start Docker container{suffix}")

        container_id = str(proc.stdout or "").strip()
        if not container_id:
            raise InfrastructureError("Docker run returned no container ID")
        self._container_id = container_id
        self._last_container_id = container_id
        self._connected = True
        self._cleanup_done = False
        self._cleanup_attempted = False
        self._cleanup_error = None

    def _recover_timed_out_start(self) -> None:
        """A timed out CLI may have created a container; verify its unique label."""
        try:
            found = subprocess.run(
                ["docker", "inspect", "--format", '{{.Id}} {{index .Config.Labels "paulshaclaw.deploy-run"}}', self.container_name],
                capture_output=True, text=True, timeout=30, check=False,
            )
            parts = found.stdout.strip().split()
            if found.returncode == 0 and len(parts) == 2 and parts[1] == self._ownership:
                self._container_id = self._last_container_id = parts[0]
                self.disconnect()
        except (OSError, subprocess.TimeoutExpired):
            self._cleanup_error = "could not inspect container after start failure"

    @staticmethod
    def _text_output(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value or "")

    def _execute(
        self,
        command: str,
        timeout: float = 30.0,
        *,
        user: str | int | None = None,
    ) -> dict[str, Any]:
        """Execute one command with a bounded timeout and full output capture."""
        if not self.is_connected or not self._container_id:
            raise InfrastructureError("Cannot execute: Docker container is not connected")

        exec_cmd = [
            "docker",
            "exec",
            "-i",
        ]
        if user is not None:
            exec_cmd.extend(["--user", str(user)])
        exec_cmd.extend([
            self._container_id,
            "bash",
            "-c",
            command,
        ])

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                exec_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start_time
            stdout = self._text_output(exc.stdout)
            return {
                "returncode": -1,
                "stdout": stdout,
                "stderr": f"Command timed out after {timeout} seconds",
                "elapsed": elapsed,
                "timed_out": True,
                "infrastructure_error": True,
            }
        except OSError as exc:
            elapsed = time.monotonic() - start_time
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Docker exec unavailable: {type(exc).__name__}",
                "elapsed": elapsed,
                "infrastructure_error": True,
            }

        elapsed = time.monotonic() - start_time
        return {
            "returncode": proc.returncode,
            "stdout": self._text_output(proc.stdout),
            "stderr": self._text_output(proc.stderr),
            "elapsed": elapsed,
        }

    def execute(self, command: str, timeout: float = 30.0) -> dict[str, Any]:
        """Execute one command as the container's configured non-root user."""
        return self._execute(command, timeout=timeout)

    def execute_as(
        self,
        command: str,
        *,
        user: str | int,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute one command as an explicit user for bounded setup steps."""
        return self._execute(command, timeout=timeout, user=user)

    def disconnect(self) -> None:
        """Remove only the container created by this transport instance."""
        if not self._container_id:
            self._connected = False
            return

        cid = self._container_id
        self._last_container_id = cid
        self._cleanup_attempted = True
        log.info("Cleaning up Docker container: %s", cid)
        try:
            proc = subprocess.run(
                ["docker", "rm", "-f", cid],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            self._cleanup_done = proc.returncode == 0
            if not self._cleanup_done:
                self._cleanup_error = self._text_output(proc.stderr).strip() or "docker rm failed"
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._cleanup_done = False
            self._cleanup_error = f"{type(exc).__name__}"
        finally:
            self._connected = False
            if self._cleanup_done:
                self._container_id = None
                self._cleanup_error = None
