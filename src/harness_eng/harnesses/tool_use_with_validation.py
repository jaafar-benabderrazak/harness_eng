"""Harness: tool_use_with_validation.

ReAct-shape loop. Before dispatching ANY non-submit tool call, validates the
args dict against TOOL_SCHEMAS[name]['input_schema'] using jsonschema. On
ValidationError, instead of dispatching, returns a structured error tool_result
back to the model and increments a per-call retry counter (max 3). After 3
validation failures on the same logical call site, fails the cell with
stop_reason='schema_validation_exhausted'.

Reference: Pydantic-style validation pattern, but using jsonschema directly
(per CONTEXT decision #6: schemas already exist as dicts in tools.py).
"""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import TOOL_SCHEMAS, ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

# Pre-build validators once at import time — schemas are static.
_VALIDATORS: dict[str, Draft202012Validator] = {
    name: Draft202012Validator(schema["input_schema"])
    for name, schema in TOOL_SCHEMAS.items()
}

MAX_VALIDATION_RETRIES = 3

EXEC_TOOLS_HTML = ["read_html", "css_select", "extract_text", "submit_answer"]
EXEC_TOOLS_CODE = ["check_syntax", "run_tests", "submit_answer"]


def _validate_args(tool_name: str, args: dict) -> str | None:
    """Returns None on valid, structured error string on invalid."""
    v = _VALIDATORS.get(tool_name)
    if v is None:
        return None  # unknown tool — let dispatch produce its own error
    try:
        v.validate(args)
        return None
    except ValidationError as e:
        return (
            f"SCHEMA_VIOLATION in {tool_name}: {e.message} "
            f"(path={list(e.absolute_path)}, "
            f"schema_required={e.schema.get('required', [])}, "
            f"schema_properties={list(e.schema.get('properties', {}).keys())})"
        )


class ToolUseWithValidationHarness(Harness):
    name = "tool_use_with_validation"
    # UNION across HTML + code-gen needs. Per-task subset enforced via build_tool_list.
    TOOL_WHITELIST = frozenset({
        "read_html", "css_select", "extract_text",
        "check_syntax", "run_tests",
        "submit_answer",
    })

    def _execute(self, task: Task, ctx: ToolContext, tracer: Tracer, usage: _Usage) -> tuple[dict[str, str] | None, str]:
        if task.type == "code_gen":
            tool_names = EXEC_TOOLS_CODE
        else:
            tool_names = EXEC_TOOLS_HTML
        system = (
            BASE_ROLE
            + "\n\nEvery tool call's arguments will be JSON-schema-validated before dispatch. "
            "If validation fails you will receive a structured error and may retry. After 3 "
            "validation failures the task fails. Read each tool's schema carefully."
        )
        tools = build_tool_list(tool_names)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)},
        ]
        validation_failures = 0
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
                # Validate (skip submit_answer — it's the universal output channel; loose schema)
                if name != "submit_answer":
                    err = _validate_args(name, args)
                    if err is not None:
                        validation_failures += 1
                        tracer.log("schema_validation_fail",
                                   tool=name, args=args, error=err, n_failures=validation_failures)
                        if validation_failures >= MAX_VALIDATION_RETRIES:
                            return None, "schema_validation_exhausted"
                        # Return structured error tool_result; model gets to retry
                        tool_results.append({
                            "type": "tool_result", "tool_use_id": tu["id"],
                            "content": err,
                        })
                        continue
                    tracer.log("schema_validation_pass", tool=name)
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
