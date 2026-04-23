# Phase 1: Audit and Harden Scaffold - Research

**Researched:** 2026-04-23
**Domain:** Retroactive hardening of committed Python scaffold (trace writer, grader, SDK client, harness base) against methodology invariants
**Confidence:** HIGH

## Summary

Phase 1 is not a build phase. Every file it touches is already committed. Its job is to diff the committed surface against five hard invariants (schema_version v1, grader Unicode/locale determinism, SDK `max_retries=0` + full usage recording, tool-result-token regression test, held-out fixture decision) and apply the smallest possible set of additive edits that make each invariant machine-verifiable. Over-engineering is the main risk — any touch to `harnesses/*.py`, `tools.py`, or `model.py` beyond the minimum compounds cost later because Phase 2 freezes those files.

The actual committed state has five concrete gaps against the success criteria: (1) `trace.py` flushes but never fsyncs and emits no `schema_version`; (2) `grader.py` uses `.lower()` (locale-dependent for Turkish-locale Windows installs) with no NFC normalization and no determinism test; (3) `model.py` never passes `max_retries=0` to `Anthropic()` and drops cache usage fields (`cache_read_input_tokens`, `cache_creation_input_tokens`) when building `ModelCall`; (4) no synthetic-transcript test exists covering tool-result token re-billing; (5) no `HELD_OUT.md` exists. Everything else the phase requirement IDs mention is already implemented and passes tests — the phase's remaining work is to add tests that pin the current behavior before Phase 2 tags the freeze.

The platform gotchas are all mild. `os.fsync` on Windows maps to `_commit()` and works on any `fileno()` — but the current text-mode file handle needs a `flush()` before `fsync()` because Python's buffer sits above the OS buffer. `unicodedata.normalize("NFC", ...)` is locale-independent by design (pure table lookup). `str.casefold()` is the correct primitive (handles German ß, Turkish dotted/dotless i, Greek sigma) where `.lower()` is not.

**Primary recommendation:** Additive edits only. Add `schema_version: 1` as a required field written by `Tracer.log`; add `os.fsync(self._fh.fileno())` after `flush()`; rewrite `grader._norm` as NFC → strip → casefold → ASCII-whitespace collapse; add `max_retries=0` to the `Anthropic()` constructor; expand `ModelCall` to record the full `usage.model_dump()` blob; add four new test files (`test_trace_schema.py`, `test_grader_determinism.py`, `test_model_usage.py`, `test_tool_result_rebilling.py`); create `HELD_OUT.md`. Do not restructure, do not refactor, do not rename.

<phase_requirements>
## Phase Requirements

The 34 phase requirement IDs split into three categories. Distinguish carefully — the phase's deliverable is tests that pin existing behavior, not re-implementation.

### Already implemented AND already tested — phase only verifies pytest passes

| ID | Description | Where it lives | Existing test |
|----|-------------|----------------|---------------|
| INTG-01 | Only `model.py` imports `anthropic`; AST-enforced | `src/harness_eng/model.py` (sole site), `tests/test_model_seal.py` | `test_model_seal.py::test_only_model_py_imports_anthropic` |
| INTG-02 | Every harness routes through `model.call()` | `harnesses/base.py::_step_model` | Implicitly covered by `test_harness_registry.py::test_no_harness_imports_anthropic_directly` |
| INTG-03 | Model id, temperature, max_tokens live in frozen `config.py` | `config.py::ExperimentConfig` + `ModelConfig` | Indirect: passes via `CONFIG` singleton |
| HARN-01..HARN-06 | Five harnesses exist, all terminate via `submit_answer` | `harnesses/{single_shot, react, plan_execute, reflexion, minimal}.py` | `test_harness_registry.py` (registry + no-anthropic-import) |
| BENCH-01..BENCH-03 | 5 fixtures across 5 domains, 3+ fields, decoys | `tasks/fixtures/*.html` + `tasks.jsonl` | `test_tasks.py::test_tasks_load`, `test_expected_field_counts` |
| TRACE-01, TRACE-04, TRACE-05 | Events written before return, `run_start`/`run_end` bracket, wall-clock ts + type + payload | `trace.py::Tracer.log`, `harnesses/base.py::run` try/except/finally-equivalent | No regression test — phase adds one |
| RUN-01 | CLI runs matrix sequentially | `runner.py::run_matrix` | No test, but trivial; phase adds smoke coverage if needed |
| RUN-03 | JSONL row per cell with predicted/tokens/grade | `runner.py::_result_row` | No test — phase adds one |
| RUN-05, RUN-06 | Cost estimator + `--yes` confirmation | `cost_estimator.py` | `test_cost_estimator.py::test_estimate_shape` |
| ANAL-01, ANAL-03, ANAL-04 | summary.csv, frontier.png, heatmap.png | `analysis.py` | No test — phase does not require one (analysis is downstream) |
| ART-01, ART-02 | Article auto-drafted from CSV | `analysis.py` article generator | No test — phase does not require one |
| VIEW-01..VIEW-04 | Standalone HTML trace viewer | `trace_viewer.py` | No test — phase does not require one |
| TEST-01 | pytest suite covers grader, tasks, tools, AST seal, harness registry, cost estimator | `tests/*.py` | Suite already green |
| ONB-03 | `.env.example` shipped | Root of repo (verify existence) | Manual check |

### Already implemented but needs a hardening edit AND a new test

| ID | Description | Gap | Delta required |
|----|-------------|-----|----------------|
| TRACE-02 | Line buffering + flush per event | `Tracer.__post_init__` uses default buffering (text mode → line-buffered by default on text files, but NOT guaranteed; no `fsync`) | Change `open("a", encoding="utf-8")` to `open("a", buffering=1, encoding="utf-8")`; add `os.fsync(self._fh.fileno())` after `self._fh.flush()` in `log()` |
| TRACE-03 | `schema_version` field on every event | Not present anywhere in `trace.py` | Add `SCHEMA_VERSION = 1` module constant; include `"schema_version": SCHEMA_VERSION` in every record written |
| BENCH-04 | Grader does NFC + casefold + whitespace collapse | Current `_norm` uses `.strip().lower()` with `re.sub(r"\s+", ...)`. Missing NFC. Uses `.lower()` (Turkish-locale break) instead of `.casefold()` | Rewrite `_norm` as pipeline: `unicodedata.normalize("NFC", s).strip().casefold()` then `re.sub(r"[ \t\n\r\f\v]+", " ", ...)` (explicit ASCII whitespace class to avoid locale-dependent `\s`) |
| TEST-02 | Trace-schema regression test: synthetic multi-turn transcript confirms tool-result tokens accounted | No such test exists | New `tests/test_tool_result_rebilling.py` — monkeypatch `harness_eng.model.call` with a fake that emits known input/output tokens scaling with history length; assert `usage.input_tokens` accumulates correctly |

### Not yet done — phase must add

| ID | Description | New artifact |
|----|-------------|--------------|
| (not an ID — success criterion 3) | `Anthropic(max_retries=0)` in client constructor | Edit `model.py::_get_client` to pass `max_retries=0` |
| (not an ID — success criterion 3) | Full `response.usage` blob recorded (not just two fields) | Expand `ModelCall` dataclass: add `usage_raw: dict` field populated via `resp.usage.model_dump()`; `Tracer` `model_response` event writes it |
| (not an ID — success criterion 5) | `HELD_OUT.md` decision recorded | New file at repo root or `docs/HELD_OUT.md` |
</phase_requirements>

## Standard Stack

Phase 1 is plumbing hardening in Python stdlib + already-pinned project deps. No new libraries.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `unicodedata` | stdlib | NFC normalization before compare | Only locale-independent Unicode normalization in stdlib; pure function (verified: no locale dependence in the `normalize()` API — table-driven) |
| Python `os.fsync` | stdlib | Force write to disk post-flush | Maps to `_commit()` on Windows; works on any fileno from a flushed text-mode file |
| Python `str.casefold` | stdlib (3.3+) | Caseless string comparison | Correct primitive — handles German ß → `ss`, Turkish dotted i, Greek sigma variants; `.lower()` does not |
| `pytest` | `>=8.3` (already pinned) | All new tests | Already the repo's test runner |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `anthropic` | `>=0.96,<1.0` (already pinned) | Only consumed via its `Anthropic(max_retries=0)` constructor kwarg in `model.py`; `Message.usage` fields read via `model_dump()` | No API changes needed beyond `max_retries=0` — SDK already supports it |
| `pytest.monkeypatch` | pytest fixture | Stub `anthropic` client in the multi-turn transcript test without recording real API calls | Fixture-based mocking is the repo's existing test pattern (verified: no `vcrpy`, no `responses`, no recorded cassettes) |

### Alternatives Considered

| Instead of | Could Use | Why rejected |
|------------|-----------|----------|
| `os.fsync` after every JSONL write | `open(path, "a", buffering=0)` raw binary | Can't use `buffering=0` with text mode; would require `f.write(line.encode())` rewrites. `fsync` after `flush` is the canonical pattern and is in Python's own docs. |
| `unicodedata.normalize("NFC", s)` | `"NFKC"` | NFKC is compatibility-compat (half-width → full-width, etc.) — too aggressive; collapses `½` to `1⁄2`. The invariant is visual equivalence, NFC is correct. |
| `str.casefold()` | `str.lower()` | `.lower()` is locale-sensitive on Turkish (`İ` → `i̇`); `.casefold()` is always locale-independent and also handles German ß correctly. |
| Mock `anthropic.Anthropic` for re-billing test | Record real transcript via cassette | Re-billing is math, not API behavior — a pure stub is more deterministic and doesn't burn tokens on CI |
| Pin HTML/JSONL as `-text` in `.gitattributes` | Do it in Phase 1 | Defer to Phase 7 per ROADMAP; only matters for Windows-CI determinism which is a Phase 7 concern. Phase 1 does NOT touch `.gitattributes`. |

## Architecture Patterns

Phase 1 preserves the existing architecture. Only two editing patterns apply, both additive.

### Pattern 1: Add schema_version as a module constant, write on every event

**What:** One `SCHEMA_VERSION: int = 1` at the top of `trace.py`. Every `Tracer.log` payload includes it. Changes to the record shape bump it.

**When to use:** Any append-only log format that will be read post-hoc by code that may have drifted from the writer.

**Example:**
```python
# src/harness_eng/trace.py (AFTER edit)
SCHEMA_VERSION = 1

def log(self, event_type: str, **payload: Any) -> None:
    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": time.time(),
        "type": event_type,
        **payload,
    }
    self._fh.write(json.dumps(record, default=str) + "\n")
    self._fh.flush()
    os.fsync(self._fh.fileno())
```

### Pattern 2: Grader as an explicit, documented pipeline

**What:** `_norm` becomes a 4-step pipeline where each step is a single line with a comment naming the invariant it preserves. Testable at the step level (optional — end-to-end golden trace test is sufficient).

**When to use:** Any deterministic string-compare function where the normalization pipeline's ordering is load-bearing.

**Example:**
```python
# src/harness_eng/grader.py (AFTER edit)
import unicodedata
import re

_ASCII_WS = re.compile(r"[ \t\n\r\f\v]+")  # NOT \s — \s matches unicode whitespace, which varies

def _norm(s: str) -> str:
    # 1. NFC: visually identical graphemes become byte-identical
    s = unicodedata.normalize("NFC", s)
    # 2. Strip leading/trailing whitespace
    s = s.strip()
    # 3. casefold (not lower) — locale-independent, handles Turkish i and German ß
    s = s.casefold()
    # 4. Collapse ASCII whitespace runs to single space
    s = _ASCII_WS.sub(" ", s)
    return s
```

### Anti-Patterns to Avoid

- **Refactoring `Tracer` into a class hierarchy for testability** — the current dataclass is fine; add `os.fsync` in place. Any refactor costs reviewer cycles and risks breaking the freeze window.
- **Adding a `GraderConfig` class** — normalization steps are explicit because they're few, not because they need to be configurable. Making them pluggable creates drift risk.
- **Moving `max_retries=0` to an env var** — method signatures are the contract; env vars are user-visible configuration. `max_retries` is load-bearing experimental plumbing. Hardcode it in the constructor.
- **Running the synthetic transcript test against the real Anthropic API** — the test is about math (3 turns × 1000 tokens ≈ 3000 cumulative input_tokens), not about API fidelity. Burn no tokens.
- **Rewriting `ModelCall` from `@dataclass` to `pydantic.BaseModel`** — out of scope; touch only the fields added.
- **Writing a comprehensive trace-schema specification document** — `schema_version: 1` is a number. The shape IS the spec. Don't write prose.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unicode normalization | Custom canonicalizer | `unicodedata.normalize("NFC", s)` | Only stdlib correct implementation; locale-independent; table-driven |
| Caseless compare | `.lower()` or custom lowercase map | `str.casefold()` | `.lower()` breaks on Turkish locales; `.casefold()` is the Unicode spec's caseless-match primitive |
| Whitespace detection in regex | `\s` | Explicit `[ \t\n\r\f\v]+` | `\s` matches ` ` (NBSP), ` ` (line separator), other Unicode whitespace — adds non-determinism if fixtures ever contain NBSP (product price fixtures routinely do) |
| Fsync on Windows | Custom `ctypes` call to `_commit` | `os.fsync(fd)` | stdlib; CPython already does the right thing |
| Mock SDK for re-billing test | VCR cassettes, `responses` lib, recorded fixtures | `monkeypatch.setattr("harness_eng.model.call", fake_call)` | Pure math test; real API adds non-determinism and token cost |
| Detecting "partial trace survives crash" | Kill-mid-write subprocess test | Truncate-and-parse test: write N records, truncate last line mid-way, parse remaining N-1 as JSON — assert each parses | Equivalent semantics, no subprocess, cross-platform |

**Key insight:** Every non-stdlib primitive for Phase 1 is a smell. The phase is a hardening pass; hardening uses well-known platform primitives, not new dependencies.

## Common Pitfalls

### Pitfall 1: `\s` in whitespace collapse regex

**What goes wrong:** `re.sub(r"\s+", " ", s)` matches Unicode whitespace characters (NBSP ` `, narrow NBSP ` `, line separator ` `, etc.). Fixtures with `&nbsp;` in product prices normalize differently on different platforms depending on re module compile flags.
**Why it happens:** Standard Python idiom; developers copy from Stack Overflow without reading that `\s` is Unicode-aware in Python 3.
**How to avoid:** Use explicit ASCII character class: `re.compile(r"[ \t\n\r\f\v]+")`. Or use `re.compile(r"\s+", re.ASCII)`. First is clearer.
**Warning signs:** Grader test passes locally, fails on another dev's machine; or passes on Linux, fails on Windows.

### Pitfall 2: `str.lower()` vs `str.casefold()`

**What goes wrong:** `.lower()` is locale-sensitive on Turkish systems (`İ.lower()` → `i̇`, not `i`). Product fixtures with Turkish-named entities grade differently on CI (en_US locale) vs a contributor's Istanbul machine.
**Why it happens:** `.lower()` is the obvious first guess; `.casefold()` is the Unicode-correct primitive but is less well-known.
**How to avoid:** Always `.casefold()` for caseless compare. Never `.lower()` in grader code.
**Warning signs:** Any grader test output differs between contributors; any ticket about "weird character handling."

### Pitfall 3: `os.fsync` on an unflushed buffered handle

**What goes wrong:** Python's text-mode buffer sits above the OS buffer. `os.fsync(fileno())` only flushes the OS buffer. If Python buffered the last write, that last record is lost on crash despite the `fsync` call.
**Why it happens:** Developers assume `fsync` is absolute. It is not — it's "flush OS buffer to disk," not "flush everything."
**How to avoid:** Always `f.flush(); os.fsync(f.fileno())` in that order. Python docs state this explicitly.
**Warning signs:** Crash-recovery tests show the last JSON line is truncated or missing.

### Pitfall 4: Text-mode fsync interaction with CRLF translation on Windows

**What goes wrong:** On Windows, text mode translates `\n` → `\r\n` on write. If the writer's `json.dumps(record) + "\n"` is 100 bytes in Python, the on-disk byte count differs from the logical line count. `fsync` works either way, but the downstream reader must handle CRLF if present. `json.loads` strips whitespace, so this is usually invisible — but file byte-size tests that pin a specific byte count will fail on Windows.
**Why it happens:** Text mode is the Python default; CRLF conversion is invisible until you hash the file.
**How to avoid:** Either open in binary mode (`open("ab", buffering=0)` + encode manually) OR accept CRLF and do not assert byte-size. For this phase, the latter — the trace file is read line-by-line, not byte-hashed. Defer binary-mode to Phase 7 if `.gitattributes`-based CRLF handling surfaces a real reader bug.
**Warning signs:** A byte-count or hash-based test of the trace file differs between Linux and Windows CI.

### Pitfall 5: Recording only `input_tokens`/`output_tokens` and dropping cache fields

**What goes wrong:** Current `ModelCall.__init__` reads `resp.usage.input_tokens` and `resp.usage.output_tokens`. If the project ever enables prompt caching (out of scope for v1 but possible for v2), the cache fields (`cache_read_input_tokens`, `cache_creation_input_tokens`) are already silently dropped. Retroactively recovering them requires re-running the matrix.
**Why it happens:** Usage blob has 4+ fields; only 2 are "obviously important" on first pass.
**How to avoid:** Store the full `resp.usage.model_dump()` (or equivalent dict conversion) as `ModelCall.usage_raw`. Keep the two aggregated fields for convenience; the raw blob is the source of truth the trace event writes.
**Warning signs:** Any analysis script that assumes cache fields are zero when they might not be.

### Pitfall 6: Synthetic transcript test that doesn't exercise the re-billing shape

**What goes wrong:** A test that stubs `anthropic` to always return `input_tokens=100, output_tokens=50` regardless of history length "passes" but proves nothing about re-billing. The real question is whether, when a harness sends a 3-turn conversation with tool_result blocks, the **cumulative** `input_tokens` over the three model calls scales approximately linearly with history size.
**Why it happens:** Mock simplicity; developers stub a constant return.
**How to avoid:** The fake `model.call` in the test must return `input_tokens == f(len(messages))` — e.g., `input_tokens = sum(len(str(m)) for m in messages) // 4`. Then the test asserts that `usage.input_tokens` after N turns is strictly greater than after N-1, AND that growth is roughly proportional to tool output size. The assertion is on monotonic growth with message history, not on a specific token count.
**Warning signs:** Test has a hardcoded expected number like `assert usage.input_tokens == 3000` — that's testing the stub, not the re-billing semantics.

### Pitfall 7: Writing `schema_version` on some events but not others

**What goes wrong:** Adding `schema_version` to `Tracer.log` but forgetting that the initial `run_start` in `base.py` also goes through the same method — fine. BUT if `runner.py` ever writes directly to a file (it does, for `results.jsonl`), those rows won't have `schema_version`. Mixed-format JSONL breaks downstream readers.
**Why it happens:** Two "trace-like" writers in the codebase: `Tracer` (traces) and `runner._result_row` → `results.jsonl`. Easy to conflate.
**How to avoid:** `schema_version` applies to `traces/` files written by `Tracer`. `results/runs/*.jsonl` is a separate artifact with its own shape. Document this distinction in the trace schema test. Do NOT retrofit `schema_version` into results rows in Phase 1 — out of scope.
**Warning signs:** A test that asserts `schema_version` is present in every `results/runs/*.jsonl` row fails because it's a different artifact.

### Pitfall 8: Asserting `max_retries=0` is respected via introspection

**What goes wrong:** A test that does `client._max_retries == 0` relies on a private attribute of the `anthropic` SDK. SDK version bumps silently break it.
**Why it happens:** Obvious path to assert the kwarg took effect.
**How to avoid:** Test the wire contract: instantiate the client with `max_retries=0`, monkeypatch the underlying transport to raise `anthropic.APIStatusError` with a 429, and assert that it raises after exactly one attempt (not 3 or 6). This tests observable behavior, not SDK internals.
**Warning signs:** The test file imports `anthropic._base_client` or any underscore-prefixed name.

### Pitfall 9: Opening the trace file in `"a"` mode on Windows and expecting exclusive write

**What goes wrong:** Windows Git-Bash doesn't enforce POSIX advisory locks. If two runs with the same (harness, task, run_id) execute concurrently (shouldn't happen — matrix is sequential — but a test might), both append interleaved lines.
**Why it happens:** `"a"` is atomic-append on POSIX, best-effort on Windows.
**How to avoid:** Not a real concern at matrix scale (runner is sequential). Document as a known limitation. Do not add a lock in Phase 1 — premature hardening.

### Pitfall 10: Held-out fixture decision deferred without recording

**What goes wrong:** Phase 1 completes, Phase 2 tags the freeze, and no decision was made about held-out fixtures. The article can't later claim "2 of 5 held out" because no artifact proves it.
**Why it happens:** The decision requires judgment (5 fixtures is tight) and feels defer-able.
**How to avoid:** `HELD_OUT.md` at repo root commits the choice before Phase 2 freeze. Either "task_04 and task_05 held out from pilot, used only in matrix" OR "no holdout — all 5 used for pilot and matrix, rationale: N=5 too small for meaningful holdout." Either is defensible; silence is not.
**Warning signs:** Phase 2 planning starts without `HELD_OUT.md` in git.

## Code Examples

### Hardened `Tracer.log` (trace.py)

```python
# src/harness_eng/trace.py — additive edit
import os  # NEW import

SCHEMA_VERSION = 1  # NEW module constant

@dataclass
class Tracer:
    # ... existing fields unchanged ...

    def __post_init__(self) -> None:
        self.path = TRACES_DIR / self.harness / self.task_id / f"{self.run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", buffering=1, encoding="utf-8")  # line buffering explicit

    def log(self, event_type: str, **payload: Any) -> None:
        record = {
            "schema_version": SCHEMA_VERSION,  # NEW
            "ts": time.time(),
            "type": event_type,
            **payload,
        }
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())  # NEW — crash durability
```

### Hardened `grader._norm` (grader.py)

```python
# src/harness_eng/grader.py — rewrite of _norm only
import unicodedata
import re

_ASCII_WS = re.compile(r"[ \t\n\r\f\v]+")  # explicit, not \s

def _norm(s: str) -> str:
    # Pipeline order matters: NFC first so composed/decomposed are equal,
    # then strip/casefold, then whitespace collapse (which may re-expose whitespace
    # that was inside a trimmed region).
    s = unicodedata.normalize("NFC", s)
    s = s.strip()
    s = s.casefold()  # NOT .lower() — locale-independent; handles ß, Turkish i, Greek sigma
    s = _ASCII_WS.sub(" ", s)
    return s
```

### Hardened `model.py` — max_retries=0 + full usage blob

```python
# src/harness_eng/model.py — two edits

def _get_client() -> Any:
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic(max_retries=0)  # NEW: disable SDK auto-retry
    return _client


@dataclass
class ModelCall:
    input_tokens: int
    output_tokens: int
    latency_s: float
    stop_reason: str
    content: list[dict[str, Any]]
    usage_raw: dict[str, Any]  # NEW: full usage blob including cache fields


def call(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> ModelCall:
    # ... unchanged setup ...
    resp = client.messages.create(**kwargs)
    latency = time.perf_counter() - t0

    # NEW: capture full usage via model_dump (or dict() fallback)
    try:
        usage_raw = resp.usage.model_dump()  # pydantic v2 method, SDK >=0.39
    except AttributeError:
        usage_raw = dict(resp.usage.__dict__)  # defensive fallback

    return ModelCall(
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        latency_s=latency,
        stop_reason=resp.stop_reason or "",
        content=[b.model_dump() for b in resp.content],
        usage_raw=usage_raw,  # NEW
    )
```

Correspondingly, `harnesses/base.py::_step_model` writes `usage_raw` in the `model_response` event:
```python
tracer.log(
    "model_response",
    input_tokens=mc.input_tokens,
    output_tokens=mc.output_tokens,
    usage=mc.usage_raw,  # NEW — full blob to trace
    latency_s=mc.latency_s,
    stop_reason=mc.stop_reason,
    content=mc.content,
)
```

### Synthetic multi-turn re-billing test

```python
# tests/test_tool_result_rebilling.py — NEW file
"""Regression test: tool_result tokens re-billed on each subsequent turn.

Anthropic's API bills a tool_result block as input_tokens on the turn AFTER it
is sent. A multi-turn harness with a 1000-token tool output must pay roughly
1000 extra input_tokens per turn that keeps the history.

This test stubs model.call to return input_tokens proportional to message
history size, then drives a minimal ReAct-style loop and asserts cumulative
input_tokens grows strictly with each turn (not flat). Flat growth indicates
the harness is clobbering usage accumulation.
"""
from __future__ import annotations

import pytest

from harness_eng import model as model_module
from harness_eng.harnesses.base import _Usage
from harness_eng.model import ModelCall


def _fake_call_factory(tool_out_tokens: int = 1000):
    """Returns a fake model.call whose input_tokens scales with message count."""
    turn_counter = {"n": 0}

    def fake_call(system, messages, tools=None):
        turn_counter["n"] += 1
        # Simulate: input_tokens == 500 baseline + 1000 per prior assistant+tool_result pair
        n_prior_tool_results = sum(
            1
            for m in messages
            if isinstance(m.get("content"), list)
            and any(b.get("type") == "tool_result" for b in m["content"])
        )
        input_tokens = 500 + tool_out_tokens * n_prior_tool_results
        return ModelCall(
            input_tokens=input_tokens,
            output_tokens=50,
            latency_s=0.01,
            stop_reason="tool_use",
            content=[],
            usage_raw={"input_tokens": input_tokens, "output_tokens": 50},
        )

    return fake_call, turn_counter


def test_tool_result_tokens_accumulate_across_turns(monkeypatch):
    fake, _ = _fake_call_factory(tool_out_tokens=1000)
    monkeypatch.setattr(model_module, "call", fake)

    usage = _Usage()
    # Simulate 3 model calls, each with growing history.
    # Turn 1: no prior tool_results → 500 in
    mc1 = model_module.call("sys", [{"role": "user", "content": "go"}])
    usage.record(mc1)
    # Turn 2: 1 prior tool_result → 500 + 1000 = 1500 in
    msgs_t2 = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 100}]},
    ]
    mc2 = model_module.call("sys", msgs_t2)
    usage.record(mc2)
    # Turn 3: 2 prior tool_results → 500 + 2000 = 2500 in
    msgs_t3 = msgs_t2 + [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "y" * 100}]},
    ]
    mc3 = model_module.call("sys", msgs_t3)
    usage.record(mc3)

    # Cumulative input_tokens across 3 calls: 500 + 1500 + 2500 = 4500
    assert usage.input_tokens == 4500
    assert usage.turns == 3
    # Monotonic: each turn's input is strictly >= prior turn's
    assert mc2.input_tokens > mc1.input_tokens
    assert mc3.input_tokens > mc2.input_tokens
    # Growth is dominated by tool_output size (~1000 per turn), proving re-billing
    assert mc3.input_tokens - mc2.input_tokens >= 900  # allow slack for stub rounding
```

### Trace schema regression test

```python
# tests/test_trace_schema.py — NEW file
import json
from pathlib import Path

from harness_eng.trace import SCHEMA_VERSION, Tracer


def test_every_record_has_schema_version(tmp_path, monkeypatch):
    monkeypatch.setattr("harness_eng.trace.TRACES_DIR", tmp_path)
    with Tracer("test_harness", "task_01", "runid123") as t:
        t.log("run_start", foo=1)
        t.log("model_call", n_messages=2)
        t.log("run_end", ok=True)

    trace_file = tmp_path / "test_harness" / "task_01" / "runid123.jsonl"
    records = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    for r in records:
        assert r["schema_version"] == SCHEMA_VERSION
        assert "ts" in r
        assert "type" in r
    assert [r["type"] for r in records] == ["run_start", "model_call", "run_end"]


def test_partial_trace_parseable_after_truncation(tmp_path, monkeypatch):
    """Simulate crash mid-write: truncate file mid-line, ensure prior records parse."""
    monkeypatch.setattr("harness_eng.trace.TRACES_DIR", tmp_path)
    with Tracer("h", "t", "r") as t:
        t.log("run_start")
        t.log("model_call", n=1)
        t.log("model_call", n=2)

    trace_file = tmp_path / "h" / "t" / "r.jsonl"
    raw = trace_file.read_bytes()
    # Truncate last 5 bytes to simulate partial last line
    trace_file.write_bytes(raw[:-5])
    good_lines = []
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        try:
            good_lines.append(json.loads(line))
        except json.JSONDecodeError:
            break  # partial terminal line — expected
    assert len(good_lines) >= 2
    assert good_lines[0]["type"] == "run_start"
```

### Grader determinism test

```python
# tests/test_grader_determinism.py — NEW file
"""Golden-trace determinism: grading the same input 100x gives byte-identical output.

Ensures _norm is pure, no hidden state, no locale dependence. Covers the
Turkish-i, German-ß, NFC/NFD, NBSP, and trailing-whitespace edge cases.
"""
from __future__ import annotations

import json

from harness_eng.grader import grade


GOLDEN_CASES = [
    # (predicted, expected, expected_success)
    ({"name": "Hello World"}, {"name": "hello world"}, True),
    ({"name": "  HELLO\tWORLD\n"}, {"name": "hello world"}, True),
    # Turkish uppercase dotted I — .lower() would break this, .casefold() is fine
    ({"name": "İstanbul"}, {"name": "i̇stanbul"}, True),  # NFC-equivalent after casefold
    # German ß — .lower() keeps ß, .casefold() normalizes to "ss"
    ({"greeting": "straße"}, {"greeting": "strasse"}, True),
    # NFC vs NFD: é as one codepoint vs e + combining acute
    ({"word": "café"}, {"word": "café"}, True),
    # Wrong answer still wrong
    ({"a": "foo"}, {"a": "bar"}, False),
]


def test_golden_cases():
    for predicted, expected, expect_success in GOLDEN_CASES:
        r = grade(predicted, expected)
        assert r.success is expect_success, f"failed: {predicted} vs {expected}"


def test_100x_determinism():
    """Same input graded 100 times — all results byte-identical."""
    predicted = {"name": "  Hello  WORLD  ", "price": "19.99"}
    expected = {"name": "hello world", "price": "19.99"}
    results = [grade(predicted, expected) for _ in range(100)]
    # Serialize to canonical JSON and compare
    serialized = [
        json.dumps(
            {"per_field": r.per_field, "field_accuracy": r.field_accuracy, "success": r.success},
            sort_keys=True,
        )
        for r in results
    ]
    assert len(set(serialized)) == 1, "grader is non-deterministic"
```

### max_retries test

```python
# tests/test_model_usage.py — NEW file
"""Verify SDK client is constructed with max_retries=0 and usage_raw is populated.

Does NOT assert on private SDK internals — tests observable behavior only.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness_eng import model as model_module


def test_client_constructed_with_max_retries_zero(monkeypatch):
    """When _get_client is called, the Anthropic(...) constructor receives max_retries=0."""
    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    # Patch the lazy import path
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    # Reset the cached client
    monkeypatch.setattr(model_module, "_client", None)
    model_module._get_client()
    assert captured.get("max_retries") == 0


def test_usage_raw_populated(monkeypatch):
    """ModelCall.usage_raw contains every field the SDK's usage object returns."""
    class FakeUsage:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 10
        cache_creation_input_tokens = 5

        def model_dump(self):
            return {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            }

    class FakeContent:
        def model_dump(self):
            return {"type": "text", "text": "ok"}

    class FakeResp:
        usage = FakeUsage()
        stop_reason = "end_turn"
        content = [FakeContent()]

    class FakeMessages:
        def create(self, **_kw):
            return FakeResp()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(model_module, "_client", FakeClient())
    mc = model_module.call(system="sys", messages=[{"role": "user", "content": "hi"}])
    assert mc.usage_raw == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    }
    assert mc.input_tokens == 100
    assert mc.output_tokens == 50
```

### HELD_OUT.md

```markdown
# Held-Out Fixtures Decision

**Decided:** 2026-04-23 (before Phase 2 freeze)
**Decision:** [TO BE FILLED IN BY IMPLEMENTER — pick one of the two branches below]

## Option A: No holdout (recommended for v1)

With 5 fixtures total, holding 2 out leaves 3 for harness development and pilot runs.
Given that the harnesses are already committed and their prompts were written
against an unknown (to author, at time of writing) subset of fixtures, the "clean
holdout" property is already weak. Rather than claim a holdout that isn't truly
held, v1 uses all 5 fixtures for both pilot and matrix. The article will state:
"All 5 fixtures were visible during harness development. v2 (SCALE-02) introduces
a 2-fixture holdout against an expanded 40-fixture set."

## Option B: Retroactive holdout

task_04 and task_05 are designated held-out. Any commit touching the harnesses,
tools, or model files that references task_04 or task_05 by id (`grep -r task_04
src/`) invalidates the holdout. Verified by a pytest.

## Rationale

[Selected option] chosen because [one-paragraph justification].
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `str.lower()` for caseless compare | `str.casefold()` | Python 3.3 (2012) | Must use `.casefold()` in grader; `.lower()` is Turkish-locale-hostile |
| `\s` in regex for whitespace | explicit `[ \t\n\r\f\v]+` or `\s` with `re.ASCII` | always — `\s` has been Unicode-aware since Python 3.0 | Grader must use explicit class or ASCII flag |
| `open(path, "a")` alone for crash safety | `open(path, "a", buffering=1)` + `f.flush()` + `os.fsync()` | always — crash safety is POSIX-standard | Every durable JSONL writer needs this triad |
| `anthropic.Anthropic()` default retries | `anthropic.Anthropic(max_retries=0)` | SDK has supported this since early 0.x | Experimental plumbing must disable SDK-level retry to prevent double-billing |
| Recording `resp.usage.input_tokens` + `.output_tokens` only | Recording `resp.usage.model_dump()` (full blob) | SDK 0.39+ ships pydantic v2 usage | Cache fields must be persisted even if caching is disabled, to prove they're zero |

**Deprecated/outdated in THIS codebase:**
- `trace.py` current state: no `schema_version`, no `fsync`. Deprecated as of this phase.
- `grader.py::_norm` using `.lower()`: deprecated; rewrite to casefold.
- `model.py::_get_client()` using `Anthropic()` without `max_retries=0`: deprecated; add kwarg.

## Open Questions

1. **Should `schema_version` also appear in `results/runs/*.jsonl`?**
   - What we know: Requirements mention it on trace events (TRACE-03). Requirements do not mention results rows.
   - What's unclear: Future schema drift on results rows is also a real risk.
   - Recommendation: Phase 1 does ONLY traces per TRACE-03 scope. File a v2 item for results schema versioning. Don't expand scope here.

2. **Does `HELD_OUT.md` live at repo root or under `docs/`?**
   - What we know: PROJECT.md and REQUIREMENTS.md live at `.planning/`. `HARNESSES_FROZEN.md` (Phase 2) is described as a root-level artifact.
   - What's unclear: Conventions for "methodology decision notes" in this repo.
   - Recommendation: Repo root, alongside `README.md` — it's a first-class methodology artifact that readers of the article will look for next to the code.

3. **Should the trace `usage` event field be named `usage` (short) or `usage_raw` (explicit)?**
   - What we know: `ModelCall.usage_raw` is the dataclass field. The trace event is what downstream analysis parses.
   - What's unclear: Naming is load-bearing for analysis scripts.
   - Recommendation: Trace event uses `"usage": mc.usage_raw` — matches Anthropic SDK naming (`Message.usage`). Dataclass can stay `usage_raw` to distinguish from the aggregated fields.

4. **On Windows, does text-mode line-buffering actually flush per-line?**
   - What we know: Python docs say `buffering=1` means line buffering, only meaningful in text mode. Works on POSIX reliably.
   - What's unclear: Windows CRT line buffering on text streams is historically flaky.
   - Recommendation: Always follow with `f.flush(); os.fsync()`. Line buffering is belt, fsync is suspenders. Don't rely on one.

5. **Will `resp.usage.model_dump()` fail on pydantic v1?**
   - What we know: Anthropic SDK 0.39+ uses pydantic v2; `model_dump()` is v2-only. Project pins `anthropic>=0.96`.
   - What's unclear: Whether transitive pydantic version is v2 (it is, for anthropic 0.96+).
   - Recommendation: Defensive fallback in `call()` (`try: model_dump() except AttributeError: dict(__dict__)`) is cheap insurance.

## Sources

### Primary (HIGH confidence)

- `.planning/research/SUMMARY.md` — phase 1 scope and gaps identified
- `.planning/research/PITFALLS.md` — Pitfalls 2, 3, 6, 11 map directly to this phase
- `.planning/research/ARCHITECTURE.md` — component responsibilities (what may/may not change)
- `.planning/ROADMAP.md` — Phase 1 success criteria (the five bullets)
- `.planning/REQUIREMENTS.md` — 34 phase-1 requirement IDs
- `src/harness_eng/trace.py` — current committed state (verified: no `schema_version`, no `fsync`, but has `flush`)
- `src/harness_eng/grader.py` — current committed state (verified: `.lower()`, no NFC, `\s` regex)
- `src/harness_eng/model.py` — current committed state (verified: `Anthropic()` with no kwargs, drops cache fields)
- `src/harness_eng/harnesses/base.py` — current committed state (verified: `run_start`/`run_end` invariant already holds via try/except + finally-equivalent structure in `with Tracer`)
- `tests/test_*.py` — verified existing test inventory (grader, seal, registry, tasks, tools, cost_estimator)
- [Python docs: os.fsync](https://docs.python.org/3/library/os.html#os.fsync) — confirmed Windows behavior (`_commit()`), flush-before-fsync requirement
- Python stdlib: `unicodedata.normalize` is pure and locale-independent (table-driven; no `locale` module coupling)
- Python stdlib: `str.casefold()` is specified by Unicode caseless-match algorithm (language-independent)

### Secondary (MEDIUM confidence)

- [Anthropic SDK Python GitHub](https://github.com/anthropics/anthropic-sdk-python) — `max_retries` is a documented constructor kwarg; `Message.usage` exposes `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` in pydantic-v2 model
- WebFetch verified SDK constructor signature and usage fields from the repo's README

### Tertiary (LOW confidence)

- None — all load-bearing claims verified against committed source or stdlib docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all primitives are stdlib; Anthropic SDK kwargs verified via official repo
- Architecture: HIGH — reading committed source directly, not inferring
- Pitfalls: HIGH — Unicode/locale and fsync pitfalls are well-established; SDK usage-field omissions verified against SDK docs

**Research date:** 2026-04-23
**Valid until:** 2026-07-23 (90 days; stable stdlib and SDK contract — no fast-moving surfaces)
