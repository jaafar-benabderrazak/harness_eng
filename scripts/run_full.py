"""Run the full matrix after confirming the estimated cost."""
from __future__ import annotations

import argparse
import sys

from harness_eng.analysis import produce_all
from harness_eng.cost_estimator import estimate_matrix, format_estimate
from harness_eng.harnesses import HARNESSES
from harness_eng.runner import run_matrix
from harness_eng.tasks.loader import load_tasks
from harness_eng.trace_viewer import build_viewer


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=3,
                   help="Seeds per cell (default 3; Wilson CIs are brittle below 3)")
    p.add_argument("--yes", action="store_true", help="Skip cost-confirmation prompt.")
    p.add_argument("--harnesses", nargs="+", default=list(HARNESSES.keys()))
    args = p.parse_args()

    tasks = load_tasks()
    est = estimate_matrix(n_tasks=len(tasks), n_seeds=args.seeds)
    print(format_estimate(est))
    if not args.yes:
        ans = input(f"\nProceed at estimated ${est['total_usd']:.2f} (with safety ${est['total_usd_with_safety']:.2f})? [y/N] ")
        if ans.strip().lower() != "y":
            print("Aborted.")
            return 1

    run_path = run_matrix(args.harnesses, tasks=tasks, seeds=args.seeds)
    print(f"\nRun written to: {run_path}")

    artifacts = produce_all(run_path)
    for k, v in artifacts.items():
        print(f"  {k}: {v}")

    viewer = build_viewer()
    print(f"  trace_viewer: {viewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
