"""TOOL_WHITELIST assertions on every harness + runtime enforcement in _step_model."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from harness_eng.harnesses import HARNESSES
from harness_eng.harnesses.base import ToolAllowlistViolation, _Usage


EXPECTED = {
    "single_shot": {"submit_answer"},
    "react": {"read_html", "css_select", "extract_text", "submit_answer"},
    "plan_execute": {"css_select", "extract_text", "submit_answer"},
    "reflexion": {"read_html", "css_select", "extract_text", "submit_answer"},
    "minimal": {"css_select", "submit_answer"},
}


def test_every_harness_declares_whitelist():
    for name, cls in HARNESSES.items():
        assert isinstance(cls.TOOL_WHITELIST, frozenset), f"{name} TOOL_WHITELIST not frozenset"
        assert cls.TOOL_WHITELIST == frozenset(EXPECTED[name]), (
            f"{name} whitelist drift: {cls.TOOL_WHITELIST} vs expected {EXPECTED[name]}"
        )


def test_minimal_lacks_read_html_and_extract_text():
    """Structural, not prompt-level: minimal cannot see raw HTML."""
    cls = HARNESSES["minimal"]
    assert "read_html" not in cls.TOOL_WHITELIST
    assert "extract_text" not in cls.TOOL_WHITELIST


def test_step_model_raises_on_extra_tool(monkeypatch):
    """Passing a tool outside the whitelist to _step_model raises ToolAllowlistViolation."""
    harness = HARNESSES["minimal"]()
    usage = _Usage()
    tracer = MagicMock()
    tools = [
        {"name": "css_select", "input_schema": {}},
        {"name": "read_html", "input_schema": {}},  # NOT in minimal's whitelist
    ]
    with pytest.raises(ToolAllowlistViolation) as exc_info:
        harness._step_model(system="sys", messages=[], tools=tools, tracer=tracer, usage=usage)
    assert "read_html" in str(exc_info.value)


def test_step_model_accepts_subset_of_whitelist(monkeypatch):
    """Passing a strict subset of the whitelist is fine."""
    from harness_eng.harnesses import base as base_module
    from harness_eng.model import ModelCall

    def fake_call(system, messages, tools):
        return ModelCall(
            input_tokens=1, output_tokens=1, latency_s=0.0,
            stop_reason="end_turn", content=[], usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)

    harness = HARNESSES["react"]()
    usage = _Usage()
    tracer = MagicMock()
    tools = [{"name": "css_select", "input_schema": {}}]  # subset of react's whitelist
    mc = harness._step_model(system="sys", messages=[], tools=tools, tracer=tracer, usage=usage)
    assert mc.input_tokens == 1
