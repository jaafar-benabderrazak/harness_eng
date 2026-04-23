"""Aggregate the latest (or specified) run file into summary artifacts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness_eng.analysis import produce_all  # noqa: E402
from harness_eng.config import RESULTS_DIR  # noqa: E402
from harness_eng.trace_viewer import build_viewer  # noqa: E402


def _latest() -> Path:
    runs_dir = RESULTS_DIR / "runs"
    files = sorted(runs_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no run files in {runs_dir}")
    return files[-1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, default=None)
    args = p.parse_args()
    run_path = args.run or _latest()
    out = produce_all(run_path)
    for k, v in out.items():
        print(f"{k}: {v}")
    viewer = build_viewer()
    print(f"trace_viewer: {viewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
