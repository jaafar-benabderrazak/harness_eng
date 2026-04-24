# I benchmarked 8 agent frameworks — ReAct scored 2/15, the no-framework baseline scored 9/15

![Editorial illustration — an elaborate Rube Goldberg machine of gears, belts, gauges, and copper pipes labeled "planner", "executor", "critic", "retry loop", and "tool dispatch", straining and emitting a puff of smoke. Next to it on the same desk sits a single glossy green button labeled "ASK ONCE" with a checkmark, already lit and unbothered.](hero.png)

It lost to 15 lines of code that dump the HTML into a single prompt and ask for JSON back.

If your team is deciding between LangGraph, CrewAI, OpenAI Agents SDK, or a custom ReAct loop this quarter, this is the baseline you're forgetting to benchmark.

---

## The frameworks you're probably running

Every harness I tested maps to something in the ecosystem you already know:

- `single_shot` → a direct API call. No framework.
- `react` → LangChain's `AgentExecutor` / `create_react_agent`. The default.
- `plan_execute` → LangGraph plan-and-execute, OpenAI Agents SDK planner patterns.
- `reflexion` → Reflexion-paper implementations, CrewAI critic agents.
- `test_driven` → Aider, Cursor agent mode, Devin-style loops.
- `chain_of_thought` → any "think step by step" system prompt.
- `retry_on_fail` → CI-style retry wrappers, most production error-handling.

I ran all eight against the same frozen open-source model (`glm-4.7-flash`, 19 GB, local Ollama, temperature 0) across two benchmarks: messy HTML extraction (hard for this model) and Python code generation (easy). 150 graded runs. Every harness ends on the same `submit_answer` tool so I'm comparing control flow, not output parsing.

The finding in one line: **harness complexity has a cost. You only get a return on that cost when the base model's first-shot accuracy is both below target AND multi-turn-recoverable. Both conditions rarely hold at once.**

---

## Experiment 1: HTML extraction (hard for this model)

Pull 3–5 structured fields (brand, price, title, date) from 5 messy HTML pages. Deterministic grader: per-field normalized exact match.

![Success rate vs wall-clock on HTML extraction — single_shot sits in the top-left corner (high accuracy, low time); plan_execute is isolated far right at 1,600+ seconds](frontier-glm-20260423.png)

| harness       | success    | wall-clock total |
|---------------|-----------:|-----------------:|
| single_shot   | **9/15**   | **228 s**        |
| minimal       | 9/15       | 1,059 s          |
| plan_execute  | 6/15       | 1,615 s          |
| reflexion     | 3/15       | 977 s            |
| react         | 2/15       | ~220 s           |

`single_shot` and `minimal` tied for best accuracy. `single_shot` got there in under 4 minutes. `plan_execute` spent 27 minutes for a *worse* score. The default ReAct loop — the one shipping as the entrypoint in most frameworks — scored 2/15.

Every complex harness had the same failure mode: they needed the model to do the right thing multiple turns in a row, and the model drifted.

![Per-task field-accuracy heatmap — product_01 destroys react and minimal (0/3); paper_01 defeats reflexion (0/3)](field_heatmap-glm-20260423.png)

`product_01` destroys the multi-turn harnesses because the HTML uses `<div class="brand-line">Brand: <a>Lumina</a></div>` — no generic CSS selector catches it. `paper_01` defeats `reflexion` entirely; the critique loop locked onto a wrong selector and kept retrying it.

![Stop-reason distribution — single_shot is pure green (always cleanly submits); react is more than half red (SDK-boundary errors); plan_execute burns its full turn budget on 60% of cells](stop_reasons-glm-20260423.png)

`single_shot` is pure green — always cleanly submits. `react` is more than half red: SDK-boundary errors killed 8 of 15 cells. `plan_execute` hit its 12-turn cap on 60% of cells because the planner wrote wrong selectors and the executor had no way to revise them.

### The damning number

In one N=15 run, `plan_execute` fired the selector `span.date-submitted-date` **417 times** across 75 cells. That selector does not exist on any of the five pages. The planner invented it. The executor had no feedback path, so it kept firing into the void. **87.6%** of that run's `plan_execute` CSS-select calls returned nothing.

Across all multi-turn harnesses, roughly two out of three tool calls were wasted guesses.

### What this costs if you're paying by the token

At frontier-model list prices (roughly $2.50/M input, $10/M output):

- `single_shot`: ~$0.0045 per HTML extraction
- `plan_execute`: ~$0.045 per HTML extraction

**10× the cost per task for a lower success rate.** At 10,000 tasks/day, that's about **$140k/year** of ceremony — paid for an agent that gets the answer less often than the baseline.

### The variance finding nobody publishes

I ran the same matrix twice on the same frozen model at temperature 0. Middle-of-the-pack rankings swung by up to **0.33 in success rate** between runs:

| harness      | run 1 | run 2 |
|--------------|------:|------:|
| single_shot  | 0.60  | 0.60  |
| minimal      | 0.27  | 0.60  |
| plan_execute | 0.60  | 0.40  |
| reflexion    | 0.47  | 0.20  |
| react        | 0.13  | 0.40  |

The *approximate tiers* stay stable — `single_shot` near the top, `reflexion` near the bottom. But exact middle orderings aren't reliable at N=15, even deterministic. Multi-turn tool loops branch on stochasticity at every turn. A one-shot call has exactly one branch point.

If you're publishing a harness comparison at seeds=1, you're publishing a flip of a coin.

---

## Experiment 2: Code generation (easy for this model)

Implement 5 Python functions (fizzbuzz, fibonacci, is_anagram, binary_search, word_count) that pass a pytest suite.

**Every harness scored 15/15.** The question stops being "which one works?" and becomes "which one is wasteful?"

![Resource bars — when everyone scores 100%, the only axes are wall-clock and tokens. test_driven uses 6× the input tokens; chain_of_thought takes 2× the wall-clock](resource_bars-code-glm-20260423.png)

| harness          | wall-clock | input tokens |
|------------------|-----------:|-------------:|
| single_shot      | 283 s      | 6,438        |
| retry_on_fail    | 328 s      | 6,168        |
| react            | 381 s      | 9,189        |
| test_driven      | 478 s      | **35,469**   |
| chain_of_thought | **598 s**  | 6,573        |

`chain_of_thought` took 2× the wall-clock for the same result — "think step by step" is just tokens the model has to generate before getting to the answer it already had. `test_driven` used **6× the input tokens** of any other harness, because every `run_tests` call feeds the full pytest output back into the model's context.

![Token efficiency scatter — all five harnesses cluster at y=1.0 (perfect accuracy). The only spread is horizontal: test_driven is alone on the far right of the log-scale token axis](token_efficiency-code-glm-20260423.png)

All at y=1.0. `test_driven` alone on the far right — **5.8× the tokens of `retry_on_fail` for identical accuracy.**

At frontier-model prices, `test_driven` runs at about $0.012 per function vs `single_shot`'s $0.005. Roughly **$25k/year of overhead at 10,000 tasks/day** for insurance against a first-attempt failure that never happened.

---

## When complex harnesses DO pay (the honest limit)

I won't pretend complexity is always wrong. The conditions where `test_driven`, `reflexion`, or `plan_execute` earn their cost:

- **First-shot accuracy is genuinely below target** — if your baseline hits 95%, no retry loop will help. If it hits 40%, every extra turn is a real chance to climb.
- **Failures are structurally recoverable** — the model needs a signal it can actually act on (a concrete test failure, a visible schema mismatch). If your multi-turn loop feeds the model "NO_MATCH" on CSS selectors for 12 turns, you're not recovering anything; you're paying to fail more elaborately.
- **The base model's multi-turn tool-use reliability exceeds ~90% per turn.** Below that, each extra turn multiplies the odds of SDK-boundary errors. On weak models, complexity accelerates failure.

On a stronger model (Claude Sonnet 4.6, GPT-4o, Gemini 2.5), all three conditions plausibly hold and `test_driven`-style loops probably do pay. On a weak local model, none of them do.

Know which regime you're in before picking a harness.

---

## The three takeaways worth remembering

**1. Always benchmark `single_shot` first.** Fifteen lines of code. If it hits your target, ship it. The fancy framework is a cost you can only justify against a measured gap.

**2. `seeds=1` lies. On weak models, `seeds=3` also lies about middle rankings.** Two independent N=15 runs of my matrix moved middle-of-the-pack rankings by up to 0.33. If ordering matters in your eval, run the matrix multiple times, not just more seeds.

**3. Harness complexity has a cost that pays returns only when first-shot is below target AND failures are multi-turn-recoverable.** Both rarely hold at once on weak models. Check your regime before adding a retry loop.

---

## Your Monday action

Before your next sprint, add one 15-line `single_shot` baseline to your eval harness. Make it the first row in your results table. If your production agent — whatever framework it's built on — doesn't beat it by more than 10%, rip out the production agent.

Most of the ceremony around modern agents is paid for a problem the model already solved in one call.

---

**Full writeup, code, and reproducible 150-run matrix:** [github.com/jaafar-benabderrazak/harness-bench](https://github.com/jaafar-benabderrazak/harness-bench). All local inference, no API keys required, 55 offline tests. If you want to run this against Claude, GPT-4o, or Gemini and send me the numbers, I'll publish a follow-up.
