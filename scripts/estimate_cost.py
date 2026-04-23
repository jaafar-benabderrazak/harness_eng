"""Standalone cost estimate. Run before committing to a full matrix."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness_eng.cost_estimator import estimate_matrix, format_estimate  # noqa: E402
from harness_eng.tasks.loader import load_tasks  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=1)
    args = p.parse_args()
    n = len(load_tasks())
    est = estimate_matrix(n_tasks=n, n_seeds=args.seeds)
    print(format_estimate(est))
    return 0


if __name__ == "__main__":
    sys.exit(main())
