"""Harness: self_consistency.

Wraps single_shot. Samples N=5 at temperature=0.7. Vote per CONTEXT decision #4:
- HTML extraction: per-field majority across samples (resilient to one bad field)
- Code generation: majority over ast.unparse-normalized code string (winner is raw)

Critical: requires per-call temperature override (Wave-1 _step_model kwarg).
Without temperature > 0, all 5 samples are bit-identical — see Pitfall 4.
"""
from __future__ import annotations

import ast
from collections import Counter

from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

N_SAMPLES = 5
SAMPLE_TEMPERATURE = 0.7  # Wang et al. 2022 setting; pre-registered in article.


def _normalize_code(code: str) -> str:
    """Strip comments + collapse whitespace via AST round-trip. Falls back to raw on parse error."""
    try:
        tree = ast.parse(code)
        return ast.unparse(tree)
    except SyntaxError:
        return code


class SelfConsistencyHarness(Harness):
    name = "self_consistency"
    TOOL_WHITELIST = frozenset({"submit_answer"})

    def _execute(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        if task.type == "code_gen":
            return self._execute_code(task, ctx, tracer, usage)
        return self._execute_html(task, ctx, tracer, usage)

    def _execute_html(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        html = ctx.html()
        user = (
            self._task_prompt(task)
            + "\n\nHere is the full HTML of the page:\n\n```html\n"
            + html
            + "\n```\nCall submit_answer now. Do not call any other tools."
        )
        tools = build_tool_list(["submit_answer"])
        samples: list[dict[str, str]] = []
        for i in range(N_SAMPLES):
            mc = self._step_model(
                BASE_ROLE,
                [{"role": "user", "content": user}],
                tools,
                tracer,
                usage,
                temperature=SAMPLE_TEMPERATURE,
            )
            pred = self._extract_submit_html(mc)
            tracer.log("self_consistency_sample", i=i, predicted=pred)
            if pred is not None:
                samples.append(pred)
        if not samples:
            return None, "no_submit"
        # Per-field majority — independent vote per field per CONTEXT decision #4
        final: dict[str, str] = {}
        for f in task.fields:
            values = [s.get(f, "") for s in samples]
            majority, _count = Counter(values).most_common(1)[0]
            final[f] = majority
        tracer.log("self_consistency_vote", n_samples=len(samples), final=final)
        return final, "submitted"

    def _execute_code(
        self,
        task: Task,
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> tuple[dict[str, str] | None, str]:
        user = (
            self._task_prompt(task)
            + f"\n\nFunction signature:\n```python\n{task.signature}\n```\n"
            "Call submit_answer with the full Python source in the `code` argument."
        )
        tools = build_tool_list(["submit_answer"])
        samples: list[str] = []  # raw code strings
        for i in range(N_SAMPLES):
            mc = self._step_model(
                BASE_ROLE,
                [{"role": "user", "content": user}],
                tools,
                tracer,
                usage,
                temperature=SAMPLE_TEMPERATURE,
            )
            code = self._extract_submit_code(mc)
            tracer.log("self_consistency_sample", i=i, code_len=len(code) if code else 0)
            if code:
                samples.append(code)
        if not samples:
            return None, "no_submit"
        # Majority over ast-normalized form; return WINNING raw code (preserves model's actual submission)
        normalized = [_normalize_code(s) for s in samples]
        win_norm, _ = Counter(normalized).most_common(1)[0]
        # Return the first raw sample whose normalized form matches the winner
        for raw, norm in zip(samples, normalized):
            if norm == win_norm:
                tracer.log(
                    "self_consistency_vote",
                    n_samples=len(samples),
                    winner_normalized_len=len(win_norm),
                )
                return {"code": raw}, "submitted"
        return {"code": samples[0]}, "submitted"  # unreachable in practice

    @staticmethod
    def _extract_submit_html(mc) -> dict[str, str] | None:
        for block in mc.content:
            if block.get("type") == "tool_use" and block.get("name") == "submit_answer":
                inp = block.get("input", {}) or {}
                fields = inp.get("fields", {})
                return {k: str(v) for k, v in fields.items()}
        return None

    @staticmethod
    def _extract_submit_code(mc) -> str | None:
        for block in mc.content:
            if block.get("type") == "tool_use" and block.get("name") == "submit_answer":
                inp = block.get("input", {}) or {}
                if "code" in inp:
                    return inp["code"]
        return None
