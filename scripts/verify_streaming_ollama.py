"""One-shot verification: streaming_react against Ollama + the configured local model.

Exit codes:
  0 — Streaming + tool-use compatible. streaming_react can run in the local matrix.
  1 — Streaming hung or errored. streaming_react MUST be registered with task_type=[].

The result is also written to .planning/phases/08-expand-harness-family/08-05-VERIFY.md
so plan 08-06 (registration) can read it programmatically.

Usage:
    HARNESS_BACKEND=ollama python scripts/verify_streaming_ollama.py

Bypasses the freeze gate (HARNESS_ENG_SKIP_FREEZE_GATE=1) — this is verification,
not a matrix run.

Wall-clock guard: TIMEOUT_S = 90s. If the smallest fixture doesn't finish in 90s,
the script reports FAIL with reason "hung". Note: this is a soft guard — the
script does NOT itself preempt the model call (Windows lacks signal.alarm). If
the model hangs indefinitely, the user must Ctrl+C; the OUTCOME file then has to
be written by the caller (or re-run the script after killing Ollama).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["HARNESS_ENG_SKIP_FREEZE_GATE"] = "1"

TIMEOUT_S = 90.0
OUTCOME_PATH = ROOT / ".planning" / "phases" / "08-expand-harness-family" / "08-05-VERIFY.md"

STREAMING_OLLAMA_VERIFY_RESULT = "see 08-05-VERIFY.md"


def main() -> int:
    from harness_eng.harnesses.streaming_react import StreamingReActHarness
    from harness_eng.tasks.loader import load_tasks

    html_tasks = [t for t in load_tasks() if t.type == "html_extract"]
    if not html_tasks:
        _write_outcome(False, "No html_extract tasks found in tasks.jsonl", elapsed=0.0)
        return 1
    task = html_tasks[0]
    harness = StreamingReActHarness()

    backend = os.environ.get("HARNESS_BACKEND", "ollama")
    print(
        f"Running streaming_react against task {task.id!r} "
        f"(backend={backend}, timeout_guard={TIMEOUT_S}s)..."
    )
    t0 = time.perf_counter()
    try:
        result = harness.run(task, run_id="verify_streaming")
        elapsed = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001 — record any failure shape
        elapsed = time.perf_counter() - t0
        msg = f"Exception during streaming_react.run: {type(e).__name__}: {e}"
        print(f"FAILED — {msg}")
        _write_outcome(False, msg, elapsed=elapsed)
        return 1

    if elapsed > TIMEOUT_S:
        msg = f"Hung — elapsed={elapsed:.1f}s > {TIMEOUT_S}s timeout"
        print(f"FAILED — {msg}")
        _write_outcome(False, msg, elapsed=elapsed)
        return 1
    if result.stop_reason in ("error", "no_submit"):
        msg = (
            f"Bad stop_reason={result.stop_reason!r}, elapsed={elapsed:.1f}s, "
            f"error={result.error!r}"
        )
        print(f"FAILED — {msg}")
        _write_outcome(False, msg, elapsed=elapsed)
        return 1
    msg = f"OK — stop_reason={result.stop_reason!r}, elapsed={elapsed:.1f}s"
    print(msg)
    _write_outcome(True, msg, elapsed=elapsed)
    return 0


def _write_outcome(passed: bool, msg: str, *, elapsed: float) -> None:
    OUTCOME_PATH.parent.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("HARNESS_BACKEND", "ollama")
    if passed:
        implication = (
            "Register `streaming_react` with `task_type=[\"html_extract\"]` in "
            "`HARNESSES_BY_TASK_TYPE`."
        )
    else:
        implication = (
            "Register `streaming_react` with `task_type=[]` in "
            "`HARNESSES_BY_TASK_TYPE` (excluded from local-model matrix). "
            "Document the exclusion in HARNESSES_FROZEN.md when the freeze tag "
            "moves in plan 08-07."
        )
    body = (
        "# streaming_react Ollama Compatibility Verification\n\n"
        f"**Backend:** {backend}\n"
        f"**Outcome:** {'PASS' if passed else 'FAIL'}\n"
        f"**Elapsed:** {elapsed:.1f}s\n"
        f"**Detail:** {msg}\n\n"
        "**Implication for plan 08-06 registration:**\n"
        f"- {implication}\n\n"
        "**Reference:** Ollama issue #13840 — Generation stops after tool call "
        "with Ollama (GLM-4.7-Flash) — "
        "https://github.com/ollama/ollama/issues/13840\n"
    )
    OUTCOME_PATH.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
