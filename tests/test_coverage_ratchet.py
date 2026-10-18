"""Coverage gate consumes the successful test run's report and fails closed."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "coverage_ratchet", Path(__file__).resolve().parents[1] / "scripts" / "coverage-ratchet.py"
)
ratchet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratchet)


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"kernel": {"allowed": 21.3, "directory": "tests"}}))
    monkeypatch.setattr(ratchet, "BASELINE_FILE", path)
    return path


def test_report_does_not_rerun_tests(monkeypatch, tmp_path, baseline):
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"covered_lines": 3, "num_statements": 10}}))
    monkeypatch.setattr(ratchet, "run_coverage", lambda *a: pytest.fail("must not rerun pytest"))
    assert ratchet.main(["--report", str(report), "kernel"]) == 0


@pytest.mark.parametrize(
    "content", ["invalid", "{}", '{"totals": {"covered_lines": 0, "num_statements": 0}}']
)
def test_invalid_report_fails(tmp_path, baseline, content):
    report = tmp_path / "coverage.json"
    report.write_text(content)
    assert ratchet.main(["--report", str(report), "kernel"]) == 1


def test_missing_report_fails(tmp_path, baseline):
    assert ratchet.main(["--report", str(tmp_path / "absent.json"), "kernel"]) == 1


def test_below_existing_floor_fails(tmp_path, baseline):
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"covered_lines": 2, "num_statements": 10}}))
    assert ratchet.main(["--report", str(report), "kernel"]) == 1
