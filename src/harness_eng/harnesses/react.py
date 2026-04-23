"""Harness 2: ReAct loop.

The model calls tools; the harness appends tool_result blocks and loops until
submit_answer or the turn cap. No planning step.
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

REACT_TOOLS = ["read_html", "css_select", "extract_text", "submit_answer"]


class ReActHarness(Harness):
    name = "react"
    TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nYou have tools to inspect the page: read_html (whole page, verbose), "
            "css_select (targeted, preferred), extract_text (visible text only). "
            "Investigate the page, then call submit_answer. Prefer css_select over read_html."
        )
        tools = build_tool_list(REACT_TOOLS)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)},
        ]
        max_turns = CONFIG.react_max_turns
        for _ in range(max_turns):
            mc = self._step_model(system, messages, tools, tracer, usage)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            if not tool_uses:
                # Model ended without calling a tool. Nudge once.
                return None, "no_submit"
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                name = tu["name"]
                args = tu.get("input", {}) or {}
                if name == "submit_answer":
                    if "code" in args:
                        return {"code": args["code"]}, "submitted"
                    fields = args.get("fields", {})
                    return {k: str(v) for k, v in fields.items()}, "submitted"
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap"
