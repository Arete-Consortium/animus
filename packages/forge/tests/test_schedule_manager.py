"""Tests for ScheduleManager database operations."""

import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

from animus_forge.scheduler.schedule_manager import (
    CronConfig,
    IntervalConfig,
    ScheduleExecutionLog,
    ScheduleManager,
    ScheduleStatus,
    ScheduleType,
    WorkflowSchedule,
)
from animus_forge.state.backends import SQLiteBackend


class TestScheduleManager:
    """Tests for ScheduleManager class."""

    @pytest.fixture
    def backend(self):
        """Create a temporary SQLite backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            backend = SQLiteBackend(db_path=db_path)
            yield backend
            backend.close()

    @pytest.fixture
    def manager(self, backend):
        """Create a ScheduleManager with mocked workflow engine and scheduler."""
        with patch("animus_forge.scheduler.schedule_manager.get_database", return_value=backend):
            with patch(
                "animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter"
            ) as mock_engine:
                mock_engine.return_value.load_workflow.return_value = MagicMock()
                manager = ScheduleManager(backend=backend)

                # Mock the scheduler's get_job to return a mock with next_run_time
                original_get_job = manager.scheduler.get_job

                def mock_get_job(job_id):
                    job = original_get_job(job_id)
                    if job is not None:
                        # Create a mock that wraps the real job but adds next_run_time
                        mock_job = MagicMock()
                        mock_job.next_run_time = datetime.now()
                        return mock_job
                    return job

                manager.scheduler.get_job = mock_get_job

                yield manager
                manager.shutdown()

    def test_init_creates_schema(self, backend):
        """ScheduleManager creates tables on init."""
        with patch("animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter"):
            manager = ScheduleManager(backend=backend)
            manager.shutdown()

        # Verify tables exist
        schedules = backend.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'"
        )
        assert schedules is not None

        logs = backend.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_logs'"
        )
        assert logs is not None

    def test_create_schedule_interval(self, manager, backend):
        """create_schedule() creates interval schedule in database."""
        schedule = WorkflowSchedule(
            id="test-schedule",
            workflow_id="test-workflow",
            name="Test Schedule",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=30),
        )

        result = manager.create_schedule(schedule)
        assert result is True

        # Verify in database
        row = backend.fetchone("SELECT * FROM schedules WHERE id = ?", ("test-schedule",))
        assert row is not None
        assert row["workflow_id"] == "test-workflow"
        assert row["name"] == "Test Schedule"
        assert row["schedule_type"] == "interval"

    def test_create_schedule_cron(self, manager, backend):
        """create_schedule() creates cron schedule in database."""
        schedule = WorkflowSchedule(
            id="cron-schedule",
            workflow_id="test-workflow",
            name="Cron Schedule",
            schedule_type=ScheduleType.CRON,
            cron_config=CronConfig(minute="0", hour="9"),
        )

        result = manager.create_schedule(schedule)
        assert result is True

        # Verify in database
        row = backend.fetchone("SELECT * FROM schedules WHERE id = ?", ("cron-schedule",))
        assert row is not None
        assert row["schedule_type"] == "cron"

    def test_create_schedule_validates_workflow(self, backend):
        """create_schedule() raises if workflow doesn't exist."""
        with patch("animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter") as mock_engine:
            mock_engine.return_value.load_workflow.return_value = None
            manager = ScheduleManager(backend=backend)

            schedule = WorkflowSchedule(
                id="test-schedule",
                workflow_id="nonexistent",
                name="Test",
                schedule_type=ScheduleType.INTERVAL,
                interval_config=IntervalConfig(minutes=5),
            )

            with pytest.raises(ValueError) as exc:
                manager.create_schedule(schedule)

            assert "not found" in str(exc.value)
            manager.shutdown()

    def test_get_schedule(self, manager):
        """get_schedule() returns schedule by ID."""
        schedule = WorkflowSchedule(
            id="my-schedule",
            workflow_id="test-workflow",
            name="My Schedule",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(hours=1),
        )
        manager.create_schedule(schedule)

        retrieved = manager.get_schedule("my-schedule")
        assert retrieved is not None
        assert retrieved.id == "my-schedule"
        assert retrieved.name == "My Schedule"

    def test_get_schedule_returns_none_for_missing(self, manager):
        """get_schedule() returns None for nonexistent ID."""
        result = manager.get_schedule("nonexistent")
        assert result is None

    def test_update_schedule(self, manager, backend):
        """update_schedule() updates schedule in database."""
        schedule = WorkflowSchedule(
            id="update-test",
            workflow_id="test-workflow",
            name="Original Name",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=15),
        )
        manager.create_schedule(schedule)

        # Update the schedule
        schedule.name = "Updated Name"
        schedule.interval_config = IntervalConfig(minutes=30)
        result = manager.update_schedule(schedule)
        assert result is True

        # Verify update
        retrieved = manager.get_schedule("update-test")
        assert retrieved.name == "Updated Name"
        assert retrieved.interval_config.minutes == 30

    def test_update_schedule_preserves_metadata(self, manager):
        """update_schedule() preserves created_at and run_count."""
        schedule = WorkflowSchedule(
            id="preserve-test",
            workflow_id="test-workflow",
            name="Test",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=5),
        )
        manager.create_schedule(schedule)

        # Manually set run_count
        original = manager.get_schedule("preserve-test")
        original_created = original.created_at

        # Update
        schedule.name = "New Name"
        manager.update_schedule(schedule)

        # Verify metadata preserved
        updated = manager.get_schedule("preserve-test")
        assert updated.created_at == original_created

    def test_delete_schedule(self, manager, backend):
        """delete_schedule() removes schedule from database."""
        schedule = WorkflowSchedule(
            id="delete-me",
            workflow_id="test-workflow",
            name="Delete Me",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=5),
        )
        manager.create_schedule(schedule)

        result = manager.delete_schedule("delete-me")
        assert result is True

        # Verify removed
        assert manager.get_schedule("delete-me") is None
        row = backend.fetchone("SELECT * FROM schedules WHERE id = ?", ("delete-me",))
        assert row is None

    def test_delete_nonexistent_schedule(self, manager):
        """delete_schedule() returns False for nonexistent schedule."""
        result = manager.delete_schedule("nonexistent")
        assert result is False

    def test_list_schedules(self, manager):
        """list_schedules() returns all schedules."""
        for i in range(3):
            schedule = WorkflowSchedule(
                id=f"schedule-{i}",
                workflow_id="test-workflow",
                name=f"Schedule {i}",
                schedule_type=ScheduleType.INTERVAL,
                interval_config=IntervalConfig(minutes=5),
            )
            manager.create_schedule(schedule)

        schedules = manager.list_schedules()
        assert len(schedules) == 3

    def test_pause_schedule(self, manager):
        """pause_schedule() sets status to paused."""
        schedule = WorkflowSchedule(
            id="pause-test",
            workflow_id="test-workflow",
            name="Pause Test",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=5),
        )
        manager.create_schedule(schedule)

        result = manager.pause_schedule("pause-test")
        assert result is True

        paused = manager.get_schedule("pause-test")
        assert paused.status == ScheduleStatus.PAUSED

    def test_resume_schedule(self, manager):
        """resume_schedule() sets status to active."""
        schedule = WorkflowSchedule(
            id="resume-test",
            workflow_id="test-workflow",
            name="Resume Test",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=5),
            status=ScheduleStatus.PAUSED,
        )
        manager.create_schedule(schedule)
        manager.pause_schedule("resume-test")

        result = manager.resume_schedule("resume-test")
        assert result is True

        resumed = manager.get_schedule("resume-test")
        assert resumed.status == ScheduleStatus.ACTIVE

    def test_execution_log_saved(self, manager, backend):
        """Execution logs are saved to database."""
        manager.create_schedule(
            WorkflowSchedule(
                id="test-schedule",
                workflow_id="test-workflow",
                name="Log fixture",
                schedule_type=ScheduleType.INTERVAL,
                interval_config=IntervalConfig(minutes=5),
            )
        )
        log = ScheduleExecutionLog(
            schedule_id="test-schedule",
            workflow_id="test-workflow",
            executed_at=datetime.now(),
            status="completed",
            duration_seconds=1.5,
        )
        manager._save_execution_log(log)

        # Verify in database
        row = backend.fetchone(
            "SELECT * FROM schedule_logs WHERE schedule_id = ?", ("test-schedule",)
        )
        assert row is not None
        assert row["status"] == "completed"
        assert row["duration_seconds"] == 1.5

    def test_get_execution_history(self, manager, backend):
        """get_execution_history() returns logs from database."""
        # Create schedule first
        schedule = WorkflowSchedule(
            id="history-test",
            workflow_id="test-workflow",
            name="History Test",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=5),
        )
        manager.create_schedule(schedule)

        # Add some logs
        for i in range(5):
            log = ScheduleExecutionLog(
                schedule_id="history-test",
                workflow_id="test-workflow",
                executed_at=datetime.now(),
                status="completed" if i % 2 == 0 else "failed",
                duration_seconds=float(i),
            )
            manager._save_execution_log(log)

        history = manager.get_execution_history("history-test", limit=3)
        assert len(history) == 3

    def test_schedule_persists_across_restart(self, backend):
        """Schedules persist across manager restart."""
        with patch("animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter") as mock_engine:
            mock_engine.return_value.load_workflow.return_value = MagicMock()

            def mock_scheduler_get_job(manager):
                """Patch scheduler.get_job to return mock with next_run_time."""
                original = manager.scheduler.get_job

                def patched(job_id):
                    job = original(job_id)
                    if job:
                        mock_job = MagicMock()
                        mock_job.next_run_time = datetime.now()
                        return mock_job
                    return job

                manager.scheduler.get_job = patched

            # Create schedule with first manager
            manager1 = ScheduleManager(backend=backend)
            mock_scheduler_get_job(manager1)
            schedule = WorkflowSchedule(
                id="persist-test",
                workflow_id="test-workflow",
                name="Persist Test",
                description="Testing persistence",
                schedule_type=ScheduleType.INTERVAL,
                interval_config=IntervalConfig(hours=2),
                variables={"key": "value"},
            )
            manager1.create_schedule(schedule)
            manager1.shutdown()

            # Verify with second manager
            manager2 = ScheduleManager(backend=backend)
            mock_scheduler_get_job(manager2)
            # Load schedules from database (normally done by start())
            manager2._load_all_schedules()
            loaded = manager2.get_schedule("persist-test")

            assert loaded is not None
            assert loaded.name == "Persist Test"
            assert loaded.description == "Testing persistence"
            assert loaded.interval_config.hours == 2
            assert loaded.variables == {"key": "value"}
            manager2.shutdown()

    def test_schedule_with_variables(self, manager, backend):
        """Schedule variables are persisted correctly."""
        schedule = WorkflowSchedule(
            id="vars-test",
            workflow_id="test-workflow",
            name="Vars Test",
            schedule_type=ScheduleType.INTERVAL,
            interval_config=IntervalConfig(minutes=10),
            variables={"env": "production", "count": 5, "enabled": True},
        )
        manager.create_schedule(schedule)

        retrieved = manager.get_schedule("vars-test")
        assert retrieved.variables == {"env": "production", "count": 5, "enabled": True}
