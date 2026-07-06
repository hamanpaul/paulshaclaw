## 1. 服務腳本抽取

- [ ] 1.1 RED：service-{cost,dream,manager,bot}.sh 存在性/語法/參數測試（沿 test_start_sh* 模式，避開 SIGKILL）
- [ ] 1.2 四 loop 函式體抽成腳本；start.sh 改薄（--dev 直跑，行為不變）；GREEN＋既有 start.sh 測試零回歸

## 2. 模板與 planner

- [ ] 2.1 RED：新模板渲染測試（-dream/-cost.service）＋manager .service 常駐＋timer deprecated 標記＋per-service env 清單宣告測試
- [ ] 2.2 deploy templates 新增/調整＋planner 接線＋`systemd-analyze --user verify` 靜態檢查；GREEN

## 3. install 與 verify

- [ ] 3.1 unit 安裝（複製到 ~/.config/systemd/user/）＋`loginctl enable-linger` 冪等步驟＋env 檔/鍵存在性 verify（不印值）
- [ ] 3.2 假 $HOME 環境 install→verify 綠

## 4. cutover（ops，一次一服務）

- [ ] 4.1 cost cutover：stop start.sh 側→enable --now→功能驗證→觀察 ≥1 天
- [ ] 4.2 dream cutover（驗 idle-gate/lock 語意不變）
- [ ] 4.3 manager cutover（驗 manager.lock 單實例互斥）
- [ ] 4.4 bot cutover（最後）＋P0-2 respawn 降級 dev-mode only
- [ ] 4.5 真 cold-start DoD：wsl --shutdown→重開→四服務自起全驗（不過則 fallback 文件化）

## 5. adr 與收尾

- [ ] 5.1 adr-001-always-on-deployment（實測依據/選路/rollback/運維指令表）
- [ ] 5.2 全套件綠；PR body `Closes #126`
