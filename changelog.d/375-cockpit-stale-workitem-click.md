---
type: fix
scope: cockpit
---
Cockpit WORK 清單在 `_refresh_widgets()` clear/append 重建後，若舊 `WorkItem` 的 child-click 事件晚到，現在會先停掉 stale 事件而不再對已移除列做 index 查找，避免偶發 `ValueError` 崩潰，同時保留現役列的單擊選取、雙擊 swap 與 enter swap 行為。
