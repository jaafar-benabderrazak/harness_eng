"""Harness: chain-of-thought for code-gen.

A single model call with a prompt that asks the model to reason step-by-step
in text before writing and submitting the code. No tool loops, no retries —
the difference from `single_shot` is purely the prompting.
"""
from __future__ import annotations

from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

COT_TOOLS = ["submit_answer"]


class ChainOfThoughtHarness(Harness):
    name = "chain_of_thought"
    TOOL_WHITELIST = frozenset({"submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nWrite a Python implementation for the given task. BEFORE writing "
            "code, explain your approach as a numbered list (max 4 steps). Then "
            "write the implementation. Then call submit_answer with the complete "
            "Python source in the `code` argument. A single model turn; do not "
            "call any other tools."
        )
        user = (
            f"TASK: {task.description}\n"
            f"SIGNATURE: {task.signature}\n"
            "Work through steps 1-4, then submit."
        )
        tools = build_tool_list(COT_TOOLS)
        mc = self._step_model(system, [{"role": "user", "content": user}], tools, tracer, usage)
        for block in self._tool_uses(mc.content):
            if block["name"] == "submit_answer":
                inp = block.get("input", {}) or {}
                code = inp.get("code", "")
                return {"code": code}, "submitted"
        return None, "no_submit"
