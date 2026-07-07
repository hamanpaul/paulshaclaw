### Added
- G3 常駐服務 systemd 化（#126）：四 loop 抽成 `scripts/service-{bot,cost,dream,manager}.sh`（行為零變更，保 #211 deident env／manager --specs-dir／#205 respawn）；deploy 平面補 `-dream`/`-cost` unit 模板與 planner 接線、install/verify（假 $HOME 綠）；`adr-001-always-on-deployment` 補寫（實測依據＋選路＋rollback）；dream unit 標 will-migrate-to-hippo（#125）
