"""Harness 4: Reflexion-style retry.

First attempt runs as ReAct. On failure (per-field grader), the model is shown
its own trace and asked to critique it, then given one retry with the critique
prepended. Retry tokens are accumulated in the same usage counter as the first
attempt so total cost is honest.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import CONFIG
from ..grader import grade
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage
from .react import REACT_TOOLS


class ReflexionHarness(Harness):
    name = "reflexion"
    TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        first_pred, first_reason, first_trace_text = self._attempt(
            task, ctx, tracer, usage, critique=None, attempt_tag="attempt_1"
        )
        first_grade = grade(first_pred, task.expected)
        tracer.log("reflexion_first_grade", success=first_grade.success, per_field=first_grade.per_field)
        if first_grade.success:
            return first_pred, "submitted"

        if CONFIG.reflexion_max_retries <= 0:
            return first_pred, first_reason

        critique = self._critique(task, first_pred, first_trace_text, tracer, usage)
        tracer.log("reflexion_critique", critique=critique)

        second_pred, second_reason, _ = self._attempt(
            task, ctx, tracer, usage, critique=critique, attempt_tag="attempt_2"
        )
        return second_pred, second_reason

    def _attempt(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
        critique: str | None,
        attempt_tag: str,
    ) -> tuple[dict[str, str] | None, str, str]:
        system = BASE_ROLE + "\n\nInvestigate with css_select; submit via submit_answer."
        if critique:
            system += "\n\nYour previous attempt failed. Critique of that attempt:\n" + critique
        tools = build_tool_list(REACT_TOOLS)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)},
        ]
        tracer.log("attempt_start", tag=attempt_tag)
        trace_text = ""
        for _ in range(CONFIG.react_max_turns):
            mc = self._step_model(system, messages, tools, tracer, usage)
            trace_text += "\n" + self._text_of(mc.content)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            if not tool_uses:
                return None, "no_submit", trace_text
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                name = tu["name"]
                args = tu.get("input", {}) or {}
                if name == "submit_answer":
                    fields = args.get("fields", {})
                    return {k: str(v) for k, v in fields.items()}, "submitted", trace_text
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                trace_text += f"\n[{name}({json.dumps(args)})] -> {out[:200]}"
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap", trace_text

    def _critique(
        self,
        task: Task,
        predicted: dict[str, str] | None,
        trace_text: str,
        tracer: Tracer,
        usage: _Usage,
    ) -> str:
        system = (
            BASE_ROLE
            + "\n\nYou are reviewing your own failed attempt. Produce a short "
            "critique (max 6 bullets) naming the concrete mistakes and the "
            "selector or reasoning that would have worked. No preamble."
        )
        user = (
            "TASK: " + task.description + "\n"
            "FIELDS: " + ", ".join(task.fields) + "\n"
            "YOUR PREDICTED FIELDS (wrong): " + json.dumps(predicted or {}) + "\n\n"
            "YOUR TRACE (may be truncated):\n" + trace_text[-3000:]
        )
        mc = self._step_model(system, [{"role": "user", "content": user}], None, tracer, usage)
        return self._text_of(mc.content)
