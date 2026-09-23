"""Integration tests for SkillEvolver — full cycle end-to-end."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from animus_forge.self_improve.approval import ApprovalGate
from animus_forge.skills.evolver.evolver import SkillEvolver
from animus_forge.skills.evolver.models import SkillChange
from animus_forge.state.backends import SQLiteBackend


def _make_backend():
    """Create in-memory backend with all evolver tables."""
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
        CREATE TABLE IF NOT EXISTS skill_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            version TEXT NOT NULL,
            previous_version TEXT,
            change_type TEXT NOT NULL,
            change_description TEXT,
            schema_snapshot TEXT NOT NULL,
            diff_summary TEXT,
            approval_id TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT DEFAULT 'skill_evolver',
            UNIQUE(skill_name, version)
        );
        CREATE TABLE IF NOT EXISTS skill_experiments (
            id TEXT PRIMARY KEY,
            skill_name TEXT NOT NULL,
            control_version TEXT NOT NULL,
            variant_version TEXT NOT NULL,
            traffic_split REAL DEFAULT 0.5,
            status TEXT DEFAULT 'active',
            min_invocations INTEGER DEFAULT 100,
            start_date TEXT NOT NULL,
            end_date TEXT,
            winner TEXT,
            conclusion_reason TEXT,
            created_at TEXT NOT NULL,
            concluded_at TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_deprecations (
            skill_name TEXT PRIMARY KEY,
            status TEXT DEFAULT 'flagged',
            flagged_at TEXT NOT NULL,
            deprecated_at TEXT,
            retired_at TEXT,
            reason TEXT,
            success_rate_at_flag REAL,
            invocations_at_flag INTEGER,
            replacement_skill TEXT,
            approval_id TEXT
        );
    """)
    return backend


def _make_skills_dir(tmp_path: Path) -> Path:
    """Create a minimal skills directory with registry.yaml and one skill."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "system" / "test_skill"
    skill_dir.mkdir(parents=True)

    schema = {
        "name": "test_skill",
        "version": "1.0.0",
        "agent": "builder",
        "type": "agent",
        "category": "system",
        "description": "A test skill",
        "status": "active",
        "consensus_level": "any",
        "risk_level": "low",
        "trust": "supervised",
        "parallel_safe": False,
        "capabilities": [
            {"name": "build", "description": "Build code"},
        ],
    }
    (skill_dir / "schema.yaml").write_text(yaml.dump(schema))

    registry = {
        "version": "1.0.0",
        "categories": {"system": "System skills"},
        "skills": [
            {
                "name": "test_skill",
                "path": "system/test_skill",
                "agent": "builder",
                "version": "1.0.0",
                "status": "active",
                "description": "A test skill",
                "capabilities": ["build"],
            }
        ],
    }
    (skills_dir / "registry.yaml").write_text(yaml.dump(registry))
    return skills_dir


def _insert_outcomes(backend, skill_name, skill_version, count, success=1, quality=0.9, days_ago=0):
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    for _ in range(count):
        with backend.transaction():
            backend.execute(
                "INSERT INTO outcome_records "
                "(step_id, workflow_id, agent_role, provider, model, success, "
                "quality_score, cost_usd, tokens_used, latency_ms, metadata, timestamp, "
                "skill_name, skill_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "w1",
                    "builder",
                    "openai",
                    "gpt-4o",
                    success,
                    quality,
                    0.05,
                    1000,
                    500,
                    "{}",
                    ts,
                    skill_name,
                    skill_version,
                ),
            )


class TestEvolutionCycle:
    def test_empty_cycle(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        report = evolver.run_evolution_cycle()
        assert report["metrics_computed"] == 0
        assert report["tuning_proposals"] == []

    def test_cycle_with_data(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        _insert_outcomes(backend, "test_skill", "1.0.0", 20, success=1)

        report = evolver.run_evolution_cycle()
        assert report["metrics_computed"] >= 1

    def test_cycle_detects_underperformers(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        _insert_outcomes(backend, "test_skill", "1.0.0", 15, success=0, quality=0.1)

        report = evolver.run_evolution_cycle()
        assert len(report["deprecation_flags"]) >= 1


class TestApplyChange:
    def test_apply_with_auto_approve(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        change = SkillChange(
            skill_name="test_skill",
            old_version="1.0.0",
            new_version="1.0.1",
            change_type="tune",
            description="Test change",
            modifications={"consensus_escalation": True},
        )
        result = evolver.apply_change(change)
        assert result is True

        # Version should be recorded
        history = evolver.versioner.get_version_history("test_skill")
        assert len(history) == 1
        assert history[0]["version"] == "1.0.1"

    def test_apply_without_approval(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=False)

        change = SkillChange(
            skill_name="test_skill",
            old_version="1.0.0",
            new_version="1.0.1",
            change_type="tune",
            description="Test",
            modifications={},
        )
        # Without approval, should not apply (pending status)
        result = evolver.apply_change(change)
        assert result is False

    def test_apply_nonexistent_skill(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        change = SkillChange(
            skill_name="nonexistent",
            old_version="1.0.0",
            new_version="1.0.1",
            change_type="tune",
            description="Test",
            modifications={},
        )
        assert evolver.apply_change(change) is False


class TestABTestIntegration:
    def test_start_and_route(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        change = SkillChange(
            skill_name="test_skill",
            old_version="1.0.0",
            new_version="1.0.1",
            change_type="tune",
            description="test",
            modifications={"consensus_escalation": True},
        )
        config = evolver.start_ab_test("test_skill", change)
        assert config.skill_name == "test_skill"

        # Routing should return a version
        version = evolver.route_skill("test_skill", "workflow_1")
        assert version in ("1.0.0", "1.0.1")

    def test_check_experiments_empty(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)
        assert evolver.check_experiments() == []


class TestRouteSkill:
    def test_no_experiment(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        version = evolver.route_skill("test_skill")
        assert version == "1.0.0"

    def test_unknown_skill(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        version = evolver.route_skill("unknown")
        assert version == "1.0.0"


class TestGetEvolutionStatus:
    def test_empty_status(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        status = evolver.get_evolution_status()
        assert status["active_experiments"] == []
        assert status["flagged_skills"] == []
        assert status["deprecated_skills"] == []

    def test_status_with_experiment(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        change = SkillChange(
            skill_name="test_skill",
            old_version="1.0.0",
            new_version="1.0.1",
            change_type="tune",
            description="test",
            modifications={},
        )
        evolver.start_ab_test("test_skill", change)

        status = evolver.get_evolution_status()
        assert len(status["active_experiments"]) == 1

    def test_status_with_flagged(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        evolver = SkillEvolver(backend, skills_dir, auto_approve=True)

        evolver.deprecator.flag_for_deprecation("test_skill", "bad")

        status = evolver.get_evolution_status()
        assert "test_skill" in status["flagged_skills"]


class TestSkillEvolverInit:
    def test_missing_skills_dir(self, tmp_path):
        backend = _make_backend()
        evolver = SkillEvolver(backend, tmp_path / "nonexistent")
        assert evolver._library is None

    def test_with_approval_gate(self, tmp_path):
        backend = _make_backend()
        skills_dir = _make_skills_dir(tmp_path)
        gate = ApprovalGate()
        evolver = SkillEvolver(backend, skills_dir, approval_gate=gate)
        assert evolver._approval_gate is gate
