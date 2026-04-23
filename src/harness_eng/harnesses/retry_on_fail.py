"""Harness: retry-on-fail for code-gen.

Attempt 1: single_shot-style submission. Runs the grader via run_tests.
If the tests pass, done. If they fail, show the test output to the model
and ask for a revised submission. Up to 3 attempts total.

Simpler than reflexion: no separate critique call — the test output IS the
feedback. More faithful to how real developers iterate against failing tests.
"""
from __future__ import annotations

from typing import Any

from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list, dispatch
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

ROF_TOOLS = ["submit_answer"]
MAX_ATTEMPTS = 3


class RetryOnFailHarness(Harness):
    name = "retry_on_fail"
    TOOL_WHITELIST = frozenset({"submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nImplement a Python function. Submit your best attempt via "
            "submit_answer. If your tests fail, you will be shown the failure "
            "and given a chance to revise. Focus on correctness."
        )
        user_prompt = (
            f"TASK: {task.description}\n"
            f"SIGNATURE: {task.signature}\n"
            "Write the implementation and call submit_answer."
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        tools = build_tool_list(ROF_TOOLS)

        last_code: str | None = None
        last_reason = "no_submit"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            tracer.log("attempt_start", attempt=attempt)
            mc = self._step_model(system, messages, tools, tracer, usage)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            submitted = next((tu for tu in tool_uses if tu["name"] == "submit_answer"), None)
            if not submitted:
                return (({"code": last_code} if last_code else None), "no_submit")
            args = submitted.get("input", {}) or {}
            code = args.get("code", "")
            last_code = code
            last_reason = "submitted"

            if attempt == MAX_ATTEMPTS:
                return {"code": code}, "submitted"

            # Run the tests as a 'tool' so the model sees the actual failure text.
            test_result = dispatch("run_tests", ctx, code=code)
            tracer.log("attempt_test_result", attempt=attempt, output_len=len(test_result))
            if test_result.startswith("[PASSED"):
                return {"code": code}, "submitted"
            # Feed the failure back and ask for a revision.
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": submitted["id"], "content": test_result},
                        {"type": "text", "text": "The tests failed. Read the output and call submit_answer with a fixed implementation."},
                    ],
                }
            )
        return {"code": last_code} if last_code else None, last_reason
