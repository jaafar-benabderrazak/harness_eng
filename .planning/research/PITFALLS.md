# Pitfalls Research

**Domain:** LLM agent-harness benchmarking (controlled experiment, same model across harnesses)
**Researched:** 2026-04-23
**Confidence:** HIGH for methodology pitfalls (well-established in the ML-eval and agent-benchmark literature: BIG-bench, HELM, SWE-bench lessons, LangChain/LlamaIndex harness eval post-mortems). MEDIUM for the subtler engineering traps (Anthropic SDK tool-use token accounting, structured-output determinism) — verified against the project's existing code surface but not against a specific published post-mortem.

The purpose of this document is to prevent the article from being embarrassing after publication. Two failure classes dominate: (1) methodological contamination — the numbers are real but measure the wrong thing; (2) silent accounting bugs — the numbers measure the right thing but are computed wrong in a way that happens to flatter one harness. Both invalidate the comparison equally. The defenses below aim at structural impossibility (code paths that cannot be written incorrectly) over procedural discipline (code paths that reviewers must remember to check).

---

## Critical Pitfalls

### Pitfall 1: Unfreezing harnesses after seeing results ("peeking and patching")

**What goes wrong:**
Full matrix runs. react looks bad. Author notices react's system prompt has a typo, or its retry loop terminates one iteration too early, and "fixes" it. Re-runs. Publishes the post-fix numbers alongside the other harnesses' original numbers. The comparison is now a comparison between "tuned react" and "un-tuned everything else" — exactly what the article claims it isn't.

**Why it happens:**
Engineers' instinct when a module performs badly is to debug it. In a methodology experiment this instinct is the enemy. The comparison is only valid if every harness is equally under-optimized. "But it's objectively a bug" is the siren song — every loser can be made to look like a bug to someone motivated to find one.

**How to avoid:**
- Git-tag `harnesses-frozen` on the commit where the last harness file is merged, BEFORE the matrix runs. Runner refuses to execute if `HEAD` is not a descendant of that tag with only non-harness files changed (enforce via a pre-run check: `git diff --name-only harnesses-frozen HEAD` must not include `harnesses/` or `src/harness_eng/model.py` or `src/harness_eng/tools.py`).
- All five harnesses reviewed and merged in a single PR if possible, or in PRs that cannot reference earlier run outputs. No harness PR descriptions may cite benchmark numbers from an earlier matrix run.
- Separate the "pilot" runs (single task, debugging the plumbing) from the "matrix" run. Pilot is allowed to iterate. Matrix is one-shot.
- Document freeze date in `ARTICLE.md` header explicitly: "Harnesses frozen on commit `<sha>` at `<date>`. All matrix runs are on this commit or descendants that touch only runner/analysis code."

**Warning signs:**
- Commits on `harnesses/*.py` dated after the first matrix run timestamp in `traces/`.
- Harness file mtimes newer than any JSONL trace file.
- PR diff on a harness file whose description contains "fix" and whose timing is post-pilot.
- Anyone on a code review saying "let me just tweak the react prompt and rerun."

**Phase to address:**
- **Phase defining the runner** must ship the freeze-enforcement gate. The gate is non-negotiable scaffolding, not a later addition.
- **Phase writing the article** must cite the freeze commit SHA, not just dates.

---

### Pitfall 2: Tool-output tokens omitted from cost accounting

**What goes wrong:**
Cost is computed from `response.usage.input_tokens + response.usage.output_tokens` on the assistant turn. But in a tool-use loop, the tool result that comes back in the NEXT turn's `input_tokens` is where the expensive HTML payload lives. If the harness accumulates conversation history (react, reflexion, plan_execute do; single_shot does not), the same tool output is re-billed on every subsequent turn as part of `input_tokens`. Harnesses that aggressively re-send context pay linearly more, and this is the REAL cost story. If the accounting sums only the final turn's usage, or sums per-turn usage but loses the growth-with-turn signal, `minimal` and `single_shot` will look unfairly expensive per-call and the multi-turn harnesses' compounding input cost vanishes.

A second variant: a harness implementation truncates or summarizes tool output before resending. If the cost meter reads the truncated tokens rather than what was actually billed by the API, the meter lies in the harness's favor.

**Why it happens:**
Anthropic SDK's `Message.usage` reports tokens per API call correctly, but the harness-level cost is the SUM across the agent loop, and it's easy to bill only the assistant's output while forgetting that input_tokens on call N+1 includes call N's tool_result blocks. Python dict mutation of the `messages` list also makes it hard to audit what was actually sent — the on-disk trace of the conversation state at time T may not equal what the API actually tokenized.

**How to avoid:**
- In `model.call()`: record `response.usage.input_tokens`, `response.usage.output_tokens`, `response.usage.cache_read_input_tokens`, `response.usage.cache_creation_input_tokens` — every field the SDK returns, no pre-aggregation. Write to the JSONL trace.
- Cost is computed DOWNSTREAM by `analyze.py`, never by the harness. The harness has no concept of "cost" and cannot lie about it.
- The cost calculation sums `input_tokens` and `output_tokens` across all API calls in the run. Tool results are re-billed on each turn; this is correct because the API genuinely charges that way. Do not "deduplicate" tokens across turns.
- Unit test: a synthetic 3-turn transcript with a 1000-token tool output should produce approximately `3 * 1000` input tokens cumulatively, not `1000`.
- Separate `api_cost_usd` (what the credit card was charged) from any derived metric like `unique_cost` or `compressed_cost`. The article publishes `api_cost_usd`.
- Cross-check the end-of-run cost against the Anthropic console's billed spend for the API key used during the run; deviation >5% is a bug.

**Warning signs:**
- Cost per harness is flat across turns (implausible for any multi-turn harness).
- `reflexion` or `plan_execute` reports cost lower than `react` on the same task (multi-phase harnesses should cost more, not less — if they cost less, token accounting is broken).
- Sum of per-call usage in trace != aggregate reported in summary.csv.
- Cache token fields (`cache_read_input_tokens`) are zero on every call despite prompt caching being available (may indicate SDK version issue but also may indicate incorrect usage parsing).

**Phase to address:**
- **Phase defining `model.py`** records complete usage blob.
- **Phase building analysis** computes cost only from trace data, never from harness-reported values.
- **Test phase** must include the cumulative-input-tokens regression test.

---

### Pitfall 3: Traces only written on success paths ("survivorship bias in the trace corpus")

**What goes wrong:**
Trace writer is wrapped in a try/except in the run loop. Exceptions during a harness run are caught, the failure is counted as grade=0, but the trace file for the failing run is either incomplete (missing the final error), empty, or not written at all. The article's "surprising failure" section is then sampled from an impoverished corpus — you end up showcasing the failures that completed the trace-flush path, not the actually interesting ones (context overflows, infinite loops, malformed tool calls, API rate-limit retries that ate the budget).

A subtler variant: the trace writer flushes per-record but uses a buffered file handle that isn't flushed on process kill (Ctrl-C during a hung run). The most interesting failures — the infinite-loop ones — are the ones whose traces you have no record of.

**Why it happens:**
JSONL writers default to buffered mode. Exception handlers prioritize not crashing the batch run over preserving evidence. Developers test trace-writing on happy-path unit tests and never exercise the path where the harness itself throws.

**How to avoid:**
- `trace.py` opens the file in line-buffered or unbuffered mode, flushes+fsyncs after every record write. (`open(path, "a", buffering=1)` gives line buffering; adding `f.flush(); os.fsync(f.fileno())` gives crash safety.)
- Every harness run is wrapped in a try/except/finally: exception → write an `event: "error"` record with the traceback; finally → write an `event: "run_end"` record with terminal status even on exception. The trace is only considered valid if it contains both a `run_start` and a `run_end` record — validated by the analysis step, which drops malformed traces and logs them as "unaccounted runs."
- The runner maintains a manifest: before each (harness, task, seed) triple is executed, append the triple to `runs_expected.jsonl`. After each, append to `runs_completed.jsonl`. Diff at end of matrix: any expected-but-not-completed is a ghost failure and must be investigated.
- Dedicated "adversarial" test: a fixture harness that deliberately raises midway, infinite-loops until killed, exceeds context window. Verify the trace viewer can still render what's there.

**Warning signs:**
- Number of unique (harness, task, seed) triples in trace files < expected matrix size.
- Any trace file missing a terminal `run_end` record.
- Failure rate for any harness is 0% (statistically implausible on messy HTML — if one harness shows no failures, it's probably eating them).
- `traces/` directory size is smaller for high-failure-rate harnesses than low-failure-rate ones (failures should produce MORE trace bytes, not fewer, because they're typically longer loops).

**Phase to address:**
- **Phase defining `trace.py`** must implement line-buffering + fsync + run_end invariant.
- **Phase defining the runner** must implement the expected/completed manifest diff.
- **Phase building analysis** must report unaccounted-run counts, not silently drop them.

---

### Pitfall 4: Prompt contamination across harnesses (one harness gets "better" wording)

**What goes wrong:**
During implementation, developer writes react's system prompt first, iterates on it against fixture task 1 until it works, then copies it as the base for reflexion and plan_execute. Single_shot gets a minimal prompt written last, in a rush. Minimal deliberately gets a stripped prompt. The article concludes that plan_execute beats single_shot, when what actually happened is that plan_execute had 4 hours of prompt tuning and single_shot had 20 minutes.

Secondary form: task descriptions are wrapped in harness-specific scaffolding ("You have access to these tools: ..." for react; "Plan first, then execute" for plan_execute). Some harnesses include the expected output schema in the system prompt, some derive it from the task description. This is a real part of the harness design — but if it's coupled with other prompt variations that aren't load-bearing, you can't attribute the spread to any single factor.

**Why it happens:**
Prompt engineering is path-dependent. Whoever is written last inherits the developer's accumulated intuition about what works on the specific fixtures. Prompts also drift because "just one more instruction" is free-looking.

**How to avoid:**
- Task description is passed to all harnesses IDENTICALLY. Harnesses wrap it in their own scaffolding (that's their design), but the wrapped task string must contain the raw task string verbatim. Unit test: for every harness, the rendered prompt contains `task.description` as a substring.
- The harness-specific wrapping (the "scaffolding prompt") lives in each harness file and is a single string constant at module top. Diff them during review — similar harnesses (react vs reflexion) should differ ONLY in the parts the article claims are their defining difference. If react and reflexion's system prompts also differ in tone, formatting, examples included, that's contamination.
- Write all five harness scaffolding prompts in ONE sitting, side-by-side, before running any of them against real tasks. If you later iterate on one, iterate on all.
- Record the full rendered prompt (system + messages) at `run_start` in the trace. A prompt-diff utility can post-hoc check that the task content is identical across harnesses for the same task.

**Warning signs:**
- One harness's system prompt is noticeably longer than the others without a design reason.
- Examples or few-shot demonstrations in one prompt but not others.
- Commit history shows one harness prompt edited 10 times, another edited once.
- Harness comments like "works best with this wording" — that wording probably doesn't exist in the other harnesses.

**Phase to address:**
- **Phase implementing the remaining two harnesses (reflexion, minimal)** — the last two harnesses are where contamination risk is highest because the first three's prompts are already "known good."
- **Review gate before freeze**: side-by-side prompt diff, single reviewer, checklist.

---

### Pitfall 5: Tool implementation drift (one harness gets a better `read_html` or grader-shaped tools)

**What goes wrong:**
`tools.py` defines shared tools. During react development, a subtle bug in `read_html` gets fixed — for example, `BeautifulSoup(html, "lxml")` used to drop comments, now it keeps them. That fix is committed before plan_execute is implemented. Then the author realizes reflexion would benefit from a `search_text_in_html` convenience tool and adds it. Now reflexion has strictly more tool capability than single_shot. The comparison measures tool surface area, not harness design.

The grader-shaped variant is worse: somewhere in tool development, someone adds a helper that returns data in a format very close to the expected output schema (because it's what made debugging easy). Any harness that uses that helper essentially skips the extraction work. This can happen invisibly if, say, `read_html` with a CSS selector argument returns cleaned text that the grader happens to normalize identically.

**Why it happens:**
Tools feel "shared infrastructure," not "part of the experiment." Developers improve them ambiently. The `minimal` harness's constraint (no `read_html`) is enforced by convention, not structure — it's one `self.tools = [...]` line away from being broken.

**How to avoid:**
- Tool definitions (name, description, schema, implementation) live in `tools.py` as a frozen registry. Each harness declares its allowed tool set by NAME from a fixed allowlist. The allowlist is committed and reviewed alongside the harnesses.
- `minimal` harness doesn't just "not use" `read_html` — the harness base class's `run()` method does not pass `read_html` to the model's tools parameter if the harness's declared allowlist excludes it. Test: inspect the API call payload and assert the tools list.
- Freeze `tools.py` on the same commit as the harnesses. Any post-freeze change to `tools.py` invalidates the matrix run.
- Code review rule: diff `tools.py` between "harness 1 merged" and "harness 5 merged." Any semantic change in that window is a contamination risk.
- No tool may return data whose schema is close to the expected output schema. If tempted, that's the grader in disguise — move the logic out of the tool and into the harness where it belongs.

**Warning signs:**
- Commits to `tools.py` dated between the first and last harness merge.
- A tool whose output requires no transformation to match `expected_output`.
- Tool descriptions that name fields from the task schema ("returns the product price" when the task asks for price).
- `git log --follow tools.py` shows activity post-harness-freeze.

**Phase to address:**
- **Phase implementing tools.py** — establish the frozen-registry pattern at the start.
- **Phase implementing each harness** — declare tool allowlist explicitly, test assertion on API payload.
- **Phase before matrix run** — tools.py frozen under the same tag as harnesses.

---

### Pitfall 6: Grader non-determinism (the "normalization" function has state or locale dependence)

**What goes wrong:**
Per-field normalized exact match sounds deterministic. Then you discover:
- Python's `str.lower()` behaves differently for Turkish locale (`İ` → `i̇`).
- BeautifulSoup text extraction order depends on parser (`html.parser` vs `lxml` differ on malformed HTML).
- Whitespace normalization via `" ".join(s.split())` collapses newlines differently from `re.sub(r"\s+", " ", s)` on non-ASCII whitespace.
- Unicode normalization form mismatches (`NFC` vs `NFD`) — same visual string, different bytes.
- Floating-point price comparison: `"19.99"` vs `"19.990"` vs `"19,99"` (comma-decimal locales in fixtures).
- The grader uses a set for field comparison but the model's output uses a list, and order matters when you don't want it to (or vice versa).

Re-running the grader on the same traces gives different scores, or the scores depend on the OS. The article's numbers can't be reproduced by readers on other platforms.

**Why it happens:**
"Normalize and compare" looks trivial. The edge cases don't show up on clean fixtures. Windows vs Linux locales differ silently.

**How to avoid:**
- Grader operates on strings only, with explicit normalization steps written as a documented pipeline: (1) NFC unicode normalize, (2) `.strip()`, (3) `.casefold()` (not `.lower()`), (4) `re.sub(r"\s+", " ", s)` with explicit ASCII-only whitespace regex if locale-independence matters.
- Grader is a pure function. Unit tests include: the same (predicted, expected) pair graded 100 times returns identical scores. Run tests on at least Linux + Windows (GitHub Actions `runs-on` matrix).
- Numeric fields have an explicit type: `{"type": "number", "tolerance": 0.001}` or `{"type": "string", "normalization": "exact"}` — the task schema declares which. No implicit coercion.
- "Golden trace" test: commit a small set of (model_output, expected, expected_score) triples to the repo. CI runs the grader on them. If the score changes, the grader changed.
- Grader version stored in each trace record. Grader version bump invalidates the cached scores; analysis re-grades from raw traces.
- Grader is agnostic to harness. It sees only `(task_id, final_output)` — never the harness name. Prevents accidental per-harness branches.

**Warning signs:**
- CI flakes ("passes on rerun") on grader tests.
- Results differ between local and CI runs.
- The same task+harness scores differently across two full matrix runs (non-determinism in grading, not the harness).
- Grader imports `locale` or anything platform-specific.

**Phase to address:**
- **Phase implementing `grader.py`** — establish pure-function + golden-trace test pattern.
- **CI phase** — grader tests run on Windows + Linux.

---

### Pitfall 7: Single-seed conclusions (inference from N=1)

**What goes wrong:**
Five tasks × five harnesses × temperature=0. Author thinks this is deterministic and runs once. Publishes a chart showing react at 40% and plan_execute at 60%. Reader reruns and gets react at 60%, plan_execute at 40%. The Anthropic API is not bitwise deterministic even at temperature=0 (tie-breaking, backend load balancing, minor prompt rendering differences). The spread you published was within the noise floor.

Even if the API were deterministic, 5 tasks gives 5 Bernoulli trials per harness — confidence interval on a 40% success rate with n=5 is roughly [12%, 74%]. Any claim like "react beats single_shot" without confidence intervals is statistically unsupported.

**Why it happens:**
Temperature=0 creates an illusion of determinism. "Run the matrix" feels like a scary expensive thing to do once, let alone N times. Budget pressure argues against seeds.

**How to avoid:**
- Minimum N=3 seeds per (harness, task) cell. Seed varies prompt-level nonce (e.g., a random task ordering in the batch, or a run-ID in an otherwise-ignored field) so that API nondeterminism gets exercised.
- Report success rate ± standard error or with Wilson 95% CI on the binomial proportion. Chart error bars, not point estimates.
- Explicitly state in the article: "With N=3 seeds × 5 tasks = 15 trials per harness, the minimum detectable difference at α=0.05 is roughly X percentage points."
- If cost-constrained, prefer fewer harnesses × more seeds over more harnesses × one seed. Five harnesses is already at the limit; dropping to three harnesses with 10 seeds each tells a more honest story than five with one.
- Seed is recorded in the trace. Seed is an explicit CLI argument to the runner, not a hidden global.

**Warning signs:**
- `success_rate_vs_cost` chart has no error bars.
- Runner has no `--seeds` or `--n-runs` parameter.
- The article uses the word "beats" or "outperforms" without a confidence statement.
- Two independent runs of the full matrix produce visibly different rankings.

**Phase to address:**
- **Phase defining the runner** — seed is a first-class input, multi-run is default.
- **Phase building analysis** — Wilson CIs computed and plotted.
- **Phase writing the article** — section explicitly stating statistical power.

---

## Moderate Pitfalls

### Pitfall 8: Context-window overflow silently degrading a harness

**What goes wrong:**
reflexion and plan_execute accumulate turns. On a messy HTML fixture that's already 8k tokens, they hit Claude Sonnet's context limit mid-run. The SDK either errors (visible) or the harness's manual truncation quietly drops the earliest messages (invisible). The harness then appears to "forget" the task mid-execution and fails. Failure is attributed to harness design rather than to the truncation bug.

**How to avoid:**
- Every harness logs input_tokens per API call. Analysis step flags any run where input_tokens exceeded 80% of context limit (configurable threshold) and excludes those from the main comparison or reports them separately as "context-pressured."
- Manual message truncation, if any, emits an explicit `event: "truncation"` trace record with before/after token counts.
- The article has a separate chart: "runs lost to context overflow per harness." Hiding this in aggregate results is dishonest.

**Phase to address:** Phase implementing multi-turn harnesses (react, reflexion, plan_execute) must include overflow detection. Analysis phase reports it.

---

### Pitfall 9: Retry/rate-limit handling that double-counts cost or hides failures

**What goes wrong:**
The Anthropic SDK may auto-retry on 429s or 5xxs. A retried call bills twice. If the harness-level token counter only reads `response.usage` on success, the retry tokens are invisible. Conversely, if the harness catches a rate-limit error and treats it as "task failure," the failure is attributed to the harness, not the infrastructure — reflexion (which makes more calls) will eat more rate limits and look worse than it is.

**How to avoid:**
- Use `anthropic.Anthropic(max_retries=0)` explicitly. All retry logic is inside the harness or runner, visible and logged.
- Rate-limit failures are tagged distinctly from task failures in traces (`failure_mode: "rate_limit"` vs `"grade_zero"` vs `"exception"`).
- Analysis step reports failures broken down by mode. Rate-limit failures are either retried at the matrix level (after the run, with explicit re-queuing) or excluded and noted.
- Runner sleeps/throttles between calls if necessary to keep under rate limit — this is a cost/time tradeoff, not a harness property.

**Phase to address:** Runner phase. Model.py phase (disable SDK auto-retry).

---

### Pitfall 10: Fixture leakage (model sees fixtures during development, memorizes them)

**What goes wrong:**
Developer iterates on harnesses by running them against `fixture_1.html` repeatedly. Each call is independent so this is fine for the model — except the developer then commits fixture_1 alongside the code and runs the "real" matrix on the same fixtures. The frozen model was never trained on these fixtures, but the author's prompt-tuning decisions absolutely were, and those prompts are what's being evaluated.

This is the same pitfall as Pitfall 4 (prompt contamination) but widened — the entire harness design is implicitly overfit to the fixture set.

**How to avoid:**
- Reserve 2 of the 5 tasks as "held out" — not looked at during harness development. Implement the harnesses against tasks 1–3; only run tasks 4–5 for the first time in the matrix run. Any harness that performs drastically differently on held-out tasks reveals overfitting.
- This mildly constrains the article's claims to "evaluated on a 5-task suite, 2 of which were held out" — which is a stronger claim than "evaluated on 5 tasks" anyway.
- If 5 tasks is too few for holdout, pilot on synthetic HTML (generated, not from the real fixtures) and save all 5 real fixtures for the matrix.

**Phase to address:** Phase selecting tasks / authoring fixtures. Phase running the matrix.

---

### Pitfall 11: Latency measured at the wrong boundary

**What goes wrong:**
Latency is one of the three published metrics. Measured as `time.perf_counter()` delta around `client.messages.create()`. But that excludes:
- Tool execution time (a slow BeautifulSoup parse adds real wall-clock).
- Harness-internal reasoning time (reflexion's critique step if it's a separate call).
- Retry-and-wait time.

Or it's measured wall-clock from `run_start` to `run_end` — which includes the developer's print-debugging statements, trace-writing IO, or a `time.sleep(1)` rate limiter.

Either way, latency numbers favor one harness over another depending on which boundary was chosen.

**How to avoid:**
- Standardize on TWO latency metrics, both logged: `api_latency_sum` (sum of per-call API times, harness-agnostic) and `wall_clock_total` (end-to-end). Report both in the chart or only report `api_latency_sum` for the comparison.
- Tool execution time is logged separately as `tool_latency_sum` — not counted as API latency, but reported.
- Runner-level throttling (sleep between calls for rate-limit safety) is logged and subtracted from `wall_clock_total` if reported.

**Phase to address:** Model.py phase (per-call timing), trace.py phase (structured timing events), analysis phase (which metric is headline).

---

### Pitfall 12: Structured-output parsing failures miscounted as task failures

**What goes wrong:**
The grader expects JSON (or a specific schema). The model sometimes returns the right data in prose, or with a trailing ```json fence, or with a stray explanation before the JSON block. The harness's output parser fails to extract, the grader sees empty output, the task is scored 0. Some harnesses may be more robust to this (plan_execute's explicit "output this JSON" step) purely because of the parse, not the reasoning.

This is a real harness-design factor — output formatting IS part of the harness. But if parsing is fragile and inconsistent across harnesses, you're measuring the parser, not the harness.

**How to avoid:**
- Single shared output-extraction function in a shared module. All harnesses use it. Tested against adversarial model outputs (fenced, unfenced, with preamble, with trailing text).
- Consider using the Anthropic tool-use mechanism as the output channel for ALL harnesses: define a `submit_answer` tool whose schema matches the expected output. Then there's no parse — the tool-call arguments ARE the answer. This makes output format harness-independent by construction.
- If free-form output is kept, report parse-failure rate as a separate metric. If harness X has 20% parse failures and 40% task failures, the reader should see both.

**Phase to address:** Phase defining the output channel (ideally at harness base class or tools.py time). Tests phase.

---

## Minor Pitfalls

### Pitfall 13: Trace file naming collisions across reruns

**What goes wrong:**
Traces named `traces/react_task1.jsonl`. Second run overwrites the first. No record of prior-run data. Makes seed comparisons impossible.

**How to avoid:** Trace filename includes `(run_id, harness, task_id, seed)`. `run_id` is a timestamp or UUID generated once per matrix run. Filenames never collide.

---

### Pitfall 14: Cost-estimator diverges from real cost

**What goes wrong:**
Estimator says "projected: $3.50." Real run costs $47 because estimator didn't account for tool-result tokens being re-sent on every multi-turn iteration (see Pitfall 2).

**How to avoid:** Estimator uses the same cost-computation function as the post-run analyzer, applied to a synthetic trace generated by running ONE task through each harness. Multiply by task count. Over-estimate rather than under-estimate; document the estimation method.

---

### Pitfall 15: `README` onboarding depends on environment variables the stranger doesn't know about

**What goes wrong:**
Reproducer clones the repo, follows README, hits `ANTHROPIC_API_KEY not set` — fine. Sets it. Then hits `ANTHROPIC_API_KEY_FOR_CACHE`, or some developer-machine-specific path. Stranger gives up.

**How to avoid:** CI is the canonical onboarding doc. If CI (running on a fresh GitHub runner) can reproduce the pilot, the README instructions work. If CI cheats by having extra secrets, the README is lying. Document every env var in `.env.example` and make CI load from `.env.example`-compatible values.

---

### Pitfall 16: `harness_eng` module naming clash with the published article's framing

**What goes wrong:**
The project is "harness_eng" but in article prose it becomes "harness engineering" or "the harness-eng benchmark" — the casual reader can't tell if it's a framework, an experiment, or a blog post. Reduces citeability.

**How to avoid:** Article opens with a one-paragraph "what this is" disclaimer. Repo README header explicitly states "this is an experiment, not a library."

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip `--seeds` flag, single-run matrix | Saves 3–5x API cost | Results within noise; article can't claim spread | Never for the published run; fine for pilot |
| Trace-writing in a `try: ... except: pass` block | Keeps matrix running through bugs | Corrupted/empty traces for exactly the runs that matter | Never — fail loud, preserve evidence |
| Inline prompts in each harness rather than a prompt module | Faster to write | Drift between harnesses impossible to review | Acceptable only if all five harnesses are reviewed side-by-side before freeze |
| Grade in-line during run (no separate analysis step) | Fewer files | Re-grading requires re-running the API calls; grader bugs invalidate the matrix | Never — always grade from traces |
| Share mutable state (e.g., `messages` list) between harness and model wrapper | Natural Python pattern | Traces diverge from what was sent; retries silently double entries | Never — pass immutable copies |
| Skip context-overflow detection | Simpler harness loop | Silent truncation attributed to "harness is bad at long tasks" | Never for multi-turn harnesses |
| Hard-code model ID in each harness rather than import from config | "It works" | A version bump halfway through the matrix contaminates results | Never — central config is load-bearing |
| Skip CI | Saves 1 hour of setup | README rot, stranger-onboard-in-5-min goal fails silently | Never for this project's portfolio goal |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Anthropic SDK `messages.create` with tools | Reading `response.content[0].text` when the assistant chose to emit a tool_use block (content[0] is the tool_use, not text) | Iterate over `response.content` and dispatch on `block.type` |
| Anthropic SDK `response.usage` | Treating `input_tokens` as "new tokens this turn" | It's all tokens sent (including prior turns' tool results); sum ACROSS turns for true cost |
| Anthropic SDK `stop_reason` | Ignoring `"tool_use"` vs `"end_turn"` distinction | Multi-turn harnesses loop while `stop_reason == "tool_use"`; terminate only on `"end_turn"` or max-iter |
| Anthropic SDK automatic retries | Relying on SDK defaults | Set `max_retries=0`; handle 429/5xx in harness/runner with explicit logging |
| BeautifulSoup | Using default `html.parser` on malformed HTML | `lxml` parser with explicit encoding; behavior is deterministic and documented |
| Pandas to_csv | Default float formatting varies by locale | `to_csv(..., float_format="%.6f")` explicitly; avoid `%g` |
| Matplotlib on Windows | Default backend tries to open a display | Set `matplotlib.use("Agg")` before any pyplot import in analysis script |
| JSONL trace reader | `json.loads(line)` on partial last line (run killed mid-write) | Wrap per-line parse in try/except; skip malformed terminal lines with warning |
| Git on Windows | CRLF line endings in fixture HTML files | `.gitattributes` pins `*.html` and `*.jsonl` as `-text` (binary) to avoid line-ending normalization altering content-derived token counts |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sequential matrix execution with no concurrency | Matrix takes hours | Out of scope per PROJECT.md — sequential is fine at 5×5×N=3 size | If N grows to 10+ seeds or tasks grow to 20+, consider asyncio with a global rate-limit semaphore |
| Trace file fsync on every record | IO-bound wall-clock on fast networks | Accept the cost — correctness > throughput at this scale | Only a problem if traces dominate runtime, which they won't |
| Re-reading full JSONL traces from disk for every analysis chart | Slow notebook experience | Read once into a DataFrame, operate in memory | At >100 MB of traces — not an issue at 5×5 scale |
| Prompt caching assumed but not enabled | Costs 2–3x what they should | Explicit `cache_control` blocks on the system prompt if supported by SDK version | Only relevant if prompt caching feature is used; document the choice |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Committing `.env` with API key | Anthropic key exfiltrated, surprise billing | `.env` in `.gitignore` from commit 1; pre-commit hook scanning for `sk-ant-` strings; `.env.example` has only placeholder values |
| Logging full prompts to traces with API key accidentally embedded | Key leaks via trace file commit | Trace writer runs a redactor pass on any string matching API-key regex |
| Publishing a repo where `traces/` directory contains real billed API responses | Fine for this project (responses are public HTML extractions) but confirm no PII in fixtures | Audit fixture HTML before commit; prefer synthetic or manually-cleaned HTML |
| Running the matrix against a production API key with low rate limits | 429 failures attributed to harnesses | Use a dedicated key if possible; document the key's rate limit in the article methodology section |
| Fixture HTML scraped from real websites without attribution/license check | Copyright / TOS issues | Either use clearly-public-domain sources, synthesize HTML, or attribute explicitly in fixtures/README |

---

## UX Pitfalls

This is a portfolio repo; UX means "the reader/reproducer's experience."

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Article publishes numbers without the trace viewer link | Reader can't verify claims | Every failure cited in the article links to a specific trace file + viewer URL (even if local `file://`) |
| Chart labels use internal harness names ("plan_execute") with no legend | Reader doesn't know what plan_execute is | Every chart has a legend that expands names and references a one-paragraph harness description |
| README's "run this" command requires env vars not documented in same section | Reproducer fails silently | The exact command sequence that CI runs is the README's quickstart, copy-pasted |
| Chart shows success rate but not cost; cost is in a CSV buried in a subdirectory | Reader draws incomplete conclusions | Headline chart is the success-rate-vs-cost frontier — both dimensions on one plot |
| Article claims "2-4x spread" but the chart shows 1.3x spread | Reader loses trust | Article draft is AUTO-GENERATED from the CSV summary (per PROJECT.md requirements); the prose cannot drift from the numbers |

---

## "Looks Done But Isn't" Checklist

- [ ] **Trace coverage:** Every (harness, task, seed) has both a `run_start` and `run_end` record — verify by diffing `runs_expected.jsonl` against actual trace inventory.
- [ ] **Cost correctness:** Sum of per-call `input_tokens` in trace equals the cost reported by analysis — verify with a unit test on a 3-turn synthetic trace.
- [ ] **Harness freeze:** No commits to `harnesses/*.py`, `src/harness_eng/model.py`, `src/harness_eng/tools.py`, or prompt strings after the `harnesses-frozen` tag — verify `git diff harnesses-frozen HEAD -- harnesses/ src/harness_eng/model.py src/harness_eng/tools.py` is empty at matrix-run time.
- [ ] **Prompt parity:** For any given task, the task description appears verbatim inside every harness's rendered system+user prompt — verify by asserting substring presence in trace records.
- [ ] **Tool parity:** The `tools` parameter sent to the API matches each harness's declared allowlist — verify by assertion in the runner, not by trust.
- [ ] **Seed count:** N ≥ 3 seeds per cell in the published matrix — verify by counting distinct `seed` values per (harness, task) in the trace corpus.
- [ ] **Confidence intervals:** Published chart has error bars or the article states CI computation — visually verify the chart; verify the computation in `analyze.py` uses Wilson intervals.
- [ ] **Parse-failure accounting:** Parse failures counted separately from task failures — verify failure-mode breakdown exists in summary output.
- [ ] **Context overflow accounting:** Runs flagged as context-pressured are reported, not silently included — verify the analysis reports a "pressured runs" count per harness.
- [ ] **Rate-limit accounting:** 429/5xx-caused failures are tagged and reported distinctly — verify trace events include `failure_mode`.
- [ ] **Grader determinism:** Re-running `analyze.py` on unchanged traces produces byte-identical output — verify with `diff` across two runs.
- [ ] **Article synchronization:** The numbers quoted in `ARTICLE.md` prose match the numbers in `summary.csv` — verify by auto-generation (the article prose uses template variables populated from the CSV; no hand-typed numbers).
- [ ] **README reproducibility:** A fresh clone + CI's exact command sequence reproduces the pilot run on GitHub Actions — verify CI is green on main.
- [ ] **Secrets hygiene:** No `sk-ant-` string in any committed file — verify with pre-commit grep.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Harness unfrozen after matrix run (Pitfall 1) | HIGH — requires full rerun at matrix cost; article cannot ethically be published on partial-freeze data | Revert all post-freeze harness commits. Re-run full matrix from clean freeze tag. Document the near-miss in article methodology. |
| Cost accounting bug discovered post-run (Pitfall 2) | LOW if traces are complete — just rerun analysis | Re-derive costs from JSONL trace `usage` fields. Document the bug and corrected numbers. Traces being the raw source means this is cheap. |
| Incomplete traces (Pitfall 3) | MEDIUM–HIGH depending on coverage | Identify missing (harness, task, seed) triples from the manifest diff. Re-run only the missing cells. Do NOT extrapolate. |
| Prompt contamination (Pitfall 4) | HIGH if discovered post-freeze | If contamination is minor (whitespace) and documented, publish with caveat. If load-bearing (one harness has examples, another doesn't), re-run after normalizing — accept cost. |
| Tool drift (Pitfall 5) | HIGH — tools.py changing mid-run requires full rerun | Revert tools.py to freeze-tag version. Rerun full matrix. |
| Grader non-determinism (Pitfall 6) | LOW — grader is downstream of traces | Fix grader, rerun analysis on existing traces. Keep old numbers for comparison, document the delta. |
| Single-seed results (Pitfall 7) | MEDIUM — need more runs, but incremental | Run additional seeds, append to existing traces. Recompute with CIs. No re-run of existing seeds needed. |
| Context overflow silently affecting one harness (Pitfall 8) | LOW — visible in trace post-hoc | Flag affected runs in analysis; report them separately. Article cites the overflow rate. |

---

## Pitfall-to-Phase Mapping

Using approximate phase names; final names are set during roadmap generation. The two existing "already built" files (model.py, tools.py, trace.py, grader.py — per PROJECT.md Context) are retroactively audited against these pitfalls in the first phase.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Harness unfreezing (peek-and-patch) | Runner / matrix-execution phase | Runner checks `git diff harnesses-frozen HEAD -- harnesses/` is empty before executing; refuses otherwise. CI check on matrix-branch. |
| 2. Tool-output tokens omitted | Model.py audit phase + Analysis phase | Unit test on synthetic 3-turn transcript verifies cumulative input_tokens scales correctly. End-of-run cross-check against Anthropic console. |
| 3. Trace gaps on failure | Trace.py audit phase + Runner phase | Every trace file validated for `run_start` + `run_end` invariant. Manifest diff reports unaccounted runs. |
| 4. Prompt contamination | Remaining-harness phase (reflexion + minimal) + freeze review gate | Side-by-side prompt diff review. Assertion: task description is substring of every harness's rendered prompt. |
| 5. Tool drift | Tools.py audit phase + per-harness phase | Frozen tool registry + per-harness allowlist. Runner asserts API payload's tools list matches allowlist. |
| 6. Grader non-determinism | Grader.py audit phase + CI phase | Pure-function unit tests. Golden-trace regression test. Grader runs on Linux+Windows CI matrix. |
| 7. Single-seed conclusions | Runner phase + Analysis phase | `--seeds N` is a required CLI argument, N≥3 default. Analysis computes Wilson CIs; charts show error bars. |
| 8. Context overflow | Multi-turn harness phases + Analysis phase | Per-call input_tokens logged; analysis flags >80%-of-limit runs. |
| 9. Retry/rate-limit accounting | Model.py audit + Runner phase | SDK `max_retries=0`. Trace records `failure_mode` field. |
| 10. Fixture leakage | Task-authoring phase + matrix-run phase | 2 held-out tasks; held-out identity recorded in config. |
| 11. Latency boundary | Model.py + Trace.py audit + Analysis phase | Both `api_latency_sum` and `wall_clock_total` logged; analysis documents which is headline. |
| 12. Parse failures | Harness-base or tools.py phase + Test phase | Shared output extraction (or tool-use for output). Parse-failure rate reported separately. |
| 13. Trace naming collisions | Trace.py + Runner phase | Filenames include `run_id`. |
| 14. Cost-estimator divergence | Cost-estimator phase | Estimator uses same cost function as analyzer. Unit test on shared function. |
| 15. README env-var drift | CI phase | CI runs the README's quickstart verbatim. |
| 16. Naming clarity | Article phase | Disclaimer paragraph; README framing. |

---

## Sources

- **Project-specific context:** `.planning/PROJECT.md` (harness_eng, 2026-04-23) — provides the core failure modes (harness freeze, trace-from-call-1, single frozen model, deterministic grader) that this document expands on.
- **Agent-benchmark methodology literature (domain-general, HIGH confidence from ML-eval discourse):** post-mortems on SWE-bench contamination (fixtures leaked to pretraining), HELM's insistence on standardized scaffolding, BIG-bench's per-task deterministic grader discipline.
- **Anthropic SDK tool-use semantics (HIGH confidence, standard SDK behavior):** `stop_reason` cycle, `response.usage` reporting input tokens inclusive of prior tool_results, `max_retries` parameter on client constructor. Verify against current SDK docs during implementation.
- **Statistical inference on small-N binomial (HIGH confidence, standard):** Wilson score interval for proportions, appropriate when n is small or p is near 0/1.
- **Observed failure patterns in public agent evaluations (MEDIUM confidence, based on community discourse around early LangChain agent benchmarks and AutoGPT eval reproductions):** prompt drift, tool drift, trace-on-success survivorship, and post-hoc harness tuning are the four recurring themes.

*Pitfalls research for: LLM agent-harness controlled-comparison experiment*
*Researched: 2026-04-23*
