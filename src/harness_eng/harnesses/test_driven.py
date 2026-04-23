"""Harness: test-driven code generation.

The model gets three tools: check_syntax, run_tests, submit_answer.
Loop: write a candidate, check_syntax, run_tests, read failures, revise.
When tests pass, submit_answer. Turn cap shared with ReAct's.
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

TD_TOOLS = ["check_syntax", "run_tests", "submit_answer"]


class TestDrivenHarness(Harness):
    name = "test_driven"
    TOOL_WHITELIST = frozenset({"check_syntax", "run_tests", "submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nYou are implementing a Python function. You have three tools: "
            "check_syntax (parse-check a candidate), run_tests (run the pytest "
            "suite against a candidate — returns pass/fail output), submit_answer "
            "(final submission, ends the task). Workflow: write a candidate, "
            "check_syntax to catch typos, run_tests to see if it passes, read "
            "the failures and revise, repeat until tests pass, then submit_answer."
        )
        user = (
            f"TASK: {task.description}\n"
            f"SIGNATURE: {task.signature}\n"
            "Iterate with run_tests until all tests pass, then submit."
        )
        tools = build_tool_list(TD_TOOLS)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        for _ in range(CONFIG.react_max_turns):
            mc = self._step_model(system, messages, tools, tracer, usage)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            if not tool_uses:
                return None, "no_submit"
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                name = tu["name"]
                args = tu.get("input", {}) or {}
                if name == "submit_answer":
                    code = args.get("code", "")
                    return {"code": code}, "submitted"
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap"
