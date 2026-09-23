"""Operator-facing skill reports preserve filters, totals and missing-data signals."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from animus_forge.cli.commands import skills


@pytest.fixture
def services(monkeypatch):
    db, agg, ab = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr("animus_forge.state.database.get_database", lambda: db)
    monkeypatch.setattr(
        "animus_forge.skills.evolver.metrics.SkillMetricsAggregator", lambda backend: agg
    )
    monkeypatch.setattr(
        "animus_forge.skills.evolver.ab_test.ABTestManager", lambda backend, metrics: ab
    )
    db.fetchall.return_value = []
    agg.get_all_skill_metrics.return_value = []
    agg.get_skill_metrics.return_value = None
    ab.get_active_experiments.return_value = []
    return db, agg, ab


def metric(name, trend="stable"):
    return SimpleNamespace(
        skill_name=name,
        skill_version="2",
        total_invocations=10,
        success_rate=0.8,
        avg_quality_score=0.75,
        avg_cost_usd=0.01,
        total_cost_usd=0.1,
        avg_latency_ms=123,
        trend=trend,
    )


@pytest.mark.parametrize(
    "command,message",
    [
        (["metrics"], "No skill metrics"),
        (["experiments"], "No active experiments"),
        (["versions", "missing"], "No versions"),
        (["deprecations"], "No skills flagged"),
        (["trend", "missing"], "No metrics"),
    ],
)
def test_empty_reports_are_successful_and_explicit(services, command, message):
    result = CliRunner().invoke(skills.skills_app, command)
    assert result.exit_code == 0, result.output
    assert message in result.output


def test_metrics_filters_case_insensitively_and_totals_only_selected_skills(services):
    _, agg, _ = services
    agg.get_all_skill_metrics.return_value = [metric("Hunter"), metric("Other")]
    result = CliRunner().invoke(skills.skills_app, ["metrics", "--skill", "HUNT", "--days", "7"])
    assert result.exit_code == 0, result.output
    assert "Hunter" in result.output and "Other" not in result.output
    assert "Total cost: $0.10" in result.output
    agg.get_all_skill_metrics.assert_called_once_with(days=7)


@pytest.mark.parametrize("trend", ["improving", "declining", "stable", "unknown"])
def test_trend_report_retains_metrics_and_category(services, trend):
    _, agg, _ = services
    agg.get_skill_metrics.return_value = metric("Hunter", trend)
    agg.get_skill_trend.return_value = trend
    result = CliRunner().invoke(skills.skills_app, ["trend", "Hunter", "--days", "9"])
    assert result.exit_code == 0, result.output
    assert "80.0%" in result.output and "123ms" in result.output and trend in result.output
    agg.get_skill_metrics.assert_called_once_with("Hunter", days=9)


def test_experiments_show_active_split_and_versions(services):
    _, _, ab = services
    ab.get_active_experiments.return_value = [
        dict(
            id="abcdefgh-more",
            skill_name="Hunter",
            control_version="1",
            variant_version="2",
            traffic_split=0.25,
            start_date="2026-09-22T12:00:00",
        )
    ]
    result = CliRunner().invoke(skills.skills_app, ["experiments"])
    assert result.exit_code == 0, result.output
    assert all(v in result.output for v in ["abcdefgh", "Hunter", "v1", "v2", "25%"])


def test_versions_pass_user_input_as_bound_parameters(services):
    db, _, _ = services
    db.fetchall.return_value = [
        dict(
            version="2",
            previous_version=None,
            change_type="fix",
            change_description="Correct retrieval",
            created_at="2026-09-22",
        )
    ]
    name = "hunter'; DROP TABLE skill_versions;--"
    result = CliRunner().invoke(skills.skills_app, ["versions", name, "--limit", "3"])
    assert result.exit_code == 0, result.output
    sql, params = db.fetchall.call_args.args
    assert name not in sql and params == (name, 3)
    assert "Correct retrieval" in result.output


@pytest.mark.parametrize("status", ["flagged", "deprecated", "retired", "unknown"])
def test_deprecation_report_shows_lifecycle_and_missing_replacement(services, status):
    db, _, _ = services
    db.fetchall.return_value = [
        dict(
            skill_name="Hunter",
            status=status,
            reason="Low success",
            success_rate_at_flag=0.2,
            replacement_skill=None,
            flagged_at="2026-09-22",
        )
    ]
    result = CliRunner().invoke(skills.skills_app, ["deprecations"])
    assert result.exit_code == 0, result.output
    assert status in result.output and "20%" in result.output and "Low success" in result.output
