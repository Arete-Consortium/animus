"""Exercise evaluation commands with local fixtures, real scoring and stored-run comparisons."""

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from animus_forge.cli.commands import eval_cmd


@pytest.fixture
def store(monkeypatch):
    value = MagicMock()
    value.record_run.return_value = "fixture-run-id"
    value.feed_to_outcome_tracker.return_value = 1
    monkeypatch.setattr("animus_forge.evaluation.store.get_eval_store", lambda: value)
    # All "live" branches use injected local providers; never read account credentials.
    monkeypatch.setattr(eval_cmd, "_ensure_provider_for_model", lambda model: None)
    return value


@pytest.fixture
def suite(tmp_path):
    (tmp_path / "fixture.yaml").write_text(
        yaml.safe_dump(
            dict(
                name="fixture",
                threshold=0.8,
                tags=["domain:test", "role:planner"],
                metrics=[{"type": "exact_match"}],
                cases=[dict(name="answer", input="question", expected="answer")],
                description="Local fixture",
            )
        )
    )
    (tmp_path / "rubric.yaml").write_text(
        yaml.safe_dump(
            dict(
                name="rubric",
                version="1.0",
                dims=[dict(name="correctness", metric="ExactMatchMetric", weight=1)],
            )
        )
    )
    return tmp_path


def invoke_run(suite, *options):
    return CliRunner().invoke(
        eval_cmd.eval_app, ["run", "fixture", "--suites-dir", str(suite), *options]
    )


def test_missing_suite_lists_available_without_running(store, suite):
    result = CliRunner().invoke(
        eval_cmd.eval_app, ["run", "missing", "--mock", "--suites-dir", str(suite)]
    )
    assert result.exit_code == 1 and "not found" in result.output and "fixture" in result.output
    store.record_run.assert_not_called()


@pytest.mark.parametrize(
    "options,message",
    [
        (["--mock", "--adapter", "fixture:answer"], "mutually exclusive"),
        (["--adapter", "invalid"], "Invalid --adapter"),
        (["--adapter", "missing_fixture_module:answer"], "Could not load adapter"),
        (["--mock", "--rubric", "missing"], "Rubric error"),
    ],
)
def test_invalid_run_configuration_is_actionable(store, suite, options, message):
    result = invoke_run(suite, *options, "--rubrics-dir", str(suite))
    assert result.exit_code == 1 and message in result.output
    store.record_run.assert_not_called()


def test_provider_initialization_failure_is_nonzero(store, suite, monkeypatch):
    def unavailable():
        raise RuntimeError("fixture provider unavailable")

    monkeypatch.setattr("animus_forge.providers.get_provider", unavailable)
    result = invoke_run(suite, "--model", "fixture-model")
    assert result.exit_code == 1 and "Failed to initialize provider" in result.output


@pytest.mark.parametrize("answer,exit_code", [("answer", 0), ("wrong", 1)])
def test_adapter_scoring_and_rubric_are_persisted_and_exported(
    store, suite, monkeypatch, answer, exit_code
):
    adapter = ModuleType("fixture_eval_adapter")
    adapter.respond = lambda prompt: answer
    monkeypatch.setitem(sys.modules, "fixture_eval_adapter", adapter)
    provider = MagicMock()
    provider.config.default_model = "local-fixture"
    monkeypatch.setattr("animus_forge.providers.get_provider", lambda: provider)
    output = suite / "report.json"
    result = invoke_run(
        suite,
        "--adapter",
        "fixture_eval_adapter:respond",
        "--rubric",
        "rubric",
        "--rubrics-dir",
        str(suite),
        "--model",
        "fixture-model",
        "--prompt-version",
        "test-v1",
        "--output",
        str(output),
    )
    assert result.exit_code == exit_code, result.output
    assert json.loads(output.read_text())
    saved = store.record_run.call_args.kwargs
    assert (
        saved["agent_role"] == "planner"
        and saved["run_mode"] == "adapter:fixture_eval_adapter:respond"
    )
    assert saved["rubric_name"] == "rubric" and saved["prompt_version"] == "test-v1"
    assert saved["result"].results[0].rubric_band == ("A" if exit_code == 0 else "F")
    assert "Run stored" in result.output and "Fed 1 outcomes" in result.output


def test_unavailable_judge_warns_but_deterministic_rubric_still_runs(store, suite, monkeypatch):
    adapter = ModuleType("fixture_eval_adapter")
    adapter.respond = lambda prompt: "answer"
    monkeypatch.setitem(sys.modules, "fixture_eval_adapter", adapter)

    def unavailable():
        raise RuntimeError("fixture judge unavailable")

    monkeypatch.setattr("animus_forge.providers.get_provider", unavailable)
    store.record_run.side_effect = RuntimeError("fixture storage unavailable")
    result = invoke_run(
        suite,
        "--adapter",
        "fixture_eval_adapter:respond",
        "--rubric",
        "rubric",
        "--rubrics-dir",
        str(suite),
    )
    assert result.exit_code == 0, result.output
    assert "judge provider unavailable" in result.output
    assert "Could not store results" in result.output


def stored_run(run_id, score):
    return dict(
        id=run_id,
        suite_name="fixture",
        model="fixture-model",
        rubric_name="fixture",
        rubric_version="1",
        prompt_version="v1",
        avg_score=score,
        pass_rate=score,
        total_cost_usd=score / 100,
        duration_ms=score * 100,
        total_cases=20,
        case_results=[
            dict(
                case_name=f"case-{i}",
                status="passed" if score > 0.5 else "failed",
                score=score,
                failure_mode=None if score > 0.5 else "wrong_answer",
                content_failure_modes=[] if score > 0.5 else ["F4_too_generic"],
            )
            for i in range(20)
        ],
    )


@pytest.mark.parametrize(
    "scores,exit_code,verdict",
    [((0.2, 0.9), 0, "IMPROVEMENT"), ((0.9, 0.2), 2, "REGRESSION"), ((0.9, 0.9), 0, "NO-CHANGE")],
)
def test_compare_renders_real_statistics_and_regression_exit(store, scores, exit_code, verdict):
    runs = {"a" * 32: stored_run("a" * 32, scores[0]), "b" * 32: stored_run("b" * 32, scores[1])}
    store.get_run.side_effect = runs.get
    result = CliRunner().invoke(
        eval_cmd.eval_app, ["compare", "a" * 32, "b" * 32, "--bootstrap", "30", "--seed", "7"]
    )
    assert result.exit_code == exit_code, result.output
    assert verdict in result.output and "95% CI" in result.output
    if scores[0] != scores[1]:
        assert "Technical failure" in result.output and "Content-quality failure" in result.output
    else:
        assert "not significant" in result.output


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["prev", "last"], "Fewer than 2 runs"),
        (["a" * 32, "a" * 32], "same run"),
        (["a" * 32, "b" * 32], "not found"),
    ],
)
def test_compare_rejects_missing_or_identical_runs(store, arguments, message):
    store.query_runs.return_value = []
    store.get_run.return_value = None
    result = CliRunner().invoke(eval_cmd.eval_app, ["compare", *arguments])
    assert result.exit_code == 1 and message in result.output


@pytest.mark.parametrize("present", [False, True])
def test_rubrics_discovery_uses_requested_directory(tmp_path, present):
    if present:
        (tmp_path / "test.yaml").write_text(
            yaml.safe_dump(dict(name="fixture-rubric", version="2", dims=[]))
        )
    result = CliRunner().invoke(eval_cmd.eval_app, ["rubrics", "--rubrics-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert ("fixture-rubric" if present else "No rubrics") in result.output
