"""#296：`custom-skills/bro` 的單一真相源是本 repo；runtime 載入點 `~/.agents/skills/bro`
應為指向本 repo checkout 的 symlink。若該路徑存在卻指向另一份實體副本（歷史上曾以
hardlink 同步、被「重建檔案」式編輯後靜默分家），這裡會把兩側 diff 攤出來，讓
CI 綠燈不再掩蓋 runtime 跑舊碼的情況。CI／乾淨 clone 沒有該路徑時跳過。"""
from __future__ import annotations

import filecmp
import os
import unittest
from pathlib import Path

REPO_BRO = Path(__file__).resolve().parents[1]
RUNTIME_BRO = Path(os.environ.get("PSC_BRO_RUNTIME_PATH") or Path.home() / ".agents" / "skills" / "bro")
TRACKED = ("SKILL.md", "scripts/reply_bridge.py", "scripts/notify.py")


class RuntimeCopyDriftTest(unittest.TestCase):
    def test_runtime_copy_is_repo_or_identical(self) -> None:
        if not RUNTIME_BRO.exists():
            self.skipTest(f"{RUNTIME_BRO} 不存在（CI／乾淨 clone）")
        runtime = RUNTIME_BRO.resolve()
        if runtime == REPO_BRO:
            return  # symlink 已指向本 repo checkout，單一真相源成立
        drifted = [
            rel for rel in TRACKED
            if not (runtime / rel).exists() or not filecmp.cmp(REPO_BRO / rel, runtime / rel, shallow=False)
        ]
        self.assertEqual(
            drifted,
            [],
            f"runtime 副本 {runtime} 與 repo 副本漂移：{drifted}；請把 ~/.agents/skills/bro 改為指向 "
            f"{REPO_BRO} 的 symlink（#296），不要維護第二份實體副本",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
