"""Harness base class. Centralizes trace + token accounting.

Subclasses override `_execute(task, ctx)` and return a dict of extracted fields
(or None on failure). Everything else — timing, token counting, tracing — is
done here so no harness can accidentally miss it.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..model import ModelCall, call as model_call
from ..tasks.loader import Task
from ..tools import ToolContext, dispatch
from ..trace import Tracer

BASE_ROLE = (
    "You are an information extraction agent. Given an HTML page, you must "
    "return a JSON object containing the requested fields exactly as they "
    "appear on the page. Fields are normalized by lowercase + whitespace "
    "collapse before grading. Numeric fields must be digits only (no $, no "
    "commas). Extract only from the MAIN subject of the page — ignore "
    "sidebars, related items, and 'similar' recommendations."
)


@dataclass
class HarnessResult:
    task_id: str
    harness: str
    run_id: str
    predicted: dict[str, str] | None
    input_tokens: int
    output_tokens: int
    tool_calls: int
    wall_clock_s: float
    turns: int
    stop_reason: str  # "submitted", "turn_cap", "error", "no_submit"
    error: str | None = None


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    turns: int = 0

    def record(self, mc: ModelCall) -> None:
        self.input_tokens += mc.input_tokens
        self.output_tokens += mc.output_tokens
        self.turns += 1


class ToolAllowlistViolation(RuntimeError):
    """Raised when a harness passes a tool outside its declared TOOL_WHITELIST."""


class Harness(ABC):
    name: str = "abstract"
    TOOL_WHITELIST: frozenset[str] = frozenset()

    def __init__(self) -> None:
        pass

    @abstractmethod
    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        """Run the harness. Return (predicted_fields, stop_reason)."""

    def run(self, task: Task, run_id: str | None = None) -> HarnessResult:
        run_id = run_id or uuid.uuid4().hex[:8]
        ctx = ToolContext(html_path=task.html_path)  # type: ignore[arg-type]
        usage = _Usage()
        t0 = time.perf_counter()
        predicted: dict[str, str] | None = None
        stop_reason = "error"
        error: str | None = None

        with Tracer(self.name, task.id, run_id) as tracer:
            tracer.log(
                "run_start",
                harness=self.name,
                task_id=task.id,
                fields=task.fields,
                html_path=str(task.html_path),
            )
            try:
                predicted, stop_reason = self._execute(task, ctx, tracer, usage)
            except Exception as e:  # noqa: BLE001 — surface to trace
                error = f"{type(e).__name__}: {e}"
                tracer.log("run_error", error=error)
                stop_reason = "error"

            wall_s = time.perf_counter() - t0
            tracer.log(
                "run_end",
                predicted=predicted,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                tool_calls=usage.tool_calls,
                turns=usage.turns,
                stop_reason=stop_reason,
                wall_clock_s=wall_s,
            )

        return HarnessResult(
            task_id=task.id,
            harness=self.name,
            run_id=run_id,
            predicted=predicted,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            tool_calls=usage.tool_calls,
            wall_clock_s=wall_s,
            turns=usage.turns,
            stop_reason=stop_reason,
            error=error,
        )

    # ------------------------------------------------------------------
    # Helpers shared by subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _task_prompt(task: Task) -> str:
        return (
            f"TASK: {task.description}\n"
            f"REQUIRED FIELDS: {', '.join(task.fields)}\n"
            "Return the answer via the submit_answer tool. The 'fields' argument "
            "must contain exactly the keys listed above."
        )

    @staticmethod
    def _text_of(content: list[dict[str, Any]]) -> str:
        return "".join(b.get("text", "") for b in content if b.get("type") == "text")

    @staticmethod
    def _tool_uses(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [b for b in content if b.get("type") == "tool_use"]

    def _step_model(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tracer: Tracer,
        usage: _Usage,
    ) -> ModelCall:
        if tools:
            passed = {t["name"] for t in tools}
            extra = passed - self.TOOL_WHITELIST
            if extra:
                raise ToolAllowlistViolation(
                    f"Harness '{self.name}' passed tools outside its whitelist: "
                    f"{sorted(extra)}. Whitelist is {sorted(self.TOOL_WHITELIST)}."
                )
            tracer.log("tool_payload", names=sorted(passed))
        tracer.log("model_call", system_len=len(system), n_messages=len(messages))
        mc = model_call(system, messages, tools)
        usage.record(mc)
        tracer.log(
            "model_response",
            input_tokens=mc.input_tokens,
            output_tokens=mc.output_tokens,
            usage=mc.usage_raw,
            latency_s=mc.latency_s,
            stop_reason=mc.stop_reason,
            content=mc.content,
        )
        return mc

    def _dispatch_tool(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
        tracer: Tracer,
        usage: _Usage,
    ) -> str:
        tracer.log("tool_call", name=name, args=args)
        usage.tool_calls += 1
        out = dispatch(name, ctx, **args)
        tracer.log("tool_result", name=name, output_len=len(out))
        return out
