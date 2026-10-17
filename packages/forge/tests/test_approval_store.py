"""Tests for ResumeTokenStore — approval token CRUD and expiry."""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, "src")

from animus_forge.state.backends import SQLiteBackend
from animus_forge.workflow.approval_store import (
    ResumeTokenStore,
    get_approval_store,
    reset_approval_store,
)


@pytest.fixture
def backend():
    """Create a temp SQLite backend with migration 014 applied."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "test.db")
        backend = SQLiteBackend(db_path=db_path)

        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "014_approval_tokens.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        backend.executescript(sql)

        yield backend
        backend.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def store(backend):
    """Create a ResumeTokenStore with the test backend."""
    return ResumeTokenStore(backend)


# =============================================================================
# TestCreateToken
# =============================================================================


class TestCreateToken:
    """Tests for creating approval tokens."""

    def test_create_returns_hex_token(self, store):
        """Token is a 16-char hex string."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="approval_gate",
            next_step_id="apply_changes",
            prompt="Apply changes?",
        )
        assert len(token) == 16
        assert all(c in "0123456789abcdef" for c in token)

    def test_create_persists_to_db(self, store):
        """Token data is retrievable after creation."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="approval_gate",
            next_step_id="apply_changes",
            prompt="Apply changes?",
            preview={"analyze": {"findings": ["issue1"]}},
            context={"step1_output": "result"},
            timeout_hours=48,
        )

        data = store.get_by_token(token)
        assert data is not None
        assert data["execution_id"] == "exec-1"
        assert data["workflow_id"] == "wf-1"
        assert data["step_id"] == "approval_gate"
        assert data["next_step_id"] == "apply_changes"
        assert data["prompt"] == "Apply changes?"
        assert data["status"] == "pending"
        assert data["preview"] == {"analyze": {"findings": ["issue1"]}}
        assert data["context"] == {"step1_output": "result"}

    def test_create_unique_tokens(self, store):
        """Multiple tokens are unique."""
        tokens = set()
        for _ in range(10):
            token = store.create_token(
                execution_id="exec-1",
                workflow_id="wf-1",
                step_id="gate",
                next_step_id="next",
            )
            tokens.add(token)
        assert len(tokens) == 10

    def test_create_with_default_timeout(self, store):
        """Default timeout is 24 hours."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        data = store.get_by_token(token)
        timeout = datetime.fromisoformat(data["timeout_at"])
        # Should be roughly 24h from now (within 5 minutes)
        delta = timeout - datetime.now()
        assert timedelta(hours=23, minutes=55) < delta < timedelta(hours=24, minutes=5)


# =============================================================================
# TestGetByToken
# =============================================================================


class TestGetByToken:
    """Tests for loading tokens."""

    def test_missing_token_returns_none(self, store):
        """Nonexistent token returns None."""
        assert store.get_by_token("nonexistent") is None

    def test_expired_token_returns_none(self, store):
        """Expired token returns None and gets marked expired."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
            timeout_hours=0,  # Expired immediately
        )

        # Force the timeout to be in the past
        with store.backend.transaction():
            store.backend.execute(
                "UPDATE approval_tokens SET timeout_at = ? WHERE token = ?",
                ((datetime.now() - timedelta(hours=1)).isoformat(), token),
            )

        assert store.get_by_token(token) is None

        # Verify it was marked expired
        row = store.backend.fetchone("SELECT status FROM approval_tokens WHERE token = ?", (token,))
        assert row["status"] == "expired"

    def test_json_fields_parsed(self, store):
        """Preview and context are deserialized from JSON."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
            preview={"key": [1, 2, 3]},
            context={"nested": {"data": True}},
        )
        data = store.get_by_token(token)
        assert data["preview"] == {"key": [1, 2, 3]}
        assert data["context"] == {"nested": {"data": True}}


# =============================================================================
# TestApproveReject
# =============================================================================


class TestApproveReject:
    """Tests for approve/reject operations."""

    def test_approve_pending_token(self, store):
        """Approving a pending token succeeds."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        assert store.approve(token, approved_by="user@test.com") is True

        data = store.get_by_token(token)
        assert data["status"] == "approved"
        assert data["decided_by"] == "user@test.com"
        assert data["decided_at"] is not None

    def test_approve_nonpending_fails(self, store):
        """Approving an already-approved token returns False."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        store.approve(token)
        assert store.approve(token) is False  # Already approved

    def test_reject_pending_token(self, store):
        """Rejecting a pending token succeeds."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        assert store.reject(token, rejected_by="admin") is True

        data = store.get_by_token(token)
        assert data["status"] == "rejected"
        assert data["decided_by"] == "admin"

    def test_reject_nonpending_fails(self, store):
        """Rejecting an already-rejected token returns False."""
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        store.reject(token)
        assert store.reject(token) is False

    def test_approve_nonexistent_returns_false(self, store):
        """Approving a nonexistent token returns False."""
        assert store.approve("nonexistent") is False

    def test_reject_nonexistent_returns_false(self, store):
        """Rejecting a nonexistent token returns False."""
        assert store.reject("nonexistent") is False


# =============================================================================
# TestExpireStale
# =============================================================================


class TestExpireStale:
    """Tests for bulk expiry."""

    def test_expire_stale_tokens(self, store):
        """Tokens past timeout_at are bulk-expired."""
        # Create a token that's already expired
        token = store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate",
            next_step_id="next",
        )
        with store.backend.transaction():
            store.backend.execute(
                "UPDATE approval_tokens SET timeout_at = ? WHERE token = ?",
                ((datetime.now() - timedelta(hours=1)).isoformat(), token),
            )

        # Create a valid token
        valid_token = store.create_token(
            execution_id="exec-2",
            workflow_id="wf-2",
            step_id="gate",
            next_step_id="next",
            timeout_hours=24,
        )

        expired_count = store.expire_stale()
        assert expired_count == 1

        # Expired token is gone
        row = store.backend.fetchone("SELECT status FROM approval_tokens WHERE token = ?", (token,))
        assert row["status"] == "expired"

        # Valid token still pending
        assert store.get_by_token(valid_token) is not None


# =============================================================================
# TestGetByExecution
# =============================================================================


class TestGetByExecution:
    """Tests for querying tokens by execution."""

    def test_get_by_execution(self, store):
        """Returns all tokens for an execution."""
        store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate1",
            next_step_id="next1",
        )
        store.create_token(
            execution_id="exec-1",
            workflow_id="wf-1",
            step_id="gate2",
            next_step_id="next2",
        )
        store.create_token(
            execution_id="exec-2",
            workflow_id="wf-2",
            step_id="gate3",
            next_step_id="next3",
        )

        tokens = store.get_by_execution("exec-1")
        assert len(tokens) == 2
        step_ids = {t["step_id"] for t in tokens}
        assert step_ids == {"gate1", "gate2"}

    def test_get_by_execution_empty(self, store):
        """Empty result for unknown execution."""
        assert store.get_by_execution("nonexistent") == []


# =============================================================================
# TestSingleton
# =============================================================================


class TestSingleton:
    """Tests for get_approval_store/reset_approval_store."""

    def test_singleton_returns_same_instance(self):
        """get_approval_store returns the same instance."""
        reset_approval_store()
        with patch("animus_forge.state.database.get_database") as mock_db:
            mock_db.return_value = SQLiteBackend(db_path=":memory:")
            s1 = get_approval_store()
            s2 = get_approval_store()
            assert s1 is s2
        reset_approval_store()

    def test_reset_clears_singleton(self):
        """reset_approval_store clears the singleton."""
        reset_approval_store()
        with patch("animus_forge.state.database.get_database") as mock_db:
            mock_db.return_value = SQLiteBackend(db_path=":memory:")
            s1 = get_approval_store()
            reset_approval_store()
            s2 = get_approval_store()
            assert s1 is not s2
        reset_approval_store()


def test_approval_decision_survives_connection_reopen(store):
    """A response to an approval request must be durable across worker restarts."""
    token = store.create_token(
        execution_id="durable-execution",
        workflow_id="workflow",
        step_id="approval",
        next_step_id="apply",
    )
    store.backend.close()
    assert store.get_by_token(token)["status"] == "pending"
    assert store.approve(token, approved_by="reviewer") is True
    store.backend.close()
    decision = store.get_by_token(token)
    assert decision["status"] == "approved"
    assert decision["decided_by"] == "reviewer"
