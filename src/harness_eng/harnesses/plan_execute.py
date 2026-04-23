"""Harness 3: plan-then-execute.

A planner call produces a numbered checklist of CSS selectors + the field each
will fill. An executor call then runs the plan, calling tools in sequence and
submitting at the end. The planner never sees the HTML; it sees only the
task description. (This is deliberate — exposes "plan is wrong from step one".)
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

EXEC_TOOLS = ["css_select", "extract_text", "submit_answer"]


class PlanExecuteHarness(Harness):
    name = "plan_execute"
    TOOL_WHITELIST = frozenset({"css_select", "extract_text", "submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        plan = self._plan(task, tracer, usage)
        tracer.log("plan", plan=plan)
        return self._execute_plan(task, plan, ctx, tracer, usage)

    def _plan(self, task: Task, tracer: Tracer, usage: _Usage) -> str:
        planner_system = (
            BASE_ROLE
            + "\n\nYou are the PLANNER. You cannot see the HTML. Produce a numbered "
            "checklist (max "
            + str(CONFIG.plan_max_steps)
            + " steps) of investigation steps the executor should take. Each step "
            "should name one field and suggest a CSS selector to try. Write the "
            "plan as plain text."
        )
        user = (
            f"TASK: {task.description}\n"
            f"FIELDS: {', '.join(task.fields)}\n"
            "Write the plan now. Do not solve; just plan."
        )
        mc = self._step_model(planner_system, [{"role": "user", "content": user}], None, tracer, usage)
        return self._text_of(mc.content)

    def _execute_plan(
        self,
        task: Task,
        plan: str,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nYou are the EXECUTOR. Follow the plan; if a step fails, adapt. "
            "You have css_select, extract_text, submit_answer. End by calling submit_answer."
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    self._task_prompt(task)
                    + "\n\nPLAN (from planner):\n"
                    + plan
                    + "\n\nExecute the plan now."
                ),
            }
        ]
        tools = build_tool_list(EXEC_TOOLS)
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
                    fields = args.get("fields", {})
                    return {k: str(v) for k, v in fields.items()}, "submitted"
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap"
