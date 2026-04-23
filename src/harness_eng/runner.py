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
from .grader import grade, grade_code
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


def _result_row(hr: HarnessResult, task: Task) -> dict:
    """Grade the harness output against the task. Branches on task.type."""
    if task.type == "code_gen":
        submitted_code = (hr.predicted or {}).get("code", "")
        g = grade_code(submitted_code, task.test_code)
        expected_repr = {"type": "code_gen", "signature": task.signature}
    else:
        g = grade(hr.predicted, task.expected)
        expected_repr = task.expected
    row = asdict(hr)
    row["task_type"] = task.type
    row["success"] = g.success
    row["field_accuracy"] = g.field_accuracy
    row["per_field"] = g.per_field
    row["expected"] = expected_repr
    return row


def _manifest_paths(run_dir: Path, run_id: str) -> tuple[Path, Path, Path]:
    return (
        run_dir / f"{run_id}.jsonl",
        run_dir / f"{run_id}.expected.jsonl",
        run_dir / f"{run_id}.completed.jsonl",
    )


def _write_expected(expected_path: Path, cells: list[tuple[str, str, int]]) -> None:
    with expected_path.open("w", encoding="utf-8") as fh:
        for h, t, s in cells:
            fh.write(json.dumps({"harness": h, "task_id": t, "seed": s}) + "\n")


def _append_completed(completed_path: Path, harness: str, task_id: str, seed: int) -> None:
    with completed_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"harness": harness, "task_id": task_id, "seed": seed}) + "\n")


def _read_completed(completed_path: Path) -> set[tuple[str, str, int]]:
    if not completed_path.exists():
        return set()
    done = set()
    for line in completed_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            done.add((o["harness"], o["task_id"], int(o["seed"])))
    return done


def run_matrix(
    harness_names: Iterable[str],
    tasks: list[Task] | None = None,
    seeds: int = 3,
    run_dir: Path | None = None,
    resume: Path | None = None,
) -> Path:
    check_freeze_gate()
    tasks = tasks or load_tasks()
    harness_list = list(harness_names)
    cells = [(h, t.id, s) for h in harness_list for t in tasks for s in range(seeds)]

    if resume is not None:
        run_id = resume.stem
        run_dir = resume.parent
        out_path, expected_path, completed_path = _manifest_paths(run_dir, run_id)
        already = _read_completed(completed_path)
        results_mode = "a"
    else:
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        run_dir = run_dir or RESULTS_DIR / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        out_path, expected_path, completed_path = _manifest_paths(run_dir, run_id)
        _write_expected(expected_path, cells)
        already = set()
        results_mode = "w"

    task_by_id = {t.id: t for t in tasks}
    harness_instances: dict[str, Harness] = {}
    for h in harness_list:
        if h not in HARNESSES:
            raise KeyError(f"unknown harness: {h}")
        harness_instances[h] = HARNESSES[h]()

    with out_path.open(results_mode, encoding="utf-8") as fh:
        for harness_name, task_id, seed in cells:
            if (harness_name, task_id, seed) in already:
                continue
            harness = harness_instances[harness_name]
            task = task_by_id[task_id]
            cell_run_id = f"{run_id}-{seed}"
            hr = harness.run(task, run_id=cell_run_id)
            row = _result_row(hr, task)
            row["seed"] = seed
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            _append_completed(completed_path, harness_name, task_id, seed)
            print(
                f"  {harness_name:<14} {task_id:<12} seed={seed} "
                f"success={row['success']} acc={row['field_accuracy']:.2f} "
                f"tok_in={hr.input_tokens} tok_out={hr.output_tokens} "
                f"tools={hr.tool_calls} t={hr.wall_clock_s:.1f}s"
            )
    return out_path


def missing_cells(run_path: Path) -> list[tuple[str, str, int]]:
    """Return (harness, task_id, seed) triples listed in expected but not completed."""
    run_id = run_path.stem
    _, expected_path, completed_path = _manifest_paths(run_path.parent, run_id)
    expected = []
    if expected_path.exists():
        for line in expected_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                expected.append((o["harness"], o["task_id"], int(o["seed"])))
    done = _read_completed(completed_path)
    return [c for c in expected if c not in done]
