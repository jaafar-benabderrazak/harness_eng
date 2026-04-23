"""Harness registry. Keep the order here aligned with the article."""
from __future__ import annotations

from .base import Harness, HarnessResult
from .chain_of_thought import ChainOfThoughtHarness
from .minimal import MinimalHarness
from .plan_execute import PlanExecuteHarness
from .react import ReActHarness
from .reflexion import ReflexionHarness
from .retry_on_fail import RetryOnFailHarness
from .single_shot import SingleShotHarness
from .test_driven import TestDrivenHarness

HARNESSES: dict[str, type[Harness]] = {
    # HTML-extraction baselines (also handle code tasks via dual-payload submit_answer)
    "single_shot": SingleShotHarness,
    "react": ReActHarness,
    "plan_execute": PlanExecuteHarness,
    "reflexion": ReflexionHarness,
    "minimal": MinimalHarness,
    # Code-gen strategies
    "chain_of_thought": ChainOfThoughtHarness,
    "test_driven": TestDrivenHarness,
    "retry_on_fail": RetryOnFailHarness,
}

# Which harnesses apply to each task type. The runner uses this to pick the
# five-harness matrix for each benchmark.
HARNESSES_BY_TASK_TYPE: dict[str, list[str]] = {
    "html_extract": ["single_shot", "react", "plan_execute", "reflexion", "minimal"],
    "code_gen":     ["single_shot", "react", "chain_of_thought", "test_driven", "retry_on_fail"],
}

__all__ = ["Harness", "HarnessResult", "HARNESSES", "HARNESSES_BY_TASK_TYPE"]
