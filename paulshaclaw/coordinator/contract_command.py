from __future__ import annotations

import shlex
from typing import Mapping

from paulshaclaw.persona import render
from paulshaclaw.persona.contract import PersonaContract

# 預設 executor 前綴：builder 首發 copilot one-shot（設計 §3）。
DEFAULT_EXECUTOR: tuple[str, ...] = ("copilot", "--model", "gpt-5.4", "--yolo", "-p")


def build_dispatch_command(
    role: str,
    *,
    task: str,
    plan_path: str,
    executor: tuple[str, ...] = DEFAULT_EXECUTOR,
    catalog: Mapping[str, PersonaContract] | None = None,
) -> str:
    """強制點 ①：把 persona 契約 render 成 prompt 前言，拼成可送進 pane 的單行指令。

    純字串函式、零 I/O：只嵌 plan_path 參照（copilot 於 worktree 內自行讀計畫），
    不在此讀檔。未知 role → ValueError（由 render_contract_prompt 冒泡）。
    以 shlex.join 收尾，prompt 為單一安全 token（TmuxPaneSender 以 -l literal 送）。
    """
    contract_prompt = render.render_contract_prompt(role, catalog)
    prompt = (
        f"{contract_prompt}\n\n"
        f"[TASK] {task}\n"
        f"[PLAN: {plan_path}]\n"
        "請於本 worktree 內讀取上述 plan 並依 persona 契約邊界執行。"
    )
    return shlex.join([*executor, prompt])
