from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import yaml

from .contract_command import build_dispatch_command

# is_satisfied predicate 型別：收 slice_id，回該相依是否「已滿足」（可釋放下游）。
# 判定來源由呼叫者決定（merged-to-main vs handoff gate_status）——#104 留開放。
IsSatisfied = Callable[[str], bool]

# Dispatcher duck-type：只需有 dispatch(task, persona, pane_id, command) -> dict（Phase 2 介面）。
DEFAULT_HANDOFF_DIR = "runtime/handoff"


# --------------------------------------------------------------------------- #
# 1) frontmatter 解析（預設 HOLD）
# --------------------------------------------------------------------------- #
def _split_frontmatter(text: str) -> str | None:
    """回 frontmatter 區塊原文；無合法 frontmatter（不以 --- 起頭/無收尾 ---）→ None。"""
    if not text.startswith("---"):
        return None
    # 首行 --- 之後找下一個單獨成行的 ---
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None  # 無收尾 ---


def parse_spec_frontmatter(path) -> dict:
    """解析 superpowers spec 開頭 --- frontmatter。

    回 {path, dispatch, slice_id, plan, depends_on}。
    硬約束：dispatch 僅在字面值為 'auto' 時為 'auto'，其餘一律 'hold'（fail-safe）。
    容忍無 frontmatter（視為 hold），不 raise。
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    block = _split_frontmatter(text)

    meta: dict = {
        "path": str(p),
        "dispatch": "hold",
        "slice_id": None,
        "plan": None,
        "depends_on": [],
    }
    if block is None:
        return meta

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return meta  # 壞 frontmatter → 視為 hold（fail-safe，不 raise）
    if not isinstance(data, dict):
        return meta

    # dispatch：只認字面 'auto'
    if data.get("dispatch") == "auto":
        meta["dispatch"] = "auto"

    sid = data.get("slice_id")
    meta["slice_id"] = sid if isinstance(sid, str) else None

    plan = data.get("plan")
    meta["plan"] = plan if isinstance(plan, str) else None

    dep = data.get("depends_on")
    if isinstance(dep, list):
        meta["depends_on"] = [str(x) for x in dep]
    elif isinstance(dep, str):
        meta["depends_on"] = [dep]  # 單一字串容錯成單元素 list
    else:
        meta["depends_on"] = []

    return meta


# --------------------------------------------------------------------------- #
# 2) scan_specs（確定性）
# --------------------------------------------------------------------------- #
def scan_specs(specs_dir) -> list[dict]:
    """掃 specs_dir 下 *.md，逐檔 parse_spec_frontmatter，確定性排序。

    目錄不存在 → []（非錯誤）。
    """
    d = Path(specs_dir)
    if not d.is_dir():
        return []
    return [parse_spec_frontmatter(p) for p in sorted(d.glob("*.md"))]


# --------------------------------------------------------------------------- #
# 3) detect_cycles（DAG 回邊偵測，refuse）
# --------------------------------------------------------------------------- #
def _build_graph(metas: list[dict]) -> dict[str, list[str]]:
    """以 slice_id 為節點、depends_on 為有向邊建圖。

    重複 slice_id → raise ValueError（身分不明確的 DAG 直接拒絕，不靜默合併）。
    兩份 spec 誤用同一 slice_id 是現實的 copy-paste 錯誤：若靜默以後者覆寫前者的
    邊，會遮蔽真實的環；下游 fan-out 也會對同一 `feature/<slice_id>` 重複派工
    （第二次 `git worktree add` 必失敗、且違反「一單位一 job」）。故 fail-safe 提前拒絕。
    不含 slice_id（None/非字串）的 meta 不入圖（無身分，不可為相依目標）。
    """
    graph: dict[str, list[str]] = {}
    for m in metas:
        sid = m.get("slice_id")
        if not isinstance(sid, str):
            continue
        if sid in graph:
            raise ValueError(f"depends_on 偵測到重複 slice_id: {sid}")
        graph[sid] = [d for d in m.get("depends_on", [])]
    return graph


def detect_cycles(metas: list[dict]) -> None:
    """以 slice_id 為節點、depends_on 為有向邊偵測循環相依。

    成環 → raise ValueError（帶 cycle path）。
    重複 slice_id → raise ValueError（先於 DFS，見 _build_graph）。
    指向不在 metas 的 slice_id 的邊不算環（外部/未掃到，交給 is_satisfied）。
    """
    graph = _build_graph(metas)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in graph}
    stack: list[str] = []

    def visit(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue  # 外部相依 → 不算環
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise ValueError(f"depends_on 偵測到循環相依: {' -> '.join(cycle)}")
            if color[dep] == WHITE:
                visit(dep)
        stack.pop()
        color[node] = BLACK

    for sid in graph:
        if color[sid] == WHITE:
            visit(sid)


# --------------------------------------------------------------------------- #
# 4) ready_units（三條件 + 先偵測環）
# --------------------------------------------------------------------------- #
def ready_units(metas: list[dict], is_satisfied: IsSatisfied) -> list[dict]:
    """回就緒單位：有 slice_id ∧ dispatch=='auto' ∧ plan 非空 ∧ depends_on 全滿足。

    MUST 先 detect_cycles（成環/重複 slice_id 整批 raise，不回部分集）。
    無 slice_id（None/非字串/空字串）的單位無身分——無法成為 depends_on 目標、
    無法被追蹤或交接——依 fail-safe 立場 MUST NOT 就緒；此檢查也使 dispatch_ready
    存取 m['slice_id'] / m['plan'] 必為合法非空字串。
    is_satisfied 為必注入參數（呼叫者決定判定來源）。確定性序（沿 metas 順序）。
    """
    detect_cycles(metas)  # 先 refuse 環/重複 slice_id
    ready: list[dict] = []
    for m in metas:
        if not (isinstance(m.get("slice_id"), str) and m["slice_id"]):
            continue
        if m.get("dispatch") != "auto":
            continue
        if not (isinstance(m.get("plan"), str) and m["plan"]):
            continue
        deps = m.get("depends_on", [])
        if all(is_satisfied(dep) for dep in deps):
            ready.append(m)
    return ready


# --------------------------------------------------------------------------- #
# 5) default_is_satisfied（預設來源 = handoff gate_status；保持可注入覆寫）
# --------------------------------------------------------------------------- #
def default_is_satisfied(slice_id: str, handoff_dir: str = DEFAULT_HANDOFF_DIR) -> bool:
    """預設判定：runtime/handoff/<slice_id>.json 存在且 gate_status=='passed'。

    檔不存在/壞檔/非 passed → False（fail-closed：未證明滿足即不釋放下游）。
    這只是預設 impl；ready_units/dispatch_ready 一律收注入 predicate，
    未來換 merged-to-main 來源只需換注入物（同 Callable[[str], bool] 介面）。
    """
    p = Path(handoff_dir) / f"{slice_id}.json"
    if not p.is_file():
        return False
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(payload, dict) and payload.get("gate_status") == "passed"


# --------------------------------------------------------------------------- #
# 6) dispatch_ready（fan-out，reuse Phase 2 Dispatcher）
# --------------------------------------------------------------------------- #
def dispatch_ready(
    metas: list[dict],
    is_satisfied: IsSatisfied,
    dispatcher,
    persona: str = "builder",
    git_runner=None,
) -> list[dict]:
    """算就緒集，對每單位經注入的 Phase 2 Dispatcher 各派一筆 job（reuse，不重寫派工）。

    一單位一 job；隔離靠 per-worktree/pane（Phase 2 性質），故並行安全。
    pane_id/command 為佔位（真實 pane 分配與 copilot prompt 拼裝屬 §5 ①，非本層）。
    git_runner 為可選注入物：給定時透傳給 Dispatcher.dispatch（沿用 Phase 2 既有 seam），
    讓測試以 fake git_runner 取代真 git（不啟動真 git）；未給定時不傳，沿用
    dispatcher 自身預設（且相容不收 git_runner 的 fake dispatcher）。
    回 dispatched jobs。
    """
    ready = ready_units(metas, is_satisfied)
    jobs: list[dict] = []
    for i, m in enumerate(ready):
        slice_id = m["slice_id"]
        kwargs = {
            "task": slice_id,
            "persona": persona,
            "pane_id": f"%{i}",
            "command": build_dispatch_command(persona, task=slice_id, plan_path=m["plan"]),
        }
        if git_runner is not None:
            kwargs["git_runner"] = git_runner
        job = dispatcher.dispatch(**kwargs)
        jobs.append(job)
    return jobs
