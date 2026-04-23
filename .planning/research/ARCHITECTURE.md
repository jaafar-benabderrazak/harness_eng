# Architecture Research

**Domain:** LLM agent harness engineering / controlled comparative eval
**Researched:** 2026-04-23
**Confidence:** HIGH on component decomposition and sealing pattern (constraints are explicit in PROJECT.md and map cleanly to established eval-harness patterns); MEDIUM on specific base-class enforcement details (these are design choices, not industry-standard).

## Standard Architecture

The project is a miniature, single-process eval harness. It is not a service. No multi-user scale concerns apply. What matters is **experimental integrity**: the model must be held constant across five harnesses, and this must be enforceable, not merely documented.

The architecture is shaped by four hard rules carried over from PROJECT.md:

1. `anthropic` SDK is imported in **exactly one file** (`src/harness_eng/model.py`). Any other import of `anthropic` is a defect.
2. Every harness routes every model call through `model.call(...)`. No harness holds its own `Anthropic()` client.
3. Every model call and every tool call writes a trace event **before returning to the harness**. Trace writing is a side effect of the model/tool layer, not of the harness.
4. Tools are shared implementations; which subset a harness may call is a per-harness whitelist (the `minimal` harness, for example, has no `read_html`).

### System Overview

```
                          ┌──────────────────────────────┐
                          │          runner.py            │
                          │  (matrix: harness × task ×    │
                          │   seed; sequential; no        │
                          │   anthropic import)           │
                          └──────────────┬───────────────┘
                                         │ iterates
          ┌──────────────────────────────┼────────────────────────────┐
          │                              │                            │
          ▼                              ▼                            ▼
   ┌─────────────┐              ┌──────────────┐             ┌────────────────┐
   │ tasks/      │              │ harnesses/   │             │ trace.py       │
   │  loader.py  │              │  base.py     │             │ (append-only   │
   │  tasks.jsonl│              │  single_shot │             │  JSONL writer; │
   │  fixtures/  │              │  react       │◄──────┐     │  single writer │
   └──────┬──────┘              │  plan_execute│       │     │  per run)      │
          │                     │  reflexion   │       │     └────────▲───────┘
          │  Task               │  minimal     │       │              │
          │  (html, targets,    └──────┬───────┘       │              │
          │   tool_whitelist)          │               │              │
          │                            │ model.call    │              │
          └──► handed to harness ──►   ▼               │              │
                                  ┌─────────────┐      │              │
                                  │ model.py    │──────┼──────────────┤
                                  │ (ONLY file  │      │  trace event │
                                  │  that       │      │  (model_call)│
                                  │  imports    │      │              │
                                  │  anthropic) │      │              │
                                  └──────┬──────┘      │              │
                                         │             │              │
                                         │ tool_use    │              │
                                         ▼             │              │
                                  ┌─────────────┐      │              │
                                  │ tools.py    │──────┘              │
                                  │ (shared     │   trace event       │
                                  │  impls +    │   (tool_call)       │
                                  │  whitelist  │─────────────────────┘
                                  │  enforcer)  │
                                  └─────────────┘

                                         ▼  (writes JSONL)
                                  ┌──────────────────┐
                                  │ runs/<id>/       │
                                  │   trace.jsonl    │
                                  │   results.jsonl  │
                                  └────────┬─────────┘
                                           │ (reads after run)
                                           ▼
                                  ┌───────────────────────┐
                                  │ analysis/             │
                                  │  grader.py            │
                                  │  aggregate.py ──► CSV │
                                  │  charts.py    ──► PNG │
                                  │  article.py   ──► MD  │
                                  │  viewer.html (static) │
                                  └───────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Forbidden from |
|-----------|----------------|----------------|
| `config.py` | Single source of truth for model id, temperature, max_tokens, API key lookup, run directory layout. Dataclass-style frozen constants. | Importing `anthropic`. Reading env vars outside a designated loader function. |
| `model.py` | **Only** file that imports `anthropic`. Exposes `call(messages, tools, *, harness_id, task_id, step) -> ModelResponse`. Applies frozen config. Emits `model_call` trace event (request + response + token usage) before returning. | Holding any per-harness state. Accepting overrides to temperature/max_tokens/model id. |
| `tools.py` | Shared implementations of HTML-fetch / DOM-extract / field-write tools. Exposes `dispatch(tool_name, args, *, allowed_tools, harness_id, task_id, step)` which rejects unlisted tools and emits `tool_call` trace event. | Importing `anthropic`. Knowing which harness is calling it beyond the whitelist parameter. |
| `trace.py` | Append-only JSONL writer. One writer instance per run. Thread-unsafe is fine (runner is sequential). Schema owner: defines event types (`run_start`, `task_start`, `model_call`, `tool_call`, `harness_step`, `task_end`, `run_end`). | Being imported by harnesses directly — they touch it through base class only. |
| `harnesses/base.py` | Abstract base. Constructor takes `model_caller`, `tool_dispatcher`, `tracer`, `tool_whitelist`, `token_budget`. Implements `run(task) -> HarnessResult` template method that: (a) opens a `harness_step` span, (b) delegates to subclass `_step()` / `_plan()` / whatever the subclass defines, (c) accumulates tokens from every `ModelResponse`, (d) enforces budget, (e) closes span. Subclasses **must not** accept an `Anthropic` client. | Providing any method that subclasses can override to skip trace writing or token accounting. |
| `harnesses/{single_shot,react,plan_execute,reflexion,minimal}.py` | The **only** independent variable. Each implements one control-flow strategy using `self.model_call(...)` and `self.tool_dispatch(...)` inherited from base. Never touches trace writer or token counter directly. Never imports `anthropic`. | Importing `anthropic`. Instantiating their own model client. Receiving anything but the injected dependencies. Modifying config. |
| `tasks/loader.py` | Reads `tasks.jsonl`, loads HTML fixtures from `fixtures/`, yields `Task` objects containing `task_id, html, expected_fields, grader_config`. | Knowing which harness will consume it. |
| `tasks/tasks.jsonl` + `fixtures/` | Data only. | — |
| `grader.py` | Pure function: `grade(expected, produced) -> {field: bool, score: float}`. Normalized exact match per field. Deterministic. No I/O beyond what the caller passes in. | Reading traces. It grades the harness's final output, not the trace. |
| `runner.py` / `run_matrix.py` | Orchestrates the matrix. For each (harness, task, seed): instantiate harness via factory, call `harness.run(task)`, grade result, write `results.jsonl` row. Sequential. Owns the run directory. | Importing `anthropic`. Calling `model.call` directly — it only goes through harnesses. |
| `analysis/aggregate.py` | Reads `results.jsonl` + `trace.jsonl`, produces `summary.csv` (per-harness success rate, mean cost, mean latency, token totals). | Live API calls. |
| `analysis/charts.py` | Reads `summary.csv` and per-field data, emits success-rate-vs-cost frontier PNG and per-field heatmap PNG. matplotlib only. | Any network. |
| `analysis/article.py` | Reads `summary.csv` + selected trace excerpts, emits `article.md` with numbers interpolated and chart paths referenced. Failure-trace examples pulled from JSONL. | Any API call. Generating prose with an LLM (would contaminate the story; article is templated). |
| `viewer.html` | Static, zero-build HTML file that fetches `trace.jsonl` via `fetch()` and renders it with collapsible tool calls. No framework. | Any server. Any build step. |
| `cost_estimator.py` | Dry-run: loads tasks, estimates prompt tokens per harness via a cheap heuristic or a single probe call, prints projected USD. Gate before full matrix. | Running the full matrix. |

## Recommended Project Structure

```
harness_eng/
├── pyproject.toml
├── .env.example
├── README.md
├── src/
│   └── harness_eng/
│       ├── __init__.py
│       ├── config.py              # frozen model settings, paths
│       ├── model.py               # ONLY file importing anthropic
│       ├── trace.py               # JSONL writer + event schema
│       ├── tools.py               # shared tool impls + whitelist dispatcher
│       ├── grader.py              # deterministic per-field grader
│       ├── harnesses/
│       │   ├── __init__.py
│       │   ├── base.py            # sealed contract: trace + tokens enforced
│       │   ├── single_shot.py
│       │   ├── react.py
│       │   ├── plan_execute.py
│       │   ├── reflexion.py       # to build
│       │   └── minimal.py         # to build (no read_html)
│       ├── tasks/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   ├── tasks.jsonl
│       │   └── fixtures/
│       │       ├── task_01.html
│       │       ├── task_02.html
│       │       ├── task_03.html
│       │       ├── task_04.html
│       │       └── task_05.html
│       ├── runner.py              # matrix orchestration
│       ├── cost_estimator.py      # pre-run gate
│       └── analysis/
│           ├── __init__.py
│           ├── aggregate.py       # JSONL → CSV
│           ├── charts.py          # CSV → PNG
│           └── article.py         # CSV + traces → MD
├── scripts/
│   ├── run_matrix.py              # thin CLI wrapper over runner
│   ├── estimate_cost.py
│   ├── aggregate.py
│   ├── render_charts.py
│   └── draft_article.py
├── viewer/
│   └── viewer.html                # standalone trace viewer
├── tests/
│   ├── test_model_seal.py         # AST check: no anthropic import outside model.py
│   ├── test_grader.py
│   ├── test_tools_whitelist.py
│   ├── test_trace_schema.py
│   ├── test_harness_base_contract.py
│   └── test_pilot_one_task.py     # CI smoke test
├── runs/                          # gitignored; one subdir per run
│   └── <run_id>/
│       ├── trace.jsonl
│       ├── results.jsonl
│       ├── summary.csv
│       ├── frontier.png
│       ├── heatmap.png
│       └── article.md
└── .github/
    └── workflows/
        └── ci.yml
```

### Structure Rationale

- **`src/harness_eng/` layout:** keeps import paths explicit (`from harness_eng.model import call`) and prevents the harnesses/ folder at repo root from being mistaken for the package boundary. Scripts in `scripts/` are thin wrappers so that the package stays importable from tests without side effects.
- **`harnesses/` as a subpackage, not top-level:** forces harnesses to be imported through the package namespace, which makes the "no direct anthropic import" test trivial to write (walk the package, parse AST).
- **`analysis/` as a subpackage:** physically separates post-run code from experimental code. Analysis can be iterated after results are frozen without risking the experiment.
- **`runs/<run_id>/` as the single output directory:** one run = one directory = one immutable artifact set. Article, CSV, charts, traces all colocated. Easy to archive or delete.
- **`viewer/viewer.html` outside `src/`:** it is not Python and not part of the package. Opened directly in a browser against a `runs/<id>/trace.jsonl`.
- **`tests/test_model_seal.py`:** the seal is enforced by a test, not by code review. Static check that `anthropic` appears as an import only in `src/harness_eng/model.py`.

## Architectural Patterns

### Pattern 1: Sealed Model Boundary (Single Import Site)

**What:** `anthropic` is imported in exactly one file (`model.py`). Everything else calls `model.call(...)`. The seal is enforced by an AST-walking unit test, not by convention.

**When to use:** Any controlled experiment where the "independent variable" is some layer around a fixed dependency, and drift in the dependency's parameters would invalidate conclusions.

**Trade-offs:**
- Pro: makes "we held the model constant" a machine-checkable claim, not a reviewer-checkable one. This is the main artifact.
- Pro: centralizes retry, rate-limit, and error handling.
- Con: adds one layer of indirection. Acceptable; the indirection is the point.
- Con: if Anthropic SDK types leak through the return value, users of `model.call` transitively depend on the SDK. Mitigation: return a `ModelResponse` dataclass defined in `model.py`, not the raw SDK object.

**Example:**
```python
# src/harness_eng/model.py
from anthropic import Anthropic
from harness_eng.config import MODEL_ID, TEMPERATURE, MAX_TOKENS
from harness_eng.trace import Tracer

_client = Anthropic()  # module-level; config comes from env via SDK's default

@dataclass(frozen=True)
class ModelResponse:
    text: str
    tool_uses: list[ToolUse]
    input_tokens: int
    output_tokens: int
    stop_reason: str
    # NOTE: no `raw` field exposing the SDK object — keeps the seal tight.

def call(messages, tools, *, harness_id, task_id, step, tracer: Tracer) -> ModelResponse:
    req_id = tracer.emit("model_call_request", harness_id=harness_id, task_id=task_id,
                         step=step, messages=messages, tools=[t["name"] for t in tools])
    resp = _client.messages.create(
        model=MODEL_ID, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
        messages=messages, tools=tools,
    )
    result = ModelResponse(...)  # normalize
    tracer.emit("model_call_response", req_id=req_id, input_tokens=result.input_tokens,
                output_tokens=result.output_tokens, stop_reason=result.stop_reason)
    return result
```
```python
# tests/test_model_seal.py
import ast, pathlib
PKG = pathlib.Path("src/harness_eng")
def test_anthropic_imported_only_in_model_py():
    offenders = []
    for py in PKG.rglob("*.py"):
        if py.name == "model.py":
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + [getattr(node, "module", "") or ""]
                if any(n and n.startswith("anthropic") for n in names):
                    offenders.append(str(py))
    assert offenders == [], f"anthropic imported outside model.py: {offenders}"
```

### Pattern 2: Sealed Harness Base Class (Template Method + Dependency Injection)

**What:** `HarnessBase` owns the outer run loop, trace-span opening, token accumulation, budget enforcement, and final result packaging. Subclasses implement only the control-flow decision (what to do on each step). Subclasses receive `model_call` and `tool_dispatch` as bound methods — they cannot construct their own.

**When to use:** When multiple implementations of a strategy must be comparable, and the comparison requires that every implementation has paid the same accounting cost.

**Trade-offs:**
- Pro: per-harness files stay short and read like the paper's pseudocode.
- Pro: adding a 6th harness is one file, not one file plus duplicated bookkeeping.
- Con: template methods can become invasive if the base class tries to dictate too much of the control flow. Solution: keep the base's public contract small — inject dependencies, wrap `run()`, provide `self.model_call` and `self.tool_dispatch` helpers, nothing else.

**Example:**
```python
# src/harness_eng/harnesses/base.py
class HarnessBase(abc.ABC):
    name: ClassVar[str]

    def __init__(self, *, model_caller, tool_dispatcher, tracer,
                 tool_whitelist: frozenset[str], token_budget: int):
        self._model_caller = model_caller
        self._tool_dispatcher = tool_dispatcher
        self._tracer = tracer
        self._whitelist = tool_whitelist
        self._budget = token_budget
        self._tokens_in = 0
        self._tokens_out = 0

    # Subclasses call these; they do NOT call model/tools/tracer directly.
    def model_call(self, messages, tools, *, task_id, step):
        allowed = [t for t in tools if t["name"] in self._whitelist]
        resp = self._model_caller(messages, allowed, harness_id=self.name,
                                  task_id=task_id, step=step, tracer=self._tracer)
        self._tokens_in += resp.input_tokens
        self._tokens_out += resp.output_tokens
        if self._tokens_in + self._tokens_out > self._budget:
            raise TokenBudgetExceeded(self.name, task_id, self._tokens_in, self._tokens_out)
        return resp

    def tool_dispatch(self, name, args, *, task_id, step):
        return self._tool_dispatcher(name, args, allowed_tools=self._whitelist,
                                     harness_id=self.name, task_id=task_id,
                                     step=step, tracer=self._tracer)

    # Template method — final; subclasses override _solve.
    def run(self, task) -> HarnessResult:
        span = self._tracer.open_span("harness_step", harness_id=self.name, task_id=task.id)
        try:
            output = self._solve(task)
            return HarnessResult(output=output, tokens_in=self._tokens_in,
                                 tokens_out=self._tokens_out, harness_id=self.name)
        finally:
            self._tracer.close_span(span, tokens_in=self._tokens_in, tokens_out=self._tokens_out)

    @abc.abstractmethod
    def _solve(self, task) -> dict: ...
```

The subclass surface area is intentionally tiny:
```python
# src/harness_eng/harnesses/single_shot.py
class SingleShot(HarnessBase):
    name = "single_shot"
    def _solve(self, task):
        resp = self.model_call(messages=[...prompt with task.html...], tools=[],
                               task_id=task.id, step=0)
        return parse_fields(resp.text)
```

### Pattern 3: Append-Only JSONL Trace, Single Writer

**What:** One `Tracer` instance per run. All events serialized to one `trace.jsonl` file. Events are dicts with a `ts`, `type`, `run_id`, `harness_id`, `task_id`, `step`, plus type-specific fields. Writes happen inside `model.py` and `tools.py`; harnesses do not write directly. Runner writes `run_start` / `run_end` / `task_start` / `task_end`.

**When to use:** Any experiment where traces must exist from the first call and must be greppable/streamable. JSONL beats structured databases for laptop-scale single-process workloads because it is trivially inspectable.

**Trade-offs:**
- Pro: post-run tooling is one `pandas.read_json(..., lines=True)` away.
- Pro: append-only means a crash mid-run still leaves partial data usable.
- Con: no query indexing. Fine at 5×5×N scale; would hurt at 10k runs.
- Con: schema drift risk. Mitigation: version each event with a `schema_version` field; freeze schema before harnesses run.

### Pattern 4: Tool-Whitelist Dispatcher (Capability Restriction by Harness)

**What:** `tools.dispatch(name, args, *, allowed_tools, ...)` rejects calls to any tool not in `allowed_tools`. The whitelist is set at harness construction time and flows through the base class to every tool call. Minimal harness is simply `tool_whitelist = frozenset()` or `frozenset({"write_field"})`.

**When to use:** Whenever differing tool availability is part of the independent variable. Prompt-level restriction ("don't use read_html") is not structurally enforced; whitelist dispatch is.

**Trade-offs:**
- Pro: "minimal omits read_html" is a fact about the code, not a fact about the prompt.
- Con: the model may still *attempt* to call a forbidden tool. The dispatcher must return a structured error that the harness can surface back to the model, and the trace records the rejected attempt.

### Pattern 5: Immutable Run Directory

**What:** Each invocation of `runner.py` creates `runs/<ISO8601>_<git_sha>/` and writes everything there. Never overwrites. Analysis always reads from a specific run dir. Article generator takes a run dir as argument.

**When to use:** Any reproducibility-sensitive project. Free to implement; prevents an entire class of "which numbers are in the article" confusion.

## Data Flow

### End-to-End Flow (one cell of the matrix)

```
runner.py
  ├─ creates runs/<id>/
  ├─ opens Tracer(runs/<id>/trace.jsonl)
  ├─ emits run_start
  │
  ├─ for each (harness_cls, task):
  │     ├─ task = tasks.loader.load(task_id)          (Task: html, expected, whitelist_override?)
  │     ├─ harness = harness_cls(
  │     │       model_caller=model.call,
  │     │       tool_dispatcher=tools.dispatch,
  │     │       tracer=tracer,
  │     │       tool_whitelist=harness_cls.TOOL_WHITELIST,
  │     │       token_budget=config.TOKEN_BUDGET)
  │     ├─ tracer.emit(task_start, harness, task)
  │     │
  │     ├─ result = harness.run(task)
  │     │    │
  │     │    ├─ harness._solve(task):
  │     │    │    ├─ self.model_call(...)
  │     │    │    │    └─ model.call(...)
  │     │    │    │         ├─ tracer.emit(model_call_request)
  │     │    │    │         ├─ anthropic.messages.create(...)
  │     │    │    │         ├─ tracer.emit(model_call_response)
  │     │    │    │         └─ return ModelResponse
  │     │    │    │    (base accumulates tokens, checks budget)
  │     │    │    │
  │     │    │    ├─ self.tool_dispatch(name, args, ...)
  │     │    │    │    └─ tools.dispatch(...)
  │     │    │    │         ├─ tracer.emit(tool_call_request)
  │     │    │    │         ├─ tool impl executes
  │     │    │    │         ├─ tracer.emit(tool_call_response)
  │     │    │    │         └─ return result
  │     │    │    │
  │     │    │    └─ return produced_fields: dict
  │     │    │
  │     │    └─ return HarnessResult(output, tokens_in, tokens_out)
  │     │
  │     ├─ grade = grader.grade(task.expected, result.output)
  │     ├─ append {harness, task, grade, tokens, latency, cost} to results.jsonl
  │     └─ tracer.emit(task_end, grade, tokens)
  │
  └─ tracer.emit(run_end); close.

Post-run (separate process, reads runs/<id>/ only):
  aggregate.py   : trace.jsonl + results.jsonl  →  summary.csv
  charts.py      : summary.csv                  →  frontier.png, heatmap.png
  article.py     : summary.csv + trace excerpts →  article.md
  viewer.html    : fetch('trace.jsonl') in browser
```

### Single-Writer, Single-Source Invariants

| Invariant | How enforced |
|-----------|--------------|
| Only `model.py` imports `anthropic` | AST test (`test_model_seal.py`) |
| Only `model.py` and `tools.py` write trace events about model/tool calls | Harnesses don't receive the tracer directly; they receive `self.model_call` / `self.tool_dispatch` helpers that call into the sealed layer |
| Only one `Tracer` instance per run | Constructed in `runner.py`, passed down; no module-level singletons |
| Only one `results.jsonl` per run | Opened by runner, appended per cell |
| Only `config.py` holds model id / temperature / max_tokens | `model.call` reads from config module, does not accept overrides |
| Only the runner writes to `runs/<id>/` | Analysis scripts read; they take a run dir argument |

## Build Order

Derived from the dependency graph. The rule: nothing that imports a higher-numbered layer can be built before that layer is stable.

### Phase A — Foundations (blocks everything)

1. `config.py` — frozen model id, temperature, max_tokens, paths, budget constant.
2. `trace.py` — `Tracer` class, event schema (with `schema_version`), JSONL writer.
3. `tasks/loader.py` + `tasks.jsonl` + `fixtures/*` — need at least one task before anything downstream can run end-to-end.
4. `grader.py` — pure function; no dependencies beyond Python stdlib. Can be built and tested in isolation.

**Gate:** `pytest tests/test_grader.py tests/test_trace_schema.py` green.

### Phase B — Sealed core (blocks harnesses)

5. `model.py` — the seal. Exposes `call(...)`. Imports `anthropic`. Emits trace events.
6. `tools.py` — shared tool implementations + whitelist dispatcher. Emits trace events.
7. `harnesses/base.py` — template method, dependency injection, token accounting, budget enforcement.
8. `tests/test_model_seal.py` — AST check. **Must pass before any harness file is written**, otherwise the seal is aspirational.

**Gate:** seal test green. `model.call` can be invoked from a REPL and produces a trace event plus a `ModelResponse`.

### Phase C — First harness end-to-end (blocks matrix)

9. `harnesses/single_shot.py` — simplest harness; validates the base class contract under real load.
10. `runner.py` — orchestrates a single (harness, task) pair first, then the full matrix.
11. Run `single_shot` on one task end-to-end. Inspect `trace.jsonl` manually.

**Gate:** one real API call, one trace file, one graded result. This is the moment the experiment becomes real.

### Phase D — Remaining harnesses (parallelizable after base stabilizes)

12. `harnesses/react.py`
13. `harnesses/plan_execute.py`
14. `harnesses/reflexion.py`
15. `harnesses/minimal.py` (no `read_html` in whitelist)

**Gate:** all five pass `tests/test_harness_base_contract.py` (verifies every harness subclasses `HarnessBase`, declares `TOOL_WHITELIST`, and has no `anthropic` import).

### Phase E — Pre-flight (blocks full matrix)

16. `cost_estimator.py` — reports projected USD for the matrix. Gate before spending.
17. CI workflow running pytest + one-task pilot of `single_shot`.

**Gate:** cost estimate reviewed; CI green on PR.

### Phase F — Full run (blocks analysis)

18. Execute full 5×5×N matrix. Writes `runs/<id>/trace.jsonl` + `results.jsonl`.

**Gate:** run completes, no budget overruns, no seal test regressions.

### Phase G — Analysis (reads from `runs/<id>/` only)

19. `analysis/aggregate.py` → `summary.csv`
20. `analysis/charts.py` → `frontier.png`, `heatmap.png`
21. `analysis/article.py` → `article.md` — **blocked on 19 and 20**; reads CSV, interpolates numbers, embeds chart paths, pulls failure-trace excerpts from `trace.jsonl`.
22. `viewer/viewer.html` — can be built in parallel with 19–21; only depends on the trace schema from Phase A.

### Critical dependencies restated

- **Before harness #1 runs:** `config.py`, `trace.py`, `tasks/loader.py` (with ≥1 task), `model.py`, `tools.py`, `harnesses/base.py`, seal test passing.
- **Before article generator runs:** `summary.csv` exists (depends on `results.jsonl` and `aggregate.py`); charts exist (depends on `charts.py`); trace excerpts come from `trace.jsonl` (which requires the full matrix to have run).
- **Before full matrix runs:** all five harnesses complete + frozen, cost estimate approved, one-task pilot green in CI.

## Anti-Patterns

### Anti-Pattern 1: Per-Harness Anthropic Client

**What people do:** Each harness file imports `anthropic` and constructs `Anthropic()` "for convenience" or "to tweak retry settings."
**Why it's wrong:** Silently invalidates the experiment. A harness can now drift on temperature, model id, retry behavior, or even model family, and no reviewer will notice. The entire "held the model constant" claim collapses.
**Do this instead:** `anthropic` is imported in exactly one file. Harnesses receive `self.model_call(...)` from the base class. Enforced by AST test, not by code review.

### Anti-Pattern 2: Retrofitting Traces After the Run

**What people do:** Run the matrix first, then add trace logging once they notice they need failure examples for the article.
**Why it's wrong:** PROJECT.md calls this out explicitly. The "surprising failures" section needs traces from before you knew what surprised you. Retrofitting produces synthetic, clean examples; real traces expose things you would have pretended didn't happen.
**Do this instead:** Trace writer exists in Phase A. Single-shot harness cannot run until the tracer is injected and emitting events. The first API call of the project produces a trace event.

### Anti-Pattern 3: Harness Owns Token Accounting

**What people do:** Each harness tracks its own token totals and reports them back.
**Why it's wrong:** Five different implementations of the same accounting, five opportunities for a bug that makes one harness look cheaper than it is. The article's cost numbers become uncomparable.
**Do this instead:** `HarnessBase` accumulates tokens from every `ModelResponse` automatically. Subclasses never touch the counters. Budget enforcement lives in the base class.

### Anti-Pattern 4: Tool Restriction by Prompt

**What people do:** The minimal harness is defined by a system prompt that says "do not use read_html."
**Why it's wrong:** The model may comply or may not. The independent variable becomes "prompt wording" rather than "tool availability."
**Do this instead:** `tools.dispatch` rejects any call to a tool not in the harness's whitelist. Minimal harness has `TOOL_WHITELIST = frozenset({"write_field"})`. A rejected attempt is itself a trace event — which is useful data.

### Anti-Pattern 5: Article Generated by the LLM Under Test

**What people do:** Feed the results into the same model and have it write the article.
**Why it's wrong:** Contaminates the story. The model being evaluated should not be narrating its own benchmark. Also, prose generation is not reproducible across reruns; numbers will drift.
**Do this instead:** `analysis/article.py` is a template with f-string or Jinja interpolation. Numbers come from `summary.csv`. Chart references are static paths. Failure-trace excerpts are selected by deterministic rule (e.g., "first task where harness X produced a wrong field"). The article is a function of the CSV.

### Anti-Pattern 6: Iterating on Losing Harnesses After Seeing Results

**What people do:** See that `reflexion` underperformed, tweak its prompt, rerun.
**Why it's wrong:** This is methodology fraud. Any harness that is "improved" after seeing the results is no longer comparable to harnesses that were not. PROJECT.md explicitly flags this as a portfolio-killing error.
**Do this instead:** Freeze all five harnesses before running the full matrix. CI runs a one-task pilot on each to catch bugs; bugs are allowed to be fixed, performance is not allowed to be tuned. A `HARNESSES_FROZEN.md` file with git SHAs is a useful public commitment.

### Anti-Pattern 7: Live API Calls from Analysis Code

**What people do:** The chart script re-fetches something, the article script asks the model to summarize failures.
**Why it's wrong:** Analysis must be deterministic given a run directory. Otherwise every rerun of `charts.py` produces different output and the article becomes unauditable.
**Do this instead:** Analysis code imports only stdlib, pandas, matplotlib. No `harness_eng.model`. The analysis subpackage can have its own `__init__.py` with a test that asserts `anthropic` is not reachable from it.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic API | sole import in `model.py`; uses official `anthropic` Python SDK | Rate limits are the main operational concern at full-matrix scale. Retry with exponential backoff belongs in `model.py`, not in harnesses. Read `ANTHROPIC_API_KEY` from env via SDK default — do not pass it around the codebase. |
| GitHub Actions | CI runs pytest + 1-task pilot on every PR | Needs `ANTHROPIC_API_KEY` as a repo secret for the pilot. Keep pilot cheap (one task, `single_shot`). |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| runner.py ↔ harness | direct Python call (`harness.run(task)`) | Runner owns lifecycle. Harness returns `HarnessResult`, no side-channel output. |
| harness ↔ model.py | through `self.model_call` helper in base class | Harness cannot construct its own caller; injected at construction. |
| harness ↔ tools.py | through `self.tool_dispatch` helper in base class | Whitelist is applied inside dispatch; harness cannot call an unlisted tool even by mistake. |
| model.py + tools.py ↔ trace.py | direct `tracer.emit(...)` calls | Tracer passed in from runner; not a module-level singleton. |
| analysis/* ↔ runs/<id>/ | file I/O only (JSONL read, CSV read, PNG write) | No in-process coupling to experimental code. Analysis can be iterated after results freeze. |
| viewer.html ↔ trace.jsonl | browser `fetch()` of a local file | Open `viewer.html?run=runs/2026-04-23_abc123/` — query param points at the run dir. |

## How Established Eval Harnesses Decompose This (and which pattern fits here)

**Confidence: MEDIUM.** These are observations from training data on Inspect AI (UK AISI), OpenAI Evals, HELM (Stanford CRFM), and DSPy. Specifics of each framework's current API may have drifted; decomposition principles below are stable.

| Framework | Model layer | Harness/Solver layer | Task layer | Grader layer | Fits 5×5 pilot? |
|-----------|-------------|----------------------|------------|--------------|-----------------|
| **Inspect AI** | `Model` abstraction with provider plugins; one-client-per-model-id | `Solver` — composable functions (e.g., `chain_of_thought`, `use_tools`, `generate`) that transform `TaskState` | `Task` with `Dataset` of `Sample`s, `plan` (list of solvers), `scorer` | `Scorer` — pure function `(state, target) -> Score` | Partially. Inspect's solver composition is more granular than "five sealed harnesses"; our harnesses are whole strategies, not composable pieces. But Inspect's separation of `Solver` / `Model` / `Scorer` / `Task` is exactly the split we want. |
| **OpenAI Evals** | `CompletionFn` interface; one implementation per provider | `Eval` class owns the loop, calls `completion_fn` | YAML-defined eval specs + dataset files | Inline grading inside the `Eval` class, or `ModelGradedEval` for LLM-judge | Partially. Good separation of completion function from eval logic. Grader is often coupled to eval class, which we don't want. |
| **HELM** | `Client` per provider, `Request`/`RequestResult` | `Adapter` transforms `Instance`s into `RequestState`s; `Executor` runs requests | `Scenario` produces `Instance`s (input + references) | `Metric`s consume `RequestState`s | Overkill. HELM's adapter/executor/metric/scenario split is designed for hundreds of scenarios × dozens of models. Borrow the naming instincts (scenario-instance-metric), don't adopt the infrastructure. |
| **DSPy** | `LM` client abstraction | `Module` composes predictors; `Teleprompter` optimizes them | Examples in a `Trainset`/`Devset` | `Metric` function | Wrong fit. DSPy's value is in program optimization across a fixed module structure; we want five *different* module structures compared head-to-head with no optimization. |

### What to borrow

- **From Inspect AI:** the `Solver` / `Model` / `Scorer` / `Task` quadripartition. Our `HarnessBase` / `model.py` / `grader.py` / `Task` is the same split at a smaller scale. Our harnesses correspond to whole `plan`s in Inspect terms.
- **From OpenAI Evals:** the `CompletionFn` analog — a callable passed into the harness rather than constructed inside it. Our `model.call` plays this role.
- **From HELM:** the discipline of a `RequestState` / trace event with enough fields to reconstruct exactly what happened. Our `trace.jsonl` schema should be as complete as HELM's request records, not as terse as a log line.
- **From DSPy:** nothing structural for this project — but if the experiment evolves into "optimize one harness across many tasks," DSPy's optimizer pattern becomes relevant.

### What not to borrow

- Do not adopt a plugin-registry architecture for harnesses. Five harnesses × one dev × long weekend. A `harness_id -> HarnessClass` dict in `runner.py` is sufficient.
- Do not adopt YAML task specs. `tasks.jsonl` + HTML fixtures is strictly simpler and more auditable.
- Do not adopt an LLM-as-judge grader. The whole point is deterministic per-field exact match; LLM judges would reintroduce the "the judge sees its own output" failure mode this project is built to avoid.

### Right decomposition for 5×5 pilot

```
Task        ← data only (html + expected + per-task tool override if any)
Model       ← sealed call site; one ModelResponse type; token accounting source
Tools       ← shared impls; whitelist-aware dispatch; single tool-call trace site
Harness     ← the independent variable; subclass of sealed base; no SDK access
Grader      ← pure function of (expected, produced)
Runner      ← iterates the matrix; owns the run directory and the tracer lifetime
Analysis    ← reads only from runs/<id>/; produces CSV, PNGs, MD
```

This is Inspect AI's model minus the composable-solver machinery, plus an explicit seal test, plus a single-file trace writer. It is the smallest decomposition that still makes the cross-harness comparison defensible.

## Sources

- PROJECT.md (authoritative for all hard constraints) — HIGH confidence
- Training-data knowledge of Inspect AI, OpenAI Evals, HELM, DSPy decomposition patterns — MEDIUM confidence (frameworks iterate; the high-level splits have been stable)
- General template-method / dependency-injection patterns — HIGH confidence (language-agnostic, not framework-specific)

**Not verified via Context7 or web search in this pass.** Architectural recommendations above are derived from the explicit constraints in PROJECT.md and well-known software-design patterns. If any specific framework API claim needs to be relied upon (e.g., "Inspect AI's Solver signature is X"), verify via Context7 before committing code that depends on it.

---
*Architecture research for: LLM agent harness engineering / comparative eval*
*Researched: 2026-04-23*
