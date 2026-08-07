"""測試層環境隔離防線（#285）。

deploy 流程的家目錄根 `paths.home_root()` 預設走 `Path.home()`，但優先吃
`PSC_HOME_ROOT` 覆寫點。任一 deploy 呼叫點漏帶隔離就會寫進真實 host。

這裡對 deploy / home-isolation 測試模組提供第二道防線：把 `PSC_HOME_ROOT`
指向 pytest 暫存目錄，讓 `home_root()` 即使在沒有顯式 `--home-dir` / 換 `HOME`
的情況下也只會解析到 tmp，不會命中真實家目錄。

**範圍限制**：只對 deploy / home-isolation 相關測試模組生效。其他測試模組
（如 test_stage8_cost、test_reply_bridge）會拿 `paths.home_root()` 與 import 時
以 `Path.home()` 算出的模組常數做一致性比對——session 全域覆寫 `PSC_HOME_ROOT`
會讓函式側回 tmp、常數側回真實家目錄而誤判漂移。故此 fixture 以測試模組路徑
篩選，不全域覆寫。

各 stage7 測試的 `deploy_env()` 仍顯式把 `PSC_HOME_ROOT` 設成該測試的假 `HOME`，
避開 conftest tmp 與假 HOME 不一致導致斷言找不到檔案的陷阱。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# 受第二道防線保護的測試模組檔名前綴：deploy 流程會寫家目錄的測試。
_DEPLOY_TEST_PREFIXES = ("test_stage7_deploy", "test_home_isolation")


def _is_deploy_test(request: pytest.FixtureRequest) -> bool:
    module = getattr(request.node, "module", None)
    if module is None or not hasattr(module, "__file__"):
        return False
    name = Path(module.__file__).name
    return name.startswith(_DEPLOY_TEST_PREFIXES)


@pytest.fixture(scope="session")
def _psc_home_root_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("psc-home-root")


@pytest.fixture(autouse=True)
def isolate_home_root_for_deploy(
    request: pytest.FixtureRequest,
    _psc_home_root_dir: Path,
) -> Iterator[None]:
    if not _is_deploy_test(request):
        yield
        return
    previous = os.environ.get("PSC_HOME_ROOT")
    os.environ["PSC_HOME_ROOT"] = str(_psc_home_root_dir)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PSC_HOME_ROOT", None)
        else:
            os.environ["PSC_HOME_ROOT"] = previous