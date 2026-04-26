# I benchmarked 8 agent frameworks — ReAct scored 2/15, the no-framework baseline scored 9/15

![Same model, sixteen harnesses, two tasks](thumbnail.png)

It lost to 15 lines of code that dump the HTML into a single prompt and ask for JSON back.

If your team is deciding between LangGraph, CrewAI, OpenAI Agents SDK, or a custom ReAct loop this quarter, this is the baseline you're forgetting to benchmark.

---

## The frameworks you're probably running

Every harness I tested maps to something in the ecosystem you already know:

- **`single_shot`** → a direct API call. No framework.
- **`react`** → LangChain's `AgentExecutor` / `create_react_agent`. The default.
- **`plan_execute`** → LangGraph plan-and-execute, OpenAI Agents SDK planner patterns.
- **`reflexion`** → Reflexion-paper implementations, CrewAI critic agents.
- **`test_driven`** → Aider, Cursor agent mode, Devin-style loops.
- **`chain_of_thought`** → any "think step by step" system prompt.
- **`retry_on_fail`** → CI-style retry wrappers, most production error-handling.

I ran all eight against the same frozen open-source model (`glm-4.7-flash`, 19 GB, local Ollama, temperature 0) across two benchmarks: messy HTML extraction (hard for this model) and Python code generation (easy). 150 graded runs. Every harness ends on the same `submit_answer` tool so I'm comparing control flow, not output parsing.

The finding in one line: **harness complexity has a cost. You only get a return on that cost when the base model's first-shot accuracy is both below target AND multi-turn-recoverable. Both conditions rarely hold at once.**

---

## Experiment 1: HTML extraction (hard for this model)

Pull 3–5 structured fields (brand, price, title, date) from 5 messy HTML pages. Deterministic grader: per-field normalized exact match.

| harness       | success    | wall-clock total |
|---------------|-----------:|-----------------:|
| single_shot   | **9/15**   | **228 s**        |
| minimal       | 9/15       | 1,059 s          |
| plan_execute  | 6/15       | 1,615 s          |
| reflexion     | 3/15       | 977 s            |
| react         | 2/15       | ~220 s           |

`single_shot` and `minimal` tied for best accuracy. `single_shot` got there in under 4 minutes. `plan_execute` spent 27 minutes for a *worse* score. The default ReAct loop — the one shipping as the entrypoint in most frameworks — scored 2/15.

Every complex harness had the same failure mode: they needed the model to do the right thing multiple turns in a row, and the model drifted.

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

| harness          | wall-clock | input tokens |
|------------------|-----------:|-------------:|
| single_shot      | 283 s      | 6,438        |
| retry_on_fail    | 328 s      | 6,168        |
| react            | 381 s      | 9,189        |
| test_driven      | 478 s      | **35,469**   |
| chain_of_thought | **598 s**  | 6,573        |

`chain_of_thought` took 2× the wall-clock for the same result — "think step by step" is just tokens the model has to generate before getting to the answer it already had. `test_driven` used **6× the input tokens** of any other harness, because every `run_tests` call feeds the full pytest output back into the model's context.

Going in, I expected `retry_on_fail` to justify itself by rescuing a failed first attempt. It didn't — because no first attempts failed. The insurance was never needed.

This isn't an argument against test-driven or retry patterns in general. On tasks where the first attempt has a realistic failure probability, those patterns earn their tokens. On textbook algorithms this model already knows by heart, they're pure overhead.

---

## When complex harnesses DO pay (the honest limit)

I won't pretend complexity is always wrong. The conditions where `test_driven`, `reflexion`, or `plan_execute` earn their cost:

- **First-shot accuracy is genuinely below target** — if your baseline hits 95%, no retry loop will help. If it hits 40%, every extra turn is a real chance to climb.
- **Failures are structurally recoverable** — the model needs a signal it can actually act on (a concrete test failure, a visible schema mismatch). If your multi-turn loop feeds the model "NO_MATCH" on CSS selectors for 12 turns, you're not recovering anything; you're paying to fail more elaborately.
- **The base model's multi-turn tool-use reliability exceeds ~90% per turn.** Below that, each extra turn multiplies the odds of SDK-boundary errors. On weak models, complexity accelerates failure.

On a stronger model (Claude Sonnet, GPT-4o, Gemini), all three conditions plausibly hold and `test_driven`-style loops probably do pay. On a weak local model, none of them do.

Know which regime you're in before picking a harness.

---

## The three takeaways worth remembering

**1. Always benchmark `single_shot` first.** Fifteen lines of code. If it hits your target, ship it. The fancy framework is a cost you can only justify against a measured gap.

**2. `seeds=1` lies. On weak models, `seeds=3` also lies about middle rankings.** Two independent N=15 runs of my matrix moved middle-of-the-pack rankings by up to 0.33. If ordering matters in your eval, run the matrix multiple times, not just more seeds in one.

**3. Harness complexity has a cost that pays returns only when first-shot is below target AND failures are multi-turn-recoverable.** Both rarely hold at once on weak models. Check your regime before adding a retry loop.

---

## Your Monday action

Before your next sprint, add one 15-line `single_shot` baseline to your eval harness. Make it the first row in your results table. If your production agent — whatever framework it's built on — doesn't beat it by more than 10%, rip out the production agent.

Most of the ceremony around modern agents is paid for a problem the model already solved in one call.

---

**Full writeup, code, and reproducible 150-run matrix:** [github.com/jaafar-benabderrazak/harness-bench](https://github.com/jaafar-benabderrazak/harness-bench). All local inference, no API keys required, 87 offline tests. The repo also catalogs eight more harness strategies (Tree of Thoughts, multi-agent, Program-Aided Language models, self-consistency, schema-validated tool dispatch, streaming early-termination, in-cell memoization, loop-detection-and-recovery), implemented and unit-tested but matrix re-run pending stronger hardware. If you have a beefier machine and want to run the expanded matrix and send the numbers, I'll publish a follow-up.
