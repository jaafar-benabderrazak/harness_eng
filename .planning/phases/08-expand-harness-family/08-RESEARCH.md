# Phase 8: Expand Harness Family + Refresh Article — Research

**Researched:** 2026-04-24
**Domain:** Agent harness engineering (Python, Anthropic-shape content blocks, Ollama backend, frozen-experiment methodology)
**Confidence:** HIGH for in-repo patterns; MEDIUM for Ollama streaming (validated against current Ollama blog + open issue); HIGH for jsonschema lib choice

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**1. `multi_agent` — message history scope: ISOLATED.** Each of planner / executor / critic has its own message history. Structured handoff messages explicitly copied between them via harness orchestration code, not via shared state. Why: faithful to CrewAI / AutoGen semantics. Cost implication: ~3× tokens of single-log harness — document in article's per-harness `weaknesses`. Implementation: harness owns orchestration loop; each agent call gets only the messages relevant to its role.

**2. `tree_of_thoughts` — candidate scoring: HEURISTIC.** Score each candidate selector by `(num_matched_nodes / mean_text_length_per_match)`, normalized. Deterministic, no extra model call. Why: keeps harness comparable on cost. Trade-off accepted: less faithful to ToT paper (which uses model self-eval). Document in `weaknesses` as "scoring is heuristic, not model-judged — paper-faithful variant would be a separate harness."

**3. `react_with_replan` — loop-detection trigger: TWO CONSECUTIVE NO_MATCH ON SAME SELECTOR.** When executor fires same CSS selector twice in a row and both return NO_MATCH, trigger a `replan` model call before continuing the ReAct loop. Why: cheapest signal that catches most common stall pattern in existing `react` traces. Detection lives in harness loop body, comparing the most-recent two tool_call args. Replan call shares same message context.

**4. `self_consistency` — HTML voting: PER-FIELD MAJORITY.** For HTML extraction: `{field_k: majority(samples[*][field_k]) for k in fields}` across N=5 samples. For code-gen: majority over full submitted code string after AST normalization (whitespace + comment stripping). Document this asymmetry in the article.

**5. `program_aided` — execution sandbox: subprocess.run with 5s timeout.** New `run_python` tool writes submitted code to tempfile, executes via `subprocess.run` with 5-second timeout. Captures stdout/stderr. Returns both to model as tool result. Why: matches existing `test_driven` security model (`run_tests` is also subprocess-based). Reuses safety pattern. Killable by timeout. **Tool addition: the new `run_python` tool added to `tools.py` is a Phase 8 file change — counts as a freeze-tag move, requires `harnesses-frozen` re-anchor.**

**6. `tool_use_with_validation` — schema source: tools.py existing schemas.** Validate every tool call against JSON schema already declared in `tools.py`. No per-harness override. Why: zero new infrastructure. Implementation: add a JSON-schema validator (`jsonschema` lib — add explicitly to deps) to harness's tool-call handler. On schema violation, return structured error tool_result and retry up to 3 times before failing the cell with `failure_mode = "schema_validation_exhausted"`.

**7. `streaming_react` — Ollama compatibility: SKIP-WITH-NOTE.** If Ollama streaming tool-use semantics don't match Anthropic's 1:1, harness is excluded from local-model matrix and documented as Anthropic-only. **Verification step (must run during planning):** test Ollama's streaming tool-use behavior against existing model wrapper. If it works, run in matrix. If not, mark `task_type = []` (excluded) and document in HARNESSES_FROZEN.md why. If Ollama-incompatible, harness file still exists with full implementation against Anthropic backend; just isn't registered in `HARNESSES_BY_TASK_TYPE` for local-model run.

**8. `cached_react` — cache scoping: CELL-SCOPED.** `(html_hash, selector)` → result cache lives only for duration of one (harness, task, seed) cell. Reset between cells. Why: seed independence — if cache leaked across seeds, sample N+1 would benefit from sample N's tool calls — breaks statistical model. Article framing: this harness shows what `react` *would* cost if tool calls were free.

### Cross-cutting Locked Decisions

- **Freeze tag move** moves forward EXACTLY ONCE: AFTER all eight harnesses merged AND `tools.py` (with `run_python`) finalized AND runner updated to register them, BEFORE any matrix run against them. Logged in `HARNESSES_FROZEN.md` with reason "Phase 8 harness expansion" and per-file SHAs.
- **Matrix runs gated on user confirmation.** ~3 hours of local CPU on glm-4.7-flash. Implementation phase ends at "harnesses + freeze move + tests green." User explicitly triggers matrix re-runs (via `scripts/run_full.py` and `scripts/run_code_benchmark.py`) — Phase 8's plans MUST NOT auto-run the matrix.
- **Article refresh happens AFTER matrix run.** Plans for article work sequenced to execute only after matrix re-runs produce updated `runs/<id>/` outputs.
- **Test coverage requirement:** every new harness ships with (1) AST seal test passing existing `test_harness_registry.py`, (2) per-harness control-flow pytest (model-mocked, asserts documented control flow), (3) freeze-gate test passing the runner pre-flight diff check.

### Claude's Discretion

- Choice of `jsonschema` vs `pydantic` for `tool_use_with_validation` (research below: `jsonschema`).
- Internal data structures (TypedDict vs dict) for multi-agent handoff messages.
- File-naming and module-organization for new harnesses, as long as they live under `src/harness_eng/harnesses/` and follow existing conventions.
- Per-harness pytest scaffold structure (recommendation below).

### Deferred Ideas (OUT OF SCOPE)

- **Cross-backend matrix on Anthropic.** This phase's matrix runs on existing default backend (Ollama + glm-4.7-flash). Anthropic-backend run is a separate operational phase, deferred.
- **`streaming_react` faithfulness on Ollama.** If verification step in decision #7 finds Ollama incompatible, that's documented and accepted. No work to make Ollama streaming match Anthropic.
- **Cost-savings claims for `cached_react`.** Cell-scoped cache is intentionally narrow. Article must not claim cross-run cost savings — only within-cell amortization.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (from REQUIREMENTS / ROADMAP) | Research Support |
|----|-------------------------------------------|------------------|
| HARN-08 | `tree_of_thoughts` harness (HTML, heuristic candidate scoring) | "Per-harness implementation notes → tree_of_thoughts" + heuristic scorer pattern |
| HARN-09 | `multi_agent` harness (both task types, isolated histories) | "Per-harness implementation notes → multi_agent" + isolated-history TypedDict pattern |
| HARN-10 | `react_with_replan` harness (HTML, two-NO_MATCH trigger) | "Per-harness implementation notes → react_with_replan" + last-two-args inspection pattern |
| HARN-11 | `self_consistency` harness (both, per-field majority / AST-normalized code) | "Per-harness implementation notes → self_consistency" + per-call temperature override required (§Decisive findings #5) |
| HARN-12 | `program_aided` harness (code-gen, subprocess sandbox) | "Per-harness implementation notes → program_aided" + reusable `_run_python_subprocess` helper extracted from `_tool_run_tests` shape |
| HARN-13 | `tool_use_with_validation` harness (both, jsonschema validates against tools.py) | "Per-harness implementation notes → tool_use_with_validation" + dependency add (§Standard Stack) |
| HARN-14 | `streaming_react` harness (HTML, Ollama-conditional) | "Per-harness implementation notes → streaming_react" + Decisive finding #1 (Ollama bug for glm-4.7-flash) |
| HARN-15 | `cached_react` harness (HTML, cell-scoped cache) | "Per-harness implementation notes → cached_react" + cache key derivation (§Decisive findings #8) |
| BENCH-06 | Benchmark expansion implied by HARN-08..15 — no new fixtures, harnesses run on existing 5 HTML + 5 code tasks | Existing `tasks.jsonl` loader already supports both task types; no fixture work needed |
| RUN-07 | Runner registers new harnesses in `HARNESSES_BY_TASK_TYPE` and the matrix reflects expanded set | "Architecture Patterns → registration" + `HARNESSES_BY_TASK_TYPE` is in `harnesses/__init__.py` (NOT in runner.py) — confirmed not freeze-gated |
| ANAL-06 | Analysis aggregates the expanded set without breaking existing aggregations + new color entries in `HARNESS_COLORS` | "Architecture Patterns → analysis adjustments" + `HARNESS_COLORS` palette in `analysis.py` needs 8 new entries |
| ART-05 | Article + Medium HTML refreshed against new matrix outputs; per-harness description blocks for all 16 harnesses | "Architecture Patterns → article refresh" + sequencing constraint (post-matrix only) |
</phase_requirements>

## Decisive findings (these change plan structure)

These ten items change what the planner must specify. Each is sourced from the codebase itself unless tagged otherwise.

### 1. `streaming_react` is almost certainly Ollama-incompatible on glm-4.7-flash

**Why this matters:** decides whether harness #7 has `task_type = ["html_extract"]` or `task_type = []` in the local-model matrix. This is the single biggest plan-shape decision.

**Evidence:**
- Ollama's *server* announced streaming tool calls with mid-stream detection in mid-2025 ([Ollama blog](https://ollama.com/blog/streaming-tool)).
- `ollama-python` `0.6.1` (current installed version in this env) supports `chat(..., stream=True, tools=[...])`.
- BUT: open Ollama issue [#13840 "Generation stops after tool call with Ollama (GLM-4.7-Flash)"](https://github.com/ollama/ollama/issues/13840) confirms glm-4.7-flash specifically halts generation immediately after any tool call. Reproduces on Linux ARM, NVIDIA GH200, ollama 0.14.3.
- The recommended workaround in the broader ecosystem is to use vLLM with `--tool-call-parser glm47`, which is out of scope for this project (Ollama-only by config decision).

**Implication for the plan:** the verification step in CONTEXT decision #7 will almost certainly fail on glm-4.7-flash. The planner should structure the `streaming_react` plan as:

1. Implement the harness against Anthropic content-block / streaming semantics (the harness file lives in `harnesses/streaming_react.py`).
2. Add a `_call_anthropic_streaming(...)` path in `model.py` (gated, opt-in) — but ONLY behind a flag so the existing non-streaming path is untouched.
3. Run the verification: `HARNESS_BACKEND=ollama` + glm-4.7-flash + `streaming_react` on a single fixture.
4. **Expected outcome:** failure. Document in `HARNESSES_FROZEN.md`. Set `task_type = []` for the harness in `HARNESSES_BY_TASK_TYPE`. Article calls this out explicitly as "Anthropic-only — Ollama streaming + tool-use parser does not work for glm-4.7-flash today."

**Confidence:** HIGH on the outcome; MEDIUM on whether the verification can be avoided entirely (running it produces evidence; the planner may want to keep the verification step explicit).

### 2. Adding `run_python` to `tools.py` MUST trigger a freeze-tag move

**Confirmed by reading `runner.py`:**
```python
GATED_PATHS = (
    "src/harness_eng/harnesses/",
    "src/harness_eng/tools.py",
    "src/harness_eng/model.py",
)
```
`runner.py` itself is NOT gated. So the registration line in `harnesses/__init__.py` (`HARNESSES_BY_TASK_TYPE`) and any orchestration changes do not require a re-anchor.

**Files that DO require a re-anchor:**
- `src/harness_eng/tools.py` (add `run_python` schema + impl)
- `src/harness_eng/harnesses/*.py` (new files + any edits to `base.py` if the planner extracts shared utilities — see finding #10)
- `src/harness_eng/model.py` IF `streaming_react` requires a streaming code path

**Files that do NOT require a re-anchor:**
- `src/harness_eng/harnesses/__init__.py` (registry — but it lives under `harnesses/` so it IS gated; the file gets edited as part of the freeze move anyway)
- `src/harness_eng/runner.py`
- `src/harness_eng/analysis.py` (color palette additions)
- `src/harness_eng/cost_estimator.py`
- `tests/*.py`
- `pyproject.toml`

**Important nuance:** `harnesses/__init__.py` IS under the gated path. So technically, adding the new harness imports and updating `HARNESSES_BY_TASK_TYPE` IS a gated edit. This means the freeze-move is the moment when ALL eight new harness files + `__init__.py` registration + `tools.py` `run_python` addition land together. The planner must sequence this as ONE atomic merge before re-anchoring.

### 3. AST seal test contract — what every new harness must satisfy

From `tests/test_harness_registry.py` and `tests/test_tool_allowlist.py`, every harness file must:

1. **Module path:** live at `src/harness_eng/harnesses/{harness_name}.py`.
2. **Class export:** define a class inheriting from `Harness` (in `harnesses/base.py`).
3. **`name` attribute:** equal to the registry key (e.g., `name = "tree_of_thoughts"`).
4. **`TOOL_WHITELIST` attribute:** a `frozenset[str]` of tool names — must include `submit_answer` (universal output channel — HARN-06).
5. **`_execute(self, task, ctx, tracer, usage) -> tuple[dict[str, str] | None, str]` method:** returns `(predicted, stop_reason)`. Stop reason is one of `"submitted"`, `"turn_cap"`, `"no_submit"`, `"error"`, or a harness-specific reason like `"schema_validation_exhausted"`.
6. **No direct `import anthropic`:** AST seal in `test_no_harness_imports_anthropic_directly()` — string-greps `"import anthropic"` and `"from anthropic"`.
7. **Registered in `harnesses/__init__.py` `HARNESSES` dict** (the discovery point — `test_all_harnesses_registered` enumerates this).
8. **Registered in `HARNESSES_BY_TASK_TYPE`** under at least one of `"html_extract"` / `"code_gen"` (or `[]` if Ollama-skipped per CONTEXT decision #7).
9. **`test_tool_allowlist.py::EXPECTED`** dict must be updated with the new harness's whitelist — the test will FAIL otherwise.

**Plan implication:** every harness plan must end with a step "update `tests/test_harness_registry.py` `test_all_harnesses_registered` set + `tests/test_tool_allowlist.py::EXPECTED` dict to include the new name." This is mechanical but forgotten will fail CI.

### 4. `HARNESSES_BY_TASK_TYPE` already supports the dual-registration shape

Looked up `harnesses/__init__.py`:
```python
HARNESSES_BY_TASK_TYPE: dict[str, list[str]] = {
    "html_extract": ["single_shot", "react", "plan_execute", "reflexion", "minimal"],
    "code_gen":     ["single_shot", "react", "chain_of_thought", "test_driven", "retry_on_fail"],
}
```

Harnesses appearing in BOTH lists (e.g., `single_shot`, `react`) get matrixed for both task types. This means `multi_agent`, `self_consistency`, and `tool_use_with_validation` need entries in BOTH lists. `tree_of_thoughts`, `react_with_replan`, `cached_react` go in `html_extract` only. `program_aided` in `code_gen` only. `streaming_react` likely in NEITHER (Ollama-incompatible) — leave list entries empty rather than omit the harness.

**The matrix sizes the article cites:**
- HTML matrix: 5 + 6 new (multi_agent, react_with_replan, self_consistency, tool_use_with_validation, tree_of_thoughts, cached_react) = **11 HTML harnesses** (10 if streaming_react is Ollama-skipped, otherwise 12).
- Code-gen matrix: 5 + 4 new (multi_agent, self_consistency, tool_use_with_validation, program_aided) = **9 code-gen harnesses**.

The ROADMAP success criterion says "~12 harnesses × 5 tasks × 3 seeds = ~180 cells" for HTML and "~9 × 5 × 3 = ~135 cells" for code-gen. **Confirmed alignment.**

### 5. `model.py` does NOT support per-call temperature override — must change for `self_consistency`

Reading `model.py:62-69` and `model.py:206-210`:
```python
kwargs: dict[str, Any] = {
    "model": CONFIG.model.name,
    "max_tokens": CONFIG.model.max_tokens,
    "temperature": CONFIG.model.temperature,  # frozen, no override
    ...
}
```

Both Anthropic and Ollama paths pull `temperature` directly from `CONFIG`. There is no `call(..., temperature=X)` parameter.

**`self_consistency` requires per-call temperature > 0** to get sample diversity. Two implementation options:

**Option A (recommended): add an optional `temperature` kwarg to `call()`.**
```python
def call(system, messages, tools=None, *, temperature: float | None = None) -> ModelCall:
    eff_temp = CONFIG.model.temperature if temperature is None else temperature
    ...
```
Pros: minimal surface change; backward-compatible (existing harnesses pass nothing); the override is auditable in trace via `model_call` event.
Cons: this is a `model.py` edit, which is a gated file — the freeze-tag move covers this anyway.

**Option B: a separate config key `self_consistency_temperature` and a separate model entry point.** Worse: more API surface, more freeze-gate scope.

**Recommendation: Option A.** The planner must specify:
1. Add `temperature: float | None = None` keyword arg to `call()` in `model.py`.
2. Threading: pass through `_call_anthropic` and `_call_ollama` as `temperature` override; preserve existing default-from-config behavior when not provided.
3. Trace event `model_call` records the effective temperature so traces show seed diversity.
4. `self_consistency` calls `model_call(..., temperature=0.7)` (or whatever the planner picks; document choice).

**Seed independence:** `model.py` does NOT pass a `seed` to either backend. The runner threads `seed` only into `cell_run_id` for trace organization, not into the model call. Sample diversity at `self_consistency` therefore comes from temperature + the model's internal stochasticity, NOT from explicit seeding. This is consistent with how seeds work in the existing matrix (which uses temperature 0 — different "seeds" produce identical outputs because the model is deterministic). For `self_consistency`, N=5 samples within ONE cell come from N=5 separate model calls at temperature > 0; the `_step_model` helper handles each separately so they have independent stochastic draws.

### 6. `_run_python_subprocess` should be extracted as a shared utility, mirroring `_tool_run_tests`

Looking at `tools.py:76-105` (`_tool_run_tests`):
```python
def _tool_run_tests(ctx: ToolContext, code: str, **_: Any) -> str:
    if not ctx.test_code:
        return "ERROR: no test_code in task context (are you on an HTML task?)."
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "solution.py"
        src.write_text(code, encoding="utf-8")
        tests = Path(td) / "test_solution.py"
        tests.write_text(...)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", "--no-header", str(tests)],
                cwd=td, capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: tests did not complete within 15s."
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 1500:
        out = out[:1500] + "\n...[truncated]"
    status = "PASSED" if proc.returncode == 0 else "FAILED"
    return f"[{status} rc={proc.returncode}]\n{out}"
```

`run_python` for `program_aided` is structurally identical, minus the test-code wrapping:

```python
def _tool_run_python(ctx: ToolContext, code: str, **_: Any) -> str:
    """Execute submitted code as a script. Returns truncated stdout/stderr."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "snippet.py"
        src.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(src)],
                cwd=td, capture_output=True, text=True, timeout=5,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: snippet did not complete within 5s."
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 1500:
        out = out[:1500] + "\n...[truncated]"
    return f"[rc={proc.returncode}]\n{out}"
```

**Should we extract a `_run_python_in_subprocess(code, *, args, timeout, max_bytes)` helper?** The existing `_tool_run_tests` is wedded to pytest-specific args — extracting now would muddy the freeze move. **Recommendation: do NOT extract.** Keep `_tool_run_python` as a sibling to `_tool_run_tests` in `tools.py`; both are 20 lines; extraction adds an indirection nobody asked for. Article-honesty point: this is faithful to "no premature abstraction" and keeps the freeze diff tight.

**Plan implication:** add `_tool_run_python` next to `_tool_run_tests` in `tools.py`, register in `TOOL_IMPLS` and `TOOL_SCHEMAS`. Schema:
```python
"run_python": {
    "name": "run_python",
    "description": "Execute Python code as a standalone script in a temp subprocess (5s timeout). Returns rc + truncated stdout/stderr. Use to verify intermediate values during reasoning.",
    "input_schema": {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
},
```

### 7. Cache for `cached_react` — `html_path` is loaded ONCE per cell via `ToolContext._html_cache`

From `tools.py:32-38`:
```python
@dataclass
class ToolContext:
    html_path: Path = Path("")
    ...
    _html_cache: str | None = None

    def html(self) -> str:
        if self._html_cache is None:
            self._html_cache = (FIXTURES_DIR / self.html_path).read_text(encoding="utf-8")
        return self._html_cache
```

So within a cell, `ctx.html()` returns the same string every time — `html_hash = hashlib.sha256(ctx.html().encode("utf-8")).hexdigest()` is computed once and stable for the cell. `(html_hash, selector)` is therefore safe as a cache key.

**Where to put the cache:** as an INSTANCE ATTRIBUTE on the harness, RESET in `_execute()`. The harness instances are reused across cells (`runner.py:140-144` instantiates each harness once per matrix run, then reuses for all cells), so a class-level or instance-level cache that isn't explicitly reset would leak across cells — VIOLATING CONTEXT decision #8.

**Pattern:**
```python
class CachedReactHarness(Harness):
    name = "cached_react"
    TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})

    def _execute(self, task, ctx, tracer, usage):
        cache: dict[tuple[str, str], str] = {}  # cell-scoped — local var, dies with method scope
        html_hash = hashlib.sha256(ctx.html().encode("utf-8")).hexdigest()
        ...
```

Use `cache` as a local — that guarantees cell-scope. **Don't put it on `self`** because instance lifetime spans all cells. Trace it: every `tool_call` event for css_select records both args AND a `cache_hit: bool` field so the article can quantify amortization.

### 8. JSON-schema validation library: use `jsonschema 4.x` (add explicitly)

**Verified in environment:**
- `jsonschema 4.25.1` is installed globally as a transitive of unrelated packages (altair, sagemaker). It is NOT a transitive of any current harness_eng dep.
- Cannot rely on it being present in a clean install.

**Decision: add `jsonschema>=4.20.0` to `pyproject.toml` `[project] dependencies`** (NOT optional). This is required by `tool_use_with_validation` at runtime.

**Why `jsonschema` over alternatives:**
| Option | Verdict |
|--------|---------|
| `jsonschema` (Python-pure) | Use this. Ubiquitous. Draft 7 + 2020-12 support. Stable API. Sufficient performance for ~5 validations per ReAct turn. |
| `fastjsonschema` | Faster but Draft 7 only, less common, no value-add at our scale. |
| `jsonschema-rs` | Rust binding; faster but adds a binary dep — friction for Windows + bash onboarding (a deliberate constraint per ROADMAP Phase 7). |
| `pydantic` | Already a dep. But the schemas live as plain dicts in `tools.py` — wrapping them as Pydantic models would mean rewriting every schema; doubles the freeze-diff scope. Reject. |

**Validation API:**
```python
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

validator = Draft202012Validator(TOOL_SCHEMAS["css_select"]["input_schema"])
try:
    validator.validate(args)  # raises ValidationError on violation
except ValidationError as e:
    error_msg = f"Schema violation in {tool_name}: {e.message} (path={list(e.absolute_path)})"
```

Sources verified: [jsonschema 4.26.0 docs](https://python-jsonschema.readthedocs.io/en/stable/validate/), [jsonschema PyPI](https://pypi.org/project/jsonschema/).

### 9. `multi_agent` isolated histories — recommended Python data structure

CONTEXT decision #1 says isolated histories with structured handoffs. Looking at how existing harnesses pass messages to `model.call()`:

- `model.call(system, messages, tools)` where `messages: list[dict[str, Any]]` and each element is `{"role": "user|assistant", "content": str | list[dict]}`.
- Each agent (planner / executor / critic) maintains its OWN `messages` list. The harness orchestration code calls `model.call()` three times per turn (once per agent), each with that agent's separate list.

**Recommended structure (keep simple, dict-based):**
```python
@dataclass
class AgentRole:
    name: str           # "planner" | "executor" | "critic"
    system: str         # the role's system prompt
    messages: list[dict[str, Any]]  # this role's private message history
    tool_whitelist: frozenset[str]  # which tools THIS role may call (subset of harness whitelist)

# Handoff message — typed for clarity, not enforced at runtime:
class Handoff(TypedDict):
    from_role: str
    to_role: str
    summary: str        # the structured handoff payload as text
    artifacts: dict[str, Any]  # selectors, candidate fields, etc.
```

**Why TypedDict over plain dict for Handoff:** `TypedDict` is type-checker-friendly without runtime overhead; the handoff schema is the contract between roles and ought to be visible to readers. But all fields are still strings/dicts — no Pydantic, no validation. The harness orchestration code converts a `Handoff` to a string and prepends to the next agent's `messages`.

**Tool whitelist for `multi_agent`:** the planner role uses no tools (just thinks); executor uses ReAct-shaped tools; critic uses no tools (analyzes the trace). The harness's class-level `TOOL_WHITELIST` must be the UNION:
```python
TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})
```
Per-role tool subsets are passed to `_step_model` per call — `_step_model` already enforces `passed ⊆ TOOL_WHITELIST` (base.py:160-167), so the per-role subset is enforceable but the test in `test_tool_allowlist.py::EXPECTED` only sees the union.

**Confidence:** HIGH — pattern matches existing `plan_execute` (which already separates planner system from executor system in the same harness).

### 10. Per-harness control-flow tests — pattern doesn't yet exist; define it

Audit of `tests/`:
- `test_harness_registry.py` — registry-level (tests THAT harnesses exist + don't import anthropic).
- `test_tool_allowlist.py` — whitelist-level (tests TOOL_WHITELIST attrs).
- `test_freeze_gate.py` — gate-level (tests runner pre-flight).

**No per-harness control-flow tests exist.** CONTEXT requirement #2 ("per-harness control-flow pytest, model-mocked, asserts the documented control flow") is NEW for Phase 8.

**Recommended pattern, drawn from `test_tool_allowlist.py::test_step_model_accepts_subset_of_whitelist` (which already mocks `model_call`):**

```python
# tests/test_multi_agent_harness.py
from unittest.mock import MagicMock
from harness_eng.harnesses import HARNESSES
from harness_eng.harnesses import base as base_module
from harness_eng.model import ModelCall
from harness_eng.tasks.loader import Task

def _fake_call_factory(scripted: list[ModelCall]):
    """Returns a fake model_call that pops scripted responses in order."""
    it = iter(scripted)
    def _fake(system, messages, tools, **kw):
        return next(it)
    return _fake

def test_multi_agent_runs_three_distinct_system_prompts(monkeypatch):
    """multi_agent must call model with planner / executor / critic system prompts in order."""
    seen_systems: list[str] = []
    def _fake(system, messages, tools=None, **kw):
        seen_systems.append(system)
        # return a submit_answer to short-circuit
        return ModelCall(
            input_tokens=1, output_tokens=1, latency_s=0.0,
            stop_reason="end_turn",
            content=[{"type": "tool_use", "id": "tu_1", "name": "submit_answer",
                      "input": {"fields": {"title": "X"}}}],
            usage_raw={},
        )
    monkeypatch.setattr(base_module, "model_call", _fake)

    harness = HARNESSES["multi_agent"]()
    task = Task(
        id="test_task", type="html_extract", description="test",
        fields=["title"], expected={"title": "X"},
        html_path="product_01.html", test_code="", signature="",
    )
    harness.run(task, run_id="test")
    # Assert: planner / executor / critic all show up
    assert any("PLANNER" in s for s in seen_systems)
    assert any("EXECUTOR" in s for s in seen_systems)
    assert any("CRITIC" in s for s in seen_systems)
    # Assert exactly THREE distinct system prompts (not 1, not 5)
    assert len({s for s in seen_systems}) >= 3
```

**Each new harness gets one such file.** The control-flow invariants to assert:

| Harness | Invariant |
|---------|-----------|
| `tree_of_thoughts` | 3 candidate selectors generated, scoring computed deterministically, highest-scoring used downstream |
| `multi_agent` | ≥3 distinct system prompts; planner runs before executor before critic |
| `react_with_replan` | After 2 consecutive NO_MATCH on same selector, an event `replan_triggered` appears in trace |
| `self_consistency` | Exactly N=5 model calls before the vote; each at temperature > 0 (asserted via the `temperature` kwarg) |
| `program_aided` | At least one `run_python` tool call before submit (else what's the point) |
| `tool_use_with_validation` | Schema-violating arg → `ValidationError` is caught; structured error tool_result returned to model; up to 3 retries before failure |
| `streaming_react` | Stream is consumed; submit_answer detection terminates stream early (mock the stream iterator to verify break-out timing). If Ollama-incompatible: only test against mocked Anthropic stream |
| `cached_react` | Second call to same selector within a cell is a cache hit (no model_call → tool_call → tool_result roundtrip; just a cache lookup) |

**Confidence:** HIGH — pattern compiles against existing test infrastructure.

---

## Standard Stack

### Core (already in pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` | `>=0.40.0` | Anthropic SDK (gated import in `model.py` only) | Existing |
| `ollama` | `>=0.4.0` (env has 0.6.1) | Local backend SDK | Existing; 0.6.1 supports `chat(stream=True, tools=...)` per [ollama-python README](https://github.com/ollama/ollama-python) |
| `beautifulsoup4` | `>=4.12.0` | HTML parsing in tools | Existing |
| `pydantic` | `>=2.6.0` | Already in deps; **NOT used for tool validation** | Existing — kept; the validation harness uses `jsonschema` instead |
| `pytest` | `>=8.0.0` (dev) | Test runner — also invoked via subprocess by `_tool_run_tests` and (new) `_tool_run_python` | Existing |

### New (must add to pyproject.toml in Phase 8)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `jsonschema` | `>=4.20.0` | `tool_use_with_validation` validates each tool call against the existing `tools.py` schemas | Sufficient API; pure-Python; widely deployed; Draft 2020-12 support. See finding #8. |

### Alternatives considered + rejected
| Considered | Rejected because |
|------------|------------------|
| `fastjsonschema` for validation | Draft 7 only; adds dep with no observable speed benefit at ≤5 validations / turn |
| `jsonschema-rs` | Adds Rust binary; friction with Windows + bash onboarding constraint |
| `pydantic` for tool-call validation | Schemas would need rewriting as Pydantic models; widens freeze-diff |
| `httpx`-direct streaming for Ollama | Ollama-python 0.6.1 already exposes streaming; bypassing it costs more than it saves |

**Installation (Phase 8 must add):**
```toml
# in pyproject.toml [project] dependencies
"jsonschema>=4.20.0",
```

---

## Architecture Patterns

### Recommended file layout (additive — no restructure)

```
src/harness_eng/
├── harnesses/
│   ├── base.py                   # UNCHANGED (extracting shared util muddles freeze)
│   ├── single_shot.py            # UNCHANGED
│   ├── react.py                  # UNCHANGED
│   ├── plan_execute.py           # UNCHANGED
│   ├── reflexion.py              # UNCHANGED
│   ├── minimal.py                # UNCHANGED
│   ├── chain_of_thought.py       # UNCHANGED
│   ├── test_driven.py            # UNCHANGED
│   ├── retry_on_fail.py          # UNCHANGED
│   ├── tree_of_thoughts.py       # NEW
│   ├── multi_agent.py            # NEW
│   ├── react_with_replan.py      # NEW
│   ├── self_consistency.py       # NEW
│   ├── program_aided.py          # NEW (code-gen)
│   ├── tool_use_with_validation.py  # NEW
│   ├── streaming_react.py        # NEW (likely Ollama-disabled)
│   ├── cached_react.py           # NEW
│   └── __init__.py               # EDITED — register all 8 in HARNESSES + HARNESSES_BY_TASK_TYPE
├── tools.py                      # EDITED — add _tool_run_python + schema + register
├── model.py                      # EDITED — add temperature kwarg; (conditionally) streaming path
├── analysis.py                   # EDITED — add 8 entries to HARNESS_COLORS
├── runner.py                     # UNCHANGED (but registration in __init__.py is sufficient)
├── ...
tests/
├── test_harness_registry.py      # EDITED — add 8 names to expected set
├── test_tool_allowlist.py        # EDITED — add 8 entries to EXPECTED dict
├── test_tools.py                 # EDITED — add _tool_run_python tests (subprocess timeout, rc, stdout)
├── test_tree_of_thoughts.py      # NEW per-harness control-flow test
├── test_multi_agent.py           # NEW
├── test_react_with_replan.py     # NEW
├── test_self_consistency.py      # NEW
├── test_program_aided.py         # NEW
├── test_tool_use_with_validation.py  # NEW
├── test_streaming_react.py       # NEW
├── test_cached_react.py          # NEW
HARNESSES_FROZEN.md               # EDITED — append tag-move row + per-file SHAs
pyproject.toml                    # EDITED — add jsonschema dep
writeup/article.md                # EDITED post-matrix — 8 new harness blocks + framework mapping rows + table refresh
writeup/article-medium.html       # EDITED post-matrix — regenerated by build_medium_html.py
writeup/diagrams/                 # EDITED post-matrix — 8 new mermaid PNGs (or .md fallback)
```

### Pattern: per-harness file template (drawn from `react.py` + `plan_execute.py`)

```python
"""Harness N: <one-line summary>.

<2-4 line description of what makes this harness distinct from the others.>
"""
from __future__ import annotations

from typing import Any

from ..config import CONFIG
from ..tasks.loader import Task
from ..tools import ToolContext, build_tool_list
from ..trace import Tracer
from .base import BASE_ROLE, Harness, _Usage

NEW_TOOLS = ["css_select", "submit_answer"]  # whatever subset


class XxxHarness(Harness):
    name = "xxx"
    TOOL_WHITELIST = frozenset({"css_select", "submit_answer"})

    def _execute(self, task, ctx, tracer, usage):
        system = BASE_ROLE + "\n\n<role-specific augmentation>"
        tools = build_tool_list(NEW_TOOLS)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._task_prompt(task)}
        ]
        for _ in range(CONFIG.react_max_turns):
            mc = self._step_model(system, messages, tools, tracer, usage)
            messages.append({"role": "assistant", "content": mc.content})
            tool_uses = self._tool_uses(mc.content)
            if not tool_uses:
                return None, "no_submit"
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                name = tu["name"]
                args = tu.get("input", {}) or {}
                if name == "submit_answer":
                    if "code" in args:
                        return {"code": args["code"]}, "submitted"
                    fields = args.get("fields", {})
                    return {k: str(v) for k, v in fields.items()}, "submitted"
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": out}
                )
            messages.append({"role": "user", "content": tool_results})
        return None, "turn_cap"
```

Every existing harness follows this skeleton. Deviations:
- `single_shot`, `chain_of_thought`: no loop (one model call).
- `reflexion`, `retry_on_fail`: nested loops (outer = attempts; inner = ReAct turns).
- `plan_execute`: two-phase (plan call without tools, then loop).

### Pattern: registration in `harnesses/__init__.py`

```python
# After adding 8 new imports:
HARNESSES: dict[str, type[Harness]] = {
    # HTML-extraction baselines
    "single_shot": SingleShotHarness,
    "react": ReActHarness,
    "plan_execute": PlanExecuteHarness,
    "reflexion": ReflexionHarness,
    "minimal": MinimalHarness,
    # Code-gen strategies
    "chain_of_thought": ChainOfThoughtHarness,
    "test_driven": TestDrivenHarness,
    "retry_on_fail": RetryOnFailHarness,
    # Phase 8 — agent-pattern family
    "tree_of_thoughts": TreeOfThoughtsHarness,
    "multi_agent": MultiAgentHarness,
    "react_with_replan": ReActWithReplanHarness,
    "self_consistency": SelfConsistencyHarness,
    "program_aided": ProgramAidedHarness,
    "tool_use_with_validation": ToolUseWithValidationHarness,
    "streaming_react": StreamingReActHarness,
    "cached_react": CachedReActHarness,
}

HARNESSES_BY_TASK_TYPE: dict[str, list[str]] = {
    "html_extract": [
        "single_shot", "react", "plan_execute", "reflexion", "minimal",
        # Phase 8 additions for HTML
        "tree_of_thoughts", "multi_agent", "react_with_replan",
        "self_consistency", "tool_use_with_validation", "cached_react",
        # streaming_react omitted IF Ollama-incompatible (verification step decides)
    ],
    "code_gen": [
        "single_shot", "react", "chain_of_thought", "test_driven", "retry_on_fail",
        # Phase 8 additions for code-gen
        "multi_agent", "self_consistency", "program_aided", "tool_use_with_validation",
    ],
}
```

### Pattern: analysis color additions in `analysis.py`

```python
HARNESS_COLORS: dict[str, str] = {
    # existing 8...
    # Phase 8 additions — pick distinguishable hues
    "tree_of_thoughts":       "#7c3aed",  # violet
    "multi_agent":            "#0d9488",  # teal-dark
    "react_with_replan":      "#b91c1c",  # red-dark
    "self_consistency":       "#1d4ed8",  # blue-dark
    "program_aided":          "#a16207",  # amber-dark
    "tool_use_with_validation": "#16a34a",  # green-mid
    "streaming_react":        "#e11d48",  # rose
    "cached_react":           "#7e22ce",  # purple-dark
}
```

### Pattern: article refresh sequencing (post-matrix only)

```
Plan order:
  1. Implement harness files (8 plans, parallel)
  2. Add run_python to tools.py + register
  3. Add jsonschema dep
  4. Add temperature kwarg to model.py
  5. Update __init__.py registry
  6. Update tests (registry + allowlist + per-harness)
  7. Run pytest — green
  8. Move freeze tag — log in HARNESSES_FROZEN.md
  --- HANDOFF TO USER ---
  9. User runs: scripts/run_full.py --seeds 3 --yes  (~2 hr)
  10. User runs: scripts/run_code_benchmark.py --seeds 3 --yes  (~1 hr)
  --- RESUME WITH ARTIFACTS ---
  11. Article refresh (writeup/article.md): 8 new harness blocks, framework mapping, table refresh, dollar extrapolation
  12. Regenerate Medium HTML: python scripts/build_medium_html.py
  13. Verify diagrams render
```

Steps 1–8 are the code-side phase 8. Steps 11–13 are the article phase. Step 9 + 10 are user-action gates per CONTEXT cross-cutting decision.

### Anti-patterns to avoid

- **Editing `base.py` to add per-harness utilities.** It's gated AND every existing test depends on it. If a util emerges that 3+ harnesses need, the planner can extract — but only with explicit reason in HARNESSES_FROZEN.md.
- **Importing `from anthropic import ...` or `from ollama import ...` in any harness file.** AST seal will fail. All model calls go through `model.call()`.
- **Putting per-cell state on `self`.** Instance is shared across cells. Use locals or pass-through args. Direct violation of CONTEXT decision #8 cell-scoped cache.
- **Silently dropping the freeze gate when `tools.py` changes.** The gate must be re-anchored once, AFTER all 8 + tools.py + model.py changes are in.
- **Auto-running the matrix from a plan task.** Per CONTEXT cross-cutting decision: matrix runs are user-gated.

---

## Per-harness implementation notes

### `tree_of_thoughts` (HTML)

**Control flow:**
1. Single model call: "Propose 3 distinct CSS selectors for field `<f>`. Return as `submit_answer({fields: {selector_1, selector_2, selector_3}})` … wait that abuses the tool." → Use a TOOLLESS first call, parse text for selectors.
2. For each candidate selector: `dispatch("css_select", ctx, selector=s)` — record `(num_matched_nodes, mean_text_length)`.
3. Score: `score = num_matched_nodes / mean_text_length_per_match` (normalized across candidates). Highest wins.
4. Run a SECOND model call with the top-scoring candidate's result text + ask for `submit_answer`.

**Tool whitelist:** `{"css_select", "submit_answer"}`. (No need for `read_html` — the candidates ARE the proposals.)

**Heuristic scorer (deterministic):**
```python
def _score_candidate(matches: list[str]) -> float:
    """High score = many matches, short text per match (specific selector).
    Returns 0 for empty match list."""
    if not matches:
        return 0.0
    n = len(matches)
    avg_len = sum(len(m) for m in matches) / n
    return n / max(avg_len, 1.0)
```

Pitfalls: `css_select` returns `"NO_MATCH"` (a literal string), not an empty list. Check for that sentinel explicitly. The dispatch returns concatenated text; you'd parse with `output.split("\n---\n")` to get the per-match list.

**Article framing:** "ToT-paper-style search but with a heuristic scorer instead of an LLM judge — saves the second-round model call. Faithful variant would replace `_score_candidate` with another `_step_model` call."

### `multi_agent` (both)

**Three roles, three system prompts, three message lists:**

```python
PLANNER_SYSTEM = BASE_ROLE + "\n\nYou are the PLANNER. Produce a numbered list of investigation steps. You will not execute them. Hand off to the executor when done."
EXECUTOR_SYSTEM = BASE_ROLE + "\n\nYou are the EXECUTOR. Execute the planner's steps using tools. Submit via submit_answer."
CRITIC_SYSTEM = BASE_ROLE + "\n\nYou are the CRITIC. Read the executor's result and decide if it satisfies the task. If not, write specific corrections."
```

**Flow:**
1. Planner call (no tools): emit a checklist as text.
2. Build a `Handoff` object summarizing the plan; convert to text; prepend to executor's `messages`.
3. Executor loop (ReAct-shape) until submit_answer or turn cap.
4. Critic call (no tools): given the executor's output, return either "OK" or a critique.
5. If critic says "OK": return executor's submission. If critique: ONE retry of the executor with the critique appended. (No second critic round — keeps cost bounded.)

**Handoff structure:**
```python
class Handoff(TypedDict):
    from_role: str
    to_role: str
    summary: str
    artifacts: dict[str, Any]
```
Render as:
```
## Handoff from {from_role} to {to_role}
{summary}

Artifacts:
- selector_candidates: ...
- partial_extraction: ...
```
Then prepend as a `user` message in the receiving role's `messages` list.

**Tool whitelist:** UNION of executor's needs: `{"read_html", "css_select", "extract_text", "submit_answer"}` for HTML, `{"check_syntax", "run_tests", "submit_answer"}` for code-gen — meaning per-task-type the harness emits a different `tools` payload to `_step_model`. `TOOL_WHITELIST` at class level must be the UNION across both task types: `{"read_html", "css_select", "extract_text", "check_syntax", "run_tests", "submit_answer"}`. Per-task selection is enforced internally; `_step_model`'s subset check still passes because per-call tools ⊆ class TOOL_WHITELIST.

**Cost note for article:** ~3× the tokens of `react`. Document.

### `react_with_replan` (HTML)

**Detection invariant:** the harness tracks the last css_select args. After a tool result, IF (current selector == previous selector) AND (current result == "NO_MATCH") AND (previous result == "NO_MATCH"): trigger replan.

```python
last_selector: str | None = None
last_was_nomatch: bool = False

# inside the tool-result loop:
if name == "css_select":
    sel = args.get("selector", "")
    if sel == last_selector and last_was_nomatch and out == "NO_MATCH":
        # replan
        replan_msg = {"role": "user", "content": "You've called this selector twice with NO_MATCH. Stop and write a brief revised plan, then continue."}
        messages.append(replan_msg)
        tracer.log("replan_triggered", selector=sel)
    last_selector = sel
    last_was_nomatch = (out == "NO_MATCH")
else:
    last_selector = None
    last_was_nomatch = False
```

**Tool whitelist:** same as ReAct: `{"read_html", "css_select", "extract_text", "submit_answer"}`.

**Trace event added:** `replan_triggered` so the article can quantify "this fired N times across the matrix and saved/wasted X turns on average."

### `self_consistency` (both)

**Requires per-call temperature override (finding #5).**

**Flow for HTML task (per-field majority):**
```python
N_SAMPLES = 5
SAMPLE_TEMPERATURE = 0.7

samples: list[dict[str, str]] = []
for i in range(N_SAMPLES):
    # Run a single_shot-style call at temperature > 0
    mc = self._step_model(system, messages, tools, tracer, usage, temperature=SAMPLE_TEMPERATURE)
    pred = self._extract_submit(mc)  # dict[str, str] | None
    if pred is not None:
        samples.append(pred)
    tracer.log("self_consistency_sample", i=i, predicted=pred)

# Per-field majority
fields = task.fields
final: dict[str, str] = {}
for f in fields:
    values = [s.get(f, "") for s in samples if s]
    if values:
        majority = Counter(values).most_common(1)[0][0]
        final[f] = majority
return final, "submitted"
```

**For code-gen:** majority over AST-normalized code string.
```python
import ast
def _normalize_code(code: str) -> str:
    """Strip comments + collapse whitespace via AST round-trip."""
    try:
        tree = ast.parse(code)
        return ast.unparse(tree)  # Python 3.9+ — drops comments, normalizes spacing
    except SyntaxError:
        return code  # fall back to raw
```
Then majority-vote on `_normalize_code(s["code"])`. Return the WINNING raw code (not the normalized one) — preserves the model's actual submission.

**Tool whitelist:** `{"submit_answer"}` only — `self_consistency` is N independent single-shot calls. Article framing: "5x cost of single_shot for marginal accuracy gain. The original Wang et al. 2022 paper saw bigger gains because models were less reliable then."

**`_step_model` change:** must accept `temperature` kwarg, threading it to `model.call(..., temperature=temperature)`. This is a minor extension but it lives in `base.py` (gated). Check: `_step_model` already has signature `(system, messages, tools, tracer, usage)` — adding `temperature: float | None = None` is backward-compatible.

**Trace event added:** `self_consistency_sample` per sample, `self_consistency_vote` for the final majority result with vote tallies.

### `program_aided` (code-gen only)

**Tool whitelist:** `{"run_python", "submit_answer"}`.

**Flow:**
1. System prompt: "Write Python that explores the problem. Use `run_python` to verify intermediate values. When confident, submit the final implementation via submit_answer."
2. ReAct-shape loop: model emits `run_python(code=...)` tool calls; harness dispatches to the new `_tool_run_python`; result text fed back as tool_result.
3. On `submit_answer(code=...)`: return `{"code": ...}, "submitted"`.

**Distinct from `test_driven`:** `test_driven` uses `run_tests` — the official pytest grading suite. `program_aided` uses `run_python` to execute scratch code (e.g., "let me check what `sorted([3,1,2])` returns"). The model uses execution AS REASONING, not as grading.

**Trace event added:** `program_aided_run_python` events with the (truncated) code and rc — useful for "did the model actually use this or just call submit?" article analysis.

### `tool_use_with_validation` (both)

**Flow:** wraps a ReAct loop. Before dispatching any tool call, validate `args` against `TOOL_SCHEMAS[name]["input_schema"]`. On `ValidationError`, instead of dispatching, return a structured error tool_result and increment a per-call retry counter (max 3). After 3 violations on the same tool call site, fail the cell.

```python
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

VALIDATORS = {n: Draft202012Validator(s["input_schema"]) for n, s in TOOL_SCHEMAS.items()}

def _validate_or_error(name, args) -> str | None:
    """Returns None if valid, error string if invalid."""
    v = VALIDATORS.get(name)
    if v is None:
        return None  # unknown tool — let dispatch handle
    try:
        v.validate(args)
    except ValidationError as e:
        return f"SCHEMA_VIOLATION in {name}: {e.message} at path={list(e.absolute_path)}. Schema requires: {e.schema}"
    return None
```

**Failure mode:** if 3 consecutive violations: return `(None, "schema_validation_exhausted")`. The runner records this as a stop_reason; analysis chart will show this as a new bar in the stop-reason stacked chart — already visualized by `stop_reason_chart` in `analysis.py:251` (no chart change needed; just a new label).

**Tool whitelist:** UNION across HTML + code-gen needs: `{"read_html", "css_select", "extract_text", "check_syntax", "run_tests", "submit_answer"}`. Per-task-type, the harness emits the right subset.

**Trace events added:** `schema_validation_pass`, `schema_validation_fail` (with error details).

### `streaming_react` (HTML — likely Ollama-disabled)

**Verification step (run during planning):** with HARNESS_BACKEND=ollama, glm-4.7-flash, `streaming_react` against `product_01.html` fixture (smallest, fastest). If model doesn't halt-after-tool: enable in matrix. If it halts: document, set `task_type=[]`, leave file in tree as Anthropic-only.

**Anthropic streaming implementation (the file always lives — registration is conditional):**
```python
# in model.py — guarded by an opt-in kwarg, not the default path
def call_streaming(system, messages, tools=None) -> Iterator[ModelCall]:
    """Stream content blocks. Yields partial ModelCall snapshots; final one is complete."""
    # Anthropic SDK: client.messages.stream(...) context manager
    # Detect early termination on submit_answer tool_use start
    ...
```

**Mid-stream termination logic:**
```python
with anthropic_client.messages.stream(...) as stream:
    for event in stream:
        if event.type == "content_block_start" and event.content_block.type == "tool_use":
            if event.content_block.name == "submit_answer":
                # break early — don't read the rest of the stream
                stream.close()
                break
```

**For Ollama (if it works):** ollama-python `chat(stream=True, tools=[...])` yields chunks; per [Ollama blog](https://ollama.com/blog/streaming-tool), `chunk.message.tool_calls` may populate mid-stream. Detect `submit_answer` in chunk's tool_calls and break.

**Tool whitelist:** ReAct-shape `{"read_html", "css_select", "extract_text", "submit_answer"}`.

**Verification outcome documented in HARNESSES_FROZEN.md** with concrete error message + Ollama issue link [#13840](https://github.com/ollama/ollama/issues/13840).

### `cached_react` (HTML)

**Cache scope: cell-scoped (CONTEXT decision #8). Implementation: local variable in `_execute`.**

```python
import hashlib

class CachedReActHarness(Harness):
    name = "cached_react"
    TOOL_WHITELIST = frozenset({"read_html", "css_select", "extract_text", "submit_answer"})

    def _execute(self, task, ctx, tracer, usage):
        cache: dict[tuple[str, str], str] = {}  # (html_hash, selector) -> result
        html_hash = hashlib.sha256(ctx.html().encode("utf-8")).hexdigest()[:16]
        # ... ReAct loop ...
        for tu in tool_uses:
            name = tu["name"]
            args = tu.get("input", {}) or {}
            if name == "css_select":
                sel = args.get("selector", "")
                key = (html_hash, sel)
                if key in cache:
                    out = cache[key]
                    tracer.log("tool_call", name=name, args=args, cache_hit=True)
                    tracer.log("tool_result", name=name, output_len=len(out), cache_hit=True)
                    # do NOT increment usage.tool_calls — that's the whole point
                else:
                    out = self._dispatch_tool(name, args, ctx, tracer, usage)
                    cache[key] = out
            else:
                out = self._dispatch_tool(name, args, ctx, tracer, usage)
            tool_results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": out})
```

**What to count in `usage.tool_calls`:** decide per CONTEXT framing. The harness "shows what react would cost if tool calls were free." So `tool_calls` SHOULD count cache hits (the model still emitted the call) BUT wall-clock should be lower. **Recommendation:** count cache hits as tool_calls (they were emitted) but clearly trace `cache_hit=True` so analysis can split them. The article's framing is consistent: the harness shows token+turn cost, but wall-clock savings.

**Trace events:** `tool_call cache_hit=True/False`. Analysis summary can compute "% of css_select calls that hit cache" per harness.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON-schema validation | Custom dict-walking validator | `jsonschema.Draft202012Validator` | Edge cases (nested refs, format validators, error path reporting) |
| Subprocess sandbox | Threading-based timeout | `subprocess.run(..., timeout=N)` | Existing `_tool_run_tests` already does it; consistent + tested |
| AST-normalized code comparison | Regex-based whitespace stripping | `ast.parse` + `ast.unparse` | Comments + structural equivalence handled correctly |
| HTML hash | Per-line hashing or fragile representation | `hashlib.sha256(ctx.html().encode("utf-8")).hexdigest()` | `ctx.html()` already memoizes; SHA-256 is overkill for collisions but the code is one line |
| Stream parsing for Ollama | Manual `httpx` chunk-reading | `ollama.chat(stream=True, tools=[...])` SDK | The 0.6.x line surfaces `chunk.message.tool_calls` per [Ollama blog](https://ollama.com/blog/streaming-tool) |
| Stream parsing for Anthropic | Manual SSE event parsing | `client.messages.stream(...)` context manager | Official SDK handles content_block_start / delta / stop events |
| Multi-agent message routing framework | Build agent runtime | Plain Python dicts + the existing `_step_model` per role | Project values structural simplicity + small freeze diff |
| Per-call temperature config | Read env var per call | Add `temperature: float | None = None` kwarg to `model.call()` | One line in `model.py`; explicit; auditable in trace |

**Key insight:** the project's value is the experimental control. Every "convenience library" added widens the freeze surface. Prefer 20 lines of locally-readable Python over a 500-line dep that does the same plus a dozen things you don't want.

---

## Common Pitfalls

### Pitfall 1: forgetting to update `tests/test_tool_allowlist.py::EXPECTED`

**What goes wrong:** new harness added, registry test passes, but `EXPECTED` dict still has only 8 entries — `test_every_harness_declares_whitelist` fails because it iterates `HARNESSES.items()` and looks up each in `EXPECTED`.

**Why it happens:** the test is in a different file from the harness file; AI-assisted edits often miss the test update.

**How to avoid:** every harness plan ends with a step "update EXPECTED dict in test_tool_allowlist.py."

**Warning signs:** `KeyError: 'tree_of_thoughts'` in the test output.

### Pitfall 2: cache leaks across cells in `cached_react`

**What goes wrong:** putting `self._cache = {}` in `__init__` means `runner.py`'s reused harness instance carries the cache from cell 1 to cell 2 — seed N+1 benefits from selector results computed for seed N. Statistical model breaks.

**Why it happens:** `runner.py:140-144` creates each harness exactly once: `harness_instances[h] = HARNESSES[h]()` and reuses for all (task, seed) cells.

**How to avoid:** cache lives as a LOCAL VARIABLE in `_execute()`. Method scope dies with the cell. Verified by per-harness control-flow test that runs the harness twice on the same task and asserts the second run does cold lookups.

**Warning signs:** suspiciously low tool_call counts after the first cell of a given harness.

### Pitfall 3: streaming_react silently runs against Ollama and hangs

**What goes wrong:** glm-4.7-flash halts after the first tool call. The harness blocks indefinitely waiting for more chunks. Cell never completes. Matrix run grinds.

**Why it happens:** `runner.py` doesn't enforce per-cell timeouts. The harness loop will spin. See [Ollama issue #13840](https://github.com/ollama/ollama/issues/13840).

**How to avoid:** the verification step in CONTEXT decision #7 must run BEFORE the freeze move. If it fails: register `streaming_react` with empty `task_type` list. Confirm with a smoke test: run `python scripts/run_full.py --harnesses streaming_react --seeds 1` and verify it terminates. Document in `HARNESSES_FROZEN.md` with the issue link.

**Warning signs:** matrix cell exceeds 5 minutes of wall-clock with no progress; stuck on `streaming_react`.

### Pitfall 4: `self_consistency` produces identical samples (temperature override forgotten)

**What goes wrong:** harness calls `model.call(...)` without temperature kwarg → uses `CONFIG.model.temperature = 0.0` → all 5 samples are bit-identical → majority vote is trivial → article framing falls apart.

**Why it happens:** the change to `model.call()` and the change to `_step_model()` to accept temperature are in different files; the harness might pass temperature to `_step_model` but `_step_model` might drop it.

**How to avoid:**
1. Add `temperature` param to BOTH `_step_model` (in `base.py`) AND `model.call()`.
2. Per-harness control-flow test asserts that when `self_consistency` runs, the underlying `model_call` is invoked with `temperature=0.7` (mock + capture kwargs).
3. Trace event includes effective temperature so post-run inspection shows it.

**Warning signs:** `self_consistency` field accuracy ≈ `single_shot` field accuracy on the matrix; suggests no diversity.

### Pitfall 5: schema validation fires on `submit_answer` and rejects valid HTML field dicts

**What goes wrong:** `submit_answer`'s schema declares `fields` as `additionalProperties: {"type": "string"}`. If model passes a `dict[str, int]` (a number), validation fails — but the existing harnesses cast to `str()` AFTER receipt. Validation BEFORE the cast catches this.

**Why it happens:** the existing single_shot does `{k: str(v) for k, v in fields.items()}` because models sometimes emit ints. If validation runs before this cast, valid-after-cast inputs are rejected pre-cast.

**How to avoid:** the validation harness should follow the existing tools.py contract — fields-as-strings is the contract. Validation rejects ints. Document in trace event `schema_validation_fail` so the article can quantify "X% of cells failed because the model emitted ints for fields."

**Warning signs:** `tool_use_with_validation` has way higher `schema_validation_exhausted` rate than expected.

### Pitfall 6: `multi_agent` tool_payload assertion in trace fails because critic call sends no tools

**What goes wrong:** `_step_model` in `base.py` logs `tool_payload` only if tools is non-empty (line 159: `if tools:`). The critic role passes no tools. So no `tool_payload` event for critic call — that's CORRECT but tests that assert "3 tool_payload events per multi_agent run" would fail.

**Why it happens:** misreading `_step_model` while writing per-harness tests.

**How to avoid:** the per-harness test asserts on `model_call` events (logged unconditionally at base.py:168), not `tool_payload`.

### Pitfall 7: `program_aided` model emits only `submit_answer` and never uses `run_python`

**What goes wrong:** the model treats `run_python` as decorative; goes straight to `submit_answer`. Article's "execution as reasoning" framing is invalid.

**Why it happens:** small models (glm-4.7-flash) often default to single-shot when they CAN.

**How to avoid:** prompt strongly: "BEFORE submitting, you MUST verify your approach with `run_python` at least once." Test asserts at least one `run_python` tool_call event in the trace. If the model still skips, document in article: "even with explicit prompt, glm-4.7-flash skipped run_python on N% of cells."

**Warning signs:** zero `run_python` events in any program_aided cell trace.

---

## Code Examples

### Example 1: jsonschema validation in `tool_use_with_validation`

```python
# Source: jsonschema 4.x API — https://python-jsonschema.readthedocs.io/en/stable/validate/
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..tools import TOOL_SCHEMAS

# Pre-build validators — schemas are static
_VALIDATORS = {
    name: Draft202012Validator(schema["input_schema"])
    for name, schema in TOOL_SCHEMAS.items()
}

def _validate_args(tool_name: str, args: dict) -> str | None:
    """Returns None on valid, structured error string on invalid."""
    v = _VALIDATORS.get(tool_name)
    if v is None:
        return None  # unknown tool — let dispatch produce its own error
    try:
        v.validate(args)
        return None
    except ValidationError as e:
        return (
            f"SCHEMA_VIOLATION in {tool_name}: {e.message} "
            f"(path={list(e.absolute_path)}, "
            f"schema_required={e.schema.get('required', [])}, "
            f"schema_properties={list(e.schema.get('properties', {}).keys())})"
        )
```

### Example 2: `run_python` tool implementation in `tools.py`

```python
# Source: existing _tool_run_tests pattern (tools.py:76-105) — adapted for arbitrary code
def _tool_run_python(ctx: ToolContext, code: str, **_: Any) -> str:
    """Execute Python code as a script. 5s timeout. Returns rc + truncated stdout/stderr."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "snippet.py"
        src.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(src)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: snippet did not complete within 5s."
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 1500:
        out = out[:1500] + "\n...[truncated]"
    return f"[rc={proc.returncode}]\n{out}"


# Register in tools.py
TOOL_IMPLS["run_python"] = _tool_run_python
TOOL_SCHEMAS["run_python"] = {
    "name": "run_python",
    "description": "Execute Python code as a standalone script in a temp subprocess (5s timeout). Returns rc + truncated stdout/stderr. Use to verify intermediate values during reasoning.",
    "input_schema": {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
}
```

### Example 3: temperature kwarg threading in `model.py`

```python
# Source: extending model.py:34-42 to accept temperature override
def call(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    temperature: float | None = None,
) -> ModelCall:
    """Single entry point. Per-call temperature overrides CONFIG default."""
    eff_temp = CONFIG.model.temperature if temperature is None else temperature
    if CONFIG.model.backend == "ollama":
        return _call_ollama(system, messages, tools, temperature=eff_temp)
    return _call_anthropic(system, messages, tools, temperature=eff_temp)


def _call_anthropic(system, messages, tools, *, temperature: float) -> ModelCall:
    ...
    kwargs = {
        "model": CONFIG.model.name,
        "max_tokens": CONFIG.model.max_tokens,
        "temperature": temperature,  # was CONFIG.model.temperature
        "system": system,
        "messages": messages,
    }
    ...

def _call_ollama(system, messages, tools, *, temperature: float) -> ModelCall:
    ...
    options = {
        "temperature": temperature,  # was CONFIG.model.temperature
        "num_predict": CONFIG.model.max_tokens,
    }
    ...
```

And in `base.py::_step_model`:
```python
def _step_model(
    self,
    system,
    messages,
    tools,
    tracer,
    usage,
    *,
    temperature: float | None = None,
) -> ModelCall:
    ...
    tracer.log("model_call", system_len=len(system), n_messages=len(messages), temperature=temperature)
    mc = model_call(system, messages, tools, temperature=temperature)
    ...
```

### Example 4: per-harness control-flow test (multi_agent)

```python
# tests/test_multi_agent.py
from unittest.mock import MagicMock
import pytest

from harness_eng.harnesses import HARNESSES
from harness_eng.harnesses import base as base_module
from harness_eng.model import ModelCall


def test_multi_agent_calls_three_distinct_systems(monkeypatch):
    seen_systems: list[str] = []
    counter = {"n": 0}

    def fake_call(system, messages, tools=None, *, temperature=None):
        seen_systems.append(system)
        counter["n"] += 1
        # First two calls = planner + executor — return text only
        # Third call = executor's submit
        if counter["n"] == 1:
            return ModelCall(1, 1, 0.0, "end_turn",
                content=[{"type": "text", "text": "Plan: 1. select title. 2. submit."}],
                usage_raw={})
        return ModelCall(1, 1, 0.0, "end_turn",
            content=[{"type": "tool_use", "id": "tu_1", "name": "submit_answer",
                      "input": {"fields": {"title": "X"}}}],
            usage_raw={})

    monkeypatch.setattr(base_module, "model_call", fake_call)
    # ... build a Task fixture ...
    harness = HARNESSES["multi_agent"]()
    result = harness.run(task, run_id="t1")
    assert result.stop_reason == "submitted"
    # 3 distinct system prompts
    assert any("PLANNER" in s for s in seen_systems)
    assert any("EXECUTOR" in s for s in seen_systems)
    assert any("CRITIC" in s for s in seen_systems)
```

### Example 5: streaming_react verification harness

```python
# scripts/verify_streaming_ollama.py — one-shot verification, runs once during planning
import sys, time
sys.path.insert(0, "src")
import os
os.environ["HARNESS_ENG_SKIP_FREEZE_GATE"] = "1"  # bypass — this is verification
from harness_eng.harnesses import HARNESSES
from harness_eng.tasks.loader import load_tasks

task = load_tasks(task_type="html_extract")[0]  # smallest
harness = HARNESSES["streaming_react"]()

t0 = time.perf_counter()
TIMEOUT = 60.0  # if it doesn't terminate in 60s on the smallest fixture, it's hung

# (run with subprocess + timeout to enforce; or use signal.alarm on Linux)
result = harness.run(task, run_id="verify")
elapsed = time.perf_counter() - t0

if elapsed > TIMEOUT or result.stop_reason in ("error", "no_submit"):
    print(f"FAILED — Ollama streaming + tool-use NOT compatible. elapsed={elapsed:.1f}s, reason={result.stop_reason}")
    print("Document in HARNESSES_FROZEN.md and set task_type=[] for streaming_react.")
    sys.exit(1)
print(f"OK — Ollama streaming WORKS. elapsed={elapsed:.1f}s")
```

---

## State of the Art

| Old approach | Current approach | Source |
|--------------|------------------|--------|
| Ollama tool-use only via non-streaming `chat` | Ollama supports `chat(stream=True, tools=[...])` with mid-stream tool detection | [Ollama blog 2025-05](https://ollama.com/blog/streaming-tool) |
| jsonschema 3.x with Draft 7 | jsonschema 4.x with Draft 2020-12 — same API, just `Draft202012Validator` | [jsonschema docs](https://python-jsonschema.readthedocs.io/en/stable/validate/) |
| `ast.dump()` for AST equivalence | `ast.unparse()` (Python 3.9+) for round-trip code-string normalization | Python 3.13 stdlib |
| Anthropic streaming via raw SSE | `client.messages.stream(...)` async/sync context manager | Anthropic SDK 0.40+ |

**Deprecated for this project's purpose:**
- vLLM with `--tool-call-parser glm47` would fix the GLM-4.7 streaming issue but adds a non-Ollama runtime — out of scope per CONFIG decision.
- `pydantic.RootModel` for tool-arg validation: rejected — schemas already exist as dicts in `tools.py`; rewriting would widen freeze diff.

---

## Open Questions

### 1. Will the `streaming_react` Anthropic implementation be tested at all?

- **What we know:** the harness file lives in tree even if Ollama-incompatible, per CONTEXT decision #7.
- **What's unclear:** there's no `harnesses-frozen` matrix run on Anthropic backend in this phase (deferred per CONTEXT cross-cutting decisions).
- **Recommendation:** the per-harness control-flow test (model-mocked) verifies the streaming termination logic in isolation. That's enough for the freeze tag. Document in HARNESSES_FROZEN.md that streaming_react is "implemented + unit-tested but not matrix-validated; deferred to a future Anthropic-backend phase."

### 2. Should `tool_use_with_validation` validate `submit_answer` strictly?

- **What we know:** `submit_answer`'s schema is loose: `fields` is `additionalProperties: {"type": "string"}` and `code` is `{"type": "string"}`, neither required.
- **What's unclear:** if model emits `submit_answer({})` (no fields, no code), strict validation passes — but the cell will fail grading.
- **Recommendation:** the validation harness validates ARGUMENTS for tools as written. Don't add stricter sub-schemas — that would diverge from the "validates against tools.py existing schemas" decision. The grader catches the empty submission as a failure, which is the right signal.

### 3. What temperature should `self_consistency` use?

- **What we know:** must be > 0 for diversity. Common choices in the literature: 0.5, 0.7, 1.0.
- **What's unclear:** glm-4.7-flash's behavior at higher temperatures is undocumented for this experiment.
- **Recommendation:** start with **0.7** (the Wang et al. 2022 paper setting; standard in the SC literature). Pre-register this in the article. If the matrix shows samples are still near-identical, document this as a model property rather than a harness-design issue.

### 4. Cache hit reporting for `cached_react` — count or not in `tool_calls`?

- **What we know:** CONTEXT framing says the harness shows "what react would cost if tool calls were free."
- **What's unclear:** does the article want `tool_calls` to drop or stay flat between react and cached_react?
- **Recommendation:** **count cache hits as tool_calls in `usage.tool_calls`** (model still emitted them), but log `cache_hit=True` so analysis can split. The article narrative becomes: "cached_react has the same tool_call count as react — same model behavior. But wall-clock drops from X to Y, and input_tokens for tool results stay flat (cached results re-billed every turn just like uncached)."

### 5. When to delete `streaming_react.py` if Anthropic backend is never run?

- **What we know:** code in tree is maintenance burden.
- **What's unclear:** is the project committing to a future Anthropic run that justifies keeping the file?
- **Recommendation:** keep the file with a `# TODO(phase-9): activate when running Anthropic-backend matrix` header comment. It's compiled, unit-tested, and registered with empty task_type — zero runtime cost. The article cites it as an "implemented but unmatrixed harness" — consistent with the project's evidence-first stance.

---

## Sources

### Primary (HIGH confidence)
- **In-repo source files** — read directly via Read tool:
  - `src/harness_eng/harnesses/{base,single_shot,react,plan_execute,reflexion,minimal,chain_of_thought,test_driven,retry_on_fail,__init__}.py`
  - `src/harness_eng/{tools,model,runner,config,trace,analysis}.py`
  - `tests/{test_harness_registry,test_tool_allowlist,test_freeze_gate,test_tools}.py`
  - `HARNESSES_FROZEN.md`, `pyproject.toml`, `.planning/{REQUIREMENTS,STATE,ROADMAP}.md`, `.planning/phases/08-expand-harness-family/CONTEXT.md`, `writeup/article.md`
- **Installed package versions** verified via `pip show`: `jsonschema 4.25.1`, `ollama 0.6.1`.

### Secondary (MEDIUM confidence — verified against official sources)
- [Ollama blog: Streaming responses with tool calling](https://ollama.com/blog/streaming-tool) — confirms mid-stream tool-call detection in current Ollama
- [Ollama issue #13840: Generation stops after tool call with Ollama (GLM-4.7-Flash)](https://github.com/ollama/ollama/issues/13840) — confirms glm-4.7-flash specifically halts post-tool-call
- [ollama-python README](https://github.com/ollama/ollama-python) — confirms `chat(stream=True, tools=[...])` API
- [jsonschema docs (Schema Validation)](https://python-jsonschema.readthedocs.io/en/stable/validate/) — confirms `Draft202012Validator` API
- [jsonschema PyPI](https://pypi.org/project/jsonschema/) — confirms versioning
- [ollama-python issue #463](https://github.com/ollama/ollama-python/issues/463) — historical context (closed) on streaming + tools

### Tertiary (LOW confidence — flagged for validation)
- [BetterClaw blog "OpenClaw + Ollama: Local Model Setup & Tool Calling Fix (2026)"](https://www.betterclaw.io/blog/openclaw-ollama-guide) — third-party guidance on glm-4.7 tool-call workaround; corroborates issue #13840 but isn't an authoritative source
- [HuggingFace discussion on GLM-4.7-Flash GGUF tool-calling](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/23) — community Modelfile fix; out-of-scope for this project but supports the "skip-with-note" decision

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — `jsonschema` is a well-known dep; addition is one pyproject line.
- Architecture patterns: **HIGH** — patterns drawn directly from existing harness files in tree.
- Streaming Ollama compatibility: **MEDIUM** — based on open issue #13840 + Ollama blog. Verification step in Phase 8 will produce empirical evidence.
- Per-harness pitfalls: **HIGH** — distilled from tool_allowlist test, freeze_gate test, and the existing analysis chart code.
- Test patterns: **HIGH** — direct extension of `test_tool_allowlist.py::test_step_model_accepts_subset_of_whitelist`.
- temperature override scope: **HIGH** — confirmed `model.py` has no current override path; addition is mechanical.

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (30 days for the in-repo findings; the Ollama streaming compatibility status may change faster — re-verify if more than 14 days elapse before the Phase 8 plans are executed).
