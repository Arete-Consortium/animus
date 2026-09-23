"""Tests for SkillMetricsAggregator."""

import uuid
from datetime import UTC, datetime, timedelta

from animus_forge.skills.evolver.metrics import SkillMetricsAggregator
from animus_forge.state.backends import SQLiteBackend


def _make_backend():
    """Create an in-memory SQLite backend with outcome_records schema + migration 015 columns."""
    backend = SQLiteBackend(":memory:")
    backend.executescript("""
        CREATE TABLE IF NOT EXISTS outcome_records (
            step_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            success INTEGER NOT NULL,
            quality_score REAL NOT NULL,
            cost_usd REAL NOT NULL,
            tokens_used INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            timestamp TEXT NOT NULL,
            skill_name TEXT DEFAULT '',
            skill_version TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS skill_metrics (
            skill_name TEXT NOT NULL,
            skill_version TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_invocations INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            avg_quality_score REAL DEFAULT 0.0,
            avg_cost_usd REAL DEFAULT 0.0,
            avg_latency_ms REAL DEFAULT 0.0,
            total_cost_usd REAL DEFAULT 0.0,
            trend TEXT DEFAULT 'stable',
            computed_at TEXT NOT NULL,
            PRIMARY KEY (skill_name, skill_version, period_start)
        );
    """)
    return backend


def _insert_outcome(
    backend,
    skill_name="skill_a",
    skill_version="1.0.0",
    success=1,
    quality=0.9,
    cost=0.05,
    latency=500,
    agent_role="builder",
    days_ago=0,
):
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    sid = str(uuid.uuid4())
    with backend.transaction():
        backend.execute(
            "INSERT INTO outcome_records "
            "(step_id, workflow_id, agent_role, provider, model, success, "
            "quality_score, cost_usd, tokens_used, latency_ms, metadata, timestamp, "
            "skill_name, skill_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                "w1",
                agent_role,
                "openai",
                "gpt-4o",
                success,
                quality,
                cost,
                1000,
                latency,
                "{}",
                ts,
                skill_name,
                skill_version,
            ),
        )


class TestGetSkillMetrics:
    def test_no_data(self):
        backend = _make_backend()
        agg = SkillMetricsAggregator(backend)
        assert agg.get_skill_metrics("nonexistent") is None

    def test_basic_metrics(self):
        backend = _make_backend()
        for _ in range(5):
            _insert_outcome(backend, success=1, quality=0.9)
        for _ in range(2):
            _insert_outcome(backend, success=0, quality=0.2)

        agg = SkillMetricsAggregator(backend)
        m = agg.get_skill_metrics("skill_a")
        assert m is not None
        assert m.total_invocations == 7
        assert m.success_count == 5
        assert m.failure_count == 2
        assert 0.7 < m.success_rate < 0.72
        assert m.skill_name == "skill_a"

    def test_with_version_filter(self):
        backend = _make_backend()
        _insert_outcome(backend, skill_version="1.0.0")
        _insert_outcome(backend, skill_version="2.0.0")

        agg = SkillMetricsAggregator(backend)
        m = agg.get_skill_metrics("skill_a", version="1.0.0")
        assert m is not None
        assert m.total_invocations == 1

    def test_respects_days_window(self):
        backend = _make_backend()
        _insert_outcome(backend, days_ago=0)
        _insert_outcome(backend, days_ago=60)

        agg = SkillMetricsAggregator(backend)
        m = agg.get_skill_metrics("skill_a", days=30)
        assert m is not None
        assert m.total_invocations == 1


class TestGetAllSkillMetrics:
    def test_empty(self):
        backend = _make_backend()
        agg = SkillMetricsAggregator(backend)
        assert agg.get_all_skill_metrics() == []

    def test_multiple_skills(self):
        backend = _make_backend()
        _insert_outcome(backend, skill_name="skill_a")
        _insert_outcome(backend, skill_name="skill_b")

        agg = SkillMetricsAggregator(backend)
        metrics = agg.get_all_skill_metrics()
        assert len(metrics) == 2
        names = {m.skill_name for m in metrics}
        assert names == {"skill_a", "skill_b"}

    def test_excludes_empty_skill_name(self):
        backend = _make_backend()
        _insert_outcome(backend, skill_name="")
        _insert_outcome(backend, skill_name="real_skill")

        agg = SkillMetricsAggregator(backend)
        metrics = agg.get_all_skill_metrics()
        assert len(metrics) == 1
        assert metrics[0].skill_name == "real_skill"


class TestGetSkillTrend:
    def test_stable_no_data(self):
        backend = _make_backend()
        agg = SkillMetricsAggregator(backend)
        assert agg.get_skill_trend("nonexistent") == "stable"

    def test_improving(self):
        backend = _make_backend()
        # Old failures
        for _ in range(5):
            _insert_outcome(backend, success=0, days_ago=20)
        # Recent successes
        for _ in range(5):
            _insert_outcome(backend, success=1, days_ago=1)

        agg = SkillMetricsAggregator(backend)
        assert agg.get_skill_trend("skill_a") == "improving"

    def test_declining(self):
        backend = _make_backend()
        # Old successes
        for _ in range(5):
            _insert_outcome(backend, success=1, days_ago=20)
        # Recent failures
        for _ in range(5):
            _insert_outcome(backend, success=0, days_ago=1)

        agg = SkillMetricsAggregator(backend)
        assert agg.get_skill_trend("skill_a") == "declining"

    def test_with_version(self):
        backend = _make_backend()
        for _ in range(5):
            _insert_outcome(backend, skill_version="1.0.0", success=1, days_ago=20)
        for _ in range(5):
            _insert_outcome(backend, skill_version="1.0.0", success=0, days_ago=1)

        agg = SkillMetricsAggregator(backend)
        assert agg.get_skill_trend("skill_a", version="1.0.0") == "declining"


class TestComputeAndStoreMetrics:
    def test_no_data(self):
        backend = _make_backend()
        agg = SkillMetricsAggregator(backend)
        assert agg.compute_and_store_metrics() == 0

    def test_stores_metrics(self):
        backend = _make_backend()
        for _ in range(5):
            _insert_outcome(backend)

        agg = SkillMetricsAggregator(backend)
        count = agg.compute_and_store_metrics()
        assert count == 1

        rows = backend.fetchall("SELECT * FROM skill_metrics", ())
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "skill_a"

    def test_includes_trend(self):
        backend = _make_backend()
        for _ in range(5):
            _insert_outcome(backend, success=1, days_ago=20)
        for _ in range(5):
            _insert_outcome(backend, success=0, days_ago=1)

        agg = SkillMetricsAggregator(backend)
        agg.compute_and_store_metrics()

        rows = backend.fetchall("SELECT * FROM skill_metrics", ())
        assert len(rows) == 1
        assert rows[0]["trend"] == "declining"


class TestComparativeMetrics:
    def test_both_versions(self):
        backend = _make_backend()
        _insert_outcome(backend, skill_version="1.0.0", success=1, quality=0.9)
        _insert_outcome(backend, skill_version="2.0.0", success=1, quality=0.7)

        agg = SkillMetricsAggregator(backend)
        a, b = agg.get_comparative_metrics("skill_a", "1.0.0", "2.0.0")
        assert a is not None
        assert b is not None
        assert a.avg_quality_score > b.avg_quality_score

    def test_missing_version(self):
        backend = _make_backend()
        _insert_outcome(backend, skill_version="1.0.0")

        agg = SkillMetricsAggregator(backend)
        a, b = agg.get_comparative_metrics("skill_a", "1.0.0", "9.9.9")
        assert a is not None
        assert b is None
