"""Harness: multi_agent.

Three roles (planner, executor, critic), three distinct system prompts, three
ISOLATED message histories. Handoffs between roles are explicit string copies
of structured Handoff dicts — no shared state. Per CONTEXT decision #1.

Faithful to CrewAI/AutoGen semantics. ~3x token cost of single-log harnesses
(documented as a weakness in the article).
"""
from __future__ import annotations

from typing import Any, TypedDict

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

PLANNER_SYSTEM = BASE_ROLE + (
    "\n\nYou are the PLANNER. Produce a numbered list of investigation steps the executor will follow. "
    "You will NOT execute them yourself — no tools available. End with 'HANDOFF: <one-line summary>'."
)
EXECUTOR_SYSTEM_HTML = BASE_ROLE + (
    "\n\nYou are the EXECUTOR. Follow the planner's checklist using tools, then call submit_answer. "
    "Read the handoff carefully — the planner has done the strategy work."
)
EXECUTOR_SYSTEM_CODE = BASE_ROLE + (
    "\n\nYou are the EXECUTOR. Follow the planner's checklist. Use check_syntax / run_tests if helpful, "
    "then call submit_answer with the final code."
)
CRITIC_SYSTEM = BASE_ROLE + (
    "\n\nYou are the CRITIC. Read the executor's submitted result. If it satisfies the task, respond exactly 'OK'. "
    "If not, respond with a brief critique starting with 'CRITIQUE:' followed by specific corrections."
)

EXECUTOR_TOOLS_HTML = ["read_html", "css_select", "extract_text", "submit_answer"]
EXECUTOR_TOOLS_CODE = ["check_syntax", "run_tests", "submit_answer"]


class Handoff(TypedDict):
    from_role: str
    to_role: str
    summary: str
    artifacts: dict[str, Any]


def _render_handoff(h: Handoff) -> str:
    arts = "\n".join(f"- {k}: {v}" for k, v in h["artifacts"].items()) or "(none)"
    return (
        f"## Handoff from {h['from_role']} to {h['to_role']}\n"
        f"{h['summary']}\n\nArtifacts:\n{arts}"
    )


class MultiAgentHarness(Harness):
    name = "multi_agent"
    # UNION across HTML + code-gen executor needs. Per-task-type subset is enforced
    # internally via the build_tool_list calls; _step_model's subset check still passes.
    TOOL_WHITELIST = frozenset({
        "read_html", "css_select", "extract_text",
        "check_syntax", "run_tests",
        "submit_answer",
    })

    def _execute(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        # Stage 1: PLANNER (no tools, isolated history)
        planner_messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)}
        ]
        plan_mc = self._step_model(PLANNER_SYSTEM, planner_messages, None, tracer, usage)
        plan_text = self._text_of(plan_mc.content)
        tracer.log("multi_agent_plan", text_len=len(plan_text))

        handoff_p2e: Handoff = {
            "from_role": "planner",
            "to_role": "executor",
            "summary": "Plan produced by planner.",
            "artifacts": {"plan": plan_text},
        }

        # Stage 2: EXECUTOR (own messages list, ReAct-shape loop)
        if task.type == "code_gen":
            exec_system = EXECUTOR_SYSTEM_CODE
            exec_tools_names = EXECUTOR_TOOLS_CODE
        else:
            exec_system = EXECUTOR_SYSTEM_HTML
            exec_tools_names = EXECUTOR_TOOLS_HTML
        exec_tools = build_tool_list(exec_tools_names)

        executor_messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": self._task_prompt(task) + "\n\n" + _render_handoff(handoff_p2e),
            },
        ]
        executor_predicted, executor_stop = self._run_executor_loop(
            exec_system, executor_messages, exec_tools, ctx, tracer, usage,
        )
        if executor_predicted is None:
            return None, executor_stop

        # Stage 3: CRITIC (no tools, isolated history)
        critic_input = (
            self._task_prompt(task)
            + f"\n\nExecutor submitted:\n{executor_predicted}\n\nIs this correct?"
        )
        critic_messages: list[dict[str, Any]] = [
            {"role": "user", "content": critic_input}
        ]
        critic_mc = self._step_model(CRITIC_SYSTEM, critic_messages, None, tracer, usage)
        critic_text = self._text_of(critic_mc.content).strip()
        tracer.log("multi_agent_critique", text=critic_text[:200])

        if critic_text.startswith("OK") or "OK" == critic_text:
            return executor_predicted, "submitted"

        # ONE retry with critique appended to executor's messages — bounded cost.
        retry_messages = list(executor_messages) + [
            {
                "role": "user",
                "content": f"Critic feedback: {critic_text}\n\nRevise and submit again.",
            }
        ]
        retry_predicted, retry_stop = self._run_executor_loop(
            exec_system, retry_messages, exec_tools, ctx, tracer, usage,
        )
        if retry_predicted is not None:
            return retry_predicted, "submitted"
        return executor_predicted, "submitted"

    def _run_executor_loop(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        max_turns = CONFIG.react_max_turns
        for _ in range(max_turns):
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
