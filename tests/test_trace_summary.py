"""Trace-summary scanner: per-harness stop-reason counts + notable-trace pointers."""
from __future__ import annotations

import json
from pathlib import Path

from harness_eng.analysis import summarize_traces


def _write_trace(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def test_summarize_traces_counts_stop_reasons(tmp_path: Path):
    """Per-harness Counter of stop_reason values from run_end events."""
    _write_trace(tmp_path / "react" / "product_01" / "r1.jsonl", [
        {"type": "run_start"},
        {"type": "model_response", "input_tokens": 100, "output_tokens": 50},
        {"type": "run_end", "stop_reason": "submitted", "input_tokens": 100, "output_tokens": 50},
    ])
    _write_trace(tmp_path / "react" / "product_01" / "r2.jsonl", [
        {"type": "run_start"},
        {"type": "run_end", "stop_reason": "turn_cap", "input_tokens": 200, "output_tokens": 100},
    ])
    _write_trace(tmp_path / "minimal" / "job_01" / "r1.jsonl", [
        {"type": "run_start"},
        {"type": "run_end", "stop_reason": "submitted", "input_tokens": 80, "output_tokens": 40},
    ])

    ts = summarize_traces(traces_dir=tmp_path)
    assert ts.stop_reasons["react"]["submitted"] == 1
    assert ts.stop_reasons["react"]["turn_cap"] == 1
    assert ts.stop_reasons["minimal"]["submitted"] == 1


def test_summarize_traces_flags_failing_cells(tmp_path: Path):
    _write_trace(tmp_path / "react" / "product_01" / "r1.jsonl", [
        {"type": "run_start"},
        {"type": "run_end", "stop_reason": "turn_cap", "input_tokens": 200, "output_tokens": 100},
    ])
    ts = summarize_traces(traces_dir=tmp_path)
    assert ts.failing_cells["react"] == [("product_01", "turn_cap")]


def test_summarize_traces_picks_most_expensive(tmp_path: Path):
    _write_trace(tmp_path / "react" / "product_01" / "cheap.jsonl", [
        {"type": "run_end", "stop_reason": "submitted", "input_tokens": 10, "output_tokens": 5},
    ])
    _write_trace(tmp_path / "react" / "job_01" / "expensive.jsonl", [
        {"type": "run_end", "stop_reason": "submitted", "input_tokens": 5000, "output_tokens": 2000},
    ])
    ts = summarize_traces(traces_dir=tmp_path)
    task, path, tokens = ts.most_expensive["react"]
    assert task == "job_01"
    assert tokens == 7000
    assert path.name == "expensive.jsonl"


def test_summarize_traces_handles_missing_run_end(tmp_path: Path):
    """Crashed runs without run_end should be flagged as incomplete, not silently dropped."""
    _write_trace(tmp_path / "react" / "product_01" / "crashed.jsonl", [
        {"type": "run_start"},
        {"type": "model_response"},
    ])
    ts = summarize_traces(traces_dir=tmp_path)
    assert ts.stop_reasons["react"]["incomplete"] == 1
    assert ("product_01", "no run_end event") in ts.failing_cells["react"]


def test_summarize_empty_traces_dir(tmp_path: Path):
    """Missing or empty traces dir returns empty summary, doesn't crash."""
    ts = summarize_traces(traces_dir=tmp_path)
    assert ts.stop_reasons == {}
    assert ts.failing_cells == {}
