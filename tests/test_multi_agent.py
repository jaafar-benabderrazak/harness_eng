"""Control-flow test: multi_agent emits 3 distinct system prompts (planner / executor / critic)."""
from harness_eng.harnesses import base as base_module
from harness_eng.harnesses.multi_agent import MultiAgentHarness
from harness_eng.model import ModelCall
from harness_eng.tasks.loader import Task


def test_multi_agent_runs_three_distinct_systems(monkeypatch):
    seen_systems: list[str] = []

    def fake_call(system, messages, tools=None, **_kw):
        seen_systems.append(system)
        # Call 1 = planner (text). Call 2+ = executor (submit_answer). Call N = critic.
        if len(seen_systems) == 1:
            return ModelCall(
                1, 1, 0.0, "end_turn",
                content=[{"type": "text", "text": "1. inspect h1\n2. submit\nHANDOFF: do it"}],
                usage_raw={},
            )
        # subsequent calls — submit_answer
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use",
                "id": "tu_x",
                "name": "submit_answer",
                "input": {"fields": {"title": "X"}},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    harness = MultiAgentHarness()
    task = Task(
        id="t1", type="html_extract", description="x",
        fields=["title"], expected={"title": "X"},
        html_path="", test_code="", signature="",
    )
    result = harness.run(task, run_id="t")
    assert result.stop_reason == "submitted"
    assert any("PLANNER" in s for s in seen_systems)
    assert any("EXECUTOR" in s for s in seen_systems)
    assert any("CRITIC" in s for s in seen_systems)
    distinct = {s for s in seen_systems}
    assert len(distinct) >= 3, f"expected >=3 distinct systems, got {len(distinct)}"


def test_multi_agent_planner_runs_before_executor(monkeypatch):
    """Order matters: planner must be the FIRST call."""
    seen_systems: list[str] = []

    def fake_call(system, messages, tools=None, **_kw):
        seen_systems.append(system)
        if len(seen_systems) == 1:
            return ModelCall(
                1, 1, 0.0, "end_turn",
                content=[{"type": "text", "text": "plan"}], usage_raw={},
            )
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use", "id": "x", "name": "submit_answer",
                "input": {"fields": {"title": "X"}},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    harness = MultiAgentHarness()
    task = Task(
        id="t1", type="html_extract", description="x", fields=["title"],
        expected={"title": "X"}, html_path="", test_code="", signature="",
    )
    harness.run(task, run_id="t")
    assert "PLANNER" in seen_systems[0], f"first call was not planner: {seen_systems[0][:60]}"


def test_multi_agent_isolated_histories(monkeypatch):
    """Planner messages should NOT appear in executor messages list."""
    captured_messages: list[list] = []

    def fake_call(system, messages, tools=None, **_kw):
        # Snapshot whether each message's content is a plain string or block-list.
        captured_messages.append([
            m.get("content") if isinstance(m.get("content"), str) else "BLOCKS"
            for m in messages
        ])
        if len(captured_messages) == 1:
            return ModelCall(
                1, 1, 0.0, "end_turn",
                content=[{"type": "text", "text": "1. step\nHANDOFF: do"}], usage_raw={},
            )
        return ModelCall(
            1, 1, 0.0, "tool_use",
            content=[{
                "type": "tool_use", "id": "x", "name": "submit_answer",
                "input": {"fields": {"title": "X"}},
            }],
            usage_raw={},
        )

    monkeypatch.setattr(base_module, "model_call", fake_call)
    harness = MultiAgentHarness()
    task = Task(
        id="t1", type="html_extract", description="x", fields=["title"],
        expected={"title": "X"}, html_path="", test_code="", signature="",
    )
    harness.run(task, run_id="t")
    # Planner's messages list (call 1) should be 1 user msg
    assert len(captured_messages[0]) == 1
    # Executor's messages list (call 2) — separate list, has the handoff prepended,
    # but should NOT have planner's text-only response in it
    exec_msgs = captured_messages[1]
    # The user message for executor includes Handoff text (the only thing copied over)
    assert any(isinstance(m, str) and "Handoff" in m for m in exec_msgs), \
        "executor's first message should contain a rendered Handoff"
