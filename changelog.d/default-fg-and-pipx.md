---
type: fix
---
JOBS 的「白色」改用終端預設前景（rich 空 style）消除與 banner 的色差（#317）：name 欄、trailer、phase 子行與五桶的 wait-for-start 白不再指定 `#E2E8F0`，其餘四桶（綠紅橘灰）不動。README end-user 安裝補 pipx 段——`pipx install <wheel>` 後 `paulshaclaw`／`psc` 直接於 PATH 可用，不需進 venv。
