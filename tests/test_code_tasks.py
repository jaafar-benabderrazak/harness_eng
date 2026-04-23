"""Code-generation task type: loader + grader + new harnesses registered."""
from __future__ import annotations

from harness_eng.grader import grade_code
from harness_eng.harnesses import HARNESSES, HARNESSES_BY_TASK_TYPE
from harness_eng.tasks.loader import load_tasks


def test_code_tasks_load():
    tasks = load_tasks(task_type="code_gen")
    assert len(tasks) == 5
    ids = {t.id for t in tasks}
    assert ids == {"fizzbuzz", "fibonacci", "is_anagram", "binary_search", "word_count"}
    for t in tasks:
        assert t.type == "code_gen"
        assert t.signature.startswith("def ")
        assert "def test_" in t.test_code
        assert t.reference_solution  # author's ref solution is present


def test_reference_solutions_pass_their_own_tests():
    """Each task's reference_solution must pass its own test_code — sanity of the task design."""
    for t in load_tasks(task_type="code_gen"):
        r = grade_code(t.reference_solution, t.test_code)
        assert r.success, f"reference solution for {t.id} failed: per_field={r.per_field}"
        assert r.field_accuracy == 1.0


def test_grade_code_fails_on_empty_submission():
    r = grade_code("", "def test_a():\n    assert 1==1\n")
    assert r.success is False
    assert r.field_accuracy == 0.0


def test_grade_code_partial_pass():
    """Partial implementation: some tests pass, some fail."""
    tasks = {t.id: t for t in load_tasks(task_type="code_gen")}
    # Broken fizzbuzz: forgets the Fizz case
    broken = "def fizzbuzz(n):\n    return [str(i) if i % 5 else 'Buzz' for i in range(1, n+1)]"
    r = grade_code(broken, tasks["fizzbuzz"].test_code)
    assert r.success is False
    assert 0.0 < r.field_accuracy < 1.0


def test_new_harnesses_registered():
    for name in ["chain_of_thought", "test_driven", "retry_on_fail"]:
        assert name in HARNESSES


def test_code_gen_harness_lineup():
    """HARNESSES_BY_TASK_TYPE['code_gen'] references existing harnesses and is size 5."""
    lineup = HARNESSES_BY_TASK_TYPE["code_gen"]
    assert len(lineup) == 5
    for name in lineup:
        assert name in HARNESSES
