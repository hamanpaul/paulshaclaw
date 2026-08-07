"""Issue #280 E 節：artifact-driven deployment 測試。

涵蓋：
- E1 安裝來源記錄與查詢入口、artifact fail-closed。
- E2 upgrade / uninstall / rollback 的 machine-readable report。
- E3 upgrade 實際執行 + state/secret preservation。
- E4 rollback 還原 core 內容。
- E5 uninstall 預設保留 state/secret，--purge-* 才清除。

沿用 test_stage7_deploy_install.py 的 fake bin + 假 HOME + command_log 模式，
絕不呼叫真實 systemd。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from paulshaclaw.deploy import (
    ArtifactVerificationError,
    build_command_plan,
    read_install_record,
    restore_core_from_checkpoint,
    run_rollback,
    run_uninstall,
    run_upgrade,
    snapshot_core_plane,
)
from paulshaclaw.deploy.installer import _install_record_path, run_install

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_test_dir(name: str) -> Path:
    path = REPO_ROOT / ".test-artifacts" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_script(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_fake_tools(base: Path, *, restart_fails: bool = False) -> tuple[Path, Path]:
    fakebin = base / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    command_log = base / "command.log"
    linger_flag = base / "linger.enabled"

    # restart_fails=True 模擬「新版 unit 起不來」：只有 restart 回非零，
    # 其餘子命令照常成功，用來驗證 upgrade 會 fail-closed 並自動 rollback。
    restart_branch = (
        """if [[ "${1:-}" == "--user" && "${2:-}" == "restart" ]]; then
  printf 'Job for %s failed.\\n' "${3:-unit}" >&2
  exit 1
fi
"""
        if restart_fails
        else ""
    )
    write_script(
        fakebin / "systemctl",
        f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "systemctl $*" >> "{command_log}"
{restart_branch}exit 0
""",
    )
    write_script(
        fakebin / "loginctl",
        f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "loginctl $*" >> "{command_log}"
if [[ "${{1:-}}" == "show-user" ]]; then
  if [[ -f "{linger_flag}" ]]; then
    printf 'yes\\n'
  else
    printf 'no\\n'
  fi
  exit 0
fi
if [[ "${{1:-}}" == "enable-linger" ]]; then
  : > "{linger_flag}"
  exit 0
fi
exit 0
""",
    )
    write_script(
        fakebin / "systemd-analyze",
        f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "systemd-analyze $*" >> "{command_log}"
exit 0
""",
    )
    return fakebin, command_log


def deploy_env(home_dir: Path, fakebin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir),
            "PATH": str(fakebin),
            "USER": "stage7tester",
            "LOGNAME": "stage7tester",
        }
    )
    return env


def run_deploy(home_dir: Path, fakebin: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "paulshaclaw.deploy",
            command,
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            *args,
        ],
        cwd=REPO_ROOT,
        env=deploy_env(home_dir, fakebin),
        check=False,
        capture_output=True,
        text=True,
    )


def seed_install(home_dir: Path, fakebin: Path) -> None:
    """先跑一次 install --apply --verify 作為 upgrade/uninstall 前置狀態。"""
    completed = run_deploy(home_dir, fakebin, "install", "--apply", "--verify")
    assert completed.returncode == 0, completed.stderr


def write_real_state_and_secret(home_dir: Path) -> dict[str, str]:
    """在 state/secret/runtime env 寫入可辨識的真實內容，驗證 upgrade 不覆寫。

    state json 保留 seed_install 寫入的合法結構並加入可辨識 marker，
    使其仍能通過 verify_install_plan 的 load_config 驗證。
    """
    secret_path = home_dir / ".config" / "paulshaclaw" / "demo-agent.telegram.secret.env"
    state_path = home_dir / ".agents" / "state" / "config" / "demo-agent.state.json"
    cost_env = home_dir / ".agents" / "core" / "runtime" / "demo-agent-cost.env"
    secret_text = "PSC_TELEGRAM_BOT_TOKEN=real-operator-token\nPSC_TELEGRAM_EXPECTED_USERNAME=u\nPSC_TELEGRAM_EXPECTED_BOT_ID=1\nPSC_CLAUDE_GEMMA4_API_KEY=k\n"
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    state_payload["allowed_user_ids"] = [42]
    state_text = json.dumps(state_payload, ensure_ascii=False)
    cost_text = "PAULSHACLAW_CONFIG=/srv/real\n"
    secret_path.write_text(secret_text, encoding="utf-8")
    state_path.write_text(state_text, encoding="utf-8")
    cost_env.write_text(cost_text, encoding="utf-8")
    return {
        "secret": secret_text,
        "state": state_text,
        "cost_env": cost_text,
        "secret_path": str(secret_path),
        "state_path": str(state_path),
        "cost_env_path": str(cost_env),
    }


class InstallRecordTests(unittest.TestCase):
    def test_install_apply_with_version_and_artifact_writes_record(self) -> None:
        scratch = make_test_dir("stage7-e1-record")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        artifact = scratch / "paulshaclaw-0.1.0-py3-none-any.whl"
        artifact.write_bytes(b"fake wheel content for sha")
        try:
            completed = run_deploy(
                home_dir,
                fakebin,
                "install",
                "--apply",
                "--verify",
                "--version",
                "0.1.0",
                "--artifact",
                str(artifact),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["artifact"]["source"], str(artifact))
            self.assertIsNotNone(payload["artifact"]["sha256"])

            record = read_install_record(str(home_dir), instance_name="demo-agent")
            self.assertIsNotNone(record)
            self.assertEqual(record["version"], "0.1.0")
            self.assertEqual(record["artifact_source"], str(artifact))
            self.assertEqual(record["artifact_sha256"], payload["artifact"]["sha256"])
            self.assertEqual(record["command"], "install")
            self.assertIn("applied_at", record)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_status_command_returns_install_record(self) -> None:
        scratch = make_test_dir("stage7-e1-status")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            # 透過 run_install 寫入 record（不指定 version，偵測安裝版本）
            run_install(
                instance_name="demo-agent",
                root_dir="/srv/paulshaclaw",
                apply=True,
                verify=True,
                home_dir=str(home_dir),
                version="0.2.0",
            )
            completed = run_deploy(home_dir, fakebin, "status")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["version"], "0.2.0")
            self.assertEqual(payload["instance"], "demo-agent")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_status_without_record_prints_empty_object(self) -> None:
        scratch = make_test_dir("stage7-e1-status-empty")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            completed = run_deploy(home_dir, fakebin, "status")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout), {})
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_fail_closed_when_artifact_missing(self) -> None:
        scratch = make_test_dir("stage7-e1-fail-missing")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            completed = run_deploy(
                home_dir,
                fakebin,
                "install",
                "--apply",
                "--artifact",
                str(scratch / "nope.whl"),
            )
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertIn("不存在", payload["error"])
            # fail-closed：不可有任何安裝檔被寫入。
            self.assertFalse((home_dir / ".agents" / "core" / "runtime").exists())
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_fail_closed_when_checksum_mismatch(self) -> None:
        scratch = make_test_dir("stage7-e1-fail-checksum")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        artifact = scratch / "paulshaclaw.whl"
        artifact.write_bytes(b"some content")
        try:
            completed = run_deploy(
                home_dir,
                fakebin,
                "install",
                "--apply",
                "--artifact",
                str(artifact),
                "--artifact-sha256",
                "deadbeef" * 8,
            )
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertIn("SHA-256 不符", payload["error"])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class UpgradeExecutionTests(unittest.TestCase):
    def test_upgrade_apply_preserves_state_secret_and_runtime_env(self) -> None:
        scratch = make_test_dir("stage7-e3-preserve")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            real = write_real_state_and_secret(home_dir)

            completed = run_deploy(
                home_dir,
                fakebin,
                "upgrade",
                "--apply",
                "--verify",
                "--version",
                "0.2.0",
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "upgrade")
            self.assertEqual(payload["status"], "ok")
            self.assertIn("checkpoint", payload)
            self.assertIn("snapshot", payload)
            self.assertIn("restart", payload)
            self.assertEqual(payload["verification"]["status"], "passed")

            # state/secret/runtime env 逐字不變（create-only 規則）。
            self.assertEqual(
                Path(real["secret_path"]).read_text(encoding="utf-8"),
                real["secret"],
            )
            self.assertEqual(
                Path(real["state_path"]).read_text(encoding="utf-8"),
                real["state"],
            )
            self.assertEqual(
                Path(real["cost_env_path"]).read_text(encoding="utf-8"),
                real["cost_env"],
            )

            # unit 檔允許覆寫（升級新版）。
            unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-cost.service"
            self.assertIn("service-cost.sh", unit.read_text(encoding="utf-8"))

            # install record 被更新為 upgrade 版本。
            record = read_install_record(str(home_dir), instance_name="demo-agent")
            self.assertEqual(record["command"], "upgrade")
            self.assertEqual(record["version"], "0.2.0")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_upgrade_fails_closed_and_rolls_back_when_restart_fails(self) -> None:
        # 新版 unit 起不來時，upgrade 不得回報成功——否則 operator 以為升級完成
        # 但服務其實是停的。應 fail-closed、自動 rollback 並回 exit 1。
        scratch = make_test_dir("stage7-e3-restart-fail")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        seed_bin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, seed_bin)
            unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-cost.service"
            custom = unit.read_text(encoding="utf-8").replace("RestartSec=10", "RestartSec=42")
            unit.write_text(custom, encoding="utf-8")
            real = write_real_state_and_secret(home_dir)

            failing_bin, _ = make_fake_tools(scratch / "fail", restart_fails=True)
            completed = run_deploy(home_dir, failing_bin, "upgrade", "--apply", "--verify")

            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertTrue(payload["rollback_triggered"])
            self.assertIn("restart", payload["error"])
            # rollback 把 core unit 還原成升級前的內容。
            self.assertEqual(unit.read_text(encoding="utf-8"), custom)
            # state/secret 全程不受影響。
            self.assertEqual(
                Path(real["secret_path"]).read_text(encoding="utf-8"), real["secret"]
            )
            self.assertEqual(
                Path(real["state_path"]).read_text(encoding="utf-8"), real["state"]
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_upgrade_plan_only_still_emits_json(self) -> None:
        scratch = make_test_dir("stage7-e3-plan")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            completed = run_deploy(home_dir, fakebin, "upgrade")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "upgrade")
            self.assertTrue(payload["rollback_checkpoints"])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class RollbackTests(unittest.TestCase):
    def test_snapshot_and_restore_roundtrip_restores_core_content(self) -> None:
        scratch = make_test_dir("stage7-e4-roundtrip")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-cost.service"
            original = unit.read_text(encoding="utf-8")
            # 模擬使用者手改 unit（例如調整 RestartSec）。
            custom = original.replace("RestartSec=10", "RestartSec=30")
            unit.write_text(custom, encoding="utf-8")

            plan = build_command_plan("upgrade", instance_name="demo-agent", root_dir="/srv/paulshaclaw")
            checkpoint = scratch / "checkpoint"
            checkpoint.mkdir()
            snapshot_core_plane(plan, home_dir=home_dir, checkpoint_dir=checkpoint)

            # 模擬升級把 unit 覆寫成新版（apply_install_plan 會用模板覆寫 systemd unit）。
            unit.write_text("OVERWRITTEN BY UPGRADE\n", encoding="utf-8")

            restore = restore_core_from_checkpoint(checkpoint, home_dir=home_dir)
            self.assertIn(str(unit), restore["restored"])
            self.assertEqual(unit.read_text(encoding="utf-8"), custom)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_run_rollback_restores_core_from_latest_checkpoint(self) -> None:
        scratch = make_test_dir("stage7-e4-rollback-cli")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-cost.service"
            custom = unit.read_text(encoding="utf-8").replace("RestartSec=10", "RestartSec=99")
            unit.write_text(custom, encoding="utf-8")

            # 跑一次 upgrade --apply 產生 checkpoint（會以模板覆寫 unit）。
            run_deploy(home_dir, fakebin, "upgrade", "--apply")
            self.assertNotEqual(unit.read_text(encoding="utf-8"), custom)

            completed = run_deploy(home_dir, fakebin, "rollback", "--from-command", "upgrade")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["command"], "rollback")
            self.assertEqual(unit.read_text(encoding="utf-8"), custom)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_run_rollback_without_checkpoint_fails(self) -> None:
        scratch = make_test_dir("stage7-e4-rollback-none")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            completed = run_deploy(home_dir, fakebin, "rollback")
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "failed")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class UninstallExecutionTests(unittest.TestCase):
    def test_uninstall_apply_removes_core_preserves_state_and_secret_by_default(self) -> None:
        scratch = make_test_dir("stage7-e5-preserve")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, command_log = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            real = write_real_state_and_secret(home_dir)

            completed = run_deploy(home_dir, fakebin, "uninstall", "--apply")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "uninstall")
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["preserved_state"])
            self.assertTrue(payload["preserved_secret"])
            self.assertFalse(payload["purge_state"])
            self.assertFalse(payload["purge_secret"])
            self.assertTrue(payload["removed_core_files"])

            # core plane 已移除。
            unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-cost.service"
            runtime_env = home_dir / ".agents" / "core" / "runtime" / "demo-agent.env"
            self.assertFalse(unit.exists())
            self.assertFalse(runtime_env.exists())

            # state / secret 逐字保留。
            self.assertEqual(
                Path(real["state_path"]).read_text(encoding="utf-8"),
                real["state"],
            )
            self.assertEqual(
                Path(real["secret_path"]).read_text(encoding="utf-8"),
                real["secret"],
            )

            # 有呼叫 disable/stop。
            log = command_log.read_text(encoding="utf-8")
            self.assertIn("systemctl --user disable", log)
            self.assertIn("systemctl --user stop", log)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_uninstall_apply_with_purge_state_and_secret_removes_them(self) -> None:
        scratch = make_test_dir("stage7-e5-purge")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            seed_install(home_dir, fakebin)
            real = write_real_state_and_secret(home_dir)

            completed = run_deploy(
                home_dir,
                fakebin,
                "uninstall",
                "--apply",
                "--purge-state",
                "--purge-secret",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["purge_state"])
            self.assertTrue(payload["purge_secret"])
            self.assertFalse(payload["preserved_state"])
            self.assertFalse(payload["preserved_secret"])

            self.assertFalse(Path(real["state_path"]).exists())
            self.assertFalse(Path(real["secret_path"]).exists())
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_uninstall_plan_only_still_emits_json(self) -> None:
        scratch = make_test_dir("stage7-e5-plan")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _ = make_fake_tools(scratch)
        try:
            completed = run_deploy(home_dir, fakebin, "uninstall")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "uninstall")
            self.assertIn("preserve-state", payload["rollback_actions"])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class ArtifactVerificationUnitTests(unittest.TestCase):
    def test_verify_and_record_artifact_url_skips_download(self) -> None:
        from paulshaclaw.deploy.installer import _verify_and_record_artifact

        record = _verify_and_record_artifact(
            artifact="https://example.com/paulshaclaw.whl",
            artifact_sha256=None,
        )
        self.assertEqual(record["source"], "https://example.com/paulshaclaw.whl")

    def test_verify_and_record_artifact_missing_raises(self) -> None:
        from paulshaclaw.deploy.installer import _verify_and_record_artifact

        with self.assertRaises(ArtifactVerificationError):
            _verify_and_record_artifact(artifact="/nonexistent/path.whl", artifact_sha256=None)

    def test_verify_and_record_artifact_sha256_without_artifact_fails_closed(self) -> None:
        # 只給 sha256 沒給 artifact：沒有任何東西可算，記下來的 checksum 會讓
        # operator 誤以為驗證過，必須 fail-closed。
        from paulshaclaw.deploy.installer import _verify_and_record_artifact

        with self.assertRaises(ArtifactVerificationError):
            _verify_and_record_artifact(artifact=None, artifact_sha256="deadbeef")

    def test_verify_flag_true_only_for_locally_computed_sha256(self) -> None:
        from paulshaclaw.deploy.installer import _verify_and_record_artifact

        scratch = make_test_dir("stage7-e1-verified-flag")
        try:
            artifact = scratch / "paulshaclaw-0.1.0-py3-none-any.whl"
            artifact.write_bytes(b"fake wheel")

            local = _verify_and_record_artifact(artifact=str(artifact), artifact_sha256=None)
            self.assertTrue(local["verified"])

            # URL 不下載，checksum 未經驗證；無 artifact 亦然。
            url = _verify_and_record_artifact(
                artifact="https://example.com/paulshaclaw.whl", artifact_sha256=None
            )
            self.assertFalse(url["verified"])
            none_record = _verify_and_record_artifact(artifact=None, artifact_sha256=None)
            self.assertFalse(none_record["verified"])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_record_path_under_state_config(self) -> None:
        path = _install_record_path(Path("/tmp/fake-home"), instance_name="demo")
        self.assertEqual(path, Path("/tmp/fake-home/.agents/state/config/demo.install-record.json"))


class CheckpointUniquenessTests(unittest.TestCase):
    def test_consecutive_checkpoints_never_share_a_directory(self) -> None:
        # 秒級 timestamp + exist_ok=True 會讓同一秒內的兩次 upgrade 共用目錄，
        # 後者的 snapshot 覆寫前者 → rollback 還原到已被改過的內容。
        from paulshaclaw.deploy.installer import _new_checkpoint_dir

        scratch = make_test_dir("stage7-e4-unique")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        try:
            created = [
                _new_checkpoint_dir(home_dir, instance_name="demo-agent", command="upgrade")
                for _ in range(20)
            ]
            self.assertEqual(len(set(created)), len(created))
            # 名稱排序即時間排序，latest_checkpoint() 才會拿到最後建立的那個。
            self.assertEqual([str(p) for p in created], sorted(str(p) for p in created))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()