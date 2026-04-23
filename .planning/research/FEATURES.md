# Feature Research

**Domain:** LLM agent harness engineering / benchmarking harness experiments (portfolio-grade controlled experiment repo)
**Researched:** 2026-04-23
**Confidence:** HIGH for table stakes (convergent across Inspect AI, lm-eval-harness, OpenAI evals, Anthropic's own eval guidance); MEDIUM for differentiator framing (novelty is the "harness-as-variable" angle, which is underserved in current eval tooling).

---

## Framing

A credible harness-comparison repo is judged on three axes:

1. **Methodological integrity** — does the experimental design actually isolate the harness as the independent variable? (frozen model, frozen prompts per harness, pre-registered freeze point, deterministic grader)
2. **Evidence quality** — can a skeptical reader reproduce numbers and drill into failures? (JSONL traces from call 1, deterministic scoring, cost accounting, seed control)
3. **Narrative payload** — does the repo produce a shareable artifact (chart + article + trace viewer) without a second pass of manual work?

Features below are categorized against these axes. Portfolio-piece success = all three axes cleared with a long-weekend budget.

---

## Feature Landscape

### Table Stakes (Users Expect These — Credibility Features)

Without any one of these, a reader with LLM-eval literacy will dismiss the experiment. These are **non-negotiable for the article to be credible**.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Single frozen model routing** (all harnesses call through `model.call()`) | Isolates harness as the independent variable; the whole experimental claim collapses if any harness can drift on temperature/max_tokens/model_id | LOW | Already built per PROJECT.md. Enforce via base class: any `anthropic` import outside `model.py` is a defect. Add a pytest that greps source for rogue imports. |
| **Deterministic grader** (per-field normalized exact match) | LLM-as-judge on a 5-task pilot introduces judge noise larger than harness signal; deterministic scoring is the whole reason HTML extraction was chosen over SWE-bench | LOW | Already built. Must handle whitespace, case, punctuation normalization consistently. Document the normalization rules in the article. |
| **JSONL traces written from call 1** | Retrofitting a trace writer post-run produces empty evidence for the "surprising failures" section; traces are the most shareable artifact | LOW | Already built. Append-only, one line per model/tool call, schema includes: timestamp, harness_id, task_id, seed, role, content, tokens_in, tokens_out, cost_usd, latency_ms, tool_name (nullable). |
| **Temperature=0 + seed control** | Any stochastic variance at n=5 tasks drowns the harness signal; reviewers will ask about seeds within the first two paragraphs | LOW | temp=0 alone is not fully deterministic with Anthropic API; run N seeds (N=3 minimum) and report mean ± range. Document that temp=0 is not a guarantee. |
| **Cost + token accounting per call** | "Harness A costs 5x more" is half the headline; you cannot compute it without per-call cost fields in the trace | LOW | Compute at trace-write time using pricing constants in config, not post-hoc from token counts — pricing can change and you want the run to record what it actually cost at the time. |
| **Latency accounting per call** | Third axis of the frontier chart (success vs cost vs latency); also exposes harnesses that loop | LOW | `time.perf_counter()` around the API call; do not include JSON parsing or trace-write time in the measurement. |
| **Aggregate summary table (CSV)** | A reader cannot verify a chart without seeing the numbers; CSV is the lingua franca | LOW | One row per (harness, task, seed); columns: success, cost_usd, latency_s, tokens_in, tokens_out, n_tool_calls, n_turns. Post-run script from JSONL. |
| **Success-rate-vs-cost frontier chart** | This IS the headline artifact; without it there is no article | LOW | matplotlib, one point per harness (mean across tasks+seeds), error bars for seed variance. Pareto frontier drawn. |
| **Runnable end-to-end on a laptop with one API key** | Reproducibility = a stranger can replicate; if it needs docker/k8s the "portfolio piece" framing fails | LOW | Single entry point `python -m harness_eng.runner`. No external services. |
| **Cost estimator (dry-run) gate** | A frontier-model full matrix at 5×5×3 seeds can still surprise; shipping without the gate is how people get $200 surprise bills | LOW | Count planned calls × est. tokens × pricing. Require `--confirm-cost` flag over a threshold. Gate, not afterthought (per PROJECT.md constraint). |
| **README that onboards in 5 minutes** | Portfolio piece that requires a 30-minute setup is not a portfolio piece | LOW | `uv pip install -e .`, set `ANTHROPIC_API_KEY`, `python -m harness_eng.estimate`, `python -m harness_eng.runner`. Screenshot of final chart in the README. |
| **Pytest suite for grader + trace schema + harness contract** | A repo without tests that claims "reproducibility" reads as amateur; reviewers check for tests before reading results | LOW | Grader unit tests on known pairs; trace schema validation; each harness passes a single canned task; mock `model.call()` so tests run offline. |
| **Harness freeze discipline documented** | Iterating on losing harnesses after seeing results is the classic p-hacking failure mode; must be called out explicitly in the article | LOW | Git tag `harnesses-frozen-v1` before first full matrix run. Article cites the tag. Methodology section explains why. |
| **Five harnesses implemented as specified** (single_shot, react, plan_execute, reflexion, minimal) | Fewer than this and the "spread" claim has insufficient data points; more than this blows the long-weekend budget | MEDIUM | Three of five already built. Remaining: reflexion (requires critique loop), minimal (requires removing `read_html` tool). |
| **Article draft autogenerated from results** | Hand-written prose will drift from the numbers on any rerun; auto-generation keeps article and data in sync | MEDIUM | Jinja2 template with placeholders for numbers, chart paths, top-3 failure traces. Post-run script fills it. |

### Differentiators (Competitive Advantage for a Portfolio Piece)

Features that elevate this from "another eval repo" to "the harness engineering piece". Align with PROJECT.md's core value: *harness design dominates model choice within a tier.*

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Harness-as-variable framing itself** | Current eval ecosystem (Inspect AI, lm-eval-harness, HELM) treats the harness as fixed and varies the model; inverting this is the novel contribution. Most portfolio eval repos re-run existing benchmarks on new models — this one asks a different question | N/A (design, not code) | This is the whole pitch. Hammer it in README, article abstract, and chart title. Do not let the repo read as "yet another eval harness". |
| **Minimal harness as structural constraint, not prompt** (omits `read_html` tool entirely) | Demonstrates the author understands that "context pruning via prompt" is wishful thinking; prompts get ignored, tool registries don't | LOW | Already decided per PROJECT.md. Call this out in the article — it's a subtle methodology point that separates the author from a prompt-tweaker. |
| **Per-field accuracy heatmap** | Reveals *which* fields each harness misses, not just overall scores; converts "harness A is better" into "harness A is better at nested-list extraction but worse at dates" | LOW | matplotlib heatmap, harnesses × fields, cell = success rate across tasks+seeds. Secondary chart, one function. |
| **Standalone HTML trace viewer** | Readers can click into failure traces in the browser without installing anything; massively lowers the bar for the article's "surprising failures" section to land | MEDIUM | Single HTML file, vanilla JS, reads JSONL via fetch or embedded data. Collapsible tool calls, syntax-highlighted JSON, filterable by harness/task/seed. Two-evening job if scoped tight. |
| **Auto-drafted article with numbers injected** | Most eval repos ship a README and no narrative; a drafted Medium-ready article off the repo's own output is rare and directly shareable | MEDIUM | Already listed as table stakes-adjacent in PROJECT.md, but the *quality* of the auto-generation is the differentiator: embed the chart, quote top failures, cite the git tag for freeze. |
| **GitHub Actions CI: pytest + 1-task pilot on every PR** | Green check on the repo signals "this actually runs" to a drive-by reviewer; most portfolio repos don't have this | MEDIUM | Pilot runs one task × one harness × one seed with API key from secrets. Budget: ~$0.02 per PR. Worth it for the green check. Gate pytest first, pilot second (so test failures are cheap). |
| **Pre-registered hypothesis in README** | "We expect 2–4x spread in success rate and 5–10x spread in cost" published *before* the run gives the experiment a falsifiable prediction; this is what turns a blog post into a credible piece | LOW | One paragraph, dated, git-committed. If the actual result contradicts, the article reports that honestly — which is itself a differentiator. |
| **Per-call retry+error trace** (not just success traces) | Most eval tooling silently retries on 429/5xx and loses the data; logging retry attempts is where pathological harness behavior shows up (react harness spinning on a bad tool response) | LOW | Trace entry for every attempt, including failures. Harness does not see retries; model.py handles them and logs them. |
| **Cost-per-success metric** (not just aggregate cost) | Dollars-per-correct-extraction is what a practitioner actually cares about; reporting it makes the piece useful, not just academic | LOW | One more column in the summary table. Free if the other accounting is there. |

### Anti-Features (Deliberately NOT Built — Scope Discipline)

Things that seem like natural extensions but would either blow the timeline, contaminate the experiment, or add engineering surface without changing the story.

| Anti-Feature | Why Requested / Tempting | Why Problematic | Alternative |
|--------------|--------------------------|-----------------|-------------|
| **Multi-provider model support** (OpenAI, Gemini, local) | "Wouldn't it be cooler to also show GPT-5 results?" | Contaminates the experimental control — the whole claim is "harness dominates model within a tier"; adding models conflates two variables and the article loses its point | Single frozen Claude Sonnet. If multi-provider is interesting, that's a *separate* follow-up project that holds the harness constant. |
| **Beyond 5 tasks / expand to 40** | Original pitch mentioned 40 | Portfolio value is harness engineering, not fixture volume; 35 more tasks = 30+ hours of labeling that doesn't change the story | Keep JSONL task format open; note in README that users can append tasks. Move on. |
| **SWE-bench Lite / WebArena / AgentBench adoption** | More prestigious benchmarks = more credible piece | Require sandboxed code execution (docker), double the engineering surface, and introduce grader complexity that masks harness differences behind infrastructure noise | HTML extraction with deterministic grader. Cite SWE-bench in the "future work" section of the article. |
| **LLM-as-judge scoring** | Popular in 2024–2026 eval tooling | Judge noise at n=5 tasks is larger than harness signal; reader will ask "is the effect from the judge or the harness?" — deterministic grader sidesteps this entirely | Normalized exact match. Call out in methodology that this is a deliberate choice *against* the industry trend, with rationale. |
| **OpenTelemetry / W&B / MLflow integration** | Industry standard for production observability | Production observability problem, not experimental evidence problem; JSONL traces are *better* for the article because they're grep-able and embeddable | JSONL + HTML viewer. Cite OTel as out-of-scope in the article's "production considerations" sidebar. |
| **Parallel run orchestration across machines** | Faster runs | 5×5×3=75 calls run sequentially in ~10 minutes at p95 latency; parallelism adds rate-limit handling, merge logic, and no speedup worth the code | Sequential `for` loop. Done. |
| **Tuning losing harnesses after seeing results** | "ReAct did badly, let me just fix the prompt" | Invalidates the comparison — you're now selecting harnesses that beat the held-out set, which is the textbook portfolio-piece methodology error | Freeze harnesses at a git tag before the full matrix. The article *explains* what the losing harnesses got wrong; it does not fix them. |
| **Docker / devcontainer / WSL requirement** | "Makes reproducibility cleaner" | Breaks Windows bash constraint from PROJECT.md; raises onboarding friction above the 5-minute README target | `uv pip install -e .` + `.env`. Any shell. |
| **Prompt-engineering rounds on each harness** | "Each harness should be shown at its best" | Unbounded time sink; defining "best" per harness is subjective and breaks the freeze discipline | Each harness gets one good-faith prompt, reviewed once, then frozen. Article acknowledges this is not prompt-optimized. |
| **Streaming / chat UI / interactive mode** | "Demo would look cool" | Zero evidentiary value; the artifact is a chart + article, not a live demo | Trace viewer gives the interactive experience post-hoc, cheaper. |
| **Hyperparameter sweeps** (temperature, max_tokens, model variants) | "Could also vary ..." | Adds independent variables that obscure the harness signal | Freeze all hyperparameters in `config.py`. Vary harness only. |
| **Fancy web dashboard / Streamlit app** | Looks impressive | Engineering cost > narrative value; readers want a chart in a blog post, not a hosted app | Static PNG chart embedded in README + auto-drafted article. |
| **Retry logic inside harnesses** | "React should handle tool failures gracefully" | Smuggles reliability engineering into the harness definition; different harnesses will end up with different retry policies and the comparison becomes about retry strategy | Retries live in `model.py` only (transport concern). Harnesses see raw success/fail from tools and handle them in-character. |
| **Token budget enforcement per harness** | "Fair comparison by capping context" | Capping context changes the harness; react vs plan_execute have different context profiles *because* of the harness design and that's what's being measured | No per-harness token caps. Report token usage as a result, not a constraint. |

---

## Feature Dependencies

```
config.py (frozen model, pricing constants)
    └──required by──> model.py (single API entry point)
                         └──required by──> trace.py (writes per-call records)
                                              └──required by──> harnesses/*
                                                                   └──required by──> runner.py (matrix loop)
                                                                                        └──required by──> analysis/summarize.py (CSV + chart)
                                                                                                             └──required by──> analysis/heatmap.py
                                                                                                             └──required by──> article/draft.py
                                                                                                             └──required by──> viewer/trace_viewer.html

estimator.py ──gates──> runner.py (cost gate before matrix run)

tests/* ──gates──> CI (must pass before pilot runs)

tasks/loader.py + tasks/tasks.jsonl + tasks/fixtures/
    └──required by──> grader.py
                         └──required by──> runner.py

harness freeze tag ──precedes──> first full matrix run (methodology gate)
```

### Dependency Notes

- **trace.py before harnesses:** PROJECT.md is explicit — traces from call 1, not retrofitted. Any harness built before the trace writer will have to be reworked, and reworking silently drops evidence.
- **estimator.py before runner.py full matrix:** Gate, not afterthought. Enforce with a command flag or a `.confirmed_cost` marker file.
- **All five harnesses before analysis:** Running the frontier chart on partial data invites the temptation to "just fix the last harness" after seeing where it sits. Complete the set, then freeze, then run.
- **Summarize.py before draft.py:** Article generator reads the CSV, not raw JSONL. Keeps the templating script simple.
- **Trace viewer is independent:** Reads JSONL directly, no Python runtime dependency on the rest of the pipeline. Can be developed in parallel with analysis.
- **CI depends on everything:** Green CI = pytest passes + 1-task pilot runs + trace validates. Last thing to add, not first.

---

## MVP Definition

### Launch With (v1 — the portfolio piece ships this)

Everything required for the article to be credible and reproducible.

- [ ] All 5 harnesses implemented and frozen at a git tag (2 remaining: reflexion, minimal)
- [ ] Runner executes full 5×5×3-seed matrix end-to-end
- [ ] JSONL traces with cost, latency, tokens, retries — from call 1
- [ ] Deterministic grader with documented normalization rules
- [ ] Cost estimator that gates full runs
- [ ] Summary CSV + frontier chart (PNG)
- [ ] Per-field accuracy heatmap (PNG)
- [ ] Auto-drafted article (Markdown) with numbers, chart, top failure excerpts injected
- [ ] Standalone HTML trace viewer
- [ ] Pytest suite covering grader, trace schema, harness contract, model-routing-singleton
- [ ] GitHub Actions CI: pytest + 1-task pilot
- [ ] README with 5-minute quickstart + pre-registered hypothesis
- [ ] Pre-run git tag `harnesses-frozen-v1`; article cites it

### Add After Validation (v1.x — only if the v1 article lands and generates feedback)

- [ ] Task count expansion (10–20 tasks) *only if* readers ask for it and the fixture labor is affordable
- [ ] Error-class taxonomy in heatmap (tool-loop vs hallucination vs format)
- [ ] Noisier HTML fixtures (more realistic scraping targets)
- [ ] Per-harness ablation: e.g., react-without-reflection, plan_execute-with-single-plan

### Future Consideration (v2+ — separate project, not this repo)

- [ ] Multi-provider comparison (hold harness constant, vary model) — this is the *inverse* experiment and deserves its own repo
- [ ] Code-execution benchmarks (SWE-bench Lite) with the same harness comparison
- [ ] WebArena/BrowserGym benchmarks
- [ ] Production observability story (OTel, tracing backend integration)
- [ ] Larger-N statistical treatment (confidence intervals, power analysis)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Remaining 2 harnesses (reflexion, minimal) | HIGH | MEDIUM | P1 |
| Runner (matrix loop) | HIGH | LOW | P1 |
| JSONL trace schema + enforcement | HIGH | LOW | P1 |
| Cost estimator gate | HIGH | LOW | P1 |
| Summary CSV + frontier chart | HIGH | LOW | P1 |
| Auto-drafted article | HIGH | MEDIUM | P1 |
| Pytest suite | HIGH | LOW | P1 |
| Per-field heatmap | MEDIUM | LOW | P1 |
| HTML trace viewer | MEDIUM | MEDIUM | P2 |
| GitHub Actions CI | MEDIUM | MEDIUM | P2 |
| Pre-registered hypothesis paragraph | MEDIUM | LOW | P1 |
| Retry logging in traces | MEDIUM | LOW | P1 |
| Cost-per-success metric | MEDIUM | LOW | P1 |
| Multi-provider support | — | HIGH | DO NOT BUILD |
| LLM-as-judge | — | MEDIUM | DO NOT BUILD |
| OTel integration | — | MEDIUM | DO NOT BUILD |
| Docker | — | MEDIUM | DO NOT BUILD |

**Priority key:**
- P1: Ships in v1, article does not go out without it
- P2: Ships in v1 if time allows; graceful degradation if cut (viewer → link to raw JSONL; CI → green badge missing but results still valid)
- DO NOT BUILD: Anti-features; explicitly scoped out

---

## Competitor / Reference Analysis

| Feature | Inspect AI (UK AISI) | lm-eval-harness (EleutherAI) | OpenAI evals | This Project |
|---------|----------------------|------------------------------|--------------|---------------|
| Primary axis of variation | Model (harness fixed) | Model (harness fixed) | Model (harness fixed) | **Harness (model fixed)** |
| Scoring | Mix: exact match, model-graded, pattern | Mostly exact match / log-likelihood | Mix incl. model-graded | Deterministic exact match only |
| Trace format | Custom log + Inspect View | Minimal logging | Custom | JSONL, grep-able |
| Trace viewer | Inspect View (Python service) | None | Web UI (hosted) | Standalone HTML, no runtime |
| Sandboxing | Docker/K8s/Modal | None | None | None (HTML only) |
| Agent framework built-in | Yes (ReAct, multi-agent) | No | Partial | **Five implementations compared** |
| Cost accounting | Yes | Partial | Yes | Yes (per-call, pricing-at-run) |
| Target user | Safety researchers | ML researchers | OpenAI customers | Portfolio reader / AI engineer |
| Setup complexity | HIGH (pip + config + sandbox) | MEDIUM | MEDIUM | **LOW (5-min README)** |

**Positioning:** This project is not competing with Inspect AI on features. It is making a different argument (harness matters more than model within a tier) using the minimum viable eval infrastructure. The differentiation is the *question asked*, backed by enough infrastructure to be credible.

---

## Sources

- [Inspect AI framework (UK AI Security Institute)](https://inspect.aisi.org.uk/) — feature reference for what a "serious" eval harness looks like (HIGH confidence)
- [inspect_ai GitHub](https://github.com/UKGovernmentBEIS/inspect_ai) — trace format, scorer patterns (HIGH)
- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — first-party guidance on agent eval design (HIGH)
- [Agent Harness Engineering Guide 2026 — QubitTool](https://qubittool.com/blog/agent-harness-evaluation-guide) — ecosystem survey of harness testing practices (MEDIUM)
- [Evaluating AI Agents in Practice — InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/) — industry lessons on benchmark design (MEDIUM)
- [LLM Evaluation Frameworks 2026 — Future AGI](https://futureagi.substack.com/p/llm-evaluation-frameworks-metrics) — current-year feature baselines (MEDIUM)
- [Evaluating LLMs — EleutherAI](https://www.eleuther.ai/projects/large-language-model-evaluation) — lm-eval-harness positioning (HIGH)
- `.planning/PROJECT.md` — authoritative project scope and constraints (HIGH)

---
*Feature research for: LLM agent harness benchmarking experiments*
*Researched: 2026-04-23*
