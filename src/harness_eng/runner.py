"""Matrix runner. Executes (harness, task, seed) cells sequentially.

Sequential on purpose: five tasks × five harnesses × small seed count is tiny,
and concurrent Anthropic calls muddle wall-clock numbers. Each cell produces a
dataclass row. Rows are appended to results/runs/{timestamp}.jsonl.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .config import RESULTS_DIR
from .grader import grade
from .harnesses import HARNESSES, Harness, HarnessResult
from .tasks.loader import Task, load_tasks

FREEZE_TAG = "harnesses-frozen"
GATED_PATHS = (
    "src/harness_eng/harnesses/",
    "src/harness_eng/tools.py",
    "src/harness_eng/model.py",
)


class FreezeGateError(RuntimeError):
    """Raised when the runner detects that gated files have diverged from the freeze tag."""


def check_freeze_gate() -> None:
    """Refuse to run if any gated file differs from the `harnesses-frozen` tag.

    Bypass with HARNESS_ENG_SKIP_FREEZE_GATE=1 — tests only.
    """
    if os.environ.get("HARNESS_ENG_SKIP_FREEZE_GATE") == "1":
        return
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", FREEZE_TAG, "HEAD", "--", *GATED_PATHS],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FreezeGateError(f"git not available: {e}") from e
    if result.returncode != 0:
        raise FreezeGateError(
            f"{FREEZE_TAG} tag not found — create with: git tag {FREEZE_TAG} <sha>. "
            f"stderr: {result.stderr.strip()}"
        )
    diverged = [line for line in result.stdout.strip().splitlines() if line]
    if diverged:
        raise FreezeGateError(
            f"Gated files diverged from {FREEZE_TAG}: {', '.join(diverged)}. "
            "Either revert these files or move the tag (which invalidates the experiment)."
        )


def _result_row(hr: HarnessResult, expected: dict[str, str]) -> dict:
    g = grade(hr.predicted, expected)
    row = asdict(hr)
    row["success"] = g.success
    row["field_accuracy"] = g.field_accuracy
    row["per_field"] = g.per_field
    row["expected"] = expected
    return row


def run_matrix(
    harness_names: Iterable[str],
    tasks: list[Task] | None = None,
    seeds: int = 3,
    run_dir: Path | None = None,
) -> Path:
    check_freeze_gate()
    tasks = tasks or load_tasks()
    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    run_dir = run_dir or RESULTS_DIR / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"{run_id}.jsonl"

    with out_path.open("w", encoding="utf-8") as fh:
        for harness_name in harness_names:
            if harness_name not in HARNESSES:
                raise KeyError(f"unknown harness: {harness_name}")
            harness: Harness = HARNESSES[harness_name]()
            for task in tasks:
                for seed in range(seeds):
                    cell_run_id = f"{run_id}-{seed}"
                    hr = harness.run(task, run_id=cell_run_id)
                    row = _result_row(hr, task.expected)
                    row["seed"] = seed
                    fh.write(json.dumps(row, default=str) + "\n")
                    fh.flush()
                    print(
                        f"  {harness_name:<14} {task.id:<12} seed={seed} "
                        f"success={row['success']} acc={row['field_accuracy']:.2f} "
                        f"tok_in={hr.input_tokens} tok_out={hr.output_tokens} "
                        f"tools={hr.tool_calls} t={hr.wall_clock_s:.1f}s"
                    )
    return out_path
