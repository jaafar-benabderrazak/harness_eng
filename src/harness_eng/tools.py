"""Tool definitions shared across harnesses.

Implementations are shared. Harnesses choose *which subset* to expose by name.

Two families of tools:
- HTML-extraction family: read_html, css_select, extract_text, submit_answer (HTML).
- Code-generation family: check_syntax, run_tests, submit_answer (code). The
  submit_answer schema is overloaded — its payload depends on task type.

`ToolContext` now carries the active Task so code-flavoured tools can get at
the test suite. HTML tools ignore the extra fields.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup

from .config import FIXTURES_DIR


@dataclass
class ToolContext:
    html_path: Path = Path("")
    test_code: str = ""
    signature: str = ""
    _html_cache: str | None = None

    def html(self) -> str:
        if self._html_cache is None:
            self._html_cache = (FIXTURES_DIR / self.html_path).read_text(encoding="utf-8")
        return self._html_cache


# --------------------------------------------------------------------------
# HTML-extraction tools
# --------------------------------------------------------------------------

def _tool_read_html(ctx: ToolContext, **_: Any) -> str:
    return ctx.html()


def _tool_css_select(ctx: ToolContext, selector: str, **_: Any) -> str:
    soup = BeautifulSoup(ctx.html(), "lxml")
    matches = soup.select(selector)
    if not matches:
        return "NO_MATCH"
    return "\n---\n".join(m.get_text(" ", strip=True) for m in matches[:10])


def _tool_extract_text(ctx: ToolContext, **_: Any) -> str:
    soup = BeautifulSoup(ctx.html(), "lxml")
    text = soup.get_text(" ", strip=True)
    return text[:4000]


# --------------------------------------------------------------------------
# Code-generation tools
# --------------------------------------------------------------------------

def _tool_check_syntax(ctx: ToolContext, code: str, **_: Any) -> str:
    """Parse Python code with ast. Returns 'OK' or the parse error."""
    try:
        ast.parse(code)
        return "OK: parses cleanly."
    except SyntaxError as e:
        return f"SYNTAX_ERROR at line {e.lineno}: {e.msg}"


def _tool_run_tests(ctx: ToolContext, code: str, **_: Any) -> str:
    """Run the task's pytest suite against submitted code in a tempfile subprocess.
    Returns a short pass/fail summary truncated to keep trace size bounded.
    """
    if not ctx.test_code:
        return "ERROR: no test_code in task context (are you on an HTML task?)."
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "solution.py"
        src.write_text(code, encoding="utf-8")
        tests = Path(td) / "test_solution.py"
        tests.write_text(
            "from solution import *\n" + ctx.test_code,
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", "--no-header", str(tests)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: tests did not complete within 15s."
    out = (proc.stdout + proc.stderr).strip()
    # Trim very long outputs
    if len(out) > 1500:
        out = out[:1500] + "\n...[truncated]"
    status = "PASSED" if proc.returncode == 0 else "FAILED"
    return f"[{status} rc={proc.returncode}]\n{out}"


def _tool_run_python(ctx: ToolContext, code: str, **_: Any) -> str:
    """Execute Python code as a standalone script in a temp subprocess (5s timeout).
    Returns rc + truncated stdout/stderr. Used by program_aided to verify intermediate values."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "snippet.py"
        src.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(src)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: snippet did not complete within 5s."
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 1500:
        out = out[:1500] + "\n...[truncated]"
    return f"[rc={proc.returncode}]\n{out}"


SUBMIT_ANSWER_TOOL = "submit_answer"


TOOL_IMPLS: dict[str, Callable[..., str]] = {
    "read_html": _tool_read_html,
    "css_select": _tool_css_select,
    "extract_text": _tool_extract_text,
    "check_syntax": _tool_check_syntax,
    "run_tests": _tool_run_tests,
    "run_python": _tool_run_python,
}


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_html": {
        "name": "read_html",
        "description": "Return the full raw HTML for the current task. Use sparingly; it is long.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "css_select": {
        "name": "css_select",
        "description": "Run a CSS selector against the page and return the text of up to 10 matches, '---'-separated. Returns 'NO_MATCH' if nothing matches.",
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
        },
    },
    "extract_text": {
        "name": "extract_text",
        "description": "Return the visible text of the page, truncated to 4000 chars.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "check_syntax": {
        "name": "check_syntax",
        "description": "Parse a Python source string. Returns 'OK' if it parses, else the SyntaxError message.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    "run_tests": {
        "name": "run_tests",
        "description": "Run the task's pytest suite against your candidate Python code. Returns a short pass/fail summary.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    "run_python": {
        "name": "run_python",
        "description": "Execute Python code as a standalone script in a temp subprocess (5s timeout). Returns rc + truncated stdout/stderr. Use to verify intermediate values during reasoning.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    "submit_answer": {
        "name": "submit_answer",
        "description": "Submit the final answer and end the task. For HTML tasks pass `fields` (field -> value dict). For code tasks pass `code` (the Python source as a string).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "HTML tasks: field name -> extracted string.",
                    "additionalProperties": {"type": "string"},
                },
                "code": {
                    "type": "string",
                    "description": "Code tasks: full Python source implementing the required function.",
                },
            },
        },
    },
}


def build_tool_list(names: list[str]) -> list[dict[str, Any]]:
    """Build the Anthropic `tools` list from a subset of tool names."""
    return [TOOL_SCHEMAS[n] for n in names]


def dispatch(name: str, ctx: ToolContext, **args: Any) -> str:
    if name not in TOOL_IMPLS:
        return f"ERROR: unknown tool {name}"
    try:
        return TOOL_IMPLS[name](ctx, **args)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
