"""Tests for workflow execution tracking module."""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, "src")

from animus_forge.executions.manager import ExecutionManager
from animus_forge.executions.models import (
    Execution,
    ExecutionLog,
    ExecutionMetrics,
    ExecutionStatus,
    LogLevel,
    PaginatedResponse,
)
from animus_forge.state.backends import SQLiteBackend


class TestExecutionModels:
    """Tests for execution Pydantic models."""

    def test_execution_status_values(self):
        """ExecutionStatus has all expected values."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.PAUSED.value == "paused"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.CANCELLED.value == "cancelled"

    def test_log_level_values(self):
        """LogLevel has all expected values."""
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"

    def test_execution_default_values(self):
        """Execution has correct default values."""
        execution = Execution(
            id="test-id",
            workflow_id="wf-1",
            workflow_name="Test Workflow",
        )

        assert execution.status == ExecutionStatus.PENDING
        assert execution.started_at is None
        assert execution.completed_at is None
        assert execution.current_step is None
        assert execution.progress == 0
        assert execution.checkpoint_id is None
        assert execution.variables == {}
        assert execution.error is None
        assert execution.logs == []
        assert execution.metrics is None

    def test_execution_with_all_fields(self):
        """Execution can be created with all fields."""
        now = datetime.now()
        execution = Execution(
            id="exec-123",
            workflow_id="wf-456",
            workflow_name="Full Workflow",
            status=ExecutionStatus.RUNNING,
            started_at=now,
            current_step="step-1",
            progress=50,
            variables={"input": "value"},
            created_at=now,
        )

        assert execution.id == "exec-123"
        assert execution.status == ExecutionStatus.RUNNING
        assert execution.progress == 50
        assert execution.variables == {"input": "value"}

    def test_execution_log_creation(self):
        """ExecutionLog can be created correctly."""
        log = ExecutionLog(
            execution_id="exec-1",
            level=LogLevel.INFO,
            message="Test message",
            step_id="step-1",
            metadata={"key": "value"},
        )

        assert log.execution_id == "exec-1"
        assert log.level == LogLevel.INFO
        assert log.message == "Test message"
        assert log.step_id == "step-1"
        assert log.metadata == {"key": "value"}

    def test_execution_metrics_defaults(self):
        """ExecutionMetrics has correct defaults."""
        metrics = ExecutionMetrics(execution_id="exec-1")

        assert metrics.total_tokens == 0
        assert metrics.total_cost_cents == 0
        assert metrics.duration_ms == 0
        assert metrics.steps_completed == 0
        assert metrics.steps_failed == 0

    def test_paginated_response_create(self):
        """PaginatedResponse.create calculates total_pages correctly."""
        response = PaginatedResponse.create(
            data=["a", "b", "c"],
            total=25,
            page=1,
            page_size=10,
        )

        assert response.data == ["a", "b", "c"]
        assert response.total == 25
        assert response.page == 1
        assert response.page_size == 10
        assert response.total_pages == 3  # ceil(25/10)

    def test_paginated_response_single_page(self):
        """PaginatedResponse handles single page correctly."""
        response = PaginatedResponse.create(
            data=[1, 2, 3],
            total=3,
            page=1,
            page_size=10,
        )

        assert response.total_pages == 1

    def test_paginated_response_empty(self):
        """PaginatedResponse handles empty data."""
        response = PaginatedResponse.create(
            data=[],
            total=0,
            page=1,
            page_size=10,
        )

        assert response.total_pages == 0


class TestExecutionManager:
    """Tests for ExecutionManager class."""

    @pytest.fixture
    def backend(self):
        """Create a temporary SQLite backend with schema."""
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "test.db")
            backend = SQLiteBackend(db_path=db_path)

            # Create schema
            backend.executescript("""
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    current_step TEXT,
                    progress INTEGER DEFAULT 0,
                    checkpoint_id TEXT,
                    variables TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    step_id TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS execution_metrics (
                    execution_id TEXT PRIMARY KEY,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost_cents INTEGER DEFAULT 0,
                    duration_ms INTEGER DEFAULT 0,
                    steps_completed INTEGER DEFAULT 0,
                    steps_failed INTEGER DEFAULT 0
                );
            """)

            yield backend
            backend.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.fixture
    def manager(self, backend):
        """Create an ExecutionManager."""
        return ExecutionManager(backend=backend)

    def test_create_execution(self, manager, backend):
        """create_execution creates and persists an execution."""
        execution = manager.create_execution(
            workflow_id="wf-test",
            workflow_name="Test Workflow",
            variables={"input": "value"},
        )

        assert execution.id is not None
        assert execution.workflow_id == "wf-test"
        assert execution.workflow_name == "Test Workflow"
        assert execution.status == ExecutionStatus.PENDING
        assert execution.variables == {"input": "value"}

        # Verify in database
        row = backend.fetchone("SELECT * FROM executions WHERE id = ?", (execution.id,))
        assert row is not None
        assert row["workflow_id"] == "wf-test"
        assert row["status"] == "pending"

    def test_create_execution_without_variables(self, manager):
        """create_execution works without variables."""
        execution = manager.create_execution(
            workflow_id="wf-1",
            workflow_name="No Variables",
        )

        assert execution.variables == {}

    def test_get_execution(self, manager):
        """get_execution retrieves an execution by ID."""
        created = manager.create_execution(
            workflow_id="wf-1",
            workflow_name="Test",
        )

        retrieved = manager.get_execution(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.workflow_id == "wf-1"

    def test_get_execution_not_found(self, manager):
        """get_execution returns None for nonexistent ID."""
        result = manager.get_execution("nonexistent-id")
        assert result is None

    def test_list_executions_pagination(self, manager):
        """list_executions returns paginated results."""
        # Create multiple executions
        for i in range(15):
            manager.create_execution(
                workflow_id=f"wf-{i}",
                workflow_name=f"Workflow {i}",
            )

        # Get first page
        page1 = manager.list_executions(page=1, page_size=10)
        assert len(page1.data) == 10
        assert page1.total == 15
        assert page1.page == 1
        assert page1.total_pages == 2

        # Get second page
        page2 = manager.list_executions(page=2, page_size=10)
        assert len(page2.data) == 5
        assert page2.page == 2

    def test_list_executions_filter_by_status(self, manager):
        """list_executions filters by status."""
        exec1 = manager.create_execution("wf-1", "Test 1")
        exec2 = manager.create_execution("wf-2", "Test 2")

        # Start one execution
        manager.start_execution(exec1.id)

        # Filter by running
        running = manager.list_executions(status=ExecutionStatus.RUNNING)
        assert running.total == 1
        assert running.data[0].id == exec1.id

        # Filter by pending
        pending = manager.list_executions(status=ExecutionStatus.PENDING)
        assert pending.total == 1
        assert pending.data[0].id == exec2.id

    def test_list_executions_filter_by_workflow(self, manager):
        """list_executions filters by workflow_id."""
        manager.create_execution("wf-alpha", "Alpha")
        manager.create_execution("wf-alpha", "Alpha 2")
        manager.create_execution("wf-beta", "Beta")

        alpha = manager.list_executions(workflow_id="wf-alpha")
        assert alpha.total == 2

        beta = manager.list_executions(workflow_id="wf-beta")
        assert beta.total == 1

    def test_start_execution(self, manager):
        """start_execution transitions from pending to running."""
        execution = manager.create_execution("wf-1", "Test")
        assert execution.status == ExecutionStatus.PENDING

        updated = manager.start_execution(execution.id)

        assert updated is not None
        assert updated.status == ExecutionStatus.RUNNING
        assert updated.started_at is not None

    def test_pause_execution(self, manager):
        """pause_execution transitions from running to paused."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)

        paused = manager.pause_execution(execution.id)

        assert paused is not None
        assert paused.status == ExecutionStatus.PAUSED

    def test_resume_execution(self, manager):
        """resume_execution transitions from paused to running."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)
        manager.pause_execution(execution.id)

        resumed = manager.resume_execution(execution.id)

        assert resumed is not None
        assert resumed.status == ExecutionStatus.RUNNING

    def test_cancel_execution_from_pending(self, manager):
        """cancel_execution works from pending state."""
        execution = manager.create_execution("wf-1", "Test")

        result = manager.cancel_execution(execution.id)

        assert result is True
        updated = manager.get_execution(execution.id)
        assert updated.status == ExecutionStatus.CANCELLED
        assert updated.completed_at is not None

    def test_cancel_execution_from_running(self, manager):
        """cancel_execution works from running state."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)

        result = manager.cancel_execution(execution.id)

        assert result is True
        updated = manager.get_execution(execution.id)
        assert updated.status == ExecutionStatus.CANCELLED

    def test_cancel_execution_already_completed(self, manager):
        """cancel_execution returns False for completed execution."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)
        manager.complete_execution(execution.id)

        result = manager.cancel_execution(execution.id)

        assert result is False

    def test_complete_execution_success(self, manager):
        """complete_execution marks as completed."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)

        completed = manager.complete_execution(execution.id)

        assert completed is not None
        assert completed.status == ExecutionStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.progress == 100
        assert completed.error is None

    def test_complete_execution_with_error(self, manager):
        """complete_execution marks as failed with error."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)

        failed = manager.complete_execution(execution.id, error="Something went wrong")

        assert failed is not None
        assert failed.status == ExecutionStatus.FAILED
        assert failed.error == "Something went wrong"

    def test_update_progress(self, manager):
        """update_progress updates progress and current_step."""
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)

        manager.update_progress(execution.id, progress=50, current_step="step-2")

        updated = manager.get_execution(execution.id)
        assert updated.progress == 50
        assert updated.current_step == "step-2"

    def test_update_variables(self, manager):
        """update_variables updates the variables dict."""
        execution = manager.create_execution("wf-1", "Test", variables={"initial": "value"})

        manager.update_variables(execution.id, {"initial": "value", "new": "data"})

        updated = manager.get_execution(execution.id)
        assert updated.variables == {"initial": "value", "new": "data"}

    def test_save_checkpoint(self, manager):
        """save_checkpoint saves checkpoint ID."""
        execution = manager.create_execution("wf-1", "Test")

        manager.save_checkpoint(execution.id, "checkpoint-123")

        updated = manager.get_execution(execution.id)
        assert updated.checkpoint_id == "checkpoint-123"

    def test_add_log(self, manager):
        """add_log creates log entries."""
        execution = manager.create_execution("wf-1", "Test")

        manager.add_log(
            execution.id,
            LogLevel.INFO,
            "Test message",
            step_id="step-1",
            metadata={"key": "value"},
        )

        logs = manager.get_logs(execution.id)
        assert len(logs) >= 1
        # Find our log (there may be automatic logs)
        test_log = next((log for log in logs if log.message == "Test message"), None)
        assert test_log is not None
        assert test_log.level == LogLevel.INFO
        assert test_log.step_id == "step-1"
        assert test_log.metadata == {"key": "value"}

    def test_get_logs_with_limit(self, manager):
        """get_logs respects limit parameter."""
        execution = manager.create_execution("wf-1", "Test")

        for i in range(10):
            manager.add_log(execution.id, LogLevel.DEBUG, f"Message {i}")

        logs = manager.get_logs(execution.id, limit=5)
        assert len(logs) == 5

    def test_get_logs_filter_by_level(self, manager):
        """get_logs filters by log level."""
        execution = manager.create_execution("wf-1", "Test")

        manager.add_log(execution.id, LogLevel.DEBUG, "Debug message")
        manager.add_log(execution.id, LogLevel.INFO, "Info message")
        manager.add_log(execution.id, LogLevel.ERROR, "Error message")

        error_logs = manager.get_logs(execution.id, level=LogLevel.ERROR)
        assert all(log.level == LogLevel.ERROR for log in error_logs)

    def test_update_metrics(self, manager):
        """update_metrics increments metric values."""
        execution = manager.create_execution("wf-1", "Test")

        manager.update_metrics(
            execution.id,
            tokens=100,
            cost_cents=5,
            duration_ms=1000,
            steps_completed=1,
        )

        metrics = manager.get_metrics(execution.id)
        assert metrics is not None
        assert metrics.total_tokens == 100
        assert metrics.total_cost_cents == 5
        assert metrics.duration_ms == 1000
        assert metrics.steps_completed == 1

        # Update again (incremental)
        manager.update_metrics(execution.id, tokens=50, steps_completed=1)

        metrics = manager.get_metrics(execution.id)
        assert metrics.total_tokens == 150
        assert metrics.steps_completed == 2

    def test_get_metrics_not_found(self, manager):
        """get_metrics returns None for nonexistent execution."""
        metrics = manager.get_metrics("nonexistent")
        assert metrics is None

    def test_delete_execution(self, manager):
        """delete_execution removes execution and related data."""
        execution = manager.create_execution("wf-1", "Test")
        manager.add_log(execution.id, LogLevel.INFO, "Test log")

        result = manager.delete_execution(execution.id)

        assert result is True
        assert manager.get_execution(execution.id) is None

    def test_delete_execution_not_found(self, manager):
        """delete_execution returns False for nonexistent ID."""
        result = manager.delete_execution("nonexistent")
        assert result is False

    def test_cleanup_old_executions(self, manager, backend):
        """cleanup_old_executions removes old completed executions."""
        # Create and complete an execution
        execution = manager.create_execution("wf-1", "Test")
        manager.start_execution(execution.id)
        manager.complete_execution(execution.id)

        # Manually backdate the completed_at
        old_time = (datetime.now() - timedelta(hours=200)).isoformat()
        with backend.transaction():
            backend.execute(
                "UPDATE executions SET completed_at = ? WHERE id = ?",
                (old_time, execution.id),
            )

        # Cleanup (168 hours = 7 days)
        deleted = manager.cleanup_old_executions(max_age_hours=168)

        assert deleted >= 1
        assert manager.get_execution(execution.id) is None

    def test_execution_lifecycle(self, manager):
        """Full execution lifecycle test."""
        # Create
        execution = manager.create_execution(
            "wf-test",
            "Lifecycle Test",
            variables={"input": "data"},
        )
        assert execution.status == ExecutionStatus.PENDING

        # Start
        manager.start_execution(execution.id)
        execution = manager.get_execution(execution.id)
        assert execution.status == ExecutionStatus.RUNNING

        # Update progress
        manager.update_progress(execution.id, 25, "step-1")
        manager.add_log(execution.id, LogLevel.INFO, "Step 1 started", "step-1")

        manager.update_progress(execution.id, 50, "step-2")
        manager.update_metrics(execution.id, tokens=100, steps_completed=1)

        # Pause
        manager.pause_execution(execution.id)
        execution = manager.get_execution(execution.id)
        assert execution.status == ExecutionStatus.PAUSED

        # Save checkpoint
        manager.save_checkpoint(execution.id, "checkpoint-1")

        # Resume
        manager.resume_execution(execution.id)
        execution = manager.get_execution(execution.id)
        assert execution.status == ExecutionStatus.RUNNING

        # Complete
        manager.update_progress(execution.id, 100, "step-3")
        manager.update_metrics(execution.id, tokens=50, steps_completed=1)
        manager.complete_execution(execution.id)

        # Final state
        execution = manager.get_execution(execution.id)
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.progress == 100

        metrics = manager.get_metrics(execution.id)
        assert metrics.total_tokens == 150
        assert metrics.steps_completed == 2

        logs = manager.get_logs(execution.id)
        assert len(logs) >= 1
