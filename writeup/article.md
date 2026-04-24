---
layout: default
title: "Same model, eight harnesses, two benchmarks (glm-4.7-flash, 2026-04-23)"
description: "One frozen model, eight harnesses, two task types, 150 graded runs. A controlled experiment on whether harness complexity pays."
---

<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('pre > code.language-mermaid').forEach((el) => {
    const d = document.createElement('div');
    d.className = 'mermaid';
    d.textContent = el.textContent;
    el.parentElement.replaceWith(d);
  });
  mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
  mermaid.run();
});
</script>

# Same model, eight harnesses, two benchmarks

*A two-part controlled experiment on agent harness design. One frozen model. Two task types. 150 runs. Source + data: [github.com/jaafar-benabderrazak/harness-bench](https://github.com/jaafar-benabderrazak/harness-bench). Freeze commit: `9977e85`.*

---

## What this is, in one diagram

```mermaid
flowchart LR
    M[glm-4.7-flash<br/>temperature 0<br/>local Ollama] --> H1[5 HTML harnesses<br/>single_shot, react,<br/>plan_execute, reflexion,<br/>minimal]
    M --> H2[5 code-gen harnesses<br/>single_shot, react,<br/>chain_of_thought, test_driven,<br/>retry_on_fail]
    H1 --> B1[5 messy HTML pages<br/>extract 3-5 fields<br/>× 3 seeds = 75 cells]
    H2 --> B2[5 Python functions<br/>pass pytest suite<br/>× 3 seeds = 75 cells]
    B1 --> R1[pull numbers:<br/>spread in success,<br/>time, tokens]
    B2 --> R2[pull numbers:<br/>spread in time, tokens<br/>everyone hit 100%]
    R1 --> C[cross-experiment finding]
    R2 --> C
```

Same model. Two task types. Eight harnesses across both (five per task type, some shared). **150 graded runs, zero dollars** (open-source model, local inference).

---

## The finding, in one sentence

**On hard tasks, complex harnesses failed more than simple ones. On easy tasks, complex harnesses cost more than simple ones. `single_shot` won on wall-clock in both experiments.**

On HTML extraction (hard for this model):

![HTML frontier](frontier-glm-20260423.png)

`single_shot` and `minimal` tied for best at 9/15 success. `single_shot` did it in **228 seconds**; `plan_execute` scored 6/15 and took **1,615 seconds** — 7× the wall-clock for a *worse* result. `reflexion` came last at 3/15 despite spending 977 seconds of wall-clock.

On code generation (easy for this model):

![code-gen resource bars — who's wasteful when everyone scores 100%](resource_bars-code-glm-20260423.png)

Every harness hit 15/15 on code-gen. `chain_of_thought` took twice single_shot's wall-clock for the same result. `test_driven` used 6× the input tokens.

Harness complexity costs something. In both experiments, on this model, it didn't buy anything back.

---

## Why this experiment exists

A popular belief in agent-engineering discourse: the **model** is the main thing; the **harness** (the control loop around the model) is a minor detail — pick your model, glue on a standard ReAct loop, done.

This project flips the variable. Freeze the model. Vary only the harness. Measure what moves.

Running two separate experiments — one where the tasks are genuinely hard for the base model, one where they're easy — tests the hypothesis from both ends. If harness complexity is universally valuable, both experiments should show it paying. If it's a crutch for weak models, the hard experiment should show it paying more. If it's mostly dead weight on this model, *neither* experiment should show it paying — which is what the data says.

---

## The eight harnesses

All eight inherit from the same `Harness` base class. What varies is the control flow. Each has a `TOOL_WHITELIST` enforced by the runner so you cannot add a tool by accident.

### HTML-extraction family (5 harnesses)

```mermaid
flowchart LR
    subgraph single_shot_html["single_shot · dump HTML, ask once"]
        direction LR
        SS1[user + full HTML] --> SS2[model] --> SS3["submit_answer(fields)"]
    end
```

```mermaid
flowchart LR
    subgraph react["react · think, act, observe, repeat"]
        direction LR
        R1[user] --> R2[model] -->|css_select /<br/>read_html| R3[tool] -->|result| R2
        R2 -->|once ready| R4["submit_answer(fields)"]
    end
```

```mermaid
flowchart TD
    subgraph plan["plan_execute · plan blind, then execute"]
        direction TB
        P1[planner call<br/>no HTML] --> P2[checklist of<br/>selectors]
        P2 --> P3[executor<br/>HTML visible]
        P3 -->|try each| P4[tool]
        P4 --> P3
        P3 --> P5["submit_answer"]
    end
```

```mermaid
flowchart LR
    subgraph reflexion["reflexion · react, critique, retry"]
        direction LR
        RF1[react #1] --> RF2{grader<br/>pass?}
        RF2 -->|yes| RF3[done]
        RF2 -->|no| RF4[critique<br/>own trace] --> RF5[react #2]
    end
```

```mermaid
flowchart LR
    subgraph minimal["minimal · react minus read_html"]
        direction LR
        M1[user] --> M2[model] -->|"css_select only"| M3[tool]
        M3 --> M2 --> M4["submit_answer"]
    end
```

### Code-gen family (5 harnesses — single_shot + react shared with above)

```mermaid
flowchart LR
    subgraph cot["chain_of_thought · reason, then submit"]
        direction LR
        C1[user + task] --> C2[model reasons:<br/>'step 1...'] --> C3["submit_answer(code)"]
    end
```

```mermaid
flowchart LR
    subgraph td["test_driven · loop with run_tests"]
        direction LR
        T1[user + task] --> T2[model writes<br/>candidate]
        T2 --> T3[check_syntax] --> T4[run_tests]
        T4 -->|fail| T5[read output,<br/>revise] --> T3
        T4 -->|pass| T6[submit_answer]
    end
```

```mermaid
flowchart LR
    subgraph rof["retry_on_fail · submit, see test output, retry"]
        direction LR
        R1[user] --> R2[attempt 1] --> R3{tests<br/>pass?}
        R3 -->|yes| R4[done]
        R3 -->|no| R5[show pytest<br/>output] --> R6[attempt 2/3] --> R3
    end
```

Every harness terminates by calling the same `submit_answer` tool. That's on purpose — parsing free-form text for a JSON answer is a huge confound on weaker models, so the tool channel is a schema-enforcing chokepoint. `single_shot` hit **100% schema compliance** on both task types.

---

## Part 1 — HTML extraction (hard tasks)

**Task**: extract 3–5 fields from 5 messy HTML pages (product, job post, event, recipe, paper metadata). Deterministic grader: per-field normalized exact match.

**Result**: `single_shot` and `minimal` tied for best at 9/15 success. `single_shot` did it in **228 s** total; `minimal` took **1,059 s** — 4.6× the wall-clock for the same result. `plan_execute` scored 6/15 despite spending **1,615 seconds**. `reflexion` came last at 3/15 — the critique loop didn't rescue failures, it kept hitting the same SDK-boundary error. Wilson CIs for the top tier (single_shot + minimal) don't overlap `reflexion`'s — that ranking is statistically reliable.

### Headline chart

![HTML frontier](frontier-glm-20260423.png)

### Per-task accuracy

![HTML field-accuracy heatmap](field_heatmap-glm-20260423.png)

- **`product_01` destroys multi-turn harnesses** — `react` and `minimal` both score 0 because the HTML uses `<div class="brand-line">Brand: <a>Lumina</a></div>`, which no generic selector catches.
- **`paper_01` defeats `reflexion`** — 0/3 seeds. The critique loop locked onto a wrong selector and kept retrying it.

### Where failures came from

![HTML stop-reason distribution](stop_reasons-glm-20260423.png)

Every cell ends one of four ways. `single_shot` is pure green (always cleanly submits). `react` is more than half red — hit an `mismatched arg_key` SDK-boundary error on 8/15 cells. `plan_execute` hits the 12-turn cap on 60% of cells because the planner wrote wrong selectors and the executor had no backchannel to revise them.

<details>
<summary><b>How the multi-turn harnesses burn their turns</b></summary>

The multi-turn harnesses all share one problem: they try CSS selectors that don't match anything. `NO_MATCH` rates across the full 75-cell matrix:

| harness      | CSS_select calls | fraction returning NO_MATCH |
|--------------|-----------------:|-----------------------------|
| minimal      | ~380             | **79.7%**                   |
| plan_execute | ~160             | **69.7%**                   |
| react        | ~50              | 61.7%                       |
| reflexion    | ~40              | 56.0%                       |

Roughly two out of three tool calls are wasted guesses. The 12-turn cap is the only thing that stops most of the loops.

The single most damning number in the whole matrix: an earlier N=15 run saw `plan_execute` fire the selector `span.date-submitted-date` **417 times** across the full 75 cells. That selector does not exist on any of the five pages. The planner invented it. The executor fired it into the void 417 times because the harness has no backchannel — once the plan is written, the executor can only follow it. **87.6%** of that run's `plan_execute` CSS-selector attempts returned nothing. Nearly nine in ten guesses were wrong, and only the 12-turn cap stopped the loop.

Top-3 most-retried selectors per harness (across the whole matrix):

```text
minimal          13x  h1
                 12x  span.arxiv-id
                 11x  span[id*="date"]

plan_execute     15x  h1
                  6x  p
                  6x  p:contains('When:')

react             4x  h1, h2, h3
                  3x  h1, h2, h3, .headline, .event-title, .main-title
                  3x  .event-date, .date, .time, .when, .datetime

reflexion         2x  article.event-details, div.event-details, ...
                  2x  .event, .event-item, .event-container
                  2x  div, section, main
```

The shapes tell you the failure mode: `minimal`'s "retry the exact same selector 13 times" pattern is different from `plan_execute`'s "try the planner's guesses then fall back to `p`" or `react`'s "OR-together a dozen maybe-selectors." All of them are a model that can't see the page structure, guessing.

Median turns spent on failure (cells that didn't submit cleanly):

| harness      | median turns burned |
|--------------|---------------------|
| plan_execute | 13.0 — hit the cap |
| react        | 1.0 — mostly errored early |
| reflexion    | 1.0 — mostly errored early |

`plan_execute` fails LATE (burns the full turn budget); `react` and `reflexion` fail EARLY (first tool call throws an SDK error). Very different cost profiles.

</details>

<details>
<summary><b>The pilot run would have lied</b></summary>

Before the 75-cell run, a 25-cell pilot (one seed per cell instead of three) produced a completely different ranking:

| harness      | seeds=1 (N=5) | seeds=3 (N=15) | Δ success  |
|--------------|---------------|----------------|------------|
| single_shot  | 0.60          | 0.60           | 0.00       |
| plan_execute | 0.40          | 0.60           | **+0.20**  |
| reflexion    | 0.40          | 0.47           | +0.07      |
| minimal      | 0.60          | **0.27**       | **−0.33**  |
| react        | 0.40          | **0.13**       | **−0.27**  |

`minimal` dropped from tied-for-best to second-worst. `plan_execute` jumped from bottom to tied-for-best. **Three of five rankings flipped.** A single-seed pilot would have published the wrong story.

The summary CSV ships a `seed_success_std` column that flags the flaky ones:

| harness      | seed std | verdict                             |
|--------------|----------|-------------------------------------|
| plan_execute | 0.00     | Deterministic — single seed enough. |
| single_shot  | 0.00     | Deterministic — single seed enough. |
| minimal      | 0.12     | Mild variance.                      |
| reflexion    | 0.23     | **Flaky** — needs more seeds.       |
| react        | 0.23     | **Flaky** — needs more seeds.       |

Multi-turn tool loops branch on model stochasticity at every turn; a one-shot call has exactly one branch point. That's why the flippy ones are flippy.

**A second finding got stronger when I re-ran the N=15 matrix later:** even at 3 seeds per cell, `glm-4.7-flash` isn't fully deterministic run-to-run. Two independent N=15 runs produced these:

| harness      | first N=15 run | second N=15 run | Δ     |
|--------------|---------------:|----------------:|-------|
| single_shot  | 0.60           | 0.60            | 0.00  |
| minimal      | 0.27           | **0.60**        | +0.33 |
| plan_execute | 0.60           | 0.40            | −0.20 |
| reflexion    | 0.47           | 0.20            | −0.27 |
| react        | 0.13           | 0.40            | +0.27 |

Run-to-run, on the *same* frozen model and temperature, the success rates swung by up to 0.33. That means this article's specific numbers are this-run-specific, and even N=15 isn't a large enough sample to pin the rankings for this particular model. The **ordering of approximate tiers** is stable across runs (single_shot always near the top, reflexion always near the bottom), but exact ordering of the middle isn't.

For models that need stable rankings in articles or dashboards, N=15 × one run on `glm-4.7-flash` is not enough. You'd want several runs across model instances or seeds >=5 before calling any middle-of-the-pack ranking real.

</details>

### Where the time went

![HTML wall-clock heatmap](wall_clock_heatmap-glm-20260423.png)

Every orange/red square is a cell where the harness was running in circles. `plan_execute` burned its turn budget on nearly every task; `minimal` earned its better score this run by also trying more selectors, at a cost of 1,059 seconds total wall-clock.

---

## Part 2 — Code generation (easy tasks)

**Task**: implement 5 Python functions (fizzbuzz, fibonacci, is_anagram, binary_search, word_count) that pass a pytest suite. **Deterministic grader**: run the task's tests against the submission; success = pytest exit 0.

**Result**: **every harness scored 15/15**. These are textbook algorithm problems that `glm-4.7-flash` solves on the first try. The question shifts from "which works?" to "which is wasteful?"

### Headline chart

![code-gen resource bars](resource_bars-code-glm-20260423.png)

| harness          | wall-clock | input tokens | verdict                          |
|------------------|-----------:|-------------:|----------------------------------|
| single_shot      | 283 s      | 6,438        | fastest + cheapest               |
| retry_on_fail    | 328 s      | 6,168        | ready if first try fails (wasn't needed here) |
| react            | 381 s      | 9,189        | 35% slower than single_shot      |
| test_driven      | 478 s      | **35,469**   | 6× the tokens for zero accuracy gain |
| chain_of_thought | **598 s**  | 6,573        | 2× wall-clock of single_shot for CoT prompting |

### Per-task wall-clock

![code-gen wall-clock heatmap](wall_clock_heatmap-code-glm-20260423.png)

`single_shot` runs every task in 13–24 seconds. `chain_of_thought` sits at 30–56 seconds per task — the step-by-step prompt generates reasoning tokens the model has to produce before getting to the code.

<details>
<summary><b>Where test_driven's extra 29,000 input tokens went</b></summary>

`test_driven` ran the pytest subprocess **30 times** across the 75-cell matrix — that's 2.0 `run_tests` calls per cell on average. Each call feeds the full pytest output back (up to ~1,500 chars) into the model's context as a tool_result.

Per cell: base prompt + signature ≈ 400 tokens; first model reply with code ≈ 300 tokens out; a `run_tests` result ≈ 300 tokens back in; second model reply ≈ 300 tokens out. With ~3 turns per cell that's 1,000 input + 900 output per cell. Times 15 cells ≈ 15k in + 13k out — actual: 35k in + 9k out. The input side blew up more than estimated because every retry feeds the **full** test output back, not just the summary.

The extra tokens are paying for "insurance against the first attempt failing." **On this task set, the first attempt did not fail a single time.** The insurance was never needed.

</details>

### Token efficiency

![code-gen token efficiency](token_efficiency-code-glm-20260423.png)

All points sit at y=1.0 (perfect score). The only comparison is horizontal. `test_driven` is alone on the far right at 35k input tokens; everyone else sits around 6–9k. Almost a **6× gap** in tokens for identical accuracy.

<details>
<summary><b>What was surprising about the code-gen run</b></summary>

Three things, none of them what I expected going in:

1. **Every harness scored 100%.** I expected at least `retry_on_fail` to justify itself by rescuing a failed first attempt. It didn't — because no first attempts failed. `glm-4.7-flash` at `max_tokens=2048` solved every one of these five textbook algorithm problems on the first try, across 15 attempts per harness. A task set with ambiguous problems, tricky edge cases, or multi-file scope would produce a different shape; these are deliberately well-posed.
2. **`chain_of_thought` is expensive and offered nothing here.** "Think step by step" is everywhere in agent-engineering posts. On these tasks it produced 2× wall-clock over `single_shot` with the same success rate. Reasoning tokens the model has to generate before getting to the answer, for answers it already had. Not an argument against CoT in general — multi-step math and constraint satisfaction likely need it — but the signal here is clear: toy algorithms the model knows by heart don't benefit.
3. **`test_driven`'s tool-use is impressive but wasteful on this task set.** It successfully called `run_tests` 30 times across the matrix and responded correctly to pytest output. The plumbing works. But because the first draft was already correct, most of those 30 tool calls were "run tests on code I already know works" — pure confirmation. On tasks with a realistic first-attempt failure rate, this pattern would be valuable. Matching harness to task is everything.

</details>

---

## The combined lesson

Two experiments, two failure shapes, one conclusion:

```mermaid
flowchart TB
    A[task difficulty<br/>for the model] --> B1[hard<br/>HTML extraction]
    A --> B2[easy<br/>code generation]

    B1 --> C1[complex harnesses fail<br/>because model can't sustain<br/>multi-turn tool fidelity<br/>· reflexion 3/15 · plan_execute 7× wall-clock<br/>· ~70% NO_MATCH rate on CSS selectors]

    B2 --> C2[complex harnesses cost more<br/>because first-shot already wins<br/>· chain_of_thought 2× wall-clock<br/>· test_driven 6× tokens · same 15/15]

    C1 --> D[harness complexity has a cost.<br/>returns on that cost require:<br/>·· first-shot below accuracy target<br/>·· failures multi-turn-recoverable<br/>both conditions rarely hold at once.]

    C2 --> D

    D --> E[single_shot wins wall-clock<br/>in both experiments.<br/>if it hits your target, ship it.]
```

On hard tasks, the failure is "extra turns introduce new failure modes faster than they add accuracy." On easy tasks, the failure is "extra turns waste time and tokens for accuracy the model already had." The two shapes converge on the same engineering advice.

---

## Seven takeaways

1. **Always run `single_shot` as your baseline.** If it hits your accuracy target, ship it. You will not find a faster, cheaper, more reliable harness.
2. **Before investing in multi-turn harnesses, check your model's single-shot schema compliance.** Our `glm-4.7-flash` hit 100% compliance on `single_shot` but its multi-turn tool loops drift. If schema compliance is below ~90%, multi-turn harnesses will underperform on that model.
3. **`seeds=1` is not enough — and on some models, `seeds=3` isn't either.** Three of five rankings flipped between our N=5 pilot and the first N=15 run on HTML. Then two independent N=15 runs of the same matrix moved the middle-of-the-pack rankings by up to 0.33. If the ordering matters, you want multiple independent runs, not just multiple seeds in one run.
4. **The `submit_answer` universal output channel was load-bearing.** Every harness uses the same submission tool — no free-form text parsing. Eliminates a huge class of weak-model failures.
5. **`plan_execute` needs a feedback loop from executor to plan.** The executor gets `NO_MATCH` back on ~70% of CSS selector calls because the planner writes selectors before seeing the HTML. Minimum viable fix: a `revise_plan` tool. Correct fix: let the planner see the HTML.
6. **Tool-call error handling belongs in the harness, not the SDK.** `ResponseError: mismatched arg_key` propagated as hard termination on multiple `react` and `reflexion` cells. A naive "retry once on malformed tool_call" loop would have recovered most of these.
7. **"Harness complexity dominates within a tier" is a conditional claim.** It's only true where the base model's first-shot success rate is *below target* AND *multi-turn-recoverable*. On `glm-4.7-flash`, the HTML tasks failed condition 2 (model drifts on multi-turn); the code tasks failed condition 1 (model hit 100% first-shot). Complex harnesses paid returns in neither experiment.

---

## Honest scope

- **Two pilots, not two benchmarks.** 5 tasks × 3 seeds per experiment. Wilson CIs overlap for most pairs on HTML; on code-gen every harness hit 15/15 so CIs are uniform [0.80, 1.00].
- **Run-to-run variance is real on this model.** Two independent N=15 HTML runs produced middle-of-the-pack rankings that differ by up to 0.33. The *approximate tiers* (single_shot near top, reflexion near bottom) are stable; exact ordering within tiers isn't. The numbers in this article are from the most recent run; rerunning would produce different specifics with a similar shape.
- **One model.** `glm-4.7-flash` is an open-source 19 GB checkpoint on CPU-heavy local inference. Results on Claude Sonnet, GPT-4o, or Gemini 2.0 could reshuffle every ordering.
- **No held-out fixtures.** All HTML pages and code tasks were visible during harness development. See [`HELD_OUT.md`](../HELD_OUT.md) for the explicit decision.
- **Eight tag-moves in the commit log.** Every move documented in [`HARNESSES_FROZEN.md`](../HARNESSES_FROZEN.md) with a reason. No move happened after a matrix had been run against the newer tag — peek-and-patch is structurally prevented by the `check_freeze_gate()` pre-flight.

---

## Reproduce either experiment

```bash
git clone https://github.com/jaafar-benabderrazak/harness-bench && cd harness-bench
pip install -e ".[dev]"
cp .env.example .env         # ollama + glm-4.7-flash default, no API key required
ollama pull glm-4.7-flash:latest
pytest -q                    # 55 tests, all offline

# HTML extraction matrix (~60 min on a modest CPU/GPU)
python scripts/run_full.py --seeds 3 --yes

# Code generation matrix (~25-35 min)
python scripts/run_code_benchmark.py --seeds 3 --yes

# Post-process — produces CSV, all charts, article, trace viewer
python scripts/make_chart.py
```

Everything reproduces locally. Zero API dollars. The run files for the numbers in this article live in `results/runs/` (gitignored per-run; produced fresh on each execution).

---

<details>
<summary><b>Repo + links</b></summary>

- [Full repo](https://github.com/jaafar-benabderrazak/harness-bench) — source, tests, all 8 harness implementations, 2 task types, 55-test offline suite
- [Offline demo](https://github.com/jaafar-benabderrazak/harness-bench/blob/main/scripts/demo_matrix.py) — exercises the pipeline with a deterministic fake model (no API spend, no local model needed)
- [`HELD_OUT.md`](../HELD_OUT.md) — held-out fixture decision + rationale
- [`HARNESSES_FROZEN.md`](../HARNESSES_FROZEN.md) — freeze manifest + tag-move log
- [`README.md`](../README.md) — quickstart, pre-registered hypothesis
- Raw trace data lives in `traces/{harness}/{task}/*.jsonl`; every number here reproducible via `python scripts/make_chart.py` on a committed run file
- Freeze commit: `9977e85` (`git rev-parse harnesses-frozen`)

</details>
