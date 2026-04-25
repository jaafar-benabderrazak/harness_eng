"""Harness: react_with_replan.

Standard ReAct loop, but tracks the last css_select args. After two consecutive
NO_MATCH calls on the same selector, injects a one-shot 'replan' user message
into the message stream before the next model call. Detection logic per CONTEXT
decision #3.
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

REPLAN_TOOLS = ["read_html", "css_select", "extract_text", "submit_answer"]


class ReActWithReplanHarness(Harness):
    name = "react_with_replan"
    TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})

    def _execute(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nYou have tools to inspect the page. Investigate, then call submit_answer. "
            "If your selector returns NO_MATCH twice in a row, you will be prompted to revise your plan."
        )
        tools = build_tool_list(REPLAN_TOOLS)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)},
        ]
        last_selector: str | None = None
        last_was_nomatch: bool = False
        max_turns = CONFIG.react_max_turns
        for _ in range(max_turns):
            mc = self._step_model(system, messages, tools, tracer, usage)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            if not tool_uses:
                return None, "no_submit"
            tool_results: list[dict[str, Any]] = []
            replan_now = False
            for tu in tool_uses:
                name = tu["name"]
                args = tu.get("input", {}) or {}
                if name == "submit_answer":
                    if "code" in args:
                        return {"code": args["code"]}, "submitted"
                    fields = args.get("fields", {})
                    return {k: str(v) for k, v in fields.items()}, "submitted"
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                if name == "css_select":
                    sel = args.get("selector", "")
                    if (
                        sel == last_selector
                        and last_was_nomatch
                        and out == "NO_MATCH"
                    ):
                        replan_now = True
                        tracer.log("replan_triggered", selector=sel)
                    last_selector = sel
                    last_was_nomatch = (out == "NO_MATCH")
                else:
                    last_selector = None
                    last_was_nomatch = False
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
            if replan_now:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You called the same selector twice with NO_MATCH. "
                            "Stop, write a brief revised plan in one short paragraph, "
                            "then continue with a different selector."
                        ),
                    }
                )
        return None, "turn_cap"
