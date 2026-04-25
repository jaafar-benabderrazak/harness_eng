"""Control-flow test: 5 model calls, each with temperature=0.7, per-field majority output."""
from harness_eng.harnesses import base as base_module
from harness_eng.harnesses.self_consistency import (
    SelfConsistencyHarness,
    N_SAMPLES,
    SAMPLE_TEMPERATURE,
    _normalize_code,
)
from harness_eng.model import ModelCall
from harness_eng.tasks.loader import Task


def test_normalize_code_strips_comments():
    """ast.unparse drops comments; whitespace canonicalized."""
    a = "x = 1   # comment\ny = 2"
    b = "x = 1\ny = 2"
    assert _normalize_code(a) == _normalize_code(b)


def test_normalize_code_falls_back_on_syntax_error():
    """Bad syntax -> return raw."""
    bad = "def x(:"
    assert _normalize_code(bad) == bad


def test_self_consistency_makes_n_samples_at_temperature(monkeypatch):
    """Exactly N=5 model calls; each at SAMPLE_TEMPERATURE."""
    captured_temps: list[float | None] = []

    def fake_call(system, messages, tools=None, *, temperature=None):
        captured_temps.append(temperature)
        # Return varying field value: titles A,A,B,A,C -> majority A
        idx = len(captured_temps) - 1
        title = ["A", "A", "B", "A", "C"][idx % 5]
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use", "id": f"tu{idx}", "name": "submit_answer",
                "input": {"fields": {"title": title}},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    # ctx.html() must return SOMETHING — patch the tools.ToolContext.html
    from harness_eng import tools as tools_mod
    monkeypatch.setattr(tools_mod.ToolContext, "html", lambda self: "<html></html>")

    harness = SelfConsistencyHarness()
    task = Task(
        id="t1", type="html_extract", description="x",
        fields=["title"], expected={"title": "A"},
        html_path="any.html", test_code="", signature="",
    )
    result = harness.run(task, run_id="t")
    assert len(captured_temps) == N_SAMPLES, \
        f"expected {N_SAMPLES} calls, got {len(captured_temps)}"
    assert all(t == SAMPLE_TEMPERATURE for t in captured_temps), \
        f"every call must use temperature={SAMPLE_TEMPERATURE}, got {captured_temps}"
    # Per-field majority: 3xA, 1xB, 1xC -> A wins
    assert result.predicted == {"title": "A"}
    assert result.stop_reason == "submitted"


def test_self_consistency_per_field_majority_independent(monkeypatch):
    """Different fields can have different majorities — vote independently per field."""
    counter = {"n": 0}

    def fake_call(system, messages, tools=None, *, temperature=None):
        counter["n"] += 1
        # 5 samples — title majority='X' (3/5), price majority='10' (3/5).
        # Title 'X' wins by 3 votes (X,X,X,Y,Z); price '10' wins by 3 votes (10,10,10,11,12).
        # On sample 4 BOTH fields are wrong simultaneously — but per-field majority resists this.
        title = ["X", "X", "X", "Y", "Z"][counter["n"] - 1]
        price = ["10", "10", "10", "11", "12"][counter["n"] - 1]
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use", "id": f"tu{counter['n']}", "name": "submit_answer",
                "input": {"fields": {"title": title, "price": price}},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    from harness_eng import tools as tools_mod
    monkeypatch.setattr(tools_mod.ToolContext, "html", lambda self: "<html></html>")

    harness = SelfConsistencyHarness()
    task = Task(
        id="t1", type="html_extract", description="x",
        fields=["title", "price"], expected={"title": "X", "price": "10"},
        html_path="any.html", test_code="", signature="",
    )
    result = harness.run(task, run_id="t")
    assert result.predicted == {"title": "X", "price": "10"}


def test_self_consistency_code_uses_ast_normalized_majority(monkeypatch):
    """Code-gen voting collapses whitespace + comment differences via AST normalization."""
    counter = {"n": 0}
    # Three semantically-equal versions (whitespace/comments differ) + two different.
    # AST-normalized form is the same for all three -> they form the majority.
    samples = [
        "def f(x):\n    return x + 1   # plus one\n",
        "def f(x):\n    return x + 1\n",
        "def f(x):    \n    return x+1\n",   # extra spacing
        "def f(x):\n    return x + 2\n",     # WRONG body
        "def f(x):\n    return x - 1\n",     # WRONG body
    ]

    def fake_call(system, messages, tools=None, *, temperature=None):
        idx = counter["n"]
        counter["n"] += 1
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use", "id": f"tu{idx}", "name": "submit_answer",
                "input": {"code": samples[idx]},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    harness = SelfConsistencyHarness()
    task = Task(
        id="t1", type="code_gen", description="add one",
        fields=[], expected={},
        html_path="", test_code="assert f(1) == 2",
        signature="def f(x):",
    )
    result = harness.run(task, run_id="t")
    assert result.stop_reason == "submitted"
    # Winner's normalized form must match the canonical 'return x + 1' body
    assert _normalize_code(result.predicted["code"]) == _normalize_code("def f(x):\n    return x + 1\n")
