---
work_item: deploy-testpilot-case
---
# deploy-testpilot-case / todo

對應 issue：hamanpaul/paulshaclaw#324（TestPilot plugin test case：Docker 重現「照 README §A 安裝 v0.2.7 後找不到 paulshaclaw 指令」，RED 供 TDD）

## Current Sprint

- [ ] 建立 repo-owned TestPilot plugin 子專案 `testpilot/`（pyproject＋entry point `paulshaclaw_deploy`）
- [ ] `docker_transport.py`（TransportBase：docker run/exec/rm，每步獨立記 exit code）
- [ ] cases：TC-1（RED）、TC-1c／TC-1g（控制組 GREEN）、TC-1p（pipx，RED）
- [ ] `testpilot/tests/` 以 StubTransport 驗 plugin 邏輯；CI 跑 tests＋list-cases，docker case 標 expected-RED
- [ ] 在有 docker 的主機實跑 TC-1 取得 RED report，附於 PR

## Blockers

- [ ] cortex 派工 builder=agy 受阻於 paulsha-cortex#799（owner 裁決 A／B 後解除）

## Evidence / Links

- 失敗契約：`~/prj_pri/tmp/paulshaclaw-docker-repro-20260826/REPRO-REPORT.md`（本機）
- wheel sha256 `cc2e0771ba09030b23280ba1ab19a898ce147f8ef4e942a226bf10ddcd2be13f`

## Handoff Notes

- 修復（#325）與 templates 打包缺陷（#326）不在本 workstream 範圍。
