# Stage5 Recovery 證據樣板

## 測試命令

```bash
python3 -m unittest tests.test_stage5_observability_recovery -v
python3 -m unittest discover -s tests
```

## 建議 artifact

- `<run_id>-stage5-unittest-red.log`
- `<run_id>-stage5-unittest-green.log`
- `<run_id>-stage5-chaos-matrix.json`
- `<run_id>-stage5-unittest-final.log`

## 結果摘要欄位

1. 執行時間
2. 命令
3. 結果摘要
4. 關聯規格 / playbook
5. 後續風險或人工介入點
