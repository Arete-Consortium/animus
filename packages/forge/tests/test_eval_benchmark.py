"""Tests for the agent quality benchmarking system.

Covers: SuiteLoader, EvalStore, MockProvider, CLI commands, integration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from animus_forge.evaluation.base import (
    AgentEvaluator,
    EvalCase,
    EvalResult,
    EvalStatus,
    EvalSuite,
)
from animus_forge.evaluation.loader import METRIC_MAP, SuiteLoader, _build_metric
from animus_forge.evaluation.metrics import ContainsMetric, LengthMetric
from animus_forge.evaluation.runner import EvalRunner, SuiteResult
from animus_forge.evaluation.store import EvalStore, get_eval_store, reset_eval_store
from animus_forge.providers.mock_provider import MockProvider

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def tmp_suites_dir(tmp_path: Path) -> Path:
    """Create a temporary suites directory with a sample YAML."""
    suites_dir = tmp_path / "eval_suites"
    suites_dir.mkdir()

    sample = {
        "name": "test_suite",
        "description": "Test suite for unit tests",
        "agent_role": "tester",
        "threshold": 0.5,
        "tags": ["test"],
        "metrics": [
            {"type": "contains", "case_sensitive": False},
            {"type": "length", "min_length": 10, "max_length": 1000},
        ],
        "cases": [
            {
                "name": "case_hello",
                "input": "Say hello",
                "expected": ["hello", "hi"],
                "metadata": {"difficulty": "easy"},
            },
            {
                "name": "case_math",
                "input": "What is 2+2?",
                "expected": ["4"],
                "metadata": {"difficulty": "easy"},
            },
        ],
    }

    import yaml

    (suites_dir / "test_suite.yaml").write_text(yaml.dump(sample))
    return suites_dir


@pytest.fixture()
def memory_backend():
    """Create an in-memory SQLite backend for testing."""
    from animus_forge.state.backends import SQLiteBackend

    backend = SQLiteBackend(":memory:")

    # Apply eval migrations (012 = base, 018 = rubric/failure/cost, 019 = content failures)
    migrations_dir = Path(__file__).parent.parent / "migrations"
    applied_any = False
    for name in (
        "012_eval_results.sql",
        "018_eval_rubric_failure.sql",
        "019_eval_content_failures.sql",
    ):
        path = migrations_dir / name
        if path.exists():
            backend.executescript(path.read_text())
            applied_any = True
    if not applied_any:
        # Inline schema for CI — kept in sync with migrations 012 + 018
        backend.executescript(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY,
                suite_name TEXT NOT NULL,
                agent_role TEXT,
                model TEXT,
                run_mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                total_cases INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0.0,
                pass_rate REAL DEFAULT 0.0,
                score_variance REAL DEFAULT 0.0,
                total_tokens INTEGER DEFAULT 0,
                metadata TEXT,
                rubric_name TEXT,
                rubric_version TEXT,
                config_hash TEXT,
                prompt_version TEXT,
                total_cost_usd REAL DEFAULT 0.0
            );
            CREATE INDEX IF NOT EXISTS idx_eval_runs_dedup
            ON eval_runs(suite_name, agent_role, model, run_mode, completed_at DESC);
            CREATE TABLE IF NOT EXISTS eval_case_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                case_name TEXT NOT NULL,
                status TEXT NOT NULL,
                score REAL NOT NULL,
                output TEXT,
                error TEXT,
                latency_ms REAL DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                metrics_json TEXT,
                failure_mode TEXT,
                rubric_band TEXT,
                rubric_scores_json TEXT,
                cost_usd REAL DEFAULT 0.0,
                content_failure_modes_json TEXT,
                FOREIGN KEY (run_id) REFERENCES eval_runs(id) ON DELETE CASCADE
            );
            """
        )
    return backend


@pytest.fixture()
def eval_store(memory_backend) -> EvalStore:
    """Create an EvalStore with in-memory backend."""
    return EvalStore(memory_backend)


@pytest.fixture()
def sample_suite_result() -> SuiteResult:
    """Create a sample SuiteResult for testing."""
    suite = EvalSuite(name="test_suite", threshold=0.5)
    case1 = EvalCase(input="test1", name="case_pass")
    case2 = EvalCase(input="test2", name="case_fail")
    case3 = EvalCase(input="test3", name="case_error")

    results = [
        EvalResult(
            case=case1,
            status=EvalStatus.PASSED,
            score=0.9,
            output="good output",
            metrics={"contains": 1.0, "length": 0.8},
            latency_ms=100,
            tokens_used=50,
        ),
        EvalResult(
            case=case2,
            status=EvalStatus.FAILED,
            score=0.3,
            output="bad output",
            metrics={"contains": 0.0, "length": 0.6},
            latency_ms=150,
            tokens_used=60,
        ),
        EvalResult(
            case=case3,
            status=EvalStatus.ERROR,
            score=0.0,
            output=None,
            error="Something broke",
            latency_ms=10,
            tokens_used=0,
        ),
    ]

    return SuiteResult(
        suite=suite,
        results=results,
        passed=1,
        failed=1,
        errors=1,
        total_score=0.4,
        duration_ms=260,
    )


# =============================================================================
# TestSuiteLoader
# =============================================================================


class TestSuiteLoader:
    """Tests for the SuiteLoader."""

    def test_load_suite(self, tmp_suites_dir: Path) -> None:
        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")

        assert suite.name == "test_suite"
        assert len(suite.cases) == 2
        assert len(suite.metrics) == 2
        assert suite.threshold == 0.5
        assert suite.cases[0].name == "case_hello"

    def test_load_suite_has_agent_role_tag(self, tmp_suites_dir: Path) -> None:
        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")
        assert "role:tester" in suite.tags

    def test_load_suite_metrics_instantiated(self, tmp_suites_dir: Path) -> None:
        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")

        metric_names = [m.name for m in suite.metrics]
        assert "contains" in metric_names
        assert "length" in metric_names

    def test_load_suite_not_found(self, tmp_suites_dir: Path) -> None:
        loader = SuiteLoader(tmp_suites_dir)
        with pytest.raises(FileNotFoundError):
            loader.load_suite("nonexistent")

    def test_list_suites(self, tmp_suites_dir: Path) -> None:
        loader = SuiteLoader(tmp_suites_dir)
        suites = loader.list_suites()

        assert len(suites) == 1
        assert suites[0]["name"] == "test_suite"
        assert suites[0]["agent_role"] == "tester"
        assert suites[0]["cases_count"] == 2
        assert suites[0]["threshold"] == 0.5

    def test_list_suites_empty_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        loader = SuiteLoader(empty_dir)
        assert loader.list_suites() == []

    def test_list_suites_nonexistent_dir(self, tmp_path: Path) -> None:
        loader = SuiteLoader(tmp_path / "no_such_dir")
        assert loader.list_suites() == []

    def test_metric_map_keys(self) -> None:
        expected = {
            "contains",
            "similarity",
            "regex",
            "regex_absence",
            "length",
            "exact_match",
            "llm_judge",
        }
        assert set(METRIC_MAP.keys()) == expected

    def test_build_metric_valid(self) -> None:
        metric = _build_metric({"type": "contains", "case_sensitive": True})
        assert metric is not None
        assert metric.name == "contains"

    def test_build_metric_unknown_type(self) -> None:
        result = _build_metric({"type": "unknown_metric"})
        assert result is None

    def test_build_metric_bad_kwargs(self) -> None:
        result = _build_metric({"type": "contains", "invalid_kwarg": 42})
        assert result is None

    def test_build_metric_string_shorthand(self, tmp_suites_dir: Path) -> None:
        """Test that string metric specs are handled."""
        import yaml

        suite_data = {
            "name": "string_metrics",
            "description": "Test string metric shorthand",
            "threshold": 0.5,
            "metrics": ["contains", "length"],
            "cases": [{"name": "c1", "input": "test", "expected": "test"}],
        }
        (tmp_suites_dir / "string_metrics.yaml").write_text(yaml.dump(suite_data))

        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("string_metrics")
        assert len(suite.metrics) == 2

    def test_load_real_suites(self) -> None:
        """Test that the real eval_suites/ directory loads correctly."""
        real_dir = Path(__file__).parent.parent / "eval_suites"
        if not real_dir.exists():
            pytest.skip("eval_suites/ not found")

        loader = SuiteLoader(real_dir)
        suites = loader.list_suites()
        assert len(suites) >= 1

        for suite_info in suites:
            suite = loader.load_suite(suite_info["name"])
            assert len(suite.cases) >= 10
            assert len(suite.metrics) >= 1


# =============================================================================
# TestEvalStore
# =============================================================================


class TestEvalStore:
    """Tests for the EvalStore."""

    def test_record_run(self, eval_store: EvalStore, sample_suite_result: SuiteResult) -> None:
        run_id = eval_store.record_run(
            suite_name="test_suite",
            result=sample_suite_result,
            agent_role="tester",
            model="mock-model",
            run_mode="mock",
        )
        assert run_id
        assert len(run_id) == 36  # UUID

    def test_query_runs(self, eval_store: EvalStore, sample_suite_result: SuiteResult) -> None:
        eval_store.record_run("suite_a", sample_suite_result, agent_role="planner")
        eval_store.record_run("suite_b", sample_suite_result, agent_role="builder")

        all_runs = eval_store.query_runs()
        assert len(all_runs) == 2

        planner_runs = eval_store.query_runs(agent_role="planner")
        assert len(planner_runs) == 1
        assert planner_runs[0]["agent_role"] == "planner"

        suite_a_runs = eval_store.query_runs(suite_name="suite_a")
        assert len(suite_a_runs) == 1

    def test_get_run(self, eval_store: EvalStore, sample_suite_result: SuiteResult) -> None:
        run_id = eval_store.record_run("test_suite", sample_suite_result, agent_role="tester")

        run = eval_store.get_run(run_id)
        assert run is not None
        assert run["suite_name"] == "test_suite"
        assert run["passed"] == 1
        assert run["failed"] == 1
        assert run["errors"] == 1
        assert len(run["case_results"]) == 3

    def test_get_run_not_found(self, eval_store: EvalStore) -> None:
        assert eval_store.get_run("nonexistent-id") is None

    def test_get_run_case_results_detail(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        run_id = eval_store.record_run("test_suite", sample_suite_result)
        run = eval_store.get_run(run_id)

        cases = run["case_results"]
        passed_case = next(c for c in cases if c["case_name"] == "case_pass")
        assert passed_case["status"] == "passed"
        assert passed_case["score"] == 0.9
        assert "contains" in passed_case["metrics"]

        error_case = next(c for c in cases if c["case_name"] == "case_error")
        assert error_case["status"] == "error"
        assert error_case["error"] == "Something broke"

    def test_get_suite_trend(self, eval_store: EvalStore, sample_suite_result: SuiteResult) -> None:
        for i in range(3):
            # Vary model so deduplication does not collapse the runs
            eval_store.record_run("trend_suite", sample_suite_result, model=f"model-{i}")

        trend = eval_store.get_suite_trend("trend_suite", days=30)
        assert len(trend) == 3

    def test_get_suite_trend_empty(self, eval_store: EvalStore) -> None:
        trend = eval_store.get_suite_trend("nonexistent", days=30)
        assert trend == []

    def test_get_agent_summary(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        eval_store.record_run("s1", sample_suite_result, agent_role="builder")
        eval_store.record_run("s2", sample_suite_result, agent_role="builder")

        summary = eval_store.get_agent_summary("builder")
        assert summary["total_runs"] == 2
        assert summary["agent_role"] == "builder"
        assert summary["avg_score"] > 0

    def test_get_agent_summary_no_data(self, eval_store: EvalStore) -> None:
        summary = eval_store.get_agent_summary("nonexistent")
        assert summary["total_runs"] == 0
        assert summary["avg_score"] == 0.0

    def test_query_runs_limit(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        for i in range(5):
            eval_store.record_run(f"suite_{i}", sample_suite_result)

        limited = eval_store.query_runs(limit=3)
        assert len(limited) == 3

    def test_record_run_with_metadata(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        run_id = eval_store.record_run(
            "meta_suite",
            sample_suite_result,
            metadata={"version": "1.0", "ci": True},
        )
        run = eval_store.get_run(run_id)
        assert run["metadata"] == {"version": "1.0", "ci": True}

    def test_feed_to_outcome_tracker(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        run_id = eval_store.record_run("feed_suite", sample_suite_result, agent_role="tester")

        mock_tracker = MagicMock()
        with (
            patch(
                "animus_forge.state.database.get_database",
                return_value=eval_store.backend,
            ),
            patch(
                "animus_forge.intelligence.outcome_tracker.OutcomeTracker",
                return_value=mock_tracker,
            ),
        ):
            fed = eval_store.feed_to_outcome_tracker(run_id, "workflow-1")

        assert fed == 3
        mock_tracker.record_many.assert_called_once()
        records = mock_tracker.record_many.call_args[0][0]
        assert len(records) == 3

    def test_feed_to_outcome_tracker_nonexistent_run(self, eval_store: EvalStore) -> None:
        result = eval_store.feed_to_outcome_tracker("bad-id", "wf-1")
        assert result == 0


# =============================================================================
# TestMockProvider
# =============================================================================


class TestMockProvider:
    """Tests for MockProvider."""

    def test_is_configured(self) -> None:
        provider = MockProvider()
        assert provider.is_configured() is True

    def test_name_and_type(self) -> None:
        provider = MockProvider()
        assert provider.name == "mock"

    def test_complete_returns_response(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider()
        response = provider.complete(CompletionRequest(prompt="Hello world"))

        assert response.content
        assert response.model == "mock-model"
        assert response.provider == "mock"
        assert response.tokens_used > 0

    def test_deterministic_output(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider()
        r1 = provider.complete(CompletionRequest(prompt="test prompt"))
        r2 = provider.complete(CompletionRequest(prompt="test prompt"))

        assert r1.content == r2.content

    def test_different_prompts_different_output(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider()
        r1 = provider.complete(CompletionRequest(prompt="prompt A"))
        r2 = provider.complete(CompletionRequest(prompt="prompt B"))

        assert r1.content != r2.content

    def test_custom_responses(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider(responses={"hello": "Hello there!"})
        r = provider.complete(CompletionRequest(prompt="say hello"))

        assert r.content == "Hello there!"

    def test_custom_responses_fallback(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider(responses={"hello": "hi"})
        r = provider.complete(CompletionRequest(prompt="completely different"))

        # Should fall back to hash-based generation
        assert r.content
        assert r.content != "hi"

    def test_token_counts(self) -> None:
        from animus_forge.providers.base import CompletionRequest

        provider = MockProvider()
        r = provider.complete(CompletionRequest(prompt="short"))

        assert r.input_tokens > 0
        assert r.output_tokens > 0
        assert r.tokens_used == r.input_tokens + r.output_tokens

    def test_initialize_noop(self) -> None:
        provider = MockProvider()
        provider.initialize()  # should not raise

    def test_fallback_model(self) -> None:
        provider = MockProvider()
        assert provider.default_model == "mock-model"


# =============================================================================
# TestEvalCLI
# =============================================================================


class TestEvalCLI:
    """Tests for CLI eval commands using CliRunner."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture()
    def cli_app(self):
        from animus_forge.cli.commands.eval_cmd import eval_app

        return eval_app

    def test_eval_list(self, runner: CliRunner, cli_app) -> None:
        result = runner.invoke(cli_app, ["list"])
        assert result.exit_code == 0
        # Should show suites from the real eval_suites/ dir, or the
        # "no suites" empty-state message.
        assert "benchgoblins-ask" in result.output or "No suites" in result.output

    def test_eval_list_custom_dir(self, runner: CliRunner, cli_app, tmp_suites_dir: Path) -> None:
        result = runner.invoke(cli_app, ["list", "--suites-dir", str(tmp_suites_dir)])
        assert result.exit_code == 0
        assert "test_suite" in result.output

    def test_eval_run_mock(self, runner: CliRunner, cli_app, tmp_suites_dir: Path) -> None:
        """Run a suite with mock provider (no API calls)."""
        result = runner.invoke(
            cli_app,
            [
                "run",
                "test_suite",
                "--mock",
                "--suites-dir",
                str(tmp_suites_dir),
            ],
        )
        # Should complete without error (exit code depends on threshold)
        assert "Running suite" in result.output
        assert "test_suite" in result.output

    def test_eval_run_suite_not_found(
        self, runner: CliRunner, cli_app, tmp_suites_dir: Path
    ) -> None:
        result = runner.invoke(
            cli_app,
            ["run", "nonexistent", "--mock", "--suites-dir", str(tmp_suites_dir)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_eval_run_with_output(
        self, runner: CliRunner, cli_app, tmp_suites_dir: Path, tmp_path: Path
    ) -> None:
        output_file = tmp_path / "report.json"
        result = runner.invoke(
            cli_app,
            [
                "run",
                "test_suite",
                "--mock",
                "--suites-dir",
                str(tmp_suites_dir),
                "--output",
                str(output_file),
            ],
        )
        assert "Report saved" in result.output
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert "suite_name" in data
        assert "results" in data

    def test_eval_results_empty(self, runner: CliRunner, cli_app) -> None:
        result = runner.invoke(cli_app, ["results"])
        # May show "No eval runs" or actual results depending on state
        assert result.exit_code in (0, 1)


# =============================================================================
# TestEvalIntegration
# =============================================================================


class TestEvalIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline(self, tmp_suites_dir: Path, memory_backend) -> None:
        """Load YAML → create evaluator → run → store → query."""
        # Load suite
        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")
        assert len(suite.cases) == 2
        assert len(suite.metrics) == 2

        # Create mock evaluator
        mock_provider = MockProvider(responses={"hello": "Hello, hi there! Nice to meet you."})

        def agent_fn(prompt):
            from animus_forge.providers.base import CompletionRequest

            return mock_provider.complete(CompletionRequest(prompt=str(prompt))).content

        evaluator = AgentEvaluator(agent_fn, threshold=suite.threshold)

        # Run
        runner = EvalRunner(evaluator)
        result = runner.run(suite)

        assert result.total == 2
        assert result.passed + result.failed + result.errors == 2
        assert result.duration_ms > 0

        # Store
        store = EvalStore(memory_backend)
        run_id = store.record_run(
            suite_name="test_suite",
            result=result,
            agent_role="tester",
            model="mock-model",
            run_mode="mock",
        )

        # Query
        runs = store.query_runs(suite_name="test_suite")
        assert len(runs) == 1
        assert runs[0]["id"] == run_id
        assert runs[0]["total_cases"] == 2

        # Get with case details
        full_run = store.get_run(run_id)
        assert len(full_run["case_results"]) == 2

        # Trend
        trend = store.get_suite_trend("test_suite")
        assert len(trend) == 1

        # Agent summary
        summary = store.get_agent_summary("tester")
        assert summary["total_runs"] == 1

    def test_parallel_execution(self, tmp_suites_dir: Path) -> None:
        """Run in parallel mode."""
        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")

        provider = MockProvider()

        def agent_fn(prompt):
            from animus_forge.providers.base import CompletionRequest

            return provider.complete(CompletionRequest(prompt=str(prompt))).content

        evaluator = AgentEvaluator(agent_fn, threshold=suite.threshold)
        runner = EvalRunner(evaluator)
        result = runner.run(suite, parallel=True)

        assert result.total == 2

    def test_reporter_output(self, tmp_suites_dir: Path) -> None:
        """Test that reporters produce output from a run."""
        from animus_forge.evaluation.reporters import ConsoleReporter, JSONReporter

        loader = SuiteLoader(tmp_suites_dir)
        suite = loader.load_suite("test_suite")

        provider = MockProvider()

        def agent_fn(prompt):
            from animus_forge.providers.base import CompletionRequest

            return provider.complete(CompletionRequest(prompt=str(prompt))).content

        evaluator = AgentEvaluator(agent_fn, threshold=suite.threshold)
        runner = EvalRunner(evaluator)
        result = runner.run(suite)

        console_report = ConsoleReporter(verbose=True).report(result)
        assert "test_suite" in console_report
        assert "Total Cases" in console_report

        json_report = JSONReporter().report(result)
        data = json.loads(json_report)
        assert data["suite_name"] == "test_suite"

    def test_mock_provider_with_eval_suite(self) -> None:
        """Test MockProvider works through the full eval framework."""
        suite = EvalSuite(name="mock_test", threshold=0.3)
        suite.add_case(
            input="Write a plan for deployment",
            expected=["plan", "deploy"],
            name="plan_test",
        )
        suite.add_metric(ContainsMetric(case_sensitive=False, all_required=False))
        suite.add_metric(LengthMetric(min_length=50))

        provider = MockProvider()

        def agent_fn(prompt):
            from animus_forge.providers.base import CompletionRequest

            return provider.complete(CompletionRequest(prompt=str(prompt))).content

        evaluator = AgentEvaluator(agent_fn, threshold=0.3)
        runner = EvalRunner(evaluator)
        result = runner.run(suite)

        assert result.total == 1
        assert result.results[0].score > 0

    def test_record_run_deduplicates_identical_recent_run(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        """An identical run within 60 min returns the existing run_id."""
        run_id_1 = eval_store.record_run(
            "dedup_suite",
            sample_suite_result,
            agent_role="tester",
            model="m",
            run_mode="live",
        )
        run_id_2 = eval_store.record_run(
            "dedup_suite",
            sample_suite_result,
            agent_role="tester",
            model="m",
            run_mode="live",
        )
        assert run_id_1 == run_id_2
        # Only one row should exist
        assert len(eval_store.query_runs(suite_name="dedup_suite")) == 1

    def test_record_run_stores_variance(
        self, eval_store: EvalStore, sample_suite_result: SuiteResult
    ) -> None:
        """score_variance from SuiteResult is persisted."""
        sample_suite_result.score_variance = 0.42
        run_id = eval_store.record_run("var_suite", sample_suite_result)
        run = eval_store.get_run(run_id)
        assert run is not None
        assert run["score_variance"] == 0.42


# =============================================================================
# TestGlobalAccessors
# =============================================================================


class TestGlobalAccessors:
    """Tests for singleton get/reset functions."""

    def test_reset_eval_store(self) -> None:
        reset_eval_store()
        # After reset, internal should be None
        from animus_forge.evaluation import store as store_mod

        assert store_mod._eval_store is None

    def test_get_eval_store_creates_singleton(self) -> None:
        """Test that get_eval_store uses lazy import pattern."""
        reset_eval_store()
        # We can't easily test the full singleton without a real DB,
        # but we can verify the reset clears state
        from animus_forge.evaluation import store as store_mod

        store_mod._eval_store = MagicMock()
        result = get_eval_store()
        assert result is store_mod._eval_store

        reset_eval_store()
        assert store_mod._eval_store is None
