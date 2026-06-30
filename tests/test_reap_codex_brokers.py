"""scripts/reap-codex-brokers.sh 的單測。

用 REAP_PS_SNAPSHOT 餵假 process 表、REAP_KILL_CMD 注入假 killer，
完全 hermetic（不依賴真 `ps`、不真的殺行程），驗證孤兒偵測與安全排除。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reap-codex-brokers.sh"

_BROKER = (
    "/home/x/.nvm/versions/node/v22.20.0/bin/node "
    "/home/x/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/app-server-broker.mjs serve "
    "--endpoint unix:/tmp/{sock}/broker.sock --cwd {cwd} --pid-file /tmp/{sock}/broker.pid"
)

# pid ppid args
SNAPSHOT_LINES = [
    "1 0 /sbin/init",
    "2 1 /init",
    "1177 2 /init",  # WSL 子收割鏈
    "300 1 /usr/lib/systemd/systemd --user",                    # systemd --user 子收割（pid != 1）
    "400 4999 node /home/x/systemd-notify-helper.js",           # args 含 "systemd" 但 exe=node → 非 reaper
    "4999 4000 -bash",
    "5000 4999 /home/x/.nvm/versions/node/v22.20.0/bin/claude",  # 活 session
    f"8001 1177 {_BROKER.format(sock='cxc-AAA', cwd='/home/x/prj/.worktrees/feat-a')}",  # 孤兒(WSL /init)
    f"8002 1 {_BROKER.format(sock='cxc-BBB', cwd='/home/x/prj/.worktrees/feat-b')}",     # 孤兒(PID 1)
    f"8003 5000 {_BROKER.format(sock='cxc-CCC', cwd='/home/x/prj/main')}",               # 活：parent=活 claude
    f"8004 300 {_BROKER.format(sock='cxc-DDD', cwd='/home/x/prj/.worktrees/feat-d')}",   # 孤兒(systemd --user 子收割)
    f"8005 400 {_BROKER.format(sock='cxc-EEE', cwd='/home/x/prj/.worktrees/feat-e')}",   # 不殺：parent exe=node，非 reaper
    "9000 8001 node /home/x/.npm/_npx/abc/node_modules/.bin/mcp-server-memory",          # 雜訊
]


def _write_snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "ps_snapshot.txt"
    snap.write_text("\n".join(SNAPSHOT_LINES) + "\n", encoding="utf-8")
    return snap


def _run(snap: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "REAP_PS_SNAPSHOT": str(snap)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, env=env, check=False,
    )


def test_dry_run_lists_orphans_excludes_live(tmp_path):
    snap = _write_snapshot(tmp_path)
    res = _run(snap)  # 預設 dry-run
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "8001" in out and "8002" in out            # /init、PID 1 孤兒
    assert "8004" in out                              # systemd --user 子收割的孤兒也列出
    assert "8003" not in out                          # 活 session 的 broker 不能被列
    assert "8005" not in out                          # parent exe=node（非 reaper）→ 不可誤判為孤兒
    assert "/home/x/prj/.worktrees/feat-a" in out     # cwd 解析正確
    assert "/home/x/prj/.worktrees/feat-b" in out
    assert "dry-run" in out


def test_dry_run_does_not_kill(tmp_path):
    snap = _write_snapshot(tmp_path)
    kill_log = tmp_path / "killed.txt"
    killer = tmp_path / "fakekill.sh"
    killer.write_text(f'#!/usr/bin/env bash\necho "$2" >> "{kill_log}"\n', encoding="utf-8")
    killer.chmod(0o755)
    res = _run(snap, env_extra={"REAP_KILL_CMD": str(killer)})  # 無 --apply
    assert res.returncode == 0, res.stderr
    assert not kill_log.exists()  # dry-run 不得呼叫 killer


def test_apply_sigterms_only_orphans(tmp_path):
    snap = _write_snapshot(tmp_path)
    kill_log = tmp_path / "killed.txt"
    killer = tmp_path / "fakekill.sh"
    # fakekill 收到 "-TERM <pid>"，把 pid 記下來
    killer.write_text(f'#!/usr/bin/env bash\necho "$2" >> "{kill_log}"\n', encoding="utf-8")
    killer.chmod(0o755)
    res = _run(snap, "--apply", env_extra={"REAP_KILL_CMD": str(killer)})
    assert res.returncode == 0, res.stderr
    killed = sorted(kill_log.read_text(encoding="utf-8").split())
    # 只殺孤兒（/init、PID 1、systemd --user 子收割）；活 8003、誤判防護 8005 不動
    assert killed == ["8001", "8002", "8004"]


def test_no_orphans_is_clean_exit(tmp_path):
    snap = tmp_path / "snap.txt"
    snap.write_text("1 0 /sbin/init\n5000 1 /home/x/bin/claude\n", encoding="utf-8")
    res = _run(snap)
    assert res.returncode == 0, res.stderr
    assert "無孤兒" in res.stdout


def test_help_exits_zero(tmp_path):
    res = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0
    assert "app-server-broker" in res.stdout
    assert "/usr/bin/env bash" not in res.stdout  # shebang 不得漏進 help 輸出
