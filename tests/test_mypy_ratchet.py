"""The type gate must never turn a checker failure into a passing count."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "mypy_ratchet", Path(__file__).resolve().parents[1] / "scripts" / "mypy-ratchet.py"
)
ratchet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratchet)


@pytest.mark.parametrize("code,output", [(2, "usage error"), (1, "internal failure"), (-9, "")])
def test_checker_failure_is_not_zero_errors(monkeypatch, code, output):
    monkeypatch.setattr(
        ratchet.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], code, output, ""),
    )
    with pytest.raises(RuntimeError):
        ratchet.count_errors("src")


def test_counts_error_lines_and_preserves_report(monkeypatch, tmp_path):
    output = "a.py:1: error: wrong type [arg-type]\na.py:1: note: detail\n"
    monkeypatch.setattr(
        ratchet.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 1, output, "")
    )
    report = tmp_path / "report.txt"
    assert ratchet.count_errors("src", report) == 1
    assert report.read_text() == output


def test_no_arguments_cannot_rebaseline(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"core": {"allowed": 1, "directory": "src"}}')
    monkeypatch.setattr(ratchet, "BASELINE_FILE", baseline)
    before = baseline.read_bytes()
    assert ratchet.main([]) == 1
    assert baseline.read_bytes() == before


def test_init_cannot_increase_allowance(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"core": {"allowed": 1, "directory": "src"}}')
    monkeypatch.setattr(ratchet, "BASELINE_FILE", baseline)
    monkeypatch.setattr(ratchet, "count_errors", lambda *a: 2)
    assert ratchet.main(["--init"]) == 1
    assert json.loads(baseline.read_text())["core"]["allowed"] == 1


def test_unknown_package_fails(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}")
    monkeypatch.setattr(ratchet, "BASELINE_FILE", baseline)
    assert ratchet.main(["unknown"]) == 1
