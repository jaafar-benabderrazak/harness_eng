"""Harness 1: single-shot baseline.

Stuff the whole HTML and the task into one prompt. Force the submit_answer
tool as the output channel, but no loop — one call, one answer.
"""
from __future__ import annotations

import json
from typing import Any

from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage


class SingleShotHarness(Harness):
    name = "single_shot"
    TOOL_WHITELIST = frozenset({"submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        html = ctx.html()
        user = (
            self._task_prompt(task)
            + "\n\nHere is the full HTML of the page:\n\n"
            + "```html\n"
            + html
            + "\n```\n"
            + "Call submit_answer now. Do not call any other tools."
        )
        tools = build_tool_list(["submit_answer"])
        mc = self._step_model(BASE_ROLE, [{"role": "user", "content": user}], tools, tracer, usage)
        for block in self._tool_uses(mc.content):
            if block["name"] == "submit_answer":
                fields = block.get("input", {}).get("fields", {})
                return {k: str(v) for k, v in fields.items()}, "submitted"
        # Model didn't call submit_answer. Try to parse JSON from text as a fallback.
        text = self._text_of(mc.content)
        parsed = _try_parse_json(text)
        if parsed is not None:
            return parsed, "submitted_via_text"
        return None, "no_submit"


def _try_parse_json(text: str) -> dict[str, str] | None:
    text = text.strip()
    # naive fenced-code strip
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    try:
        obj: Any = json.loads(text)
    except Exception:
        return None
    if isinstance(obj, dict):
        return {k: str(v) for k, v in obj.items()}
    return None
