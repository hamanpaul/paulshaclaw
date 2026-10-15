## 1. Consumer

- [x] 1.1 核對上游 merge SHA、契約與原始 fixture。
- [x] 1.2 RED：先重現身份遺失、來源未區分與刷新未顯示問題。
- [x] 1.3 實作 typed ingestion、身份來源 detail 與缺值 fallback。
- [x] 1.4 以隔離環境固定 producer SHA，驗 registry→status→consumer 與 headless refresh。
- [x] 1.5 完成 full suite、preflight、review 與 installed wheel 驗收。
- [ ] 1.6 deferred：依 2026-10-15 operator 決議等待重構後上游契約；本輪不修補 Cortex、不自行遷移。現 pin 僅為 consumer 驗證候選；Draft 不 merge、issue 保持開放。
