# harness_eng

**Same model, five harnesses, one benchmark.**

A controlled experiment: hold the model constant, vary the scaffolding, measure the spread in success rate and cost. The hypothesis is that harness design dominates model choice within a tier.

## The setup

- **Task**: structured field extraction from messy HTML. 40-task suite. Deterministic exact-match grader per field.
- **Model**: frozen. Default `claude-sonnet-4-6`, temperature 0, max_tokens 2048. Set once in `src/harness_eng/config.py` / `.env`. Every harness must route through `model.call()`.
- **Harnesses**:
  1. `single_shot` — entire HTML + instructions in one message, ask for JSON.
  2. `react` — thought / action / observation loop with a hard turn cap.
  3. `plan_execute` — one planning call emits a checklist, a separate executor follows it.
  4. `reflexion` — on grader failure, model critiques its own trace and retries once.
  5. `minimal` — reduced toolset (no raw HTML dump), context pruned every N turns.
- **Metrics per run**: success (0/1 per field + overall), input/output tokens, tool calls, wall-clock.
- **Traces**: every call and tool invocation is appended to `traces/{harness}/{task_id}/{run_id}.jsonl` from the first call, not retrofitted.

## Pre-registered hypothesis

*Registered 2026-04-23, at or before the `harnesses-frozen` git tag. Any edit to this section after the tag is a methodological defect, not a clarification — git history will show the ordering.*

On the frozen model (`claude-sonnet-4-6`, temperature 0, max_tokens 2048) and this 5-task HTML extraction suite, we expect:

1. **Success-rate ordering**: `react` and `plan_execute` will tie for top; `reflexion` will land near the top too, with upside if the critique actually catches its own errors. `single_shot` will be mid-pack — surprisingly competitive on this simple task, but fragile on the decoy-heavy fixtures. `minimal` will be worst on success rate because removing `read_html` forces selector guesswork on the harder pages.
2. **Cost ordering** (cheapest to most expensive): `single_shot` < `minimal` < `react` < `plan_execute` < `reflexion`. Reflexion's retry path is the dominant cost contributor when it activates; plan_execute pays the planner-call overhead on every task.
3. **Spread**: 2–4x in success rate across harnesses; 5–10x in cost. If the spread is smaller than 2x on success rate, the experiment is inconclusive on this suite and we say so in the article rather than over-claiming.
4. **Surprise candidates**: `reflexion` may underperform expectations if the critique is overconfident; `plan_execute` may collapse on tasks where the plan is wrong from step one. One of those two is the most likely "what surprised me" section.

## Quickstart

```bash
python -m venv .venv && . .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env                           # set ANTHROPIC_API_KEY

# Sanity pilot (5 tasks x 5 harnesses). Estimate spend before running full.
python scripts/run_pilot.py

# Full run (40 tasks x 5 harnesses x N seeds)
python scripts/run_full.py --seeds 1

# Aggregate + chart
python scripts/make_chart.py
```

## Layout

```text
src/harness_eng/
  config.py         frozen model + experiment constants
  model.py          single Anthropic client wrapper all harnesses use
  trace.py          JSONL trace writer
  tools.py          shared tool schemas + dispatch
  tasks/
    loader.py       load tasks.jsonl + HTML fixtures
    tasks.jsonl     task specs (id, html_path, fields, expected)
    fixtures/       HTML files
  grader.py         exact-match field grader
  harnesses/
    base.py         abstract Harness(task) -> Result
    single_shot.py
    react.py
    plan_execute.py
    reflexion.py
    minimal.py
  runner.py         orchestrates the matrix
  analysis.py       aggregates traces -> summary + frontier chart
scripts/            thin CLI entry points
tests/              grader + loader smoke tests
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

40 tasks is a pilot, not SWE-bench. The point is the *spread* across harnesses on the same model, not absolute rankings. Rerun with more seeds if the spread is within noise.
