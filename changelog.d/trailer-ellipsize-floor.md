---
type: fix
---
JOBS trailer 退讓到只剩最重要一項仍塞不下時，改用 `_ellipsize_middle` 縮進預算顯示（頭尾都保，branch 的 issue 編號在頭段），不再整項丟棄留白（#299）——窄面板下 #292 的 branch 曾把 wf-hash 擠掉後自己也被丟掉，trailer 全空比修之前更糟。預算低於 8 顯示欄維持留白（一小截沒資訊量）。
