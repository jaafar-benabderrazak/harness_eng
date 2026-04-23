"""Harness 5: tool-curated minimal.

Smaller tool surface (css_select + submit_answer only — no read_html,
no extract_text). Prunes the message history every N turns, keeping only
the system prompt, the initial task, and a short rolling summary of
findings so far.
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

MINIMAL_TOOLS = ["css_select", "submit_answer"]


class MinimalHarness(Harness):
    name = "minimal"
    TOOL_WHITELIST = frozenset({"css_select", "submit_answer"})

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        system = (
            BASE_ROLE
            + "\n\nYou have ONE investigation tool: css_select. You cannot read "
            "the raw HTML. Use targeted selectors. Submit via submit_answer."
        )
        tools = build_tool_list(MINIMAL_TOOLS)
        initial_user: dict[str, Any] = {"role": "user", "content": self._task_prompt(task)}
        messages: list[dict[str, Any]] = [initial_user]
        findings: list[str] = []

        for turn in range(CONFIG.minimal_max_turns):
            if turn > 0 and turn % CONFIG.minimal_prune_every == 0:
                summary = self._summarize(findings, tracer, usage)
                messages = [
                    initial_user,
                    {
                        "role": "user",
                        "content": "Findings so far (pruned history):\n" + summary,
                    },
                ]
                tracer.log("prune", turn=turn, findings_count=len(findings))
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
                findings.append(f"{name}({args}) -> {out[:120]}")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap"

    def _summarize(self, findings: list[str], tracer: Tracer, usage: _Usage) -> str:
        if not findings:
            return "(none)"
        # Cheap local summary: last 10 findings joined. We do NOT call the
        # model here because calling the model for a summary is another token
        # cost that would muddle the comparison. The point of the minimal
        # harness is cheap pruning, not another model call.
        return "\n".join(findings[-10:])
