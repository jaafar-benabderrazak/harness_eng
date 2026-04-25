"""Regression: Anthropic client constructed with max_retries=0 and ModelCall.usage_raw populated.

These tests exercise the Anthropic backend path specifically, so they pin
HARNESS_BACKEND=anthropic via a CONFIG swap even if the default is now ollama.
"""
from __future__ import annotations

import sys
import types
from dataclasses import replace

from harness_eng import model as model_module


def _force_anthropic_backend(monkeypatch):
    new_model = replace(model_module.CONFIG.model, backend="anthropic", name="claude-sonnet-4-6")
    new_cfg = replace(model_module.CONFIG, model=new_model)
    monkeypatch.setattr(model_module, "CONFIG", new_cfg)


def test_client_constructed_with_max_retries_zero(monkeypatch):
    """When _get_client instantiates the client, it passes max_retries=0."""
    _force_anthropic_backend(monkeypatch)
    captured: dict = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setattr(model_module, "_client", None)
    model_module._get_client()
    assert captured.get("max_retries") == 0, f"expected max_retries=0, got {captured!r}"


def test_usage_raw_populated(monkeypatch):
    """ModelCall.usage_raw contains every field returned by resp.usage.model_dump()."""
    _force_anthropic_backend(monkeypatch)
    class FakeUsage:
        input_tokens = 100
        output_tokens = 50

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


def test_call_uses_config_temperature_by_default(monkeypatch):
    """No temperature kwarg → CONFIG.model.temperature."""
    _force_anthropic_backend(monkeypatch)
    captured: dict = {}

    class FakeUsage:
        input_tokens = 1
        output_tokens = 1

        def model_dump(self):
            return {"input_tokens": 1, "output_tokens": 1}

    class FakeResp:
        usage = FakeUsage()
        stop_reason = "end_turn"
        content = []

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return FakeResp()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(model_module, "_client", FakeClient())
    model_module.call(system="s", messages=[{"role": "user", "content": "x"}])
    assert captured["temperature"] == model_module.CONFIG.model.temperature


def test_call_temperature_kwarg_overrides_config(monkeypatch):
    """temperature=0.7 overrides CONFIG.model.temperature for that call."""
    _force_anthropic_backend(monkeypatch)
    captured: dict = {}

    class FakeUsage:
        input_tokens = 1
        output_tokens = 1

        def model_dump(self):
            return {"input_tokens": 1, "output_tokens": 1}

    class FakeResp:
        usage = FakeUsage()
        stop_reason = "end_turn"
        content = []

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return FakeResp()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(model_module, "_client", FakeClient())
    model_module.call(
        system="s",
        messages=[{"role": "user", "content": "x"}],
        temperature=0.7,
    )
    assert captured["temperature"] == 0.7
