from harness_eng.harnesses import HARNESSES


def test_all_harnesses_registered():
    assert set(HARNESSES.keys()) == {
        # HTML-extraction family
        "single_shot", "react", "plan_execute", "reflexion", "minimal",
        # Code-gen family
        "chain_of_thought", "test_driven", "retry_on_fail",
    }


def test_harnesses_instantiate():
    for name, cls in HARNESSES.items():
        inst = cls()
        assert inst.name == name


def test_no_harness_imports_anthropic_directly():
    """The whole experiment requires that only model.py imports anthropic."""
    import importlib
    import inspect
    for name in HARNESSES:
        mod = importlib.import_module(f"harness_eng.harnesses.{name}")
        src = inspect.getsource(mod)
        assert "import anthropic" not in src, f"{name} imports anthropic directly"
        assert "from anthropic" not in src, f"{name} imports anthropic directly"
