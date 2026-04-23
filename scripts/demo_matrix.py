"""Offline demo: stub the model with a deterministic fake, drive the full matrix.

Validates the pipeline end-to-end without API spend. Per-harness behavior is
hand-tuned so the resulting frontier chart has realistic spread.

NOT for the real experiment — use scripts/run_full.py for that.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness_eng import model as model_module
from harness_eng.analysis import produce_all
from harness_eng.config import FIXTURES_DIR
from harness_eng.harnesses import HARNESSES
from harness_eng.model import ModelCall
from harness_eng.runner import run_matrix
from harness_eng.tasks.loader import load_tasks
from harness_eng.trace_viewer import build_viewer


# Per-harness "skill" and "cost" shape, picked to produce a legible frontier.
HARNESS_BEHAVIOR = {
    "single_shot":  {"miss_rate": 0.15, "turns": 1,  "in_per_turn": 2500, "out_per_turn": 250, "decoy_confuses": 0.35},
    "react":        {"miss_rate": 0.05, "turns": 4,  "in_per_turn": 1800, "out_per_turn": 180, "decoy_confuses": 0.10},
    "plan_execute": {"miss_rate": 0.10, "turns": 5,  "in_per_turn": 1900, "out_per_turn": 180, "decoy_confuses": 0.15},
    "reflexion":    {"miss_rate": 0.04, "turns": 6,  "in_per_turn": 2000, "out_per_turn": 220, "decoy_confuses": 0.05},
    "minimal":      {"miss_rate": 0.30, "turns": 3,  "in_per_turn": 1000, "out_per_turn": 100, "decoy_confuses": 0.45},
}


class _FakeState:
    """Per-harness-run state tracked by the fake model."""

    def __init__(self, harness_name: str, expected: dict[str, str], seed: int):
        self.harness_name = harness_name
        self.expected = expected
        self.seed = seed
        self.turns_taken = 0
        self.done = False
        self.rng = random.Random(hash((harness_name, tuple(expected.items()), seed)) & 0xFFFFFFFF)
        self.behavior = HARNESS_BEHAVIOR[harness_name]


# Map (harness_name, task_id, seed) -> _FakeState via message-content sniffing.
_active_state: _FakeState | None = None


def _install_fake(harness_name: str, task_id: str, expected: dict[str, str], seed: int) -> None:
    global _active_state
    _active_state = _FakeState(harness_name, expected, seed)


def _fake_call(system, messages, tools=None):
    """Behavioral fake. Decides whether to call a tool or submit_answer based on turn count."""
    state = _active_state
    if state is None:
        raise RuntimeError("fake model used without _install_fake")

    state.turns_taken += 1
    b = state.behavior
    tool_names = {t["name"] for t in (tools or [])}

    # Decide to end the run: planner-only call (no submit_answer tool) emits text only.
    has_submit = "submit_answer" in tool_names
    if not has_submit:
        # Planner step — return plain text.
        return ModelCall(
            input_tokens=b["in_per_turn"],
            output_tokens=b["out_per_turn"],
            latency_s=0.05,
            stop_reason="end_turn",
            content=[{"type": "text", "text": "Plan: use css_select on each field's likely tag."}],
            usage_raw={"input_tokens": b["in_per_turn"], "output_tokens": b["out_per_turn"]},
        )

    # If this harness has investigation tools and hasn't used enough turns, call one.
    investigation_tools = tool_names - {"submit_answer"}
    if investigation_tools and state.turns_taken < b["turns"]:
        tool_name = state.rng.choice(sorted(investigation_tools))
        args = {}
        if tool_name == "css_select":
            args = {"selector": state.rng.choice([".title", "h1", ".price", ".meta"])}
        tok_in = b["in_per_turn"] * state.turns_taken  # simulates history growth
        tok_out = b["out_per_turn"]
        return ModelCall(
            input_tokens=tok_in,
            output_tokens=tok_out,
            latency_s=0.08,
            stop_reason="tool_use",
            content=[{
                "type": "tool_use",
                "id": f"tu_{state.turns_taken}",
                "name": tool_name,
                "input": args,
            }],
            usage_raw={"input_tokens": tok_in, "output_tokens": tok_out},
        )

    # Submit. Inject per-harness miss rate.
    miss = state.rng.random() < b["miss_rate"]
    confused_by_decoy = state.rng.random() < b["decoy_confuses"]

    submitted = {}
    for k, v in state.expected.items():
        if miss or confused_by_decoy:
            # Corrupt some fields to produce realistic partial-credit outcomes.
            if state.rng.random() < 0.5:
                submitted[k] = v  # keep this one right
            else:
                submitted[k] = v[::-1] if isinstance(v, str) else v  # reverse = clearly wrong
        else:
            submitted[k] = v

    tok_in = b["in_per_turn"] * state.turns_taken
    tok_out = b["out_per_turn"] * 2
    return ModelCall(
        input_tokens=tok_in,
        output_tokens=tok_out,
        latency_s=0.1,
        stop_reason="tool_use",
        content=[{
            "type": "tool_use",
            "id": "tu_submit",
            "name": "submit_answer",
            "input": {"fields": submitted},
        }],
        usage_raw={"input_tokens": tok_in, "output_tokens": tok_out},
    )


def _patch_harness_runs():
    """Wrap Harness.run to install per-cell fake state before each run."""
    import harness_eng.harnesses.base as base_mod
    original_run = base_mod.Harness.run
    original_call = model_module.call
    model_module.call = _fake_call
    base_mod.model_call = _fake_call  # harnesses/base.py imported `call as model_call`

    def wrapped_run(self, task, run_id=None):
        # Use task id + harness name + run_id for deterministic seeding across seeds
        seed = int(str(run_id or "0").split("-")[-1]) if run_id else 0
        _install_fake(self.name, task.id, task.expected, seed)
        return original_run(self, task, run_id=run_id)

    base_mod.Harness.run = wrapped_run


def main() -> int:
    _patch_harness_runs()
    tasks = load_tasks()
    out_path = run_matrix(list(HARNESSES.keys()), tasks=tasks, seeds=3)
    print(f"\nMatrix results: {out_path}")

    artifacts = produce_all(out_path)
    for k, v in artifacts.items():
        print(f"  {k}: {v}")

    viewer = build_viewer()
    print(f"  trace_viewer: {viewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
