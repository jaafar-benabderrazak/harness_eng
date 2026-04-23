"""Deterministic graders — two paths.

- html_extract: normalized exact match per field (NFC + casefold + ws-collapse).
- code_gen: run the task's pytest suite against submitted Python source.
  Success := pytest exit 0. field_accuracy := fraction of test functions passed.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GraderResult:
    per_field: dict[str, bool]
    field_accuracy: float
    success: bool  # all fields correct / all tests pass


_ASCII_WS = re.compile(r"[ \t\n\r\f\v]+")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.strip()
    s = s.casefold()
    s = _ASCII_WS.sub(" ", s)
    return s


def grade(predicted: dict[str, str] | None, expected: dict[str, str]) -> GraderResult:
    predicted = predicted or {}
    per_field: dict[str, bool] = {}
    for key, expected_val in expected.items():
        got = predicted.get(key, "")
        per_field[key] = _norm(str(got)) == _norm(str(expected_val))
    correct = sum(per_field.values())
    total = max(len(per_field), 1)
    return GraderResult(
        per_field=per_field,
        field_accuracy=correct / total,
        success=all(per_field.values()),
    )


def grade_code(submitted_code: str | None, test_code: str) -> GraderResult:
    """Code-gen grader: run pytest against (submission ++ test_code) in a tmpdir.

    per_field maps test function name -> pass/fail (from pytest -v output).
    field_accuracy = fraction of tests passed. Success = pytest exit 0.
    """
    if not submitted_code or not submitted_code.strip():
        return GraderResult(per_field={}, field_accuracy=0.0, success=False)

    test_names = re.findall(r"^def (test_[\w]+)", test_code, flags=re.M)

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "solution.py").write_text(submitted_code, encoding="utf-8")
        (Path(td) / "test_solution.py").write_text(
            "from solution import *\n" + test_code, encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=no", "--no-header",
                 str(Path(td) / "test_solution.py")],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            return GraderResult(
                per_field={n: False for n in test_names},
                field_accuracy=0.0,
                success=False,
            )

    output = proc.stdout + proc.stderr
    per_field: dict[str, bool] = {}
    for name in test_names:
        m = re.search(rf"::{re.escape(name)}\s+(PASSED|FAILED|ERROR)", output)
        per_field[name] = m is not None and m.group(1) == "PASSED"
    if not per_field:
        per_field = {"tests": proc.returncode == 0}
    correct = sum(per_field.values())
    total = max(len(per_field), 1)
    return GraderResult(
        per_field=per_field,
        field_accuracy=correct / total,
        success=proc.returncode == 0,
    )
