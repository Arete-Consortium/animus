"""Tests for workflow scheduler module."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.executor import ExecutionResult
from animus_forge.workflow.scheduler import (
    ExecutionLog,
    ScheduleConfig,
    ScheduleStatus,
    WorkflowScheduler,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory."""
    data_dir = tmp_path / "schedules"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def mock_workflow_config():
    """Create mock workflow config."""
    mock = MagicMock()
    mock.name = "test-workflow"
    mock.steps = [MagicMock(), MagicMock()]
    return mock


@pytest.fixture
def schedule_config():
    """Create a basic schedule config."""
    return ScheduleConfig(
        id="test-schedule",
        workflow_path="workflows/test.yaml",
        name="Test Schedule",
        description="A test schedule",
        cron="0 9 * * *",
        inputs={"key": "value"},
    )


@pytest.fixture
def interval_schedule_config():
    """Create an interval-based schedule config."""
    return ScheduleConfig(
        id="interval-schedule",
        workflow_path="workflows/test.yaml",
        name="Interval Schedule",
        interval_seconds=3600,
    )


@pytest.fixture
def scheduler(temp_data_dir):
    """Create a scheduler instance."""
    with patch("animus_kernel.executor.scheduler.BackgroundScheduler") as mock_sched:
        mock_instance = MagicMock()
        mock_instance.running = False
        # Ensure get_job returns a job with a proper datetime for next_run_time
        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now(UTC) + timedelta(hours=1)
        mock_instance.get_job.return_value = mock_job
        mock_sched.return_value = mock_instance
        sched = WorkflowScheduler(data_dir=temp_data_dir)
        yield sched
        if sched.is_running:
            sched.shutdown(wait=False)


# =============================================================================
# Test ScheduleStatus
# =============================================================================


class TestScheduleStatus:
    """Tests for ScheduleStatus enum."""

    def test_active_value(self):
        """Test ACTIVE status value."""
        assert ScheduleStatus.ACTIVE.value == "active"

    def test_paused_value(self):
        """Test PAUSED status value."""
        assert ScheduleStatus.PAUSED.value == "paused"

    def test_disabled_value(self):
        """Test DISABLED status value."""
        assert ScheduleStatus.DISABLED.value == "disabled"

    def test_from_string(self):
        """Test creating status from string."""
        assert ScheduleStatus("active") == ScheduleStatus.ACTIVE
        assert ScheduleStatus("paused") == ScheduleStatus.PAUSED


# =============================================================================
# Test ScheduleConfig
# =============================================================================


class TestScheduleConfig:
    """Tests for ScheduleConfig dataclass."""

    def test_create_cron_schedule(self, schedule_config):
        """Test creating a cron-based schedule."""
        assert schedule_config.id == "test-schedule"
        assert schedule_config.cron == "0 9 * * *"
        assert schedule_config.interval_seconds is None
        assert schedule_config.status == ScheduleStatus.ACTIVE

    def test_create_interval_schedule(self, interval_schedule_config):
        """Test creating an interval-based schedule."""
        assert interval_schedule_config.interval_seconds == 3600
        assert interval_schedule_config.cron is None

    def test_default_values(self):
        """Test default values are set correctly."""
        config = ScheduleConfig(
            id="test",
            workflow_path="test.yaml",
        )
        assert config.name == ""
        assert config.description == ""
        assert config.inputs == {}
        assert config.dry_run is False
        assert config.timeout_seconds == 3600
        assert config.status == ScheduleStatus.ACTIVE
        assert config.run_count == 0

    def test_to_dict(self, schedule_config):
        """Test converting to dictionary."""
        data = schedule_config.to_dict()
        assert data["id"] == "test-schedule"
        assert data["workflow_path"] == "workflows/test.yaml"
        assert data["cron"] == "0 9 * * *"
        assert data["status"] == "active"
        assert "created_at" in data

    def test_to_dict_with_timestamps(self):
        """Test to_dict with last_run and next_run."""
        now = datetime.now(UTC)
        config = ScheduleConfig(
            id="test",
            workflow_path="test.yaml",
            last_run=now,
            next_run=now + timedelta(hours=1),
        )
        data = config.to_dict()
        assert data["last_run"] == now.isoformat()
        assert data["next_run"] is not None

    def test_from_dict_minimal(self):
        """Test creating from minimal dictionary."""
        data = {
            "id": "test",
            "workflow_path": "test.yaml",
        }
        config = ScheduleConfig.from_dict(data)
        assert config.id == "test"
        assert config.workflow_path == "test.yaml"
        assert config.status == ScheduleStatus.ACTIVE

    def test_from_dict_full(self):
        """Test creating from full dictionary."""
        now = datetime.now(UTC)
        data = {
            "id": "full-test",
            "workflow_path": "workflows/full.yaml",
            "name": "Full Test",
            "description": "A full test",
            "cron": "*/5 * * * *",
            "inputs": {"a": 1, "b": 2},
            "dry_run": True,
            "timeout_seconds": 7200,
            "status": "paused",
            "created_at": now.isoformat(),
            "last_run": now.isoformat(),
            "run_count": 5,
            "last_status": "success",
            "last_error": None,
        }
        config = ScheduleConfig.from_dict(data)
        assert config.id == "full-test"
        assert config.name == "Full Test"
        assert config.cron == "*/5 * * * *"
        assert config.dry_run is True
        assert config.status == ScheduleStatus.PAUSED
        assert config.run_count == 5

    def test_from_dict_with_status_enum(self):
        """Test from_dict handles status as enum."""
        data = {
            "id": "test",
            "workflow_path": "test.yaml",
            "status": ScheduleStatus.PAUSED,
        }
        config = ScheduleConfig.from_dict(data)
        assert config.status == ScheduleStatus.PAUSED

    def test_roundtrip(self, schedule_config):
        """Test to_dict/from_dict roundtrip."""
        data = schedule_config.to_dict()
        restored = ScheduleConfig.from_dict(data)
        assert restored.id == schedule_config.id
        assert restored.workflow_path == schedule_config.workflow_path
        assert restored.cron == schedule_config.cron


# =============================================================================
# Test ExecutionLog
# =============================================================================


class TestExecutionLog:
    """Tests for ExecutionLog dataclass."""

    def test_create_log(self):
        """Test creating an execution log."""
        now = datetime.now(UTC)
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=now,
        )
        assert log.schedule_id == "test"
        assert log.status == "running"
        assert log.completed_at is None

    def test_log_with_completion(self):
        """Test log with completion info."""
        now = datetime.now(UTC)
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=now,
            completed_at=now + timedelta(minutes=5),
            status="success",
            tokens_used=1000,
            steps_completed=3,
            steps_total=3,
        )
        assert log.status == "success"
        assert log.tokens_used == 1000
        assert log.steps_completed == 3

    def test_log_with_error(self):
        """Test log with error."""
        now = datetime.now(UTC)
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=now,
            completed_at=now,
            status="failed",
            error="Something went wrong",
        )
        assert log.status == "failed"
        assert log.error == "Something went wrong"

    def test_to_dict(self):
        """Test converting log to dictionary."""
        now = datetime.now(UTC)
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=now,
            completed_at=now + timedelta(minutes=1),
            status="success",
            tokens_used=500,
        )
        data = log.to_dict()
        assert data["schedule_id"] == "test"
        assert data["status"] == "success"
        assert data["tokens_used"] == 500
        assert "started_at" in data
        assert "completed_at" in data

    def test_to_dict_no_completion(self):
        """Test to_dict when not completed."""
        now = datetime.now(UTC)
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=now,
        )
        data = log.to_dict()
        assert data["completed_at"] is None


# =============================================================================
# Test WorkflowScheduler Initialization
# =============================================================================


class TestWorkflowSchedulerInit:
    """Tests for WorkflowScheduler initialization."""

    def test_init_creates_directories(self, temp_data_dir):
        """Test initialization creates data directories."""
        with patch("animus_kernel.executor.scheduler.BackgroundScheduler"):
            scheduler = WorkflowScheduler(data_dir=temp_data_dir)
            assert scheduler.data_dir.exists()
            assert scheduler.logs_dir.exists()

    def test_init_with_managers(self, temp_data_dir):
        """Test initialization with checkpoint and budget managers."""
        checkpoint_mgr = MagicMock()
        budget_mgr = MagicMock()

        with patch("animus_kernel.executor.scheduler.BackgroundScheduler"):
            scheduler = WorkflowScheduler(
                data_dir=temp_data_dir,
                checkpoint_manager=checkpoint_mgr,
                budget_manager=budget_mgr,
            )
            assert scheduler.checkpoint_manager is checkpoint_mgr
            assert scheduler.budget_manager is budget_mgr

    def test_init_with_callback(self, temp_data_dir):
        """Test initialization with execution callback."""
        callback = MagicMock()

        with patch("animus_kernel.executor.scheduler.BackgroundScheduler"):
            scheduler = WorkflowScheduler(
                data_dir=temp_data_dir,
                on_execution=callback,
            )
            assert scheduler.on_execution is callback

    def test_not_running_initially(self, scheduler):
        """Test scheduler is not running initially."""
        assert not scheduler.is_running


# =============================================================================
# Test WorkflowScheduler Start/Shutdown
# =============================================================================


class TestWorkflowSchedulerLifecycle:
    """Tests for scheduler start/shutdown."""

    def test_start(self, scheduler):
        """Test starting the scheduler."""
        scheduler._scheduler.running = False
        scheduler.start()
        scheduler._scheduler.start.assert_called_once()
        assert scheduler.is_running

    def test_start_loads_schedules(self, scheduler, temp_data_dir):
        """Test start loads existing schedules."""
        # Create a schedule file
        config = ScheduleConfig(
            id="existing",
            workflow_path="test.yaml",
            cron="0 * * * *",
        )
        with open(temp_data_dir / "existing.json", "w") as f:
            json.dump(config.to_dict(), f)

        scheduler._scheduler.running = False
        scheduler.start()

        assert "existing" in scheduler._schedules

    def test_start_skips_underscore_files(self, scheduler, temp_data_dir):
        """Test start skips files starting with underscore."""
        # Create a file that should be skipped
        with open(temp_data_dir / "_internal.json", "w") as f:
            json.dump({"id": "internal"}, f)

        scheduler._scheduler.running = False
        scheduler.start()

        assert "_internal" not in scheduler._schedules

    def test_shutdown(self, scheduler):
        """Test shutting down the scheduler."""
        scheduler._scheduler.running = True
        scheduler._running = True
        scheduler.shutdown(wait=True)
        scheduler._scheduler.shutdown.assert_called_once_with(wait=True)
        assert not scheduler.is_running

    def test_shutdown_not_running(self, scheduler):
        """Test shutdown when not running is safe."""
        scheduler._scheduler.running = False
        scheduler._running = False
        scheduler.shutdown()
        scheduler._scheduler.shutdown.assert_not_called()


# =============================================================================
# Test WorkflowScheduler Add/Remove
# =============================================================================


class TestWorkflowSchedulerAddRemove:
    """Tests for adding and removing schedules."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_add_schedule(self, mock_load, scheduler, schedule_config):
        """Test adding a schedule."""
        mock_load.return_value = MagicMock()

        result = scheduler.add(schedule_config)

        assert result.id == "test-schedule"
        assert "test-schedule" in scheduler._schedules
        # Check config was saved
        config_path = scheduler.data_dir / "test-schedule.json"
        assert config_path.exists()

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_add_schedule_validates_workflow(self, mock_load, scheduler):
        """Test add validates workflow exists."""
        mock_load.side_effect = FileNotFoundError("Not found")

        config = ScheduleConfig(
            id="invalid",
            workflow_path="nonexistent.yaml",
            cron="0 * * * *",
        )

        with pytest.raises(ValueError, match="Invalid workflow"):
            scheduler.add(config)

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_add_requires_cron_or_interval(self, mock_load, scheduler):
        """Test add requires either cron or interval."""
        mock_load.return_value = MagicMock()

        config = ScheduleConfig(
            id="invalid",
            workflow_path="test.yaml",
            # Neither cron nor interval_seconds
        )

        with pytest.raises(ValueError, match="cron.*interval"):
            scheduler.add(config)

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_add_registers_job_when_running(self, mock_load, scheduler, schedule_config):
        """Test add registers job when scheduler is running."""
        mock_load.return_value = MagicMock()
        scheduler._running = True

        scheduler.add(schedule_config)

        scheduler._scheduler.add_job.assert_called()

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_remove_schedule(self, mock_load, scheduler, schedule_config):
        """Test removing a schedule."""
        mock_load.return_value = MagicMock()
        scheduler.add(schedule_config)

        result = scheduler.remove("test-schedule")

        assert result is True
        assert "test-schedule" not in scheduler._schedules

    def test_remove_nonexistent(self, scheduler):
        """Test removing nonexistent schedule returns False."""
        result = scheduler.remove("nonexistent")
        assert result is False

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_remove_cleans_up_job(self, mock_load, scheduler, schedule_config):
        """Test remove cleans up APScheduler job."""
        mock_load.return_value = MagicMock()
        scheduler._scheduler.get_job.return_value = MagicMock()
        scheduler.add(schedule_config)

        scheduler.remove("test-schedule")

        scheduler._scheduler.remove_job.assert_called_with("wf_test-schedule")


# =============================================================================
# Test WorkflowScheduler Get/List
# =============================================================================


class TestWorkflowSchedulerGetList:
    """Tests for getting and listing schedules."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_get_schedule(self, mock_load, scheduler, schedule_config):
        """Test getting a schedule by ID."""
        mock_load.return_value = MagicMock()
        scheduler.add(schedule_config)

        result = scheduler.get("test-schedule")

        assert result is not None
        assert result.id == "test-schedule"

    def test_get_nonexistent(self, scheduler):
        """Test getting nonexistent schedule returns None."""
        result = scheduler.get("nonexistent")
        assert result is None

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_list_schedules(self, mock_load, scheduler):
        """Test listing all schedules."""
        mock_load.return_value = MagicMock()

        scheduler.add(
            ScheduleConfig(
                id="sched1",
                workflow_path="test.yaml",
                cron="0 * * * *",
            )
        )
        scheduler.add(
            ScheduleConfig(
                id="sched2",
                workflow_path="test.yaml",
                interval_seconds=60,
            )
        )

        result = scheduler.list()

        assert len(result) == 2
        ids = [s.id for s in result]
        assert "sched1" in ids
        assert "sched2" in ids


# =============================================================================
# Test WorkflowScheduler Pause/Resume
# =============================================================================


class TestWorkflowSchedulerPauseResume:
    """Tests for pausing and resuming schedules."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_pause_schedule(self, mock_load, scheduler, schedule_config):
        """Test pausing a schedule."""
        mock_load.return_value = MagicMock()
        scheduler._scheduler.get_job.return_value = MagicMock()
        scheduler.add(schedule_config)

        result = scheduler.pause("test-schedule")

        assert result is True
        config = scheduler.get("test-schedule")
        assert config.status == ScheduleStatus.PAUSED
        scheduler._scheduler.pause_job.assert_called_with("wf_test-schedule")

    def test_pause_nonexistent(self, scheduler):
        """Test pausing nonexistent schedule returns False."""
        result = scheduler.pause("nonexistent")
        assert result is False

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_resume_schedule(self, mock_load, scheduler, schedule_config):
        """Test resuming a paused schedule."""
        mock_load.return_value = MagicMock()
        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now(UTC) + timedelta(hours=1)
        scheduler._scheduler.get_job.return_value = mock_job
        scheduler.add(schedule_config)
        scheduler.pause("test-schedule")

        result = scheduler.resume("test-schedule")

        assert result is True
        config = scheduler.get("test-schedule")
        assert config.status == ScheduleStatus.ACTIVE
        scheduler._scheduler.resume_job.assert_called_with("wf_test-schedule")

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_resume_registers_job_if_missing(self, mock_load, scheduler, schedule_config):
        """Test resume registers job if not in scheduler."""
        mock_load.return_value = MagicMock()
        scheduler.add(schedule_config)
        scheduler._schedules["test-schedule"].status = ScheduleStatus.PAUSED
        # Reset get_job to return None for this test
        scheduler._scheduler.get_job.side_effect = lambda job_id: None

        scheduler.resume("test-schedule")

        scheduler._scheduler.add_job.assert_called()

    def test_resume_nonexistent(self, scheduler):
        """Test resuming nonexistent schedule returns False."""
        result = scheduler.resume("nonexistent")
        assert result is False


# =============================================================================
# Test WorkflowScheduler Trigger
# =============================================================================


class TestWorkflowSchedulerTrigger:
    """Tests for manually triggering schedules."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    @patch("animus_kernel.executor.scheduler.WorkflowExecutor")
    def test_trigger_schedule(self, mock_executor_class, mock_load, scheduler, schedule_config):
        """Test manually triggering a schedule."""
        mock_load.return_value = MagicMock(steps=[])
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            workflow_name="test",
            status="success",
        )
        mock_executor_class.return_value = mock_executor

        scheduler._schedules["test-schedule"] = schedule_config

        result = scheduler.trigger("test-schedule")

        assert result is not None
        assert result.status == "success"

    def test_trigger_nonexistent(self, scheduler):
        """Test triggering nonexistent schedule returns None."""
        result = scheduler.trigger("nonexistent")
        assert result is None


# =============================================================================
# Test WorkflowScheduler Execution
# =============================================================================


class TestWorkflowSchedulerExecution:
    """Tests for workflow execution."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    @patch("animus_kernel.executor.scheduler.WorkflowExecutor")
    def test_execute_success(self, mock_executor_class, mock_load, scheduler, schedule_config):
        """Test successful execution."""
        mock_workflow = MagicMock()
        mock_workflow.steps = [MagicMock(), MagicMock()]
        mock_load.return_value = mock_workflow

        mock_result = ExecutionResult(
            workflow_name="test",
            status="success",
            total_tokens=500,
        )
        mock_result.steps = [
            MagicMock(status=MagicMock(value="success")),
            MagicMock(status=MagicMock(value="success")),
        ]
        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        scheduler._schedules["test-schedule"] = schedule_config

        result = scheduler._execute(schedule_config)

        assert result.status == "success"
        assert schedule_config.run_count == 1
        assert schedule_config.last_status == "success"

    @patch("animus_kernel.executor.scheduler.load_workflow")
    @patch("animus_kernel.executor.scheduler.WorkflowExecutor")
    def test_execute_failure(self, mock_executor_class, mock_load, scheduler, schedule_config):
        """Test execution with error."""
        mock_load.side_effect = Exception("Workflow load failed")

        scheduler._schedules["test-schedule"] = schedule_config

        result = scheduler._execute(schedule_config)

        assert result.status == "failed"
        assert schedule_config.last_status == "failed"
        assert "Workflow load failed" in schedule_config.last_error

    @patch("animus_kernel.executor.scheduler.load_workflow")
    @patch("animus_kernel.executor.scheduler.WorkflowExecutor")
    def test_execute_calls_callback(
        self, mock_executor_class, mock_load, scheduler, schedule_config
    ):
        """Test execution calls callback."""
        mock_load.return_value = MagicMock(steps=[])
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            workflow_name="test",
            status="success",
        )
        mock_executor_class.return_value = mock_executor

        callback = MagicMock()
        scheduler.on_execution = callback
        scheduler._schedules["test-schedule"] = schedule_config

        scheduler._execute(schedule_config)

        callback.assert_called_once()

    @patch("animus_kernel.executor.scheduler.load_workflow")
    @patch("animus_kernel.executor.scheduler.WorkflowExecutor")
    def test_execute_saves_log(self, mock_executor_class, mock_load, scheduler, schedule_config):
        """Test execution saves log file."""
        mock_load.return_value = MagicMock(steps=[])
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            workflow_name="test",
            status="success",
        )
        mock_executor_class.return_value = mock_executor

        scheduler._schedules["test-schedule"] = schedule_config

        scheduler._execute(schedule_config)

        log_files = list(scheduler.logs_dir.glob("test-schedule_*.json"))
        assert len(log_files) == 1


# =============================================================================
# Test WorkflowScheduler History
# =============================================================================


class TestWorkflowSchedulerHistory:
    """Tests for execution history."""

    def test_get_history_empty(self, scheduler):
        """Test getting history with no logs."""
        result = scheduler.get_history("test")
        assert result == []

    def test_get_history(self, scheduler):
        """Test getting execution history."""
        # Create some log files
        now = datetime.now(UTC)
        for i in range(3):
            log = ExecutionLog(
                schedule_id="test",
                workflow_path="test.yaml",
                started_at=now - timedelta(hours=i),
                completed_at=now - timedelta(hours=i) + timedelta(minutes=5),
                status="success",
            )
            timestamp = log.started_at.strftime("%Y%m%d_%H%M%S")
            log_path = scheduler.logs_dir / f"test_{timestamp}.json"
            with open(log_path, "w") as f:
                json.dump(log.to_dict(), f)

        result = scheduler.get_history("test")

        assert len(result) == 3
        assert all(log.schedule_id == "test" for log in result)

    def test_get_history_limit(self, scheduler):
        """Test history respects limit."""
        now = datetime.now(UTC)
        for i in range(10):
            log = ExecutionLog(
                schedule_id="test",
                workflow_path="test.yaml",
                started_at=now - timedelta(hours=i),
            )
            timestamp = log.started_at.strftime("%Y%m%d_%H%M%S")
            log_path = scheduler.logs_dir / f"test_{timestamp}.json"
            with open(log_path, "w") as f:
                json.dump(log.to_dict(), f)

        result = scheduler.get_history("test", limit=5)

        assert len(result) == 5

    def test_get_history_handles_invalid_files(self, scheduler):
        """Test history handles corrupted log files."""
        # Create a valid log
        log = ExecutionLog(
            schedule_id="test",
            workflow_path="test.yaml",
            started_at=datetime.now(UTC),
        )
        with open(scheduler.logs_dir / "test_20240101_120000.json", "w") as f:
            json.dump(log.to_dict(), f)

        # Create an invalid log
        with open(scheduler.logs_dir / "test_20240101_130000.json", "w") as f:
            f.write("invalid json")

        result = scheduler.get_history("test")

        # Should still return the valid log
        assert len(result) == 1


# =============================================================================
# Test WorkflowScheduler Job Registration
# =============================================================================


class TestWorkflowSchedulerJobRegistration:
    """Tests for APScheduler job registration."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_register_cron_job(self, mock_load, scheduler, schedule_config):
        """Test registering a cron job."""
        mock_load.return_value = MagicMock()
        # No existing job
        scheduler._scheduler.get_job.side_effect = lambda job_id: None

        scheduler._register_job(schedule_config)

        scheduler._scheduler.add_job.assert_called_once()
        call_kwargs = scheduler._scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "wf_test-schedule"

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_register_interval_job(self, mock_load, scheduler, interval_schedule_config):
        """Test registering an interval job."""
        mock_load.return_value = MagicMock()
        # No existing job
        scheduler._scheduler.get_job.side_effect = lambda job_id: None

        scheduler._register_job(interval_schedule_config)

        scheduler._scheduler.add_job.assert_called_once()

    def test_register_replaces_existing(self, scheduler, schedule_config):
        """Test registering replaces existing job."""
        scheduler._scheduler.get_job.return_value = MagicMock()

        scheduler._register_job(schedule_config)

        scheduler._scheduler.remove_job.assert_called_with("wf_test-schedule")

    def test_register_no_schedule(self, scheduler):
        """Test registering with no cron or interval does nothing."""
        config = ScheduleConfig(
            id="empty",
            workflow_path="test.yaml",
        )
        # No existing job
        scheduler._scheduler.get_job.side_effect = lambda job_id: None

        scheduler._register_job(config)

        scheduler._scheduler.add_job.assert_not_called()


# =============================================================================
# Test WorkflowScheduler Persistence
# =============================================================================


class TestWorkflowSchedulerPersistence:
    """Tests for schedule persistence."""

    @patch("animus_kernel.executor.scheduler.load_workflow")
    def test_save_schedule(self, mock_load, scheduler, schedule_config):
        """Test saving schedule to disk."""
        mock_load.return_value = MagicMock()
        scheduler.add(schedule_config)

        config_path = scheduler.data_dir / "test-schedule.json"
        assert config_path.exists()

        with open(config_path) as f:
            data = json.load(f)
        assert data["id"] == "test-schedule"

    def test_load_schedules(self, scheduler, temp_data_dir):
        """Test loading schedules from disk."""
        # Create schedule files
        config1 = ScheduleConfig(id="sched1", workflow_path="test.yaml", cron="0 * * * *")
        config2 = ScheduleConfig(id="sched2", workflow_path="test.yaml", interval_seconds=60)

        with open(temp_data_dir / "sched1.json", "w") as f:
            json.dump(config1.to_dict(), f)
        with open(temp_data_dir / "sched2.json", "w") as f:
            json.dump(config2.to_dict(), f)

        scheduler._load_schedules()

        assert "sched1" in scheduler._schedules
        assert "sched2" in scheduler._schedules

    def test_load_handles_invalid_files(self, scheduler, temp_data_dir):
        """Test load handles invalid schedule files."""
        # Create invalid file
        with open(temp_data_dir / "invalid.json", "w") as f:
            f.write("not json")

        # Should not raise
        scheduler._load_schedules()

        assert "invalid" not in scheduler._schedules
