"""Run the code-generation benchmark (5 code harnesses × 5 code tasks × N seeds)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness_eng.analysis import produce_all  # noqa: E402
from harness_eng.harnesses import HARNESSES_BY_TASK_TYPE  # noqa: E402
from harness_eng.runner import run_matrix  # noqa: E402
from harness_eng.tasks.loader import load_tasks  # noqa: E402
from harness_eng.trace_viewer import build_viewer  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()

    tasks = load_tasks(task_type="code_gen")
    harnesses = HARNESSES_BY_TASK_TYPE["code_gen"]

    print(f"Code-gen matrix: {len(harnesses)} harnesses × {len(tasks)} tasks × {args.seeds} seeds = {len(harnesses) * len(tasks) * args.seeds} cells")
    print(f"Harnesses: {', '.join(harnesses)}")
    print(f"Tasks: {', '.join(t.id for t in tasks)}")
    if not args.yes:
        ans = input("Proceed? [y/N] ")
        if ans.strip().lower() != "y":
            print("Aborted.")
            return 1

    run_path = run_matrix(harnesses, tasks=tasks, seeds=args.seeds)
    print(f"\nRun written to: {run_path}")

    artifacts = produce_all(run_path)
    for k, v in artifacts.items():
        print(f"  {k}: {v}")
    viewer = build_viewer()
    print(f"  trace_viewer: {viewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
