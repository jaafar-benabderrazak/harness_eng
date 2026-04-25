"""Control-flow test: replan_triggered event fires after two consecutive NO_MATCH on same selector."""
from __future__ import annotations

from harness_eng.harnesses import base as base_module
from harness_eng.harnesses.react_with_replan import ReActWithReplanHarness
from harness_eng.model import ModelCall
from harness_eng.tasks.loader import Task


def _build_task() -> Task:
    return Task(
        id="t1",
        type="html_extract",
        description="x",
        fields=["title"],
        expected={"title": "X"},
        html_path="",
        test_code="",
        signature="",
    )


def test_replan_triggered_after_two_nomatch_same_selector(monkeypatch):
    """First two model calls emit css_select on '.bogus'; both NO_MATCH; third is the post-replan submit."""
    call_n = {"n": 0}

    def fake_call(system, messages, tools=None, *, temperature=None):
        call_n["n"] += 1
        if call_n["n"] in (1, 2):
            return ModelCall(
                input_tokens=1,
                output_tokens=1,
                latency_s=0.0,
                stop_reason="tool_use",
                content=[
                    {
                        "type": "tool_use",
                        "id": f"tu_{call_n['n']}",
                        "name": "css_select",
                        "input": {"selector": ".bogus"},
                    }
                ],
                usage_raw={},
            )
        # third+: submit
        return ModelCall(
            input_tokens=1,
            output_tokens=1,
            latency_s=0.0,
            stop_reason="tool_use",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_x",
                    "name": "submit_answer",
                    "input": {"fields": {"title": "X"}},
                }
            ],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    # Stub _dispatch_tool so css_select returns NO_MATCH unconditionally
    monkeypatch.setattr(
        "harness_eng.harnesses.react_with_replan.Harness._dispatch_tool",
        lambda self, name, args, ctx, tracer, usage: "NO_MATCH" if name == "css_select" else "X",
        raising=False,
    )

    harness = ReActWithReplanHarness()
    task = _build_task()
    captured_events: list[tuple[str, dict]] = []
    # Capture trace events by monkeypatching Tracer.log
    from harness_eng import trace as trace_mod

    orig = trace_mod.Tracer.log

    def capture(self, ev_type, **kw):
        captured_events.append((ev_type, kw))
        return orig(self, ev_type, **kw)

    monkeypatch.setattr(trace_mod.Tracer, "log", capture)

    harness.run(task, run_id="t")
    assert any(
        ev_type == "replan_triggered" for ev_type, _ in captured_events
    ), "Expected replan_triggered event after two consecutive NO_MATCH on same selector"


def test_no_replan_when_selectors_differ(monkeypatch):
    """Two NO_MATCH on DIFFERENT selectors -> no replan."""
    call_n = {"n": 0}

    def fake_call(system, messages, tools=None, *, temperature=None):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return ModelCall(
                1,
                1,
                0.0,
                "tool_use",
                content=[
                    {
                        "type": "tool_use",
                        "id": "1",
                        "name": "css_select",
                        "input": {"selector": ".a"},
                    }
                ],
                usage_raw={},
            )
        if call_n["n"] == 2:
            return ModelCall(
                1,
                1,
                0.0,
                "tool_use",
                content=[
                    {
                        "type": "tool_use",
                        "id": "2",
                        "name": "css_select",
                        "input": {"selector": ".b"},
                    }
                ],
                usage_raw={},
            )
        return ModelCall(
            1,
            1,
            0.0,
            "tool_use",
            content=[
                {
                    "type": "tool_use",
                    "id": "3",
                    "name": "submit_answer",
                    "input": {"fields": {"title": "X"}},
                }
            ],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    monkeypatch.setattr(
        "harness_eng.harnesses.react_with_replan.Harness._dispatch_tool",
        lambda self, name, args, ctx, tracer, usage: "NO_MATCH" if name == "css_select" else "X",
        raising=False,
    )
    harness = ReActWithReplanHarness()
    task = _build_task()
    captured: list[str] = []
    from harness_eng import trace as trace_mod

    orig = trace_mod.Tracer.log

    def capture(self, ev_type, **kw):
        captured.append(ev_type)
        return orig(self, ev_type, **kw)

    monkeypatch.setattr(trace_mod.Tracer, "log", capture)
    harness.run(task, run_id="t")
    assert "replan_triggered" not in captured, "Replan should NOT fire on different selectors"
