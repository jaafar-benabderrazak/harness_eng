# Requirements: harness_eng

**Defined:** 2026-04-23
**Core Value:** Produce concrete, reproducible evidence — numbers and annotated failure traces — that harness design dominates model choice within a tier on the same frozen model.

## v1 Requirements

### Integrity (experimental control — the article stands or falls on these)

- [ ] **INTG-01**: Only `src/harness_eng/model.py` imports the `anthropic` SDK; enforced by AST unit test (`tests/test_model_seal.py`)
- [ ] **INTG-02**: Every harness routes through `model.call()`; no harness instantiates its own SDK client
- [ ] **INTG-03**: Model id, temperature, and max_tokens live in a single frozen `config.py` and are identical across all five harnesses
- [ ] **INTG-04**: A git tag `harnesses-frozen` is set before the matrix runs; runner refuses to execute if `HEAD` has modified any file under `src/harness_eng/harnesses/` or `src/harness_eng/tools.py` since the tag
- [ ] **INTG-05**: The pre-registered hypothesis (expected direction of result) is written into README before the matrix runs and is not edited after
- [ ] **INTG-06**: `HARNESSES_FROZEN.md` records commit SHA and the five harness file SHAs at the time of freeze
- [ ] **INTG-07**: The final article cites the freeze commit SHA and the `runs/<id>/` directory path used for its numbers

### Harnesses

- [ ] **HARN-01**: `single_shot` harness — full HTML stuffed into a single model call; output via `submit_answer` tool
- [ ] **HARN-02**: `react` harness — thought/action/observation loop with a hard turn cap
- [ ] **HARN-03**: `plan_execute` harness — planner call produces a checklist without seeing HTML; executor follows the plan
- [ ] **HARN-04**: `reflexion` harness — first attempt runs as ReAct; on grader failure, model critiques its own trace and retries exactly once; retry tokens counted in the same usage total
- [ ] **HARN-05**: `minimal` harness — reduced tool whitelist (no `read_html`, no `extract_text`); message history pruned every N turns
- [ ] **HARN-06**: Every harness terminates by calling the `submit_answer` tool (universal output channel — no free-form text parsing)
- [ ] **HARN-07**: Each harness declares its tool allowlist by name; runner asserts the Anthropic-API `tools` payload matches the declared allowlist

### Benchmark

- [ ] **BENCH-01**: 5 HTML extraction fixtures across 5 domains (product, job posting, event, recipe, paper metadata)
- [ ] **BENCH-02**: Each task has between 3 and 5 expected fields
- [ ] **BENCH-03**: Fixtures contain deliberate decoys (sidebars, "similar items", alternate prices) that expose harness differences
- [ ] **BENCH-04**: Grader performs per-field normalized exact match (NFC + casefold + whitespace collapse); per-field score and all-fields-correct success
- [ ] **BENCH-05**: Grader determinism verified on both Linux and Windows runners in CI

### Tracing

- [ ] **TRACE-01**: Every model call and every tool call writes a structured JSON event to an append-only JSONL file before the function returns (from call 1, not retrofitted)
- [ ] **TRACE-02**: Trace file opened with line buffering and flushed after every event (partial trace survives crash)
- [ ] **TRACE-03**: Trace schema has a `schema_version` field; changes bump the version
- [ ] **TRACE-04**: A `run_start` event is written before any model call; a `run_end` event is written even on exception (try/except/finally)
- [ ] **TRACE-05**: Each event records wall-clock timestamp, event type, and type-specific payload (model call: usage blob; tool call: name, args, output length)

### Runner

- [ ] **RUN-01**: CLI runs the matrix of harness × task × seed sequentially
- [ ] **RUN-02**: `--seeds N` required, default N=3
- [ ] **RUN-03**: Writes one JSONL row per cell to `results/runs/<iso8601>_<git_sha>.jsonl` with predicted fields, tokens, tool calls, wall clock, stop_reason, per-field grade, overall success
- [ ] **RUN-04**: Expected-runs manifest written before any cell runs; completed-runs manifest updated after each cell (crash-resumable detection)
- [ ] **RUN-05**: Cost estimator runs before full matrix and prints per-harness + total projected USD with a safety margin
- [ ] **RUN-06**: Without `--yes`, runner prompts for confirmation after showing estimate

### Analysis

- [ ] **ANAL-01**: Aggregate results into `results/summary.csv` with one row per harness (success rate, field accuracy, tokens, cost, wall clock)
- [ ] **ANAL-02**: Wilson 95% confidence intervals computed on binomial success rate; shown as error bars on frontier chart
- [ ] **ANAL-03**: `results/frontier.png` — scatter of success rate vs total cost, one point per harness, labels
- [ ] **ANAL-04**: `results/field_heatmap.png` — per-harness × per-field accuracy heatmap
- [ ] **ANAL-05**: Secondary metric: cost-per-successful-extraction

### Article Output

- [ ] **ART-01**: `results/article.md` auto-drafted from `summary.csv`: chart reference, results table, success/cost spread headline, setup section, hypothesis verification
- [ ] **ART-02**: Numbers in article are never hand-typed — always interpolated from CSV
- [ ] **ART-03**: "What surprised me" section is a stub the author fills in after reading traces (auto-drafter never fakes narrative)
- [ ] **ART-04**: Article cites the freeze commit SHA and the run directory path

### Trace Viewer

- [ ] **VIEW-01**: `results/trace_viewer.html` — single standalone HTML file, vanilla inline JS, no external deps
- [ ] **VIEW-02**: Renders every JSONL file under `traces/` as collapsible sections grouped by (harness, task, run)
- [ ] **VIEW-03**: Filterable by harness and by task via inline dropdowns
- [ ] **VIEW-04**: Each event shows its type, key fields (token counts, selectors, stop reasons), and a collapsible raw-JSON view

### Tests + CI

- [ ] **TEST-01**: pytest suite covering grader normalization, task loading, tool dispatch, AST seal, harness registry, cost estimator
- [ ] **TEST-02**: Trace-schema regression test: synthetic multi-turn transcript confirms tool-result tokens are accounted
- [ ] **TEST-03**: GitHub Actions CI runs pytest on Linux and Windows (grader determinism check) on every PR to main

### Onboarding

- [ ] **ONB-01**: README quickstart onboards a stranger in under 5 minutes end-to-end (install → pilot → full run → chart)
- [ ] **ONB-02**: README contains the pre-registered hypothesis paragraph (INTG-05)
- [ ] **ONB-03**: `.env.example` shipped; no secrets in repo

## v2 Requirements

### Scale

- **SCALE-01**: Expand from 5 to 40 fixtures (original article pitch target)
- **SCALE-02**: Add 2 held-out fixtures never used during harness iteration

### Methodology

- **METH-01**: Hypothesis pre-registration lodged in a gist (timestamped external witness)
- **METH-02**: Randomized task order per seed to neutralize order-of-tasks effects

### Comparability

- **COMP-01**: Add a second frozen model (e.g. Haiku 4.5) as a control run to separate "harness effect" from "model × harness interaction"

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-provider (OpenAI, Gemini) model support | The experimental control is a frozen model; swapping providers contaminates the comparison. A separate project. |
| Inspect AI / DSPy eval framework adoption | Both homogenize the exact layer under study (the harness). Cannot measure harnesses while running under them. |
| LLM-as-judge grading | Adds a second non-deterministic evaluator; breaks the "deterministic grader" claim. |
| OpenTelemetry / W&B / Langfuse observability | JSONL trace is sufficient for the article's evidence requirements; OTel SDK is wrong scope. |
| Docker / devcontainer | Adds onboarding friction; must run on Windows + bash in a venv. |
| Prompt-tuning a losing harness after seeing results | Would invalidate the comparison; structurally blocked by the harness-freeze tag. |
| Parallel matrix across machines | 5×5×3 cells is tiny; concurrency muddles wall-clock metrics. |
| Token budget enforcement mid-run | Cost estimator is a pre-run gate; runtime budget killer adds a confound (harnesses that hit the cap vs those that don't). |
| Prompt caching (`cache_control`) | Would change cost numbers in ways that favor harnesses reusing the system prompt — an orthogonal variable to the one under study. |
| Streamlit / web dashboard | Static HTML trace viewer + static PNG charts are enough and require zero server. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTG-01 | Phase 1 | Pending |
| INTG-02 | Phase 1 | Pending |
| INTG-03 | Phase 1 | Pending |
| INTG-04 | Phase 2 | Pending |
| INTG-05 | Phase 2 | Pending |
| INTG-06 | Phase 2 | Pending |
| INTG-07 | Phase 6 | Pending |
| HARN-01 | Phase 1 | Pending |
| HARN-02 | Phase 1 | Pending |
| HARN-03 | Phase 1 | Pending |
| HARN-04 | Phase 1 | Pending |
| HARN-05 | Phase 1 | Pending |
| HARN-06 | Phase 1 | Pending |
| HARN-07 | Phase 4 | Pending |
| BENCH-01 | Phase 1 | Pending |
| BENCH-02 | Phase 1 | Pending |
| BENCH-03 | Phase 1 | Pending |
| BENCH-04 | Phase 1 | Pending |
| BENCH-05 | Phase 7 | Pending |
| TRACE-01 | Phase 1 | Pending |
| TRACE-02 | Phase 1 | Pending |
| TRACE-03 | Phase 1 | Pending |
| TRACE-04 | Phase 1 | Pending |
| TRACE-05 | Phase 1 | Pending |
| RUN-01 | Phase 1 | Pending |
| RUN-02 | Phase 3 | Pending |
| RUN-03 | Phase 1 | Pending |
| RUN-04 | Phase 4 | Pending |
| RUN-05 | Phase 1 | Pending |
| RUN-06 | Phase 1 | Pending |
| ANAL-01 | Phase 1 | Pending |
| ANAL-02 | Phase 3 | Pending |
| ANAL-03 | Phase 1 | Pending |
| ANAL-04 | Phase 1 | Pending |
| ANAL-05 | Phase 3 | Pending |
| ART-01 | Phase 1 | Pending |
| ART-02 | Phase 1 | Pending |
| ART-03 | Phase 6 | Pending |
| ART-04 | Phase 6 | Pending |
| VIEW-01 | Phase 1 | Pending |
| VIEW-02 | Phase 1 | Pending |
| VIEW-03 | Phase 1 | Pending |
| VIEW-04 | Phase 1 | Pending |
| TEST-01 | Phase 1 | Pending |
| TEST-02 | Phase 1 | Pending |
| TEST-03 | Phase 7 | Pending |
| ONB-01 | Phase 7 | Pending |
| ONB-02 | Phase 2 | Pending |
| ONB-03 | Phase 1 | Pending |

**Coverage:**

- v1 requirements: 49 total
- Mapped to phases: 49
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-23*
*Last updated: 2026-04-23 after initial definition*
