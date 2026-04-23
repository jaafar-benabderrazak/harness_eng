"""Runner manifest: expected + completed + resume detection."""
from __future__ import annotations

import json
from pathlib import Path

from harness_eng.runner import (
    _append_completed,
    _manifest_paths,
    _read_completed,
    _write_expected,
    missing_cells,
)


def test_manifest_roundtrip(tmp_path: Path):
    run_id = "20260423_120000_abcd"
    cells = [("react", "t1", 0), ("react", "t1", 1), ("minimal", "t2", 0)]
    out_path, exp_path, comp_path = _manifest_paths(tmp_path, run_id)
    _write_expected(exp_path, cells)

    _append_completed(comp_path, "react", "t1", 0)
    _append_completed(comp_path, "minimal", "t2", 0)

    done = _read_completed(comp_path)
    assert done == {("react", "t1", 0), ("minimal", "t2", 0)}

    # Need to fake a results file so run_path.parent is tmp_path — missing_cells reads by stem
    results_path = tmp_path / f"{run_id}.jsonl"
    results_path.write_text("", encoding="utf-8")
    missing = missing_cells(results_path)
    assert missing == [("react", "t1", 1)]


def test_expected_manifest_lines_parse(tmp_path: Path):
    _, exp_path, _ = _manifest_paths(tmp_path, "r0")
    _write_expected(exp_path, [("h", "t", 0), ("h", "t", 1)])
    rows = [json.loads(line) for line in exp_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"harness": "h", "task_id": "t", "seed": 0},
        {"harness": "h", "task_id": "t", "seed": 1},
    ]
