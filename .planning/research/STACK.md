# Stack Research

**Domain:** LLM agent harness benchmarking / eval experiment (portfolio piece)
**Researched:** 2026-04-23
**Overall confidence:** HIGH for core (anthropic, pandas, matplotlib, pytest, bs4); MEDIUM for positioning decisions (Inspect AI vs roll-your-own, selectolax vs bs4); LOW for trace-format-convention claims (no single standard exists).

---

## TL;DR Recommendation

**Roll your own.** No Inspect AI, no DSPy. Both are wrong-shape for a 5×5 matrix portfolio comparison with a deterministic grader. The whole point of the experiment is exposing harness-design variance; wrapping harnesses in a framework that abstracts them defeats the argument.

Stack: `anthropic` (0.96.x) + `beautifulsoup4` + `lxml` + `pandas` (2.x pinned, NOT 3.0) + `matplotlib` + `pytest` + `uv` for env. Single-file HTML trace viewer in vanilla JS, no framework. OpenTelemetry GenAI semantic conventions as naming guide for JSONL schema, but not the OTel SDK itself.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 (min), tested on 3.11–3.13 | Runtime | Already pinned in `pyproject.toml`. 3.11 is the min floor for modern typing + tomllib + speedups; no reason to go higher for a laptop script. Confidence: HIGH. |
| `anthropic` (Python SDK) | `>=0.96.0,<1.0` | Only model client | Latest is 0.96.0 (Apr 16, 2026). Tool use has been GA since 0.27.0 (May 2024). Pin tight because SDK is pre-1.0 and occasionally rewrites types. PROJECT.md constrains to this SDK. Confidence: HIGH. |
| `claude-sonnet-4-6` (model id) | n/a (server-side) | Frozen model under test | Exact id is `claude-sonnet-4-6`. Released Feb 15, 2026. Pricing $3/$15 per MTok I/O. 1M ctx beta. PROJECT.md freezes at `temperature=0`, `max_tokens=2048`. Confidence: HIGH. |
| `beautifulsoup4` | `>=4.12,<5` | HTML parsing in tools | Already in constraints. For a 5-fixture benchmark, parse speed is irrelevant — developer ergonomics dominate. Keep it. Confidence: HIGH. |
| `lxml` | `>=5.2,<6` | bs4 backend (`features="lxml"`) | Standard bs4 companion; handles malformed HTML reliably. Confidence: HIGH. |
| `pandas` | `>=2.2,<3.0` **(pin below 3.0)** | Aggregate CSV + chart data | Pandas 3.0 (Jan 21, 2026) ships breaking changes (copy-on-write default, removed deprecated APIs). For a weekend project, pin 2.2.x to avoid eating debug time on unrelated breakage. Confidence: HIGH. |
| `matplotlib` | `>=3.10,<4` | Charting | 3.10.8 current (Dec 2025). Stable, boring, no competitor worth adding. Save plotly/altair for interactive dashboards (not the point here). Confidence: HIGH. |
| `pytest` | `>=8.3,<10` | Tests + CI | pytest 9.0.3 current (Apr 7, 2026). 9.x tightens deprecation warnings to errors. A floor of 8.3 gives you wiggle room; let CI use whatever is latest. Confidence: HIGH. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | `>=1.0` | Load `ANTHROPIC_API_KEY` from `.env` | `.env.example` already exists — use it. Standard practice. |
| `tenacity` | `>=9.0` | Retry with backoff on 429 / 5xx from Anthropic | Anthropic SDK has some built-in retry but a decorator around `model.call()` gives you logged, bounded retry that also shows up in the JSONL trace. Optional — only add if pilot run shows flakes. |
| `tqdm` | `>=4.66` | Progress bars for the matrix run | 25 runs × N seeds is long enough to want a bar. Tiny dep, zero risk. |
| `rich` | `>=13.9` (optional) | Pretty console output for cost estimator + run summary | Makes the cost-estimator gate feel like a real CLI. Pure dev polish. Skip if time-constrained. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Package + env manager | Replace plain `pip`/`venv`. `uv sync`, `uv run`, lockfile via `uv.lock`. Fast, reproducible, Windows-bash friendly. Astral, 2026 default. |
| `ruff` | Lint + format (replaces black, isort, flake8) | Single tool, one `[tool.ruff]` block in `pyproject.toml`. Astral. |
| `pytest-cov` | Coverage report in CI | Optional but trivial to add. |
| GitHub Actions | CI: lint + pytest + 1-task pilot | `ubuntu-latest` runner is fine; the project also needs to *run* on Windows-bash locally (per constraints), but CI on Linux is acceptable and faster. |

---

## Installation

```bash
# Project already has pyproject.toml. Recommended uv-based flow:

# 1. Create env and install runtime + dev deps
uv sync --all-extras

# Or, if keeping classic pip:
pip install -e ".[dev]"

# Core runtime dependencies (pin in pyproject.toml):
#   anthropic>=0.96,<1.0
#   beautifulsoup4>=4.12,<5
#   lxml>=5.2,<6
#   pandas>=2.2,<3.0
#   matplotlib>=3.10,<4
#   python-dotenv>=1.0
#   tqdm>=4.66

# Dev dependencies:
#   pytest>=8.3
#   pytest-cov
#   ruff
```

---

## The Three Big Questions

### 1. Inspect AI vs DSPy vs roll-your-own: **roll-your-own**

| Option | Latest | Verdict | Why |
|--------|--------|---------|-----|
| Inspect AI (`inspect-ai`) | 0.3.210 (Apr 22, 2026) | **Do not use** for this project | Inspect's primitives (`Task` / `Solver` / `Scorer`) are exactly what you're trying to *vary and compare*. Using Inspect forces every harness into Inspect's Solver contract, which (a) homogenizes exactly the thing you want to expose differences in, (b) adds a dependency whose internals readers must understand to audit your results, and (c) couples the repo to a framework that is still 0.3.x and breaks across point releases. Inspect is right for *running standardized evals against one model*, not for *varying the orchestration layer itself*. |
| DSPy | 2.x | **Do not use** | DSPy is a prompt-compilation / program-synthesis framework. It abstracts away the control loop and substitutes its own (Predict, ChainOfThought, ReAct modules). If you use DSPy, your "harnesses" become DSPy modules with DSPy's loop underneath — you're comparing DSPy configs, not harness designs. Story dies. |
| LangChain / LangGraph | n/a | **Do not use** | Same objection as DSPy, plus: LangChain's trace format is proprietary and the dependency tree is famously heavy. Violates "minimum-surface-area reproducibility" from PROJECT.md. |
| Roll your own | — | **Use this** | Each harness is ~100–200 lines of orchestration over `client.messages.create()`. You already have `harnesses/{base, single_shot, react, plan_execute}.py`. Finish `reflexion.py` and `minimal.py` the same way. Readers can audit every byte. |

**Rationale, in one line:** frameworks *are* the independent variable in this experiment; you cannot measure them by running under them.

**When the opposite is true** (so the reader can evaluate the decision honestly): if the project were *"benchmark Sonnet 4.6 against GPT-5 on HellaSwag"*, Inspect would be the right call — it ships the models layer, the scorers, and a log viewer for free, and the harness is not the variable.

Confidence: MEDIUM-HIGH. No reviewer-credibility risk in rolling your own when you explain the rationale; the risk flips if you adopt a framework without explaining why.

### 2. Anthropic SDK tool-use pattern: **manual loop, not `tool_runner`**

Current (0.96.x) API:

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2048,
    temperature=0,
    tools=[{"name": "read_html", "description": "...", "input_schema": {...}}],
    messages=messages,
)
# Loop: check response.stop_reason == "tool_use", extract tool_use blocks,
# execute, append assistant message + tool_result user message, re-call.
```

**Use the manual loop.** The SDK also ships a `@beta_tool` decorator + `tool_runner` helper that auto-executes tools. **Do not use it here**, because:

1. It's in `anthropic.beta.*` — beta surface can change between minor versions.
2. It hides the loop, which is exactly what each harness needs to express *differently*. `react` loops until stop_reason is `end_turn`; `single_shot` short-circuits after one call; `plan_execute` runs two loops; `minimal` has no tools at all. A helper that auto-handles everything defeats the demonstration.
3. Your `model.call()` abstraction must own `stop_reason`, token usage, and trace emission. A runner that eats those hides the three numbers the article is about.

Relevant `stop_reason` values to branch on: `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`, `pause_turn`, `refusal`. Only `tool_use` drives the loop; the others terminate.

Confidence: HIGH (manual loop is documented, widely used, and what the existing `harnesses/base.py` already does).

### 3. JSONL trace format: **own schema, informed by OTel GenAI semconv, not OTel SDK**

**There is no single de-facto JSONL standard.** The closest things are:

- **OpenTelemetry GenAI Semantic Conventions** (experimental, 2026) — defines `gen_ai.*` attribute names (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.operation.name = "chat" | "invoke_agent"`). Protobuf over the wire, not JSONL.
- **Langfuse / LangSmith / OpenLLMetry** — each has its own schema; none interoperate.
- **Claude Code's own session transcript** — JSONL, one record per message. Informal.

**Recommendation:** define a small, documented JSON schema. Borrow attribute *names* from OTel GenAI where they exist; do not take the OTel SDK dependency.

Minimal per-event schema for this project:

```json
{
  "ts": "2026-04-23T12:34:56.789Z",
  "run_id": "run_2026-04-23_01",
  "harness": "react",
  "task_id": "extract_product_01",
  "seed": 0,
  "event": "model_call" | "tool_call" | "tool_result" | "run_start" | "run_end" | "error",
  "step": 3,
  "gen_ai.request.model": "claude-sonnet-4-6",
  "gen_ai.usage.input_tokens": 1820,
  "gen_ai.usage.output_tokens": 412,
  "gen_ai.usage.cache_read_input_tokens": 0,
  "stop_reason": "tool_use",
  "latency_ms": 4211,
  "payload": { "messages": [...], "response_content": [...] }
}
```

Rules:
- **Append-only**, one JSON object per line, UTF-8, `\n` separator.
- One file per run in `traces/{run_id}/{harness}__{task_id}__s{seed}.jsonl`.
- Every model call writes both a pre-call event (inputs/messages) and a post-call event (response, usage, stop_reason). Tool calls get their own events.
- Never mutate prior lines. Never rewrite on retry — log the retry as a new event.

This lines up with the "traces from call 1" constraint in PROJECT.md: the writer lives inside `model.call()` and every harness inherits it for free.

Confidence: MEDIUM. The schema itself is a design choice, not a discovery; the high-confidence part is that no existing JSONL standard is worth adopting.

### 4. HTML extraction library: **keep beautifulsoup4, do not switch to selectolax**

Benchmarks show selectolax is ~10–30× faster than bs4+lxml (rushter's commoncrawl benchmark: 16s vs 432s on 10K pages). **Irrelevant here.** You have *5 fixtures*. Total HTML-parse time in an entire matrix run is measured in milliseconds. API latency (seconds per call) is 1000× the parse cost.

Keep `beautifulsoup4 + lxml` because:
- Already in the stated constraints (PROJECT.md).
- More forgiving of malformed HTML, which the fixtures deliberately contain.
- Reader-familiar: most Python devs read bs4 code natively; selectolax calls are less common and require explaining.
- Zero performance argument at this scale.

**Switch to selectolax only if** the project ever grows to ≥10K-fixture scale or runs inside a latency-sensitive path. Neither applies.

Confidence: HIGH.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| roll-your-own harnesses | Inspect AI 0.3.x | If the experiment flipped to "compare models on a fixed benchmark," Inspect ships Anthropic adapter + log viewer + scorers for free. |
| roll-your-own harnesses | DSPy 2.x | If the goal were "which *optimized* prompt program wins" rather than "which *harness design* wins." |
| manual tool-use loop | `anthropic.beta.tool_runner` | Short scripts where the loop is incidental and not under study. Not here. |
| `beautifulsoup4` + `lxml` | `selectolax` (0.4.7, lexbor backend) | ≥1K HTML docs, latency-sensitive pipelines. |
| `pandas` 2.2.x | `pandas` 3.0.x | New projects that can absorb copy-on-write semantics and have CI time to debug. Not for a weekend. |
| `pandas` 2.2.x | `polars` 1.x | Large-scale analytics. Overkill at 5×5×N rows; adds a dep for no benefit. |
| `matplotlib` | `plotly` / `altair` | Interactive HTML dashboards. The trace viewer is the interactive surface; charts in the article are static PNGs. |
| `matplotlib` | `seaborn` | If you want pretty defaults for the success-vs-cost frontier. Thin wrapper; pull in only if the default mpl look is too spartan for the article. |
| own JSONL schema | OTel GenAI + SDK (`opentelemetry-sdk` + `opentelemetry-instrumentation-anthropic` via OpenLLMetry) | Production observability where multiple backends consume traces. Here it adds a large dep tree and an OTLP export target you won't use. |
| `uv` | plain `pip` + `venv` | If you can't install uv (you can — it's a single binary on Windows). |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LangChain / LangGraph | Heavy dep tree, proprietary trace format, abstracts the exact control loop you're comparing. | Your own `harnesses/*.py`. |
| DSPy | Turns harnesses into DSPy modules; invalidates comparison. | Your own `harnesses/*.py`. |
| Inspect AI | Homogenizes Solver contract; right tool, wrong job. | Your own runner. |
| `anthropic.beta.tool_runner` | Hides the loop; obscures `stop_reason` / usage / traces. | Manual `messages.create()` loop inside `model.call()`. |
| `tiktoken` for token counts | Wrong tokenizer. Claude uses a different BPE than OpenAI. | `client.messages.count_tokens(...)` (free, rate-limited) or trust `response.usage` after the fact. |
| `pandas` 3.0.x | Breaking changes landed Jan 2026; will burn debug budget on unrelated issues. | Pin `pandas>=2.2,<3.0`. |
| OpenTelemetry SDK + OpenLLMetry | Production-observability scope, OTLP collector, protobuf — overkill for JSONL-on-disk. | Plain JSONL writer, borrow OTel `gen_ai.*` field *names*. |
| `requests` for Anthropic calls | Duplicates SDK retry/streaming logic, invites drift. | `anthropic.Anthropic()` client, always. |
| Docker | Explicitly out of scope per PROJECT.md ("Windows + bash, no docker"). | Pure Python + uv. |
| W&B / MLflow / Langfuse | Out of scope per PROJECT.md (production observability). | JSONL + the standalone HTML viewer. |
| Jupyter notebooks for the analysis step | Non-reproducible ordering, diffs badly in git, doesn't fit the "post-run script" requirement. | A single `analyze.py` script that reads JSONL and writes CSV + PNG. |

---

## Stack Patterns by Variant

**If you later want to add a second model provider (you won't per PROJECT.md, but hypothetically):**
- `model.py` grows a provider switch; don't reach for LiteLLM unless you add ≥3 providers.
- Confidence: LOW (not in scope).

**If the fixture count grows to 50+:**
- Add `concurrent.futures.ThreadPoolExecutor` inside the runner (Anthropic SDK is thread-safe). Still no provider/framework change.
- Consider `selectolax` only past 10K fixtures.

**If you want an interactive chart in the article:**
- Export the aggregate DataFrame as JSON, render with a tiny vanilla-JS chart lib (uPlot, Chart.js) inside the same single-file HTML trace viewer. Do not add `plotly` to the Python stack.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `anthropic>=0.96` | Python 3.9+ | Requires 3.9 min; project pins 3.11. |
| `pandas>=2.2,<3` | Python 3.9–3.13 | Pandas 3.0 raises floor to 3.11 — not yet our problem. |
| `matplotlib 3.10.x` | Python 3.10–3.14 | Clean overlap. |
| `pytest>=8.3` | Python 3.8+ (9.x drops 3.9) | Fine. |
| `beautifulsoup4 4.12.x` | Python 3.7+ | Fine. |
| `lxml>=5.2` | Python 3.6+; needs C build on some Windows setups — wheels are published, so `uv sync` usually just works | Watch for install failures on unusual Windows Python builds; fallback is `html.parser`. |
| `selectolax 0.4.7` | Python >=3.9,<3.15 | Not using, noted for completeness. |

---

## Sources

- [anthropic on PyPI](https://pypi.org/project/anthropic/) — version 0.96.0 (2026-04-16). HIGH.
- [Claude tool-use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) — manual loop pattern, `stop_reason` values, token overhead table. HIGH.
- [Claude Sonnet 4.6 announcement](https://www.anthropic.com/news/claude-sonnet-4-6) — model id `claude-sonnet-4-6`, 2026-02-15 release. HIGH.
- [Claude pricing docs](https://platform.claude.com/docs/en/about-claude/pricing) — $3/$15 per MTok, prompt caching multipliers. HIGH.
- [inspect-ai on PyPI](https://pypi.org/project/inspect-ai/) — 0.3.210 (2026-04-22), Python >=3.10. HIGH for version, MEDIUM for fit-for-purpose judgment (that's an opinion backed by Inspect's own docs).
- [Inspect framework page](https://inspect.aisi.org.uk/) — Task/Solver/Scorer primitives, built-in ReAct. HIGH.
- [selectolax on PyPI](https://pypi.org/project/selectolax/) — 0.4.7 (2026-03-06), lexbor backend recommended. HIGH.
- [rushter selectolax benchmark](https://rushter.com/blog/python-fast-html-parser/) — 10K commoncrawl pages: 16s vs 432s. HIGH.
- [matplotlib on PyPI](https://pypi.org/project/matplotlib/) — 3.10.8 (2025-12-10). HIGH.
- [pandas on PyPI](https://pypi.org/project/pandas/) — 3.0.2 (2026-03-31). HIGH.
- [pandas 3.0 breaking changes](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html) — CoW default, API removals. HIGH.
- [pytest on PyPI](https://pypi.org/project/pytest/) — 9.0.3 (2026-04-07). HIGH.
- [OpenTelemetry GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — `gen_ai.*` attribute names (used for schema naming, not as SDK dep). MEDIUM (experimental spec).
- [uv docs](https://docs.astral.sh/uv/) — package/env manager. HIGH.
- [KDnuggets 2026 Python setup](https://www.kdnuggets.com/python-project-setup-2026-uv-ruff-ty-polars) — uv + ruff as 2026 default. MEDIUM (opinion piece, matches direct Astral docs).

---
*Stack research for: LLM agent harness benchmarking experiment (harness_eng)*
*Researched: 2026-04-23*
