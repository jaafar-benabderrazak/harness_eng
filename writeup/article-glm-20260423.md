---
layout: default
title: "Same model, five harnesses, one benchmark (glm-4.7-flash, 2026-04-23)"
---

# Same model, five harnesses, one benchmark

*Published 2026-04-23. Run generated against freeze commit `05554d3` (`git rev-parse harnesses-frozen`), backend: Ollama `glm-4.7-flash:latest` on local inference. 5 harnesses × 5 tasks × 3 seeds = 75 cells.*

## Hook

![success rate vs wall-clock across five harnesses](frontier-glm-20260423.png)

Five agent harnesses. Same frozen model (`glm-4.7-flash:latest`, temperature 0, max_tokens 2048). One deterministic HTML-extraction benchmark, 75 cells, Wilson 95% CIs. Spread in task success rate: **4.5×**. Spread in wall-clock: **9.0×**.

On an open-source model running locally, `single_shot` ties for best success rate (9/15) at **1/9th the wall-clock time of `plan_execute`**. `react` — the discourse's default agentic harness — lands at 2/15, with a Wilson CI that doesn't overlap the top tier. The received wisdom says harness investment beats naive prompting; on a weak base model, the inverse is true for the multi-turn harnesses that most depend on the model following instructions across turns.

## The pilot was misleading — and that's the methodology lesson

The first run of this matrix was at `seeds=1` (one run per cell, 25 cells total). That pilot put `minimal` tied for first at 0.60 and `plan_execute` at the bottom at 0.40. Rerun at `seeds=3`, three of the five rankings flipped:

| harness      | seeds=1 (N=5) | seeds=3 (N=15) | Δ success |
|--------------|---------------|----------------|-----------|
| single_shot  | 0.60          | 0.60           | 0.00      |
| plan_execute | 0.40          | 0.60           | **+0.20** |
| reflexion    | 0.40          | 0.47           | +0.07     |
| minimal      | 0.60          | **0.27**       | **−0.33** |
| react        | 0.40          | **0.13**       | **−0.27** |

If this experiment had shipped on `seeds=1`, the post would have claimed `minimal` tied for best. The claim would have been wrong. **Multi-seed is not optional at 5-task scale** — a single lucky/unlucky seed moves rankings by 0.33 in either direction.

`seed_success_std` in the summary.csv exposes which harnesses are flaky:

| harness      | seed_success_std |
|--------------|------------------|
| plan_execute | 0.00             |
| single_shot  | 0.00             |
| minimal      | 0.12             |
| reflexion    | 0.23             |
| react        | 0.23             |

`single_shot` and `plan_execute` are deterministic: given one seed, you know all seeds. `react` and `reflexion` have the highest within-cell variance — their single-seed scores are the least trustworthy. This matches the intuition: multi-turn tool loops branch on model stochasticity at every turn; a one-shot call has only one branch point.

## Why this matters

The AI-eng discourse is model-obsessed. When a new model drops, benchmarks move. What gets undersold is that the scaffolding around the model — the harness — is a much bigger lever than most teams acknowledge. This post isolates the harness as the independent variable: freeze the model, freeze the task set, freeze the tools, and vary only the control flow around them.

The result has teeth in both directions. Harness design *does* matter. But below a base-model reliability threshold, adding turns adds failure modes faster than it adds accuracy.

## The setup

- **Task**: structured field extraction from 5 messy HTML pages (product, job post, event, recipe, paper metadata). 3–5 expected fields per task. Deterministic grader: per-field NFC + casefold + whitespace-collapse exact match.
- **Model**: `glm-4.7-flash:latest` (19 GB, Ollama local inference), temperature 0.0, max_tokens 2048. Frozen in `src/harness_eng/config.py`. Every harness routes through a single `model.call()` function; an AST-walking test enforces that only `model.py` imports the LLM SDK.
- **Harnesses** (the independent variable):
  1. **single_shot** — stuff everything into one call; `submit_answer` is the only tool.
  2. **react** — thought/action/observation loop with a 12-turn cap. Tools: `read_html`, `css_select`, `extract_text`, `submit_answer`.
  3. **plan_execute** — one planning call writes a checklist without seeing HTML, then an executor follows it. No `read_html` in the executor.
  4. **reflexion** — first attempt as ReAct; on grader failure the model critiques its own trace and retries once.
  5. **minimal** — ReAct with a deliberately reduced tool allowlist: no `read_html`, no `extract_text`, only `css_select` and `submit_answer`. Context pruned every 4 turns.
- **Metrics per cell**: task success (all fields correct), per-field accuracy, input/output tokens, tool calls, wall-clock, stop reason.
- **Methodology**: all five harnesses, `tools.py`, and `model.py` are pinned under the `harnesses-frozen` git tag. The runner's `check_freeze_gate()` pre-flight refuses to execute if any gated file has drifted — peek-and-patch is structurally prevented, not just discouraged.

## Results (seeds=3, 75 cells)

| harness      | trials | successes | success rate | Wilson 95% CI | field accuracy | input tok | output tok | tool calls | wall-clock (s) |
|--------------|--------|-----------|--------------|---------------|----------------|-----------|------------|------------|----------------|
| single_shot  | 15     | 9         | 0.60         | 0.36 – 0.80   | 0.88           | 10,713    | 4,116      | 0          | 217            |
| plan_execute | 15     | 9         | 0.60         | 0.36 – 0.80   | 0.76           | 106,611   | 38,475     | 642        | 1,957          |
| reflexion    | 15     | 7         | 0.47         | 0.25 – 0.70   | 0.63           | 85,462    | 24,035     | 114        | 1,269          |
| minimal      | 15     | 4         | 0.27         | 0.11 – 0.52   | 0.51           | 70,643    | 17,162     | 328        | 858            |
| react        | 15     | 2         | 0.13         | **0.04 – 0.38** | 0.37         | 19,632    | 3,172      | 30         | 220            |

The react CI (0.04 – 0.38) does not overlap the top tier's CI (0.36 – 0.80). That ordering is statistically reliable. Other adjacent pairs overlap, so rankings among the mid-tier are not yet distinguishable at this N.

![per-task × per-harness field accuracy](field_heatmap-glm-20260423.png)

### Stop-reason distribution

plan_execute's `turn_cap` rate and reflexion's `error` rate survive the N=15 sample — both are real signatures of those harnesses' failure modes, not task-specific noise:

| harness      | submitted | turn_cap | no_submit | error |
|--------------|-----------|----------|-----------|-------|
| single_shot  | 15        | 0        | 0         | 0     |
| react        | 13        | 0        | 0         | 2     |
| plan_execute | 6         | **9**    | 0         | 0     |
| reflexion    | 10        | 0        | 0         | **5** |
| minimal      | 12        | 3        | 0         | 0     |

- **plan_execute hits turn_cap on 60% of cells** (9/15). The planner's a-priori selectors miss the page structure, the executor can't revise them, and turns get spent looping through the wrong selector batch until the cap fires.
- **reflexion hits `ResponseError: mismatched arg_key and arg_value counts` on 33% of cells** (5/15). Ollama rejects the model's malformed tool_call. The critique-and-retry loop can't fix it because the failure is at the SDK boundary, not at the reasoning layer.
- **single_shot never fails structurally** — 15/15 submit. Whether it submits correctly is a different question (9/15), but it always submits.

## What surprised me

### 1. The simplest harness tied for best — and was the only one that was fast

`single_shot`: 9/15 success at 217 seconds. `plan_execute`: 9/15 success at 1,957 seconds. Same success rate, 9× the wall-clock. If you pay for compute by the minute on a local GPU, `plan_execute` is paying a 9× premium for zero accuracy improvement.

This is the opposite of the pre-registered hypothesis, which expected `react` and `plan_execute` to lead and `single_shot` to land mid-pack. What's going on: `glm-4.7-flash` follows a 5-field tool schema well enough on the first try — `single_shot` had **100% schema compliance** (15/15 cells emitted a valid `submit_answer`). Its multi-turn tool loops drift. Harnesses that lean on iteration inherit those drift risks without being able to convert iteration into value when the first-try signal is already clean.

This result is not "harness design doesn't matter." It's that **harness design dominates within a tier only where the base model's tool-use is reliable enough to benefit from iteration**. Below that threshold, adding turns adds failure modes faster than it adds accuracy.

### 2. The pilot was a lie

`seeds=1` showed `minimal` tied for best and `plan_execute` tied for worst. `seeds=3` shows the exact opposite: `plan_execute` tied for best, `minimal` second-worst. `minimal`'s 0.60 at N=5 was three lucky seeds on product_01 that didn't replicate; at N=15 its score on product_01 collapsed to 0.00 field accuracy.

The fix is not "pick a better pilot N" — it's to publish with `seed_success_std` alongside the ranking. For `react` and `reflexion` at 0.23 std, a single-seed ranking is noise. For `single_shot` and `plan_execute` at 0.00 std, a single seed is enough. The right-sized seed count varies per harness, and the summary table should say so.

### 3. plan_execute collapsed exactly the way the pitch predicted — on 60% of cells

9 of 15 `plan_execute` cells hit the 12-turn cap. The clearest trace pattern: the planner writes a checklist of selector guesses before seeing the HTML (e.g., `h1.product-title, .product-title, h1` for title) and the page uses something different (`h1.title`). The executor sees the HTML, tries the planner's selectors, gets `NO_MATCH` back, and loops through the same wrong batch (`.brand`, `.price`, `[itemprop="price"]`) until the cap fires. It never calls `submit_answer`.

The planner couldn't see the HTML when it wrote the plan. The executor could see the HTML but couldn't revise the plan. No backchannel = no recovery. The two phases make sense in the abstract; they break down at the first page whose conventions don't match the planner's prior.

### 4. reflexion's retries didn't rescue failures — they added new ones

`reflexion` hit the `mismatched arg_key` error on 5 of 15 cells. When the first attempt fails that way, the critique-and-retry reflects on the wrong thing (it treats a SDK-boundary error as if it were a reasoning error) and the retry produces the same malformed tool_call. Net: reflexion paid 85k input / 24k output tokens and 1,269 seconds of wall-clock to recover one additional task over its first-attempt-only version (7 vs an estimated 6 based on react's first-attempt-only rate). Its value depends on the critique actually catching the error — and on this model, many errors are structural rather than semantic.

### 5. minimal's structural restriction was more expensive than predicted

`minimal`'s whole point is removing `read_html` and forcing targeted CSS-selector navigation. On `glm-4.7-flash` this turned into 328 tool calls across 15 cells (vs `react`'s 30) — the model spray-tried selectors without being able to fall back to reading the raw HTML. 4/15 success; 858 seconds of wall-clock — 4× `single_shot`'s time for less than half the success.

The token-budget claim survives (`minimal`'s input-token total is 66% of `plan_execute`'s). The time-cost claim does not. On a pay-per-token API backend, `minimal` is a win. On pay-per-minute local inference, it is not.

## Implications for harness design

Seven concrete takeaways, each actionable by EOD tomorrow:

1. **Never ship a harness comparison at N=1 seed.** Three of five rankings flip between N=5 and N=15 in this run. The rerun was mandatory, not optional. Publish `seed_success_std` alongside the ranking so readers see which rows are noise.

2. **Match harness complexity to base-model reliability.** Before investing in a multi-turn harness, verify the model follows the tool schema cleanly on a single call. If `single_shot` schema compliance is below ~90%, multi-turn harnesses will underperform.

3. **The `submit_answer` universal output channel was load-bearing.** Every harness here terminates by calling the same tool — no free-form text parsing. This eliminates a whole class of "model answered in prose instead of JSON" confounds that would otherwise dominate the failure distribution on weaker models. Adopt across every harness.

4. **plan_execute needs a feedback loop between the executor and the plan.** Minimum viable fix: give the executor a `revise_plan` tool. Correct fix: let the planner see a sample of the HTML. The rigid split is the bug, and it's a 60% turn_cap rate in this run.

5. **Tool-call error handling belongs in the harness, not the SDK.** `mismatched arg_key` errors propagated as hard run terminations. A production harness would catch the malformed output, repair the tool call, and continue. That would have moved reflexion's 33% error rate toward zero.

6. **minimal's structural restriction is worth it for token budgets, not for speed.** Pay-per-token: minimal wins on input-token efficiency vs plan_execute (66% of its tokens). Pay-per-minute: it loses on time. Know which regime you're in.

7. **Single_shot is the honest baseline — always run it.** On this model, on this task, it beat every clever harness on the wall-clock / success frontier. If your clever harness doesn't beat `single_shot`, either the clever harness is wrong or the base model is too weak for cleverness to pay off. Either way you need to know before shipping.

## Honest scope

- **5 tasks × 3 seeds = 75 cells is still a pilot.** Wilson 95% CIs overlap among the top three harnesses (`single_shot`, `plan_execute`, `reflexion`). The `react` ranking as worst-of-five is statistically reliable (CI does not overlap the top tier); the ordering among `single_shot`, `plan_execute`, `reflexion` is not. What IS reliable: the wall-clock spread (217s to 1,957s is 9×), the per-harness stop-reason distribution, and the seed-variance differences (`react`/`reflexion` at 0.23 std vs `single_shot`/`plan_execute` at 0.00).
- **No held-out fixtures.** All 5 pages were visible during harness development. See [`HELD_OUT.md`](../HELD_OUT.md) for the explicit decision.
- **`glm-4.7-flash` is one open-source 19 GB model on CPU-heavy local inference.** Results will look different on Claude Sonnet, GPT-4o, or Gemini 2.0 — those are the runs that could re-open whether `plan_execute` / `reflexion` beat `single_shot`. The harness-dominance hypothesis is about what happens *within a model tier*; this run is one tier.
- **Six tag-moves in the commit log.** Each is documented in [`HARNESSES_FROZEN.md`](../HARNESSES_FROZEN.md) with a reason. No move was post-result; every move was structural (adding tests, backend switch) and happened before the matrix was executed against the newer tag. The `runs/20260423_153534_a022/` directory that sourced this article's numbers was produced against freeze commit `05554d3`.

## Reproduce

```bash
git clone https://github.com/jaafar-benabderrazak/harness-bench && cd harness-bench
pip install -e ".[dev]"
cp .env.example .env     # HARNESS_BACKEND=ollama, HARNESS_MODEL=glm-4.7-flash:latest
ollama pull glm-4.7-flash:latest
pytest -q                # 49 tests offline, no API key required
python scripts/run_full.py --seeds 3 --yes
python scripts/make_chart.py
```

Matrix execution is local and free (no API key needed). Full run takes ~60 min on a modest CPU/GPU box.

---

*Auto-generated numbers from `results/summary.csv` against run `20260423_153534_a022`. The `seeds=1` pilot run (`20260423_150654_1d6c`) is preserved in git history as `feat(phase-6): first real writeup` — the flipped-rankings comparison in the "Pilot was a lie" section compares the two runs directly. Narrative sections written by hand from trace evidence in `traces/`. Re-rerunning the matrix produces a new set of numbers; the narrative applies to this specific run.*
