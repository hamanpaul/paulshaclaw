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
    """強制點 ①：把 persona 契約 render 成 prompt 前言，拼成 copilot 派工指令字串。

    呼叫期零檔案 I/O：只嵌 plan_path 參照（copilot 於 worktree 內自行讀計畫），
    不在此讀檔（persona catalog 於 import 期已載入，見 contract.PERSONA_CATALOG；
    catalog 壞掉時退空，對任何 role 皆 fail-closed raise）。
    未知 role → ValueError（由 render_contract_prompt 冒泡）。
    以 shlex.join 收尾，prompt 為單一 shell token（防 shell 二次解讀）。
    注意：prompt 含換行，**不可**逕經 `tmux send-keys -l` 逐字送（literal newline 會被
    當 Enter 提早提交）；實際 pane transport 屬 Phase B（PaneAllocator）決策，見設計 §4.2 / §8。
    """
    contract_prompt = render.render_contract_prompt(role, catalog)
    prompt = (
        f"{contract_prompt}\n\n"
        f"[TASK] {task}\n"
        f"[PLAN: {plan_path}]\n"
        "請於本 worktree 內讀取上述 plan 並依 persona 契約邊界執行。"
    )
    return shlex.join([*executor, prompt])
