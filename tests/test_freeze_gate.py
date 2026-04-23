"""Freeze-gate tests: the runner must refuse to execute if gated files have drifted."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from harness_eng import runner as runner_module


def _fake_run_factory(stdout: str = "", returncode: int = 0):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)
    return _fake_run


def test_freeze_gate_raises_on_diverged_gated_file(monkeypatch):
    monkeypatch.delenv("HARNESS_ENG_SKIP_FREEZE_GATE", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(
        stdout="src/harness_eng/harnesses/react.py\nsrc/harness_eng/tools.py\n",
        returncode=0,
    ))
    with pytest.raises(runner_module.FreezeGateError) as exc_info:
        runner_module.check_freeze_gate()
    assert "react.py" in str(exc_info.value)
    assert "tools.py" in str(exc_info.value)


def test_freeze_gate_passes_on_clean_diff(monkeypatch):
    monkeypatch.delenv("HARNESS_ENG_SKIP_FREEZE_GATE", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(stdout="", returncode=0))
    runner_module.check_freeze_gate()


def test_freeze_gate_raises_when_tag_missing(monkeypatch):
    monkeypatch.delenv("HARNESS_ENG_SKIP_FREEZE_GATE", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(stdout="", returncode=128))
    with pytest.raises(runner_module.FreezeGateError) as exc_info:
        runner_module.check_freeze_gate()
    assert "tag not found" in str(exc_info.value)


def test_freeze_gate_bypasses_with_env_var(monkeypatch):
    monkeypatch.setenv("HARNESS_ENG_SKIP_FREEZE_GATE", "1")
    # Should not raise even if we would otherwise hit an error.
    runner_module.check_freeze_gate()
