"""Task loader. Tasks come in two flavors: html_extract (the original) and
code_gen (Python function implementations graded by pytest).

Old-style HTML tasks keep their existing shape; code tasks carry a distinct
payload. Consumers branch on `Task.type`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import TASKS_DIR, TASKS_FILE

CODE_TASKS_FILE = TASKS_DIR / "tasks_code.jsonl"


@dataclass(frozen=True)
class Task:
    id: str
    description: str
    type: str = "html_extract"              # "html_extract" | "code_gen"
    # html_extract payload
    html_path: str = ""
    fields: list[str] = field(default_factory=list)
    expected: dict[str, str] = field(default_factory=dict)
    # code_gen payload
    signature: str = ""                     # e.g., "def fizzbuzz(n: int) -> list[str]:"
    test_code: str = ""                     # pytest-flavoured tests run against the submission
    reference_solution: str = ""            # author's solution, used as an optional grading bypass


def _from_html_obj(obj: dict[str, Any]) -> Task:
    return Task(
        id=obj["id"],
        description=obj["description"],
        type="html_extract",
        html_path=obj["html_path"],
        fields=list(obj["expected"].keys()),
        expected=obj["expected"],
    )


def _from_code_obj(obj: dict[str, Any]) -> Task:
    return Task(
        id=obj["id"],
        description=obj["description"],
        type="code_gen",
        signature=obj["signature"],
        test_code=obj["test_code"],
        reference_solution=obj.get("reference_solution", ""),
    )


def load_tasks(path: Path | None = None, task_type: str = "html_extract") -> list[Task]:
    if path is None:
        path = CODE_TASKS_FILE if task_type == "code_gen" else TASKS_FILE
    tasks: list[Task] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        t = obj.get("type", "html_extract")
        if t == "code_gen":
            tasks.append(_from_code_obj(obj))
        else:
            tasks.append(_from_html_obj(obj))
    return tasks
