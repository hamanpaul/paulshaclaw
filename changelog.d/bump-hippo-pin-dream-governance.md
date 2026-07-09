### Changed
- bump `paulsha-hippo` pin 至含 dream 資源治理（#22）的 main SHA：`hippo dream --require-idle` 加記憶體 headroom 閘（`--min-avail-mem-pct`，預設 20%）、`dream supervise` 對 systemd timer 讓位、dream systemd timer 改 hourly + 可攜 cgroup 上限（`CPUWeight=20`/`MemoryHigh=20%`/`MemoryMax=30%`/`TasksMax=256`）。
