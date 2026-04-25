"""Control-flow tests: schema violation -> structured error + retry; 3 violations -> schema_validation_exhausted."""
from harness_eng.harnesses import base as base_module
from harness_eng.harnesses.tool_use_with_validation import (
    ToolUseWithValidationHarness, _validate_args, MAX_VALIDATION_RETRIES
)
from harness_eng.model import ModelCall
from harness_eng.tasks.loader import Task


def test_validate_args_valid_passes():
    """css_select with selector arg -> valid."""
    assert _validate_args("css_select", {"selector": ".foo"}) is None


def test_validate_args_missing_required_fails():
    """css_select WITHOUT selector arg -> SCHEMA_VIOLATION."""
    err = _validate_args("css_select", {})
    assert err is not None
    assert "SCHEMA_VIOLATION" in err
    assert "css_select" in err


def test_validate_args_unknown_tool_passes():
    """Unknown tool — validator returns None, dispatch produces its own error."""
    assert _validate_args("nonexistent", {"x": 1}) is None


def test_three_violations_yields_schema_validation_exhausted(monkeypatch):
    """Model emits invalid css_select 3 times -> harness returns stop_reason=schema_validation_exhausted."""
    call_n = {"n": 0}

    def fake_call(system, messages, tools=None, **_kw):
        call_n["n"] += 1
        # Always emit invalid args (missing 'selector')
        return ModelCall(1, 1, 0.0, "tool_use",
            content=[{"type": "tool_use", "id": f"tu{call_n['n']}",
                      "name": "css_select", "input": {}}],
            usage_raw={})

    monkeypatch.setattr(base_module, "model_call", fake_call)
    harness = ToolUseWithValidationHarness()
    task = Task(id="t1", type="html_extract", description="x",
                fields=["title"], expected={"title": "X"},
                html_path="", test_code="", signature="")
    result = harness.run(task, run_id="t")
    assert result.stop_reason == "schema_validation_exhausted"
    # Should have hit MAX_VALIDATION_RETRIES = 3
    assert call_n["n"] >= MAX_VALIDATION_RETRIES


def test_valid_call_proceeds_to_submit(monkeypatch):
    """Model emits valid css_select then submit_answer -> succeeds."""
    call_n = {"n": 0}

    def fake_call(system, messages, tools=None, **_kw):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return ModelCall(1, 1, 0.0, "tool_use",
                content=[{"type": "tool_use", "id": "tu1", "name": "css_select",
                          "input": {"selector": "h1"}}],
                usage_raw={})
        return ModelCall(1, 1, 0.0, "tool_use",
            content=[{"type": "tool_use", "id": "tu2", "name": "submit_answer",
                      "input": {"fields": {"title": "X"}}}],
            usage_raw={})

    monkeypatch.setattr(base_module, "model_call", fake_call)
    monkeypatch.setattr("harness_eng.harnesses.tool_use_with_validation.Harness._dispatch_tool",
        lambda self, name, args, ctx, tracer, usage: "match", raising=False)
    harness = ToolUseWithValidationHarness()
    task = Task(id="t1", type="html_extract", description="x",
                fields=["title"], expected={"title": "X"},
                html_path="", test_code="", signature="")
    result = harness.run(task, run_id="t")
    assert result.stop_reason == "submitted"
    assert result.predicted == {"title": "X"}
