---
type: change
issue: 90
---
reply_bridge 路徑常數漂移把關（#90）：`custom-skills/bro/scripts/reply_bridge.py`（standalone 工具，不可 `import paulshaclaw.*`）的三個字面預設路徑常數，與 `paulshaclaw/bot/reply.py` 的 `default_config_path()` / `default_secret_env_path()` / `default_bindings_path()` facade 本是同一組慣例路徑的獨立副本，先前漂移只能肉眼發現（#91 已解的 `memory_root()` 三份重複是同類根因的另一半）。兩邊互相加註解指向對方，並新增 `test_default_paths_match_facade` 於 CI 把關一致性，另補優先序（CLI 參數 > `PSC_*` env > 內建預設）與「呼叫端不傳路徑時仍能正確解析」的回歸測試（對應 `scripts/gemma4-hooks/bro_out.py` / `psc-bro-return.py` 目前的實際呼叫方式）。
