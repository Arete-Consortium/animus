"""Tests for FastAPI endpoints."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "src")

from animus_forge.state.backends import SQLiteBackend


@pytest.fixture
def backend():
    """Create a temporary SQLite backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        backend = SQLiteBackend(db_path=db_path)
        yield backend
        backend.close()


@pytest.fixture
def client(backend, monkeypatch):
    """Create a test client with mocked managers."""
    from animus_forge.config.settings import get_settings
    from animus_forge.state.migrations import run_migrations as actual_run_migrations

    # Enable demo auth for tests (disabled by default for security)
    monkeypatch.setenv("ALLOW_DEMO_AUTH", "true")
    get_settings.cache_clear()

    # Run actual migrations so tables exist
    actual_run_migrations(backend)

    with patch("animus_forge.api.get_database", return_value=backend):
        with patch(
            "animus_forge.api.run_migrations", return_value=[]
        ):  # Skip in lifespan since we ran above
            with patch(
                "animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter"
            ) as mock_sched_engine:
                with patch(
                    "animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter"
                ) as mock_webhook_engine:
                    with patch(
                        "animus_forge.jobs.job_manager.WorkflowEngineAdapter"
                    ) as mock_job_engine:
                        # Mock workflow engine for all managers
                        mock_workflow = MagicMock()
                        mock_workflow.variables = {}
                        mock_sched_engine.return_value.load_workflow.return_value = mock_workflow
                        mock_webhook_engine.return_value.load_workflow.return_value = mock_workflow
                        mock_job_engine.return_value.load_workflow.return_value = mock_workflow

                        # Mock execute_workflow result - must have string status
                        mock_result = MagicMock()
                        mock_result.status = "completed"  # String, not MagicMock
                        mock_result.errors = []
                        mock_result.model_dump.return_value = {"status": "completed"}

                        # Apply to all engines
                        mock_sched_engine.return_value.execute_workflow.return_value = mock_result
                        mock_webhook_engine.return_value.execute_workflow.return_value = mock_result
                        mock_job_engine.return_value.execute_workflow.return_value = mock_result

                        from animus_forge.api import app
                        from animus_forge.api_state import limiter
                        from animus_forge.security.brute_force import (
                            get_brute_force_protection,
                        )

                        # Disable rate limiting for tests
                        limiter.enabled = False

                        # Reset brute force protection state for tests
                        protection = get_brute_force_protection()
                        protection._attempts.clear()
                        protection._total_blocked = 0
                        protection._total_allowed = 0

                        with patch(
                            "animus_kernel.executor.version_manager.WorkflowVersionManager.migrate_existing_workflows",
                            return_value=[],
                        ):
                            with TestClient(app) as test_client:
                                yield test_client

                        # Re-enable rate limiting after tests
                        limiter.enabled = True
                        get_settings.cache_clear()


@pytest.fixture
def auth_headers(client):
    """Get authentication headers."""
    response = client.post("/v1/auth/login", json={"user_id": "test", "password": "demo"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoint:
    """Tests for health endpoint."""

    def test_health_check(self, client):
        """GET /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_database_health_check(self, client):
        """GET /health/db returns database health status."""
        response = client.get("/health/db")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["backend"] == "sqlite"
        assert "migrations" in data
        assert "timestamp" in data

    def test_database_health_check_migrations_info(self, client):
        """GET /health/db returns migration status details."""
        response = client.get("/health/db")
        assert response.status_code == 200
        data = response.json()
        migrations = data["migrations"]
        assert "applied" in migrations
        assert "pending" in migrations
        assert "up_to_date" in migrations

    def test_request_id_header(self, client):
        """All responses include X-Request-ID header."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        # Request ID should be 8 characters (UUID prefix)
        assert len(response.headers["X-Request-ID"]) == 8


class TestMetricsEndpoint:
    """Tests for Prometheus metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client):
        """GET /metrics returns Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Check for expected metrics
        text = response.text
        assert "gorgon_app_ready" in text
        assert "gorgon_active_requests" in text

    def test_metrics_contains_type_annotations(self, client):
        """Metrics include TYPE annotations for Prometheus."""
        response = client.get("/metrics")
        text = response.text

        # Should have TYPE comments for gauges
        assert "# TYPE gorgon_app_ready gauge" in text
        assert "# TYPE gorgon_active_requests gauge" in text

    def test_metrics_values_are_numeric(self, client):
        """Metric values should be numeric."""
        response = client.get("/metrics")
        text = response.text

        # gorgon_app_ready should be 0 or 1
        assert "gorgon_app_ready 1" in text or "gorgon_app_ready 0" in text


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root(self, client):
        """GET / returns app info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "AI Workflow Orchestrator"
        assert data["status"] == "running"


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    def test_login_success(self, client):
        """POST /auth/login with valid credentials returns token."""
        response = client.post("/v1/auth/login", json={"user_id": "test", "password": "demo"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_failure(self, client):
        """POST /auth/login with invalid credentials returns 401."""
        response = client.post("/v1/auth/login", json={"user_id": "test", "password": "wrong"})
        assert response.status_code == 401

    def test_protected_endpoint_without_auth(self, client):
        """Protected endpoint without auth returns 401."""
        response = client.get("/v1/jobs")
        assert response.status_code == 401

    def test_protected_endpoint_with_auth(self, client, auth_headers):
        """Protected endpoint with valid auth succeeds."""
        response = client.get("/v1/jobs", headers=auth_headers)
        assert response.status_code == 200


class TestJobEndpoints:
    """Tests for job endpoints."""

    def test_list_jobs_empty(self, client, auth_headers):
        """GET /jobs returns empty list initially."""
        response = client.get("/v1/jobs", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_submit_job(self, client, auth_headers):
        """POST /jobs submits a job."""
        response = client.post(
            "/v1/jobs",
            json={"workflow_id": "test-workflow", "variables": {"key": "value"}},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert "job_id" in data
        assert data["workflow_id"] == "test-workflow"
        assert "poll_url" in data

    def test_get_job(self, client, auth_headers):
        """GET /jobs/{id} returns job details."""
        # Submit a job first
        submit_response = client.post(
            "/v1/jobs",
            json={"workflow_id": "test-workflow"},
            headers=auth_headers,
        )
        job_id = submit_response.json()["job_id"]

        # Get job
        response = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["workflow_id"] == "test-workflow"

    def test_get_job_not_found(self, client, auth_headers):
        """GET /jobs/{id} returns 404 for nonexistent job."""
        response = client.get("/v1/jobs/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_get_job_stats(self, client, auth_headers):
        """GET /jobs/stats returns statistics."""
        response = client.get("/v1/jobs/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "pending" in data
        assert "completed" in data

    def test_cancel_job(self, client, auth_headers):
        """POST /jobs/{id}/cancel cancels a pending job."""
        # Submit a job
        submit_response = client.post(
            "/v1/jobs",
            json={"workflow_id": "test-workflow"},
            headers=auth_headers,
        )
        job_id = submit_response.json()["job_id"]

        # Cancel it (may fail if already completed)
        response = client.post(f"/v1/jobs/{job_id}/cancel", headers=auth_headers)
        # Either success or already completed
        assert response.status_code in (200, 400)

    def test_list_jobs_with_filter(self, client, auth_headers):
        """GET /jobs with status filter works."""
        response = client.get("/v1/jobs?status=completed", headers=auth_headers)
        assert response.status_code == 200

    def test_list_jobs_invalid_status(self, client, auth_headers):
        """GET /jobs with invalid status returns 400."""
        response = client.get("/v1/jobs?status=invalid", headers=auth_headers)
        assert response.status_code == 400


class TestScheduleEndpoints:
    """Tests for schedule endpoints."""

    def test_list_schedules_empty(self, client, auth_headers):
        """GET /schedules returns empty list initially."""
        response = client.get("/v1/schedules", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_create_schedule(self, client, auth_headers):
        """POST /schedules creates a schedule."""
        response = client.post(
            "/v1/schedules",
            json={
                "id": "test-schedule",
                "workflow_id": "test-workflow",
                "name": "Test Schedule",
                "schedule_type": "interval",
                "interval_config": {"minutes": 30},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["schedule_id"] == "test-schedule"

    def test_get_schedule(self, client, auth_headers):
        """GET /schedules/{id} returns schedule details."""
        # Create schedule first
        client.post(
            "/v1/schedules",
            json={
                "id": "get-test",
                "workflow_id": "test-workflow",
                "name": "Get Test",
                "schedule_type": "interval",
                "interval_config": {"minutes": 15},
            },
            headers=auth_headers,
        )

        response = client.get("/v1/schedules/get-test", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "get-test"
        assert data["name"] == "Get Test"

    def test_get_schedule_not_found(self, client, auth_headers):
        """GET /schedules/{id} returns 404 for nonexistent schedule."""
        response = client.get("/v1/schedules/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_schedule(self, client, auth_headers):
        """DELETE /schedules/{id} deletes a schedule."""
        # Create schedule
        client.post(
            "/v1/schedules",
            json={
                "id": "delete-me",
                "workflow_id": "test-workflow",
                "name": "Delete Me",
                "schedule_type": "interval",
                "interval_config": {"minutes": 5},
            },
            headers=auth_headers,
        )

        # Delete it
        response = client.delete("/v1/schedules/delete-me", headers=auth_headers)
        assert response.status_code == 200

        # Verify deleted
        response = client.get("/v1/schedules/delete-me", headers=auth_headers)
        assert response.status_code == 404

    def test_pause_resume_schedule(self, client, auth_headers):
        """POST /schedules/{id}/pause and resume work."""
        # Create schedule
        client.post(
            "/v1/schedules",
            json={
                "id": "pause-test",
                "workflow_id": "test-workflow",
                "name": "Pause Test",
                "schedule_type": "interval",
                "interval_config": {"minutes": 10},
            },
            headers=auth_headers,
        )

        # Pause
        response = client.post("/v1/schedules/pause-test/pause", headers=auth_headers)
        assert response.status_code == 200

        # Resume
        response = client.post("/v1/schedules/pause-test/resume", headers=auth_headers)
        assert response.status_code == 200


class TestWebhookEndpoints:
    """Tests for webhook endpoints."""

    def test_list_webhooks_empty(self, client, auth_headers):
        """GET /webhooks returns empty list initially."""
        response = client.get("/v1/webhooks", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_create_webhook(self, client, auth_headers):
        """POST /webhooks creates a webhook."""
        response = client.post(
            "/v1/webhooks",
            json={
                "id": "test-webhook",
                "name": "Test Webhook",
                "workflow_id": "test-workflow",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["webhook_id"] == "test-webhook"
        assert "secret" in data
        assert "trigger_url" in data

    def test_get_webhook(self, client, auth_headers):
        """GET /webhooks/{id} returns webhook details."""
        # Create webhook first
        client.post(
            "/v1/webhooks",
            json={
                "id": "get-test",
                "name": "Get Test",
                "workflow_id": "test-workflow",
            },
            headers=auth_headers,
        )

        response = client.get("/v1/webhooks/get-test", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "get-test"
        assert data["name"] == "Get Test"
        assert "secret" in data

    def test_get_webhook_not_found(self, client, auth_headers):
        """GET /webhooks/{id} returns 404 for nonexistent webhook."""
        response = client.get("/v1/webhooks/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_webhook(self, client, auth_headers):
        """DELETE /webhooks/{id} deletes a webhook."""
        # Create webhook
        client.post(
            "/v1/webhooks",
            json={
                "id": "delete-me",
                "name": "Delete Me",
                "workflow_id": "test-workflow",
            },
            headers=auth_headers,
        )

        # Delete it
        response = client.delete("/v1/webhooks/delete-me", headers=auth_headers)
        assert response.status_code == 200

        # Verify deleted
        response = client.get("/v1/webhooks/delete-me", headers=auth_headers)
        assert response.status_code == 404

    def test_regenerate_secret(self, client, auth_headers):
        """POST /webhooks/{id}/regenerate-secret generates new secret."""
        # Create webhook
        create_response = client.post(
            "/v1/webhooks",
            json={
                "id": "regen-test",
                "name": "Regen Test",
                "workflow_id": "test-workflow",
            },
            headers=auth_headers,
        )
        original_secret = create_response.json()["secret"]

        # Regenerate secret
        response = client.post("/v1/webhooks/regen-test/regenerate-secret", headers=auth_headers)
        assert response.status_code == 200
        new_secret = response.json()["secret"]
        assert new_secret != original_secret

    def test_trigger_webhook_requires_signature(self, client, auth_headers):
        """POST /hooks/{id} requires X-Webhook-Signature header."""
        # Create webhook first (requires auth)
        create_resp = client.post(
            "/v1/webhooks",
            json={
                "id": "trigger-test",
                "name": "Trigger Test",
                "workflow_id": "test-workflow",
            },
            headers=auth_headers,
        )
        secret = create_resp.json().get("secret", "")

        # Trigger without signature — should be rejected
        response = client.post(
            "/hooks/trigger-test",
            json={"data": {"id": 123}},
        )
        assert response.status_code == 401

        # Trigger with valid HMAC signature
        import hashlib
        import hmac
        import json

        body = json.dumps({"data": {"id": 123}}).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        response = client.post(
            "/hooks/trigger-test",
            content=body,
            headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_trigger_webhook_not_found(self, client):
        """POST /hooks/{id} returns 404 for nonexistent webhook."""
        response = client.post("/hooks/nonexistent", json={})
        assert response.status_code == 404


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.fixture
    def rate_limited_client(self, backend, monkeypatch):
        """Create a test client with rate limiting enabled."""
        from unittest.mock import MagicMock, patch

        from animus_forge.config.settings import get_settings

        monkeypatch.setenv("ALLOW_DEMO_AUTH", "true")
        get_settings.cache_clear()

        with patch("animus_forge.api.get_database", return_value=backend):
            with patch("animus_forge.api.run_migrations", return_value=[]):
                with patch(
                    "animus_forge.scheduler.schedule_manager.WorkflowEngineAdapter"
                ) as mock_sched_engine:
                    with patch(
                        "animus_forge.webhooks.webhook_manager.WorkflowEngineAdapter"
                    ) as mock_webhook_engine:
                        with patch(
                            "animus_forge.jobs.job_manager.WorkflowEngineAdapter"
                        ) as mock_job_engine:
                            mock_workflow = MagicMock()
                            mock_workflow.variables = {}
                            mock_sched_engine.return_value.load_workflow.return_value = (
                                mock_workflow
                            )
                            mock_webhook_engine.return_value.load_workflow.return_value = (
                                mock_workflow
                            )
                            mock_job_engine.return_value.load_workflow.return_value = mock_workflow

                            from animus_forge.api import app
                            from animus_forge.api_state import limiter
                            from animus_forge.security.brute_force import (
                                get_brute_force_protection,
                            )

                            # Enable rate limiting for this test
                            limiter.enabled = True
                            # Reset limiter storage
                            limiter.reset()

                            # Reset brute force protection and increase limit for rate limit test
                            protection = get_brute_force_protection()
                            protection._attempts.clear()
                            protection._total_blocked = 0
                            protection._total_allowed = 0
                            # Temporarily increase auth limit to test slowapi limiter
                            original_limit = protection.config.max_auth_attempts_per_minute
                            protection.config.max_auth_attempts_per_minute = 10

                            from fastapi.testclient import TestClient

                            with TestClient(app) as test_client:
                                yield test_client

                            # Restore original limit
                            protection.config.max_auth_attempts_per_minute = original_limit
                            limiter.enabled = False
                            get_settings.cache_clear()

    def test_login_rate_limit(self, rate_limited_client):
        """Login endpoint enforces rate limit after 5 requests."""
        # Make 5 successful requests
        for _ in range(5):
            response = rate_limited_client.post(
                "/v1/auth/login", json={"user_id": "test", "password": "demo"}
            )
            assert response.status_code == 200

        # 6th request should be rate limited
        response = rate_limited_client.post(
            "/v1/auth/login", json={"user_id": "test", "password": "demo"}
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


# =============================================================================
# Workflow Versioning API Tests
# =============================================================================


SAMPLE_WORKFLOW_V1 = """name: test-workflow
version: 1.0.0
description: Test workflow version 1

steps:
  - id: step1
    type: shell
    params:
      command: echo "Hello"
"""

SAMPLE_WORKFLOW_V2 = """name: test-workflow
version: 2.0.0
description: Test workflow version 2 with changes

steps:
  - id: step1
    type: shell
    params:
      command: echo "Hello World"
  - id: step2
    type: shell
    params:
      command: echo "New step"
"""


class TestWorkflowVersioningAPI:
    """Tests for workflow versioning API endpoints."""

    def test_save_version(self, client, auth_headers):
        """Can save a new workflow version."""
        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={
                "content": SAMPLE_WORKFLOW_V1,
                "version": "1.0.0",
                "description": "Initial version",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_name"] == "test-workflow"
        assert data["version"] == "1.0.0"
        assert data["is_active"] is True

    def test_save_version_auto_bump(self, client, auth_headers):
        """Version auto-bumps when not specified."""
        # Save v1
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        # Save v2 without explicit version
        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.1"  # Auto-bumped patch

    def test_save_version_duplicate_content_returns_existing(self, client, auth_headers):
        """Duplicate content returns existing version."""
        # Save initial
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        # Save same content
        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"

    def test_save_version_existing_version_fails(self, client, auth_headers):
        """Saving different content with existing version fails."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "1.0.0"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["error"]["message"]

    def test_save_version_invalid_yaml_fails(self, client, auth_headers):
        """Invalid YAML content returns error."""
        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": "invalid: yaml: content:"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid YAML" in response.json()["error"]["message"]

    def test_save_version_requires_auth(self, client):
        """Save version requires authentication."""
        response = client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1},
        )

        assert response.status_code == 401

    def test_list_versions(self, client, auth_headers):
        """Can list all versions of a workflow."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.get(
            "/v1/workflows/test-workflow/versions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        versions = [v["version"] for v in data]
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_list_versions_empty(self, client, auth_headers):
        """List versions returns empty list for unknown workflow."""
        response = client.get(
            "/v1/workflows/nonexistent/versions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_list_versions_pagination(self, client, auth_headers):
        """List versions supports pagination."""
        for i in range(5):
            client.post(
                "/v1/workflows/test-workflow/versions",
                json={
                    "content": f"name: test\nversion: 1.0.{i}",
                    "version": f"1.0.{i}",
                },
                headers=auth_headers,
            )

        response = client.get(
            "/v1/workflows/test-workflow/versions?limit=2&offset=0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_versions_requires_auth(self, client):
        """List versions requires authentication."""
        response = client.get("/v1/workflows/test-workflow/versions")
        assert response.status_code == 401

    def test_get_version(self, client, auth_headers):
        """Can get a specific version."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        response = client.get(
            "/v1/workflows/test-workflow/versions/1.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"
        assert data["content"] == SAMPLE_WORKFLOW_V1

    def test_get_version_not_found(self, client, auth_headers):
        """Get nonexistent version returns 404."""
        response = client.get(
            "/v1/workflows/test-workflow/versions/99.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_version_requires_auth(self, client):
        """Get version requires authentication."""
        response = client.get("/v1/workflows/test-workflow/versions/1.0.0")
        assert response.status_code == 401

    def test_activate_version(self, client, auth_headers):
        """Can activate a specific version."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.post(
            "/v1/workflows/test-workflow/versions/1.0.0/activate",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["active_version"] == "1.0.0"

    def test_activate_version_not_found(self, client, auth_headers):
        """Activate nonexistent version returns 404."""
        response = client.post(
            "/v1/workflows/test-workflow/versions/99.0.0/activate",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_activate_version_requires_auth(self, client):
        """Activate version requires authentication."""
        response = client.post("/v1/workflows/test-workflow/versions/1.0.0/activate")
        assert response.status_code == 401

    def test_rollback(self, client, auth_headers):
        """Can rollback to previous version."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.post(
            "/v1/workflows/test-workflow/rollback",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rolled_back_to"] == "1.0.0"

    def test_rollback_no_previous_version(self, client, auth_headers):
        """Rollback with single version returns error."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        response = client.post(
            "/v1/workflows/test-workflow/rollback",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "No previous version" in response.json()["error"]["message"]

    def test_rollback_requires_auth(self, client):
        """Rollback requires authentication."""
        response = client.post("/v1/workflows/test-workflow/rollback")
        assert response.status_code == 401

    def test_compare_versions(self, client, auth_headers):
        """Can compare two versions."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.get(
            "/v1/workflows/test-workflow/versions/compare?from_version=1.0.0&to_version=2.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["from_version"] == "1.0.0"
        assert data["to_version"] == "2.0.0"
        assert data["has_changes"] is True
        assert "unified_diff" in data

    def test_compare_versions_not_found(self, client, auth_headers):
        """Compare with nonexistent version returns 400."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        response = client.get(
            "/v1/workflows/test-workflow/versions/compare?from_version=1.0.0&to_version=99.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_compare_versions_requires_auth(self, client):
        """Compare versions requires authentication."""
        response = client.get(
            "/v1/workflows/test-workflow/versions/compare?from_version=1.0.0&to_version=2.0.0"
        )
        assert response.status_code == 401

    def test_delete_version(self, client, auth_headers):
        """Can delete a non-active version."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.delete(
            "/v1/workflows/test-workflow/versions/1.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify deleted
        get_response = client.get(
            "/v1/workflows/test-workflow/versions/1.0.0",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_active_version_fails(self, client, auth_headers):
        """Cannot delete active version."""
        client.post(
            "/v1/workflows/test-workflow/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )

        response = client.delete(
            "/v1/workflows/test-workflow/versions/1.0.0",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Cannot delete active version" in response.json()["error"]["message"]

    def test_delete_version_requires_auth(self, client):
        """Delete version requires authentication."""
        response = client.delete("/v1/workflows/test-workflow/versions/1.0.0")
        assert response.status_code == 401

    def test_list_versioned_workflows(self, client, auth_headers):
        """Can list all workflows with versions."""
        client.post(
            "/v1/workflows/workflow1/versions",
            json={"content": SAMPLE_WORKFLOW_V1, "version": "1.0.0"},
            headers=auth_headers,
        )
        client.post(
            "/v1/workflows/workflow2/versions",
            json={"content": SAMPLE_WORKFLOW_V2, "version": "2.0.0"},
            headers=auth_headers,
        )

        response = client.get("/v1/workflow-versions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [w["workflow_name"] for w in data]
        assert "workflow1" in names
        assert "workflow2" in names

    def test_list_versioned_workflows_empty(self, client, auth_headers):
        """List versioned workflows returns empty when none exist."""
        response = client.get("/v1/workflow-versions", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_list_versioned_workflows_requires_auth(self, client):
        """List versioned workflows requires authentication."""
        response = client.get("/v1/workflow-versions")
        assert response.status_code == 401
