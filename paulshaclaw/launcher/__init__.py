"""paulshaclaw.launcher — 正式（release）啟動路徑（#288）。

與 dev 路徑（scripts/start.sh）的邊界：
- 本套件是 `paulshaclaw` console script 的家，行為與 start.sh 對等；
- 與 `psc`（paulshaclaw.cli，cortex dispatcher）語意分離，互不 import；
- cortex / hippo 只以 subprocess 模組字串觸碰，不做 runtime import
  （scripts/check_import_surface.py 為守門）。
"""
from __future__ import annotations
