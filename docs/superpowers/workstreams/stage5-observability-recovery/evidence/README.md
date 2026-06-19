# stage5-observability-recovery evidence index

## 命名規則

- 主格式：`<run_id>-stage5-unittest-<phase>.log`
- `phase` 固定使用：`red`、`green`、`final`
- chaos matrix artifact：`<run_id>-stage5-chaos-matrix.json`

## 本次 run 證據

| 檔名 | 用途 |
|---|---|
| `20260421T120000+0800-stage5-unittest-red.log` | Red：測試先失敗，證明 Stage5 契約尚未落地 |
| `20260421T121500+0800-stage5-unittest-green.log` | Green：補上 observability baseline 後 Stage5 專屬測試通過 |
| `20260421T122500+0800-stage5-chaos-matrix.json` | recovery / chaos baseline matrix，列出 tmux crash 與 full restart 證據檔案 |
| `20260421T123500+0800-stage5-unittest-final.log` | Final：`python3 -m unittest discover -s tests` 全量回歸結果 |

## 關聯文件

- `stage5-recovery-template.md`
- `../review.md`
- `/home/paul_chen/prj_pri/paulshaclaw-worktrees/stage5-observability-recovery/docs/ops/recovery.md`
