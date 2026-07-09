from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "scripts" / "copilot-local-vllm"
INSTALL = PROJECT_ROOT / "scripts" / "install-copilot-local-vllm"
TEMPLATE = PROJECT_ROOT / "config" / "copilot-local-vllm.env.tmpl"

_VALID_ENV = (
    "COPILOT_PROVIDER_BASE_URL=http://192.0.2.10:8001/v1\n"
    "COPILOT_PROVIDER_TYPE=openai\n"
    "COPILOT_PROVIDER_API_KEY=sk-test-123\n"
    "COPILOT_MODEL=gemma4-26b-a4b-nvfp4\n"
)


def _run_launcher(args, env_extra, stub_dir=None, timeout=10):
    env = dict(os.environ)
    env.update(env_extra)
    if stub_dir is not None:
        env["PATH"] = f"{stub_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(LAUNCHER), *args],
        capture_output=True, text=True, check=False, env=env, timeout=timeout,
    )


class CopilotLocalVllmPackagingTests(unittest.TestCase):
    def test_launcher_packaged_and_executable(self) -> None:
        self.assertTrue(LAUNCHER.exists(), "scripts/copilot-local-vllm should exist")
        self.assertTrue(os.access(LAUNCHER, os.X_OK), "scripts/copilot-local-vllm should be executable")
        result = subprocess.run(
            ["bash", "-n", str(LAUNCHER)], capture_output=True, text=True, check=False, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_launcher_contains_byok_wiring(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        # secret env resolution chain (override -> config -> legacy).
        self.assertIn("PSC_COPILOT_LOCAL_VLLM_ENV_FILE", text)
        self.assertIn("$HOME/.config/paulshaclaw/copilot-local-vllm.env", text)
        self.assertIn("$HOME/.copilot/copilot-local-vllm.env", text)
        # no-secrets guard: never silently fall through to GitHub-hosted models.
        self.assertIn("COPILOT_PROVIDER_API_KEY", text)
        # execs the real copilot, and excludes this wrapper from resolution.
        self.assertIn('exec "$real_copilot"', text)
        self.assertIn("self_path", text)
        # error hint derives the template path from the script location, not CWD.
        self.assertIn('TEMPLATE="$SCRIPT_DIR/../config/copilot-local-vllm.env.tmpl"', text)
        # de-identification: no personal absolute paths / real internal endpoint.
        self.assertNotIn("/home/", text)
        self.assertNotIn("192.168.199.199", text)

    def test_launcher_errors_when_env_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.env"
            result = _run_launcher(
                ["--help"], {"PSC_COPILOT_LOCAL_VLLM_ENV_FILE": str(missing)}
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("env file not readable", result.stderr)
        # hint must reference an absolute template path.
        self.assertIn("/config/copilot-local-vllm.env.tmpl", result.stderr)

    def test_launcher_guards_missing_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "nokey.env"
            env_file.write_text(
                "COPILOT_PROVIDER_BASE_URL=http://192.0.2.10:8001/v1\n"
                "COPILOT_MODEL=gemma4-26b-a4b-nvfp4\n",
                encoding="utf-8",
            )
            result = _run_launcher(
                ["--help"], {"PSC_COPILOT_LOCAL_VLLM_ENV_FILE": str(env_file)}
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("COPILOT_PROVIDER_API_KEY", result.stderr)

    def test_launcher_execs_real_copilot_with_byok_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stub_dir = tmp_path / "bin"
            stub_dir.mkdir()
            stub = stub_dir / "copilot"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                'echo "STUB_COPILOT"\n'
                'echo "BASE=$COPILOT_PROVIDER_BASE_URL"\n'
                'echo "KEY_SET=$([ -n "${COPILOT_PROVIDER_API_KEY:-}" ] && echo yes || echo no)"\n'
                'echo "ARGS=$*"\n',
                encoding="utf-8",
            )
            stub.chmod(0o755)
            env_file = tmp_path / "ok.env"
            env_file.write_text(_VALID_ENV, encoding="utf-8")
            result = _run_launcher(
                ["--model", "foo", "hi"],
                {"PSC_COPILOT_LOCAL_VLLM_ENV_FILE": str(env_file)},
                stub_dir=str(stub_dir),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB_COPILOT", result.stdout)
        self.assertIn("BASE=http://192.0.2.10:8001/v1", result.stdout)
        self.assertIn("KEY_SET=yes", result.stdout)
        self.assertIn("ARGS=--model foo hi", result.stdout)

    def test_installer_packaged_and_executable(self) -> None:
        self.assertTrue(INSTALL.exists(), "scripts/install-copilot-local-vllm should exist")
        self.assertTrue(os.access(INSTALL, os.X_OK), "scripts/install-copilot-local-vllm should be executable")
        result = subprocess.run(
            ["bash", "-n", str(INSTALL)], capture_output=True, text=True, check=False, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installer_symlinks_launcher_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PSC_COPILOT_LOCAL_VLLM_BIN_DIR=tmp)
            first = subprocess.run(
                ["bash", str(INSTALL)], capture_output=True, text=True, check=False, env=env, timeout=10
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            link = Path(tmp) / "copilot-local-vllm"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), LAUNCHER.resolve())

            second = subprocess.run(
                ["bash", str(INSTALL)], capture_output=True, text=True, check=False, env=env, timeout=10
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("unchanged", second.stdout)

    def test_env_template_shape_is_deidentified(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for key in (
            "COPILOT_PROVIDER_BASE_URL",
            "COPILOT_PROVIDER_TYPE",
            "COPILOT_PROVIDER_API_KEY",
            "COPILOT_MODEL",
        ):
            self.assertIn(key, text)
        # documentation placeholder endpoint, never the real internal one.
        self.assertIn("192.0.2.10", text)
        self.assertNotIn("192.168.199.199", text)
        # key must be a placeholder, not a real-looking secret.
        self.assertIn("REPLACE_WITH_YOUR_VLLM_KEY", text)


if __name__ == "__main__":
    unittest.main()
