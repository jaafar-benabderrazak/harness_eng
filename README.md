# harness_eng

**Same model, eight harnesses, two benchmarks.**

A controlled experiment: hold the model constant, vary the scaffolding, measure the spread in success rate and cost across two task types. Ran against an open-source local model (`glm-4.7-flash` via Ollama) by default; Anthropic backend swappable via `.env`.

## The setup

- **Two task types**:
  - `html_extract` — pull 3–5 structured fields from messy HTML. Deterministic per-field normalized exact-match grader.
  - `code_gen` — implement a Python function that passes a pytest suite. Deterministic grader via `pytest` subprocess (exit 0 = success).
- **Model**: frozen. Default `glm-4.7-flash:latest` via Ollama (local, 19 GB, no API key, zero dollars). Anthropic/Claude backend available by setting `HARNESS_BACKEND=anthropic` + `HARNESS_MODEL=claude-sonnet-4-6` in `.env`. Temperature 0, `max_tokens=2048`. Set once in `src/harness_eng/config.py` / `.env`. Every harness routes through `model.call()`.
- **Eight harnesses** (five per task type; `single_shot` and `react` run on both):
  - HTML-extraction family: `single_shot`, `react`, `plan_execute`, `reflexion`, `minimal`
  - Code-generation family: `single_shot`, `react`, `chain_of_thought`, `test_driven`, `retry_on_fail`
- **Metrics per run**: success (0/1 per field/test + overall), input/output tokens, tool calls, wall-clock, stop reason.
- **Traces**: every model call and tool invocation appended to `traces/{harness}/{task_id}/{run_id}.jsonl` from the first call, not retrofitted.

## Pre-registered hypothesis

*Registered 2026-04-23, at or before the `harnesses-frozen` git tag. Any edit to this section after the tag is a methodological defect, not a clarification — git history will show the ordering.*

On the frozen model (`claude-sonnet-4-6`, temperature 0, max_tokens 2048) and this 5-task HTML extraction suite, we expect:

1. **Success-rate ordering**: `react` and `plan_execute` will tie for top; `reflexion` will land near the top too, with upside if the critique actually catches its own errors. `single_shot` will be mid-pack — surprisingly competitive on this simple task, but fragile on the decoy-heavy fixtures. `minimal` will be worst on success rate because removing `read_html` forces selector guesswork on the harder pages.
2. **Cost ordering** (cheapest to most expensive): `single_shot` < `minimal` < `react` < `plan_execute` < `reflexion`. Reflexion's retry path is the dominant cost contributor when it activates; plan_execute pays the planner-call overhead on every task.
3. **Spread**: 2–4x in success rate across harnesses; 5–10x in cost. If the spread is smaller than 2x on success rate, the experiment is inconclusive on this suite and we say so in the article rather than over-claiming.
4. **Surprise candidates**: `reflexion` may underperform expectations if the critique is overconfident; `plan_execute` may collapse on tasks where the plan is wrong from step one. One of those two is the most likely "what surprised me" section.

## What actually happened

**Writeups:**

- [`writeup/article.md`](writeup/article.md) — full combined article, both task types across all eight harnesses, charts + forensics + Mermaid diagrams. Also rendered at [jaafar-benabderrazak.github.io/harness-bench](https://jaafar-benabderrazak.github.io/harness-bench/writeup/article.html).
- [`writeup/article-linkedin.md`](writeup/article-linkedin.md) — LinkedIn-friendly cut (no Mermaid, plain-text flow, sharpened hook + framework mapping to LangChain / LangGraph / CrewAI / Aider).

The experiment ran on `glm-4.7-flash:latest` via Ollama rather than Claude Sonnet — pragmatic pivot to avoid a billing block. On this model, the pre-registered ordering **did not hold**.

**HTML extraction (hard for this model):**

| harness      | success rate (N=15) | Wilson 95% CI | wall-clock (s) |
|--------------|--------------------:|---------------|---------------:|
| single_shot  | 0.60                | 0.36 – 0.80   | 228            |
| minimal      | 0.60                | 0.36 – 0.80   | 1,059          |
| plan_execute | 0.40                | 0.20 – 0.64   | 1,615          |
| reflexion    | 0.20                | 0.07 – 0.45   | 977            |
| react        | varies              | –             | ~220           |

- `single_shot` tied for best at **~7× less wall-clock** than `plan_execute`. Same-or-better success, 7× faster.
- `plan_execute` hit `turn_cap` on **60%** of cells — "planner guesses selectors before seeing HTML, executor can't revise the plan" was the pitch's predicted failure and showed up exactly. One N=15 run saw it fire a non-existent selector 417 times.
- Multi-turn harnesses all hit SDK-boundary errors (`ResponseError: mismatched arg_key`) — critique can't fix malformed tool_calls.

**Code generation (easy for this model):**

Every harness scored 15/15. The comparison collapses from "which works?" to "which is wasteful?" — `chain_of_thought` took 2× the wall-clock of `single_shot`; `test_driven` used 6× the input tokens. Same 100% accuracy.

**The methodology story turned out as big as the ranking story.** The first run (seeds=1, 25 cells) put `minimal` tied for best; the rerun (seeds=3, 75 cells) put it second-worst. Then two independent N=15 runs on the same frozen model + temperature 0 produced middle-of-the-pack swings of up to 0.33. `seed_success_std` in the summary CSV exposes the flaky rows. If ordering matters for your eval, you need multiple independent matrices, not just more seeds in one.

**What's still outstanding**: the matrix hasn't been run on Claude Sonnet (user-side billing issue blocked it). The pre-registered ordering remains untested on a strong model. That run is a straightforward rerun with `HARNESS_BACKEND=anthropic` + `HARNESS_MODEL=claude-sonnet-4-6` in `.env`; the harness code is frozen and unchanged between backends.

## Quickstart

```bash
# 1. Install (runs on Linux + Windows — CI verifies both).
python -m venv .venv && . .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# 2. Run the test suite. No API key needed — all 55 tests are offline.
pytest -q

# 3. Default backend is Ollama + glm-4.7-flash (local, no API key, zero dollars).
cp .env.example .env
ollama pull glm-4.7-flash:latest
# To run against Claude instead: set HARNESS_BACKEND=anthropic,
# HARNESS_MODEL=claude-sonnet-4-6, and ANTHROPIC_API_KEY in .env.

# 4. Cost estimate BEFORE spending (only relevant for Anthropic backend).
python scripts/estimate_cost.py --seeds 3

# 5. Sanity pilot (1 task × 5 harnesses × 1 seed). Validates the plumbing.
python scripts/run_pilot.py

# 6. Full HTML-extraction matrix (5 tasks × 5 harnesses × 3 seeds). Gated by freeze tag.
python scripts/run_full.py --seeds 3 --yes

# 7. Full code-generation matrix (5 tasks × 5 harnesses × 3 seeds). Same freeze gate.
python scripts/run_code_benchmark.py --seeds 3 --yes

# 8. Aggregate + chart + article + trace viewer (no API calls).
python scripts/make_chart.py
```

## Layout

```text
src/harness_eng/
  config.py         frozen model + experiment constants
  model.py          backend-agnostic client (Ollama + Anthropic) — all harnesses route here
  trace.py          JSONL trace writer
  tools.py          shared tool schemas + dispatch
  tasks/
    loader.py       load tasks.jsonl / tasks_code.jsonl + fixtures
    tasks.jsonl     HTML-extraction task specs (id, html_path, fields, expected)
    tasks_code.jsonl  code-generation task specs (id, signature, tests, reference)
    fixtures/       HTML files
  grader.py         exact-match field grader + pytest-subprocess code grader
  harnesses/
    base.py         abstract Harness(task) -> Result
    single_shot.py
    react.py
    plan_execute.py
    reflexion.py
    minimal.py
    chain_of_thought.py
    test_driven.py
    retry_on_fail.py
  runner.py         orchestrates the matrix
  analysis.py       aggregates traces -> summary + frontier chart
scripts/            thin CLI entry points (run_full, run_code_benchmark, make_chart, …)
tests/              55 offline tests — grader, loader, freeze gate, every harness
```

## Controls

Things held constant across harnesses:

- Model ID, temperature, max_tokens.
- Task set and grader.
- Tool implementations (though the *subset* exposed varies per harness by design).
- System-prompt role framing (each harness owns its own *control flow* prompt but not the base role).

Things that vary by design and are the independent variable:

- Control flow (single call vs loop vs plan/execute vs retry vs pruned).
- Turn cap.
- Tools exposed.
- Context management.

## Honest scope

Two pilots, not two benchmarks. 5 tasks × 3 seeds per task type = 75 cells each. The point is the *spread* across harnesses on the same model, not absolute rankings. Wilson CIs overlap for most pairs on HTML; on code-gen every harness hit 15/15 so CIs are uniform `[0.80, 1.00]`. Run-to-run variance is real on `glm-4.7-flash` even at temperature 0 — middle-of-the-pack rankings swing by up to 0.33 between independent N=15 runs. Rerun on multiple independent matrices (not just more seeds) if mid-pack ordering matters for your claim.
