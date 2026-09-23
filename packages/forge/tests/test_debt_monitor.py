"""Tests for the technical debt monitoring and audit system."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from animus_forge.metrics.audit_checks import (
    _diff_configs,
    check_error_rate,
    check_skill_integrity,
)
from animus_forge.metrics.debt_monitor import (
    AuditCheck,
    AuditFrequency,
    AuditResult,
    AuditStatus,
    DebtSeverity,
    DebtSource,
    DebtStatus,
    SystemAuditor,
    SystemBaseline,
    TechnicalDebt,
    TechnicalDebtRegistry,
    capture_baseline,
    load_active_baseline,
    save_baseline,
)
from animus_forge.state.backends import SQLiteBackend


@pytest.fixture
def backend(tmp_path: Path) -> SQLiteBackend:
    """Create an in-memory SQLite backend with schema applied."""
    db = SQLiteBackend(db_path=str(tmp_path / "test.db"))
    migration = Path(__file__).parent.parent / "migrations" / "003_debt_monitoring.sql"
    db.executescript(migration.read_text())
    # Also create a minimal jobs table for error rate checks
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            ended_at TIMESTAMP
        );
        """
    )
    return db


@pytest.fixture
def baseline() -> SystemBaseline:
    """Create a test baseline."""
    return SystemBaseline(
        captured_at=datetime.now(UTC),
        task_completion_time_avg=4.0,
        agent_spawn_time_avg=0.8,
        idle_cpu_percent=10.0,
        idle_memory_percent=40.0,
        skill_hashes={},
        config_snapshots={},
        package_versions={"requests": "2.31.0"},
    )


class TestTechnicalDebtRegistry:
    """Tests for the TechnicalDebtRegistry."""

    def test_register_and_list(self, backend: SQLiteBackend) -> None:
        registry = TechnicalDebtRegistry(backend)
        debt = TechnicalDebt(
            id="test-001",
            category="performance",
            severity=DebtSeverity.HIGH,
            title="Slow task completion",
            description="Tasks are 30% slower than baseline",
            detected_at=datetime.now(UTC),
            source=DebtSource.AUDIT,
            estimated_effort="2h",
        )
        registry.register(debt)
        items = registry.list_open()
        assert len(items) == 1
        assert items[0]["id"] == "test-001"
        assert items[0]["severity"] == "high"

    def test_resolve(self, backend: SQLiteBackend) -> None:
        registry = TechnicalDebtRegistry(backend)
        debt = TechnicalDebt(
            id="test-002",
            category="dependencies",
            severity=DebtSeverity.MEDIUM,
            title="Outdated packages",
            description="5 outdated packages",
            detected_at=datetime.now(UTC),
            source=DebtSource.AUDIT,
        )
        registry.register(debt)
        registry.resolve("test-002", "Updated all packages")

        items = registry.list_open()
        assert len(items) == 0

    def test_update_status(self, backend: SQLiteBackend) -> None:
        registry = TechnicalDebtRegistry(backend)
        debt = TechnicalDebt(
            id="test-003",
            category="reliability",
            severity=DebtSeverity.LOW,
            title="Minor issue",
            description="...",
            detected_at=datetime.now(UTC),
            source=DebtSource.MANUAL,
        )
        registry.register(debt)
        registry.update_status("test-003", DebtStatus.ACKNOWLEDGED)

        items = registry.list_open()
        assert items[0]["status"] == "acknowledged"

    def test_summary(self, backend: SQLiteBackend) -> None:
        registry = TechnicalDebtRegistry(backend)
        for i, sev in enumerate([DebtSeverity.HIGH, DebtSeverity.HIGH, DebtSeverity.LOW]):
            registry.register(
                TechnicalDebt(
                    id=f"sum-{i}",
                    category="performance",
                    severity=sev,
                    title=f"Issue {i}",
                    description="...",
                    detected_at=datetime.now(UTC),
                    source=DebtSource.AUDIT,
                )
            )
        summary = registry.get_summary()
        assert summary["total_open"] == 3
        assert summary["by_severity"]["high"] == 2
        assert summary["by_severity"]["low"] == 1


class TestSystemAuditor:
    """Tests for the SystemAuditor."""

    def test_evaluate_threshold(self, backend: SQLiteBackend) -> None:
        auditor = SystemAuditor(backend)
        assert auditor.evaluate_threshold(0.5, 1.0, 2.0) == AuditStatus.OK
        assert auditor.evaluate_threshold(1.5, 1.0, 2.0) == AuditStatus.WARNING
        assert auditor.evaluate_threshold(2.5, 1.0, 2.0) == AuditStatus.CRITICAL

    def test_is_due(self, backend: SQLiteBackend) -> None:
        auditor = SystemAuditor(backend)
        check = AuditCheck(
            name="test",
            category="test",
            frequency=AuditFrequency.DAILY,
            check_function="noop",
            threshold_warning=1.0,
            threshold_critical=2.0,
            last_run=None,
        )
        now = datetime.now(UTC)
        assert auditor._is_due(check, now) is True

    @pytest.mark.asyncio
    async def test_run_scheduled_audits(
        self, backend: SQLiteBackend, baseline: SystemBaseline
    ) -> None:
        auditor = SystemAuditor(backend, baseline=baseline, checks=[])
        # Add a simple custom check
        check = AuditCheck(
            name="custom_check",
            category="test",
            frequency=AuditFrequency.HOURLY,
            check_function="custom_fn",
            threshold_warning=1.0,
            threshold_critical=2.0,
        )
        auditor.checks.append(check)

        async def custom_fn(_: AuditCheck) -> AuditResult:
            return AuditResult(
                check_name="custom_check",
                category="test",
                status=AuditStatus.OK,
                value=0.5,
            )

        auditor.register_check("custom_fn", custom_fn)

        results = await auditor.run_scheduled_audits()
        assert len(results) == 1
        assert results[0].status == AuditStatus.OK

    @pytest.mark.asyncio
    async def test_warning_creates_debt(
        self, backend: SQLiteBackend, baseline: SystemBaseline
    ) -> None:
        auditor = SystemAuditor(backend, baseline=baseline, checks=[])
        check = AuditCheck(
            name="failing_check",
            category="reliability",
            frequency=AuditFrequency.HOURLY,
            check_function="warn_fn",
            threshold_warning=1.0,
            threshold_critical=2.0,
        )
        auditor.checks.append(check)

        async def warn_fn(_: AuditCheck) -> AuditResult:
            return AuditResult(
                check_name="failing_check",
                category="reliability",
                status=AuditStatus.WARNING,
                value=1.5,
            )

        auditor.register_check("warn_fn", warn_fn)

        await auditor.run_scheduled_audits()
        debt_items = auditor.debt_registry.list_open()
        assert len(debt_items) == 1
        assert "failing_check" in debt_items[0]["title"]

    def test_generate_report(self, backend: SQLiteBackend) -> None:
        auditor = SystemAuditor(backend)
        results = [
            AuditResult(
                check_name="task_completion_time",
                category="performance",
                status=AuditStatus.WARNING,
                value=5.5,
                baseline=4.2,
                recommendation="Review recent skill changes",
            ),
            AuditResult(
                check_name="error_rate",
                category="reliability",
                status=AuditStatus.OK,
                value=0.02,
            ),
        ]
        report = auditor.generate_report(results)
        assert "Zorya Polunochnaya" in report
        assert "WARNING" in report
        assert "1 warning(s)" in report


class TestSystemBaseline:
    """Tests for baseline capture and persistence."""

    def test_save_and_load(self, backend: SQLiteBackend, baseline: SystemBaseline) -> None:
        save_baseline(backend, baseline)
        loaded = load_active_baseline(backend)
        assert loaded is not None
        assert loaded.task_completion_time_avg == baseline.task_completion_time_avg
        assert loaded.idle_cpu_percent == baseline.idle_cpu_percent

    def test_new_baseline_deactivates_old(self, backend: SQLiteBackend) -> None:
        b1 = SystemBaseline(
            captured_at=datetime.now(UTC),
            task_completion_time_avg=4.0,
            agent_spawn_time_avg=0.8,
            idle_cpu_percent=10.0,
            idle_memory_percent=40.0,
        )
        b2 = SystemBaseline(
            captured_at=datetime.now(UTC),
            task_completion_time_avg=5.0,
            agent_spawn_time_avg=0.9,
            idle_cpu_percent=12.0,
            idle_memory_percent=45.0,
        )
        save_baseline(backend, b1)
        save_baseline(backend, b2)

        loaded = load_active_baseline(backend)
        assert loaded is not None
        assert loaded.task_completion_time_avg == 5.0

    def test_capture_baseline(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "test.md").write_text("# Test Skill")

        bl = capture_baseline(
            skills_path=skills,
            config_path=tmp_path / "config",
            task_completion_time=3.0,
        )
        assert bl.task_completion_time_avg == 3.0
        assert len(bl.skill_hashes) == 1


class TestAuditChecks:
    """Tests for individual audit check implementations."""

    @pytest.mark.asyncio
    async def test_check_error_rate_ok(self, backend: SQLiteBackend) -> None:
        # Insert some jobs
        with backend.transaction():
            for _ in range(10):
                backend.execute("INSERT INTO jobs (status) VALUES (?)", ("completed",))

        check = AuditCheck(
            name="error_rate",
            category="reliability",
            frequency=AuditFrequency.DAILY,
            check_function="check_error_rate",
            threshold_warning=0.05,
            threshold_critical=0.10,
        )
        result = await check_error_rate(check, backend=backend)
        assert result.status == AuditStatus.OK

    @pytest.mark.asyncio
    async def test_check_error_rate_warning(self, backend: SQLiteBackend) -> None:
        with backend.transaction():
            for _ in range(9):
                backend.execute("INSERT INTO jobs (status) VALUES (?)", ("completed",))
            backend.execute("INSERT INTO jobs (status) VALUES (?)", ("failed",))

        check = AuditCheck(
            name="error_rate",
            category="reliability",
            frequency=AuditFrequency.DAILY,
            check_function="check_error_rate",
            threshold_warning=0.05,
            threshold_critical=0.20,
        )
        result = await check_error_rate(check, backend=backend)
        assert result.status == AuditStatus.WARNING

    @pytest.mark.asyncio
    async def test_check_skill_integrity_ok(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_file = skills_dir / "test.md"
        skill_file.write_text("# My Skill")

        import hashlib

        expected_hash = hashlib.sha256(skill_file.read_bytes()).hexdigest()
        baseline = SystemBaseline(
            captured_at=datetime.now(UTC),
            task_completion_time_avg=0,
            agent_spawn_time_avg=0,
            idle_cpu_percent=0,
            idle_memory_percent=0,
            skill_hashes={str(skill_file): expected_hash},
        )

        check = AuditCheck(
            name="skill_integrity",
            category="skills",
            frequency=AuditFrequency.DAILY,
            check_function="check_skill_integrity",
            threshold_warning=1,
            threshold_critical=3,
        )
        result = await check_skill_integrity(check, baseline=baseline, skills_path=skills_dir)
        assert result.status == AuditStatus.OK

    @pytest.mark.asyncio
    async def test_check_skill_integrity_modified(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_file = skills_dir / "test.md"
        skill_file.write_text("# Original")

        baseline = SystemBaseline(
            captured_at=datetime.now(UTC),
            task_completion_time_avg=0,
            agent_spawn_time_avg=0,
            idle_cpu_percent=0,
            idle_memory_percent=0,
            skill_hashes={str(skill_file): "0000000000000000"},
        )

        check = AuditCheck(
            name="skill_integrity",
            category="skills",
            frequency=AuditFrequency.DAILY,
            check_function="check_skill_integrity",
            threshold_warning=1,
            threshold_critical=3,
        )
        result = await check_skill_integrity(check, baseline=baseline, skills_path=skills_dir)
        assert result.status == AuditStatus.WARNING


class TestDiffConfigs:
    """Tests for config diff utility."""

    def test_no_diff(self) -> None:
        assert _diff_configs({"a": 1}, {"a": 1}) == []

    def test_value_changed(self) -> None:
        diffs = _diff_configs({"a": 1}, {"a": 2})
        assert len(diffs) == 1
        assert diffs[0]["path"] == "a"

    def test_key_added(self) -> None:
        diffs = _diff_configs({"a": 1}, {"a": 1, "b": 2})
        assert len(diffs) == 1
        assert diffs[0]["issue"] == "added"

    def test_key_removed(self) -> None:
        diffs = _diff_configs({"a": 1, "b": 2}, {"a": 1})
        assert len(diffs) == 1
        assert diffs[0]["issue"] == "removed"

    def test_nested_diff(self) -> None:
        diffs = _diff_configs(
            {"a": {"b": 1}},
            {"a": {"b": 2}},
        )
        assert len(diffs) == 1
        assert diffs[0]["path"] == "a.b"
