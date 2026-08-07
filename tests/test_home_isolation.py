"""#285 反例測試：守住「未顯式隔離時 deploy 不寫進真實家目錄」。

三道斷言：
1. `home_root()` 尊重 `PSC_HOME_ROOT` 環境變數覆寫（整條隔離的根）。
2. CLI 帶 `--home-dir` 時，所有落點都在該目錄下、不在真實 `Path.home()`。
3. conftest 第二道防線的檔名前綴確實涵蓋所有會寫家目錄的 deploy 測試模組。

即使有人拿掉 conftest 的防線，前兩項的形狀仍能抓到逃逸；第三項則守住防線
本身不會因為新增測試檔而靜默失效。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from paulshaclaw.config.paths import home_root

REPO_ROOT = Path(__file__).resolve().parents[1]


class HomeRootOverrideTests(unittest.TestCase):
    def test_home_root_respects_psc_home_root(self) -> None:
        previous = os.environ.get("PSC_HOME_ROOT")
        fake_home = REPO_ROOT / ".test-artifacts" / "home-root-override"
        try:
            fake_home.mkdir(parents=True, exist_ok=True)
            os.environ["PSC_HOME_ROOT"] = str(fake_home)
            self.assertEqual(home_root(), fake_home)
        finally:
            if previous is None:
                os.environ.pop("PSC_HOME_ROOT", None)
            else:
                os.environ["PSC_HOME_ROOT"] = previous
            shutil.rmtree(fake_home, ignore_errors=True)

    def test_home_root_falls_back_to_path_home_without_override(self) -> None:
        previous = os.environ.pop("PSC_HOME_ROOT", None)
        try:
            self.assertEqual(home_root(), Path.home())
        finally:
            if previous is not None:
                os.environ["PSC_HOME_ROOT"] = previous


class CliHomeDirIsolationTests(unittest.TestCase):
    """CLI 帶 --home-dir 時所有落點都應在該目錄下，不得命中真實 Path.home()。"""

    def test_install_with_home_dir_writes_only_under_that_dir(self) -> None:
        scratch = REPO_ROOT / ".test-artifacts" / "home-isolation-cli"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            fakebin = scratch / "fakebin"
            fakebin.mkdir(parents=True, exist_ok=True)
            (fakebin / "systemctl").write_text(
                "#!/bin/bash\nexit 0\n", encoding="utf-8"
            )
            (fakebin / "systemctl").chmod(0o755)
            (fakebin / "loginctl").write_text(
                "#!/bin/bash\nexit 0\n", encoding="utf-8"
            )
            (fakebin / "loginctl").chmod(0o755)
            (fakebin / "systemd-analyze").write_text(
                "#!/bin/bash\nexit 0\n", encoding="utf-8"
            )
            (fakebin / "systemd-analyze").chmod(0o755)

            home_dir = scratch / "isolated-home"
            home_dir.mkdir(parents=True, exist_ok=True)
            # 誘餌家目錄：HOME 指到這裡而非真實家目錄。
            #
            # 這個測試要證明的是「--home-dir 真的決定落點」，但若直接讓 HOME 保持
            # 真實值，一旦 --home-dir 沒接上，deploy 就會把 demo-agent 寫進真實家
            # 目錄——那正是 #285 事故本身。改成 HOME 指向誘餌 tmp：--home-dir 有效
            # 時檔案落在 home_dir、失效時落在誘餌，兩種情況都碰不到真實家目錄，
            # 而斷言仍然抓得到失效。
            decoy_home = scratch / "decoy-home"
            decoy_home.mkdir(parents=True, exist_ok=True)

            # 不設 PSC_HOME_ROOT——只靠 --home-dir 決定落點。
            env = os.environ.copy()
            env["PATH"] = str(fakebin)
            env["HOME"] = str(decoy_home)
            env.pop("PSC_HOME_ROOT", None)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "paulshaclaw.deploy",
                    "install",
                    "--instance",
                    "demo-agent",
                    "--root-dir",
                    "/srv/paulshaclaw",
                    "--home-dir",
                    str(home_dir),
                    "--apply",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)

            # 所有預期落點都在 --home-dir 之下。
            relative_targets = [
                Path(".config") / "systemd" / "user" / "demo-agent-cost.service",
                Path(".agents") / "core" / "runtime" / "demo-agent.env",
                Path(".agents") / "state" / "config" / "demo-agent.state.json",
                Path(".config") / "paulshaclaw" / "demo-agent.secret.env",
            ]
            for rel in relative_targets:
                self.assertTrue((home_dir / rel).exists(), msg=str(home_dir / rel))
                # 誘餌家目錄必須完全沒被寫入——有的話代表 --home-dir 沒接上，
                # 換成真實 HOME 時就會重演 #285。
                self.assertFalse((decoy_home / rel).exists(), msg=str(decoy_home / rel))

            # 真實家目錄全程未參與（HOME 已被導向誘餌）。
            self.assertNotEqual(Path(env["HOME"]), Path.home())
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class ConftestCoverageTests(unittest.TestCase):
    """守住 conftest 第二道防線的涵蓋範圍（#285）。

    `tests/conftest.py` 的 `isolate_home_root_for_deploy` 以**檔名前綴**篩選要
    保護的測試模組（session 全域覆寫會讓 11 個做 facade↔常數漂移比對的既有測試
    誤判，見該檔 docstring）。代價是新增一個碰 deploy 寫入路徑、但檔名不符前綴
    的測試檔時，防線會靜默失效——而「靠人記得」正是 #285 的根因。

    這條測試把它變成 fail-closed：凡是會觸及 deploy 實際寫入路徑的測試模組，
    檔名都必須落在 `_DEPLOY_TEST_PREFIXES` 內。
    """

    # 會實際寫檔的入口（planner 的 build_command_plan 是純函式，不在此列）。
    _WRITE_PATH_MARKERS = (
        "deploy.installer",
        "apply_install_plan",
        "run_install",
        "run_upgrade",
        "run_uninstall",
        "run_rollback",
        '"paulshaclaw.deploy"',
    )

    def test_every_deploy_writing_test_module_is_covered_by_conftest(self) -> None:
        import tests.conftest as conftest_module

        prefixes = conftest_module._DEPLOY_TEST_PREFIXES
        uncovered: list[str] = []
        for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            if not any(marker in text for marker in self._WRITE_PATH_MARKERS):
                continue
            if not path.name.startswith(prefixes):
                uncovered.append(path.name)

        self.assertEqual(
            uncovered,
            [],
            msg=(
                "下列測試模組會觸及 deploy 的實際寫入路徑，但檔名不符 "
                f"tests/conftest.py 的 {prefixes}，家目錄隔離的第二道防線對它們無效。"
                "請改名或擴充該前綴清單："
                f"{uncovered}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
