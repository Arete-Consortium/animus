"""Tests for WebhookManager database operations."""

import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

from animus_forge.state.backends import SQLiteBackend
from animus_forge.webhooks.webhook_manager import (
    PayloadMapping,
    Webhook,
    WebhookManager,
    WebhookTriggerLog,
)


class TestWebhookManager:
    """Tests for WebhookManager class."""

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
        """Create a WebhookManager with mocked workflow engine."""
        with patch("animus_forge.webhooks.webhook_manager.get_database", return_value=backend):
            with patch(
                "animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter"
            ) as mock_engine:
                mock_engine.return_value.load_workflow.return_value = MagicMock()
                manager = WebhookManager(backend=backend)
                yield manager

    def test_init_creates_schema(self, backend):
        """WebhookManager creates tables on init."""
        with patch("animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter"):
            WebhookManager(backend=backend)

        # Verify tables exist
        webhooks = backend.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='webhooks'"
        )
        assert webhooks is not None

        logs = backend.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='webhook_logs'"
        )
        assert logs is not None

    def test_create_webhook(self, manager, backend):
        """create_webhook() creates webhook in database."""
        webhook = Webhook(
            id="test-webhook",
            name="Test Webhook",
            workflow_id="test-workflow",
        )

        result = manager.create_webhook(webhook)
        assert result is True

        # Verify in database
        row = backend.fetchone("SELECT * FROM webhooks WHERE id = ?", ("test-webhook",))
        assert row is not None
        assert row["name"] == "Test Webhook"
        assert row["workflow_id"] == "test-workflow"
        assert row["secret"] is not None

    def test_create_webhook_with_mappings(self, manager, backend):
        """create_webhook() persists payload mappings."""
        webhook = Webhook(
            id="mapping-webhook",
            name="Mapping Webhook",
            workflow_id="test-workflow",
            payload_mappings=[
                PayloadMapping(source_path="data.user.id", target_variable="user_id"),
                PayloadMapping(
                    source_path="data.action",
                    target_variable="action",
                    default="unknown",
                ),
            ],
            static_variables={"source": "webhook"},
        )

        manager.create_webhook(webhook)

        retrieved = manager.get_webhook("mapping-webhook")
        assert len(retrieved.payload_mappings) == 2
        assert retrieved.payload_mappings[0].source_path == "data.user.id"
        assert retrieved.payload_mappings[1].default == "unknown"
        assert retrieved.static_variables == {"source": "webhook"}

    def test_create_webhook_validates_workflow(self, backend):
        """create_webhook() raises if workflow doesn't exist."""
        with patch("animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter") as mock_engine:
            mock_engine.return_value.load_workflow.return_value = None
            manager = WebhookManager(backend=backend)

            webhook = Webhook(
                id="test-webhook",
                name="Test",
                workflow_id="nonexistent",
            )

            with pytest.raises(ValueError) as exc:
                manager.create_webhook(webhook)

            assert "not found" in str(exc.value)

    def test_create_webhook_rejects_duplicate(self, manager):
        """create_webhook() raises for duplicate ID."""
        webhook = Webhook(
            id="dupe-webhook",
            name="First",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        duplicate = Webhook(
            id="dupe-webhook",
            name="Second",
            workflow_id="test-workflow",
        )

        with pytest.raises(ValueError) as exc:
            manager.create_webhook(duplicate)

        assert "already exists" in str(exc.value)

    def test_get_webhook(self, manager):
        """get_webhook() returns webhook by ID."""
        webhook = Webhook(
            id="get-test",
            name="Get Test",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        retrieved = manager.get_webhook("get-test")
        assert retrieved is not None
        assert retrieved.id == "get-test"
        assert retrieved.name == "Get Test"

    def test_get_webhook_returns_none_for_missing(self, manager):
        """get_webhook() returns None for nonexistent ID."""
        result = manager.get_webhook("nonexistent")
        assert result is None

    def test_update_webhook(self, manager, backend):
        """update_webhook() updates webhook in database."""
        webhook = Webhook(
            id="update-test",
            name="Original",
            workflow_id="test-workflow",
            description="Original description",
        )
        manager.create_webhook(webhook)
        original_secret = webhook.secret

        # Update
        webhook.name = "Updated"
        webhook.description = "New description"
        result = manager.update_webhook(webhook)
        assert result is True

        # Verify
        updated = manager.get_webhook("update-test")
        assert updated.name == "Updated"
        assert updated.description == "New description"
        # Secret should be preserved
        assert updated.secret == original_secret

    def test_update_webhook_preserves_stats(self, manager):
        """update_webhook() preserves trigger stats."""
        webhook = Webhook(
            id="stats-test",
            name="Stats Test",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        # Manually update trigger count
        original = manager.get_webhook("stats-test")
        original_created = original.created_at

        webhook.name = "Updated Name"
        manager.update_webhook(webhook)

        updated = manager.get_webhook("stats-test")
        assert updated.created_at == original_created

    def test_delete_webhook(self, manager, backend):
        """delete_webhook() removes webhook from database."""
        webhook = Webhook(
            id="delete-me",
            name="Delete Me",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        result = manager.delete_webhook("delete-me")
        assert result is True

        # Verify removed
        assert manager.get_webhook("delete-me") is None
        row = backend.fetchone("SELECT * FROM webhooks WHERE id = ?", ("delete-me",))
        assert row is None

    def test_delete_nonexistent_webhook(self, manager):
        """delete_webhook() returns False for nonexistent webhook."""
        result = manager.delete_webhook("nonexistent")
        assert result is False

    def test_list_webhooks(self, manager):
        """list_webhooks() returns all webhooks without secrets."""
        for i in range(3):
            webhook = Webhook(
                id=f"webhook-{i}",
                name=f"Webhook {i}",
                workflow_id="test-workflow",
            )
            manager.create_webhook(webhook)

        webhooks = manager.list_webhooks()
        assert len(webhooks) == 3

        # Secrets should not be in list response
        for w in webhooks:
            assert "secret" not in w

    def test_verify_signature(self, manager):
        """verify_signature() validates HMAC signature."""
        webhook = Webhook(
            id="sig-test",
            name="Sig Test",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        payload = b'{"test": "data"}'
        signature = manager.generate_signature("sig-test", payload)

        assert manager.verify_signature("sig-test", payload, signature) is True
        assert manager.verify_signature("sig-test", payload, "invalid") is False
        assert manager.verify_signature("sig-test", b"wrong payload", signature) is False

    def test_regenerate_secret(self, manager):
        """regenerate_secret() creates new secret."""
        webhook = Webhook(
            id="regen-test",
            name="Regen Test",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)
        original_secret = manager.get_webhook("regen-test").secret

        new_secret = manager.regenerate_secret("regen-test")

        assert new_secret != original_secret
        assert manager.get_webhook("regen-test").secret == new_secret

    def test_trigger_log_saved(self, manager, backend):
        """Trigger logs are saved to database."""
        manager.create_webhook(
            Webhook(id="test-webhook", name="Log fixture", workflow_id="test-workflow")
        )
        log = WebhookTriggerLog(
            webhook_id="test-webhook",
            workflow_id="test-workflow",
            triggered_at=datetime.now(),
            source_ip="127.0.0.1",
            payload_size=100,
            status="success",
            duration_seconds=0.5,
        )
        manager._save_trigger_log(log)

        # Verify in database
        row = backend.fetchone("SELECT * FROM webhook_logs WHERE webhook_id = ?", ("test-webhook",))
        assert row is not None
        assert row["status"] == "success"
        assert row["source_ip"] == "127.0.0.1"

    def test_get_trigger_history(self, manager, backend):
        """get_trigger_history() returns logs from database."""
        # Create webhook
        webhook = Webhook(
            id="history-test",
            name="History Test",
            workflow_id="test-workflow",
        )
        manager.create_webhook(webhook)

        # Add some logs
        for i in range(5):
            log = WebhookTriggerLog(
                webhook_id="history-test",
                workflow_id="test-workflow",
                triggered_at=datetime.now(),
                payload_size=i * 10,
                status="success" if i % 2 == 0 else "failed",
                duration_seconds=float(i) * 0.1,
            )
            manager._save_trigger_log(log)

        history = manager.get_trigger_history("history-test", limit=3)
        assert len(history) == 3

    def test_webhook_persists_across_restart(self, backend):
        """Webhooks persist across manager restart."""
        with patch("animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter") as mock_engine:
            mock_engine.return_value.load_workflow.return_value = MagicMock()

            # Create webhook with first manager
            manager1 = WebhookManager(backend=backend)
            webhook = Webhook(
                id="persist-test",
                name="Persist Test",
                description="Testing persistence",
                workflow_id="test-workflow",
                payload_mappings=[
                    PayloadMapping(source_path="data.id", target_variable="item_id"),
                ],
                static_variables={"mode": "test"},
            )
            manager1.create_webhook(webhook)
            original_secret = manager1.get_webhook("persist-test").secret

            # Verify with second manager
            manager2 = WebhookManager(backend=backend)
            loaded = manager2.get_webhook("persist-test")

            assert loaded is not None
            assert loaded.name == "Persist Test"
            assert loaded.description == "Testing persistence"
            assert loaded.secret == original_secret
            assert len(loaded.payload_mappings) == 1
            assert loaded.static_variables == {"mode": "test"}

    def test_extract_payload_value(self, manager):
        """_extract_payload_value() extracts nested values."""
        payload = {
            "data": {"user": {"id": 123, "name": "Test"}, "action": "create"},
            "timestamp": "2024-01-01",
        }

        assert manager._extract_payload_value(payload, "data.user.id") == 123
        assert manager._extract_payload_value(payload, "data.action") == "create"
        assert manager._extract_payload_value(payload, "timestamp") == "2024-01-01"
        assert manager._extract_payload_value(payload, "missing.path") is None

    def test_map_payload_to_variables(self, manager):
        """_map_payload_to_variables() maps payload to workflow vars."""
        webhook = Webhook(
            id="map-test",
            name="Map Test",
            workflow_id="test-workflow",
            payload_mappings=[
                PayloadMapping(source_path="data.id", target_variable="item_id"),
                PayloadMapping(
                    source_path="data.missing",
                    target_variable="missing",
                    default="default_value",
                ),
            ],
            static_variables={"source": "webhook", "env": "test"},
        )

        payload = {"data": {"id": 456}}
        variables = manager._map_payload_to_variables(webhook, payload)

        assert variables["item_id"] == 456
        assert variables["missing"] == "default_value"
        assert variables["source"] == "webhook"
        assert variables["env"] == "test"
