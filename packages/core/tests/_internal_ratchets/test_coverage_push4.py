"""
Coverage push round 4.

Targets: api.py (49% → 70%+), memory.py (71% → 85%+)
"""

from __future__ import annotations

import shutil
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    from fastapi.testclient import TestClient

    from animus import api as api_module
    from animus.api import AppState, create_app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# ===================================================================
# Shared fixtures
# ===================================================================


@pytest.fixture
def api_state(tmp_path):
    """Minimal AppState for API tests."""
    from animus.cognitive import CognitiveLayer, ModelConfig
    from animus.config import AnimusConfig
    from animus.decision import DecisionFramework
    from animus.memory import MemoryLayer
    from animus.tasks import TaskTracker
    from animus.tools import create_default_registry

    config = AnimusConfig(data_dir=tmp_path)
    memory = MemoryLayer(tmp_path, backend="json")
    mock_config = ModelConfig.mock(default_response="Test response.")
    cognitive = CognitiveLayer(primary_config=mock_config)
    tools = create_default_registry()
    tasks = TaskTracker(tmp_path / "tasks")
    decisions = DecisionFramework(cognitive)

    return AppState(
        config=config,
        memory=memory,
        cognitive=cognitive,
        tools=tools,
        tasks=tasks,
        decisions=decisions,
        conversations={},
    )


@pytest.fixture
def client(api_state):
    """TestClient with injected state."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    app = create_app()
    api_module._state = api_state
    yield TestClient(app)
    api_module._state = None


# ===================================================================
# api.py — APIServer class
# ===================================================================

skip_no_fastapi = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")


@skip_no_fastapi
class TestAPIServerLifecycle:
    """Cover APIServer.__init__, start, stop, properties."""

    def test_init_stores_attributes(self, tmp_path):
        from animus.api import APIServer
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.decision import DecisionFramework
        from animus.memory import MemoryLayer
        from animus.tasks import TaskTracker
        from animus.tools import create_default_registry

        memory = MemoryLayer(tmp_path, backend="json")
        cognitive = CognitiveLayer(primary_config=ModelConfig.mock())
        tools = create_default_registry()
        tasks = TaskTracker(tmp_path / "tasks")
        decisions = DecisionFramework(cognitive)

        server = APIServer(
            memory=memory,
            cognitive=cognitive,
            tools=tools,
            tasks=tasks,
            decisions=decisions,
            host="0.0.0.0",
            port=9999,
            api_key="test-key",
        )
        assert server.host == "0.0.0.0"
        assert server.port == 9999
        assert server.api_key == "test-key"
        assert server.is_running is False
        assert server.url == "http://0.0.0.0:9999"

    def test_stop_when_not_running(self, tmp_path):
        from animus.api import APIServer
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.decision import DecisionFramework
        from animus.memory import MemoryLayer
        from animus.tasks import TaskTracker
        from animus.tools import create_default_registry

        server = APIServer(
            memory=MemoryLayer(tmp_path, backend="json"),
            cognitive=CognitiveLayer(primary_config=ModelConfig.mock()),
            tools=create_default_registry(),
            tasks=TaskTracker(tmp_path / "tasks"),
            decisions=DecisionFramework(CognitiveLayer(primary_config=ModelConfig.mock())),
        )
        assert server.stop() is False

    def test_stop_when_running(self, tmp_path):
        from animus.api import APIServer
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.decision import DecisionFramework
        from animus.memory import MemoryLayer
        from animus.tasks import TaskTracker
        from animus.tools import create_default_registry

        server = APIServer(
            memory=MemoryLayer(tmp_path, backend="json"),
            cognitive=CognitiveLayer(primary_config=ModelConfig.mock()),
            tools=create_default_registry(),
            tasks=TaskTracker(tmp_path / "tasks"),
            decisions=DecisionFramework(CognitiveLayer(primary_config=ModelConfig.mock())),
        )
        server._is_running = True
        server._server = MagicMock()
        assert server.stop() is True
        assert server.is_running is False
        assert server._server.should_exit is True

    def test_start_already_running(self, tmp_path):
        from animus.api import APIServer
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.decision import DecisionFramework
        from animus.memory import MemoryLayer
        from animus.tasks import TaskTracker
        from animus.tools import create_default_registry

        server = APIServer(
            memory=MemoryLayer(tmp_path, backend="json"),
            cognitive=CognitiveLayer(primary_config=ModelConfig.mock()),
            tools=create_default_registry(),
            tasks=TaskTracker(tmp_path / "tasks"),
            decisions=DecisionFramework(CognitiveLayer(primary_config=ModelConfig.mock())),
        )
        server._is_running = True
        assert server.start() is False


# ===================================================================
# api.py — create_app guard
# ===================================================================


@skip_no_fastapi
class TestCreateAppGuard:
    def test_create_app_when_not_available(self):
        with patch.object(api_module, "FASTAPI_AVAILABLE", False):
            with pytest.raises(ImportError):
                create_app()


# ===================================================================
# api.py — Task update with status
# ===================================================================


@skip_no_fastapi
class TestAPITaskUpdate:
    def test_update_task_status(self, client, api_state):
        # Create a task first
        resp = client.post("/tasks", json={"description": "Test task"})
        task_id = resp.json()["id"]

        resp = client.patch(f"/tasks/{task_id}", json={"status": "completed"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_update_task_invalid_status(self, client, api_state):
        resp = client.post("/tasks", json={"description": "Test task"})
        task_id = resp.json()["id"]

        resp = client.patch(f"/tasks/{task_id}", json={"status": "invalid_status"})
        assert resp.status_code == 400


# ===================================================================
# api.py — WebSocket chat
# ===================================================================


@skip_no_fastapi
class TestAPIWebSocket:
    def test_websocket_basic_chat(self, client, api_state):
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": "hello"})
            resp = ws.receive_json()
            assert "response" in resp
            assert "conversation_id" in resp

    def test_websocket_empty_message(self, client, api_state):
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": ""})
            resp = ws.receive_json()
            assert "error" in resp

    def test_websocket_with_explicit_mode(self, client, api_state):
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": "analyze this", "mode": "deep"})
            resp = ws.receive_json()
            assert resp["mode_used"] == "deep"


# ===================================================================
# api.py — Integration endpoints
# ===================================================================


@skip_no_fastapi
class TestAPIIntegrationEndpoints:
    def test_list_integrations_with_data(self, client, api_state):
        mock_integration = MagicMock()
        mock_integration.name = "test_svc"
        mock_integration.display_name = "Test Service"
        mock_integration.status.value = "connected"
        mock_integration.auth_type.value = "api_key"
        mock_integration.connected_at = datetime.now()
        mock_integration.error_message = None
        mock_integration.capabilities = ["read"]

        mock_manager = MagicMock()
        mock_manager.list_all.return_value = [mock_integration]
        api_state.integrations = mock_manager

        resp = client.get("/integrations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected_count"] == 1
        assert len(data["integrations"]) == 1

    def test_connect_integration_not_found(self, client, api_state):
        mock_manager = MagicMock()
        mock_manager.get.return_value = None
        api_state.integrations = mock_manager

        resp = client.post(
            "/integrations/nonexistent/connect",
            json={"credentials": {}},
        )
        assert resp.status_code == 404

    def test_disconnect_integration_success(self, client, api_state):
        from unittest.mock import AsyncMock

        mock_integration = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_integration
        mock_manager.disconnect = AsyncMock(return_value=True)
        api_state.integrations = mock_manager

        resp = client.delete("/integrations/test_svc")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"

    def test_disconnect_integration_not_found(self, client, api_state):
        mock_manager = MagicMock()
        mock_manager.get.return_value = None
        api_state.integrations = mock_manager

        resp = client.delete("/integrations/nonexistent")
        assert resp.status_code == 404

    def test_disconnect_integration_no_manager(self, client, api_state):
        api_state.integrations = None
        resp = client.delete("/integrations/test_svc")
        assert resp.status_code == 503


# ===================================================================
# api.py — Learning endpoints
# ===================================================================


@skip_no_fastapi
class TestAPILearningEndpoints:
    def _make_learning_mock(self):
        mock = MagicMock()
        mock.transparency = MagicMock()
        mock.guardrails = MagicMock()
        mock.rollback = MagicMock()
        return mock

    def test_learning_status(self, client, api_state):
        mock_learning = self._make_learning_mock()
        dashboard = MagicMock()
        dashboard.total_learned = 10
        dashboard.pending_approval = 2
        dashboard.events_today = 5
        dashboard.guardrail_violations = 0
        dashboard.by_category = {}
        dashboard.confidence_distribution = {}
        mock_learning.get_dashboard_data.return_value = dashboard
        api_state.learning = mock_learning

        resp = client.get("/learning/status")
        assert resp.status_code == 200
        assert resp.json()["total_learned"] == 10

    def test_learning_items_active(self, client, api_state):
        mock_learning = self._make_learning_mock()
        item = MagicMock()
        item.id = "l-1"
        item.category.value = "style"
        item.content = "Use short sentences"
        item.confidence = 0.9
        item.applied = True
        item.created_at.isoformat.return_value = "2025-01-01T00:00:00"
        item.updated_at.isoformat.return_value = "2025-01-01T00:00:00"
        mock_learning.get_active_learnings.return_value = [item]
        api_state.learning = mock_learning

        resp = client.get("/learning/items?status=active")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_learning_items_pending(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.get_pending_learnings.return_value = []
        api_state.learning = mock_learning

        resp = client.get("/learning/items?status=pending")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_learning_items_all(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.get_all_learnings.return_value = []
        api_state.learning = mock_learning

        resp = client.get("/learning/items?status=all")
        assert resp.status_code == 200

    def test_trigger_scan(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.scan_and_learn.return_value = ["p1", "p2"]
        api_state.learning = mock_learning

        resp = client.post("/learning/scan")
        assert resp.status_code == 200
        assert resp.json()["patterns_detected"] == 2

    def test_approve_learning_success(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.approve_learning.return_value = True
        api_state.learning = mock_learning

        resp = client.post("/learning/item-1/approve")
        assert resp.status_code == 200

    def test_approve_learning_not_found(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.approve_learning.return_value = False
        api_state.learning = mock_learning

        resp = client.post("/learning/item-1/approve")
        assert resp.status_code == 404

    def test_reject_learning_success(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.reject_learning.return_value = True
        api_state.learning = mock_learning

        resp = client.post("/learning/item-1/reject")
        assert resp.status_code == 200

    def test_reject_learning_not_found(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.reject_learning.return_value = False
        api_state.learning = mock_learning

        resp = client.post("/learning/item-1/reject")
        assert resp.status_code == 404

    def test_unlearn_success(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.unlearn.return_value = True
        api_state.learning = mock_learning

        resp = client.delete("/learning/item-1")
        assert resp.status_code == 200

    def test_unlearn_not_found(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.unlearn.return_value = False
        api_state.learning = mock_learning

        resp = client.delete("/learning/item-1")
        assert resp.status_code == 404

    def test_learning_history(self, client, api_state):
        mock_learning = self._make_learning_mock()
        event = MagicMock()
        event.to_dict.return_value = {"type": "learned", "id": "e-1"}
        mock_learning.transparency.get_history.return_value = [event]
        api_state.learning = mock_learning

        resp = client.get("/learning/history")
        assert resp.status_code == 200
        assert len(resp.json()["events"]) == 1

    def test_list_guardrails(self, client, api_state):
        mock_learning = self._make_learning_mock()
        g = MagicMock()
        g.id = "g-1"
        g.rule = "no profanity"
        g.description = "Avoid profanity"
        g.guardrail_type.value = "content"
        g.immutable = False
        g.source = "user"
        mock_learning.guardrails.get_all_guardrails.return_value = [g]
        api_state.learning = mock_learning

        resp = client.get("/guardrails")
        assert resp.status_code == 200
        assert len(resp.json()["guardrails"]) == 1

    def test_add_guardrail(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_guardrail = MagicMock()
        mock_guardrail.id = "g-new"
        mock_learning.add_user_guardrail.return_value = mock_guardrail
        api_state.learning = mock_learning

        resp = client.post("/guardrails?rule=no+profanity")
        assert resp.status_code == 200
        assert resp.json()["id"] == "g-new"

    def test_list_rollback_points(self, client, api_state):
        mock_learning = self._make_learning_mock()
        point = MagicMock()
        point.id = "rp-1"
        point.timestamp.isoformat.return_value = "2025-01-01T00:00:00"
        point.description = "Before changes"
        point.learned_item_ids = ["l-1", "l-2"]
        mock_learning.rollback.get_rollback_points.return_value = [point]
        api_state.learning = mock_learning

        resp = client.get("/learning/rollback-points")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rollback_points"]) == 1
        assert data["rollback_points"][0]["item_count"] == 2

    def test_rollback_success(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.rollback_to.return_value = (True, ["l-1"])
        api_state.learning = mock_learning

        resp = client.post("/learning/rollback/rp-1")
        assert resp.status_code == 200
        assert resp.json()["unlearned_count"] == 1

    def test_rollback_not_found(self, client, api_state):
        mock_learning = self._make_learning_mock()
        mock_learning.rollback_to.return_value = (False, [])
        api_state.learning = mock_learning

        resp = client.post("/learning/rollback/rp-bad")
        assert resp.status_code == 404


# ===================================================================
# api.py — Memory export / consolidation
# ===================================================================


@skip_no_fastapi
class TestAPIMemoryExport:
    def test_export_csv(self, client, api_state):
        api_state.memory.export_memories_csv = MagicMock(return_value="id,content\n1,hello")
        resp = client.get("/memory/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "memories.csv" in resp.headers["content-disposition"]

    def test_consolidate(self, client, api_state):
        api_state.memory.consolidate = MagicMock(return_value=5)
        resp = client.post("/memory/consolidate")
        assert resp.status_code == 200
        assert resp.json()["consolidated"] == 5


# ===================================================================
# api.py — Register endpoints
# ===================================================================


@skip_no_fastapi
class TestAPIRegister:
    def test_get_register(self, client, api_state):
        resp = client.get("/register")
        assert resp.status_code == 200

    def test_set_register_formal(self, client, api_state):
        resp = client.post("/register/formal")
        assert resp.status_code == 200

    def test_set_register_neutral(self, client, api_state):
        resp = client.post("/register/neutral")
        assert resp.status_code == 200

    def test_set_register_invalid(self, client, api_state):
        resp = client.post("/register/nonexistent")
        assert resp.status_code == 400


# ===================================================================
# api.py — Proactive endpoints
# ===================================================================


@skip_no_fastapi
class TestAPIProactive:
    def test_nudges_no_engine(self, client, api_state):
        api_state.proactive = None
        resp = client.get("/nudges")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_nudges_with_engine(self, client, api_state):
        nudge = MagicMock()
        nudge.to_dict.return_value = {"id": "n-1", "text": "Good morning"}
        mock_proactive = MagicMock()
        mock_proactive.get_active_nudges.return_value = [nudge]
        api_state.proactive = mock_proactive

        resp = client.get("/nudges")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_generate_briefing(self, client, api_state):
        nudge = MagicMock()
        nudge.to_dict.return_value = {"type": "briefing", "text": "Today..."}
        mock_proactive = MagicMock()
        mock_proactive.generate_morning_brief.return_value = nudge
        api_state.proactive = mock_proactive

        resp = client.post("/nudges/briefing")
        assert resp.status_code == 200

    def test_generate_briefing_no_engine(self, client, api_state):
        api_state.proactive = None
        resp = client.post("/nudges/briefing")
        assert resp.status_code == 503

    def test_meeting_prep(self, client, api_state):
        nudge = MagicMock()
        nudge.to_dict.return_value = {"type": "prep"}
        mock_proactive = MagicMock()
        mock_proactive.prepare_meeting_context.return_value = nudge
        api_state.proactive = mock_proactive

        resp = client.post("/nudges/meeting-prep?topic=standup")
        assert resp.status_code == 200

    def test_meeting_prep_no_engine(self, client, api_state):
        api_state.proactive = None
        resp = client.post("/nudges/meeting-prep?topic=standup")
        assert resp.status_code == 503

    def test_dismiss_nudge_success(self, client, api_state):
        mock_proactive = MagicMock()
        mock_proactive.dismiss_nudge.return_value = True
        api_state.proactive = mock_proactive

        resp = client.post("/nudges/n-1/dismiss")
        assert resp.status_code == 200

    def test_dismiss_nudge_not_found(self, client, api_state):
        mock_proactive = MagicMock()
        mock_proactive.dismiss_nudge.return_value = False
        api_state.proactive = mock_proactive

        resp = client.post("/nudges/n-bad/dismiss")
        assert resp.status_code == 404

    def test_proactive_stats_no_engine(self, client, api_state):
        api_state.proactive = None
        resp = client.get("/proactive/stats")
        assert resp.status_code == 200
        assert resp.json()["background_running"] is False

    def test_proactive_stats_with_engine(self, client, api_state):
        mock_proactive = MagicMock()
        mock_proactive.get_statistics.return_value = {"nudges_generated": 5}
        api_state.proactive = mock_proactive

        resp = client.get("/proactive/stats")
        assert resp.status_code == 200


# ===================================================================
# api.py — Entity endpoints
# ===================================================================


@skip_no_fastapi
class TestAPIEntityEndpoints:
    def test_list_entities_no_memory(self, client, api_state):
        api_state.entity_memory = None
        resp = client.get("/entities")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_entities_with_data(self, client, api_state):
        entity = MagicMock()
        entity.to_dict.return_value = {"id": "e-1", "name": "Alice"}
        mock_em = MagicMock()
        mock_em.list_entities.return_value = [entity]
        api_state.entity_memory = mock_em

        resp = client.get("/entities")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_list_entities_with_type_filter(self, client, api_state):
        mock_em = MagicMock()
        mock_em.list_entities.return_value = []
        api_state.entity_memory = mock_em

        resp = client.get("/entities?entity_type=person")
        assert resp.status_code == 200

    def test_create_entity(self, client, api_state):
        entity = MagicMock()
        entity.to_dict.return_value = {"id": "e-new", "name": "Bob"}
        mock_em = MagicMock()
        mock_em.add_entity.return_value = entity
        api_state.entity_memory = mock_em

        resp = client.post("/entities?name=Bob&entity_type=person")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bob"

    def test_create_entity_invalid_type(self, client, api_state):
        mock_em = MagicMock()
        api_state.entity_memory = mock_em

        resp = client.post("/entities?name=Bob&entity_type=invalid_type")
        assert resp.status_code == 400

    def test_create_entity_no_memory(self, client, api_state):
        api_state.entity_memory = None
        resp = client.post("/entities?name=Bob&entity_type=person")
        assert resp.status_code == 503

    def test_search_entities(self, client, api_state):
        entity = MagicMock()
        entity.to_dict.return_value = {"id": "e-1", "name": "Alice"}
        mock_em = MagicMock()
        mock_em.search_entities.return_value = [entity]
        api_state.entity_memory = mock_em

        resp = client.get("/entities/search?query=Alice")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_get_entity(self, client, api_state):
        entity = MagicMock()
        entity.to_dict.return_value = {"id": "e-1", "name": "Alice"}
        rel = MagicMock()
        rel.to_dict.return_value = {"type": "knows"}
        mock_em = MagicMock()
        mock_em.get_entity.return_value = entity
        mock_em.generate_entity_context.return_value = "Alice is a developer"
        mock_em.get_relationships_for.return_value = [rel]
        api_state.entity_memory = mock_em

        resp = client.get("/entities/e-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["context"] == "Alice is a developer"
        assert len(data["relationships"]) == 1

    def test_get_entity_not_found(self, client, api_state):
        mock_em = MagicMock()
        mock_em.get_entity.return_value = None
        api_state.entity_memory = mock_em

        resp = client.get("/entities/nonexistent")
        assert resp.status_code == 404

    def test_delete_entity_success(self, client, api_state):
        mock_em = MagicMock()
        mock_em.delete_entity.return_value = True
        api_state.entity_memory = mock_em

        resp = client.delete("/entities/e-1")
        assert resp.status_code == 200

    def test_delete_entity_not_found(self, client, api_state):
        mock_em = MagicMock()
        mock_em.delete_entity.return_value = False
        api_state.entity_memory = mock_em

        resp = client.delete("/entities/e-bad")
        assert resp.status_code == 404

    def test_entity_timeline(self, client, api_state):
        interaction = MagicMock()
        interaction.to_dict.return_value = {"entity_id": "e-1", "summary": "chat"}
        mock_em = MagicMock()
        mock_em.get_interaction_timeline.return_value = [interaction]
        api_state.entity_memory = mock_em

        resp = client.get("/entities/e-1/timeline")
        assert resp.status_code == 200
        assert len(resp.json()["interactions"]) == 1

    def test_entity_stats_route_shadowed(self, client, api_state):
        """Note: /entities/stats is shadowed by /entities/{entity_id} route ordering."""
        # The route is unreachable — {entity_id} catches "stats" first.
        # This test documents the behavior.
        mock_em = MagicMock()
        mock_em.get_entity.return_value = None
        api_state.entity_memory = mock_em

        resp = client.get("/entities/stats")
        # Returns 404 because get_entity("stats") finds nothing
        assert resp.status_code == 404


# ===================================================================
# api.py — Autonomous endpoints
# ===================================================================


@skip_no_fastapi
class TestAPIAutonomousEndpoints:
    def test_list_actions_no_executor(self, client, api_state):
        api_state.executor = None
        resp = client.get("/autonomous/actions")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_list_actions_with_executor(self, client, api_state):
        action = MagicMock()
        action.to_dict.return_value = {"id": "a-1", "action": "send_email"}
        mock_ex = MagicMock()
        mock_ex.get_recent_actions.return_value = [action]
        api_state.executor = mock_ex

        resp = client.get("/autonomous/actions")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_pending_actions_no_executor(self, client, api_state):
        api_state.executor = None
        resp = client.get("/autonomous/pending")
        assert resp.status_code == 200
        assert resp.json()["actions"] == []

    def test_pending_actions_with_executor(self, client, api_state):
        action = MagicMock()
        action.to_dict.return_value = {"id": "a-2", "status": "pending"}
        mock_ex = MagicMock()
        mock_ex.get_pending_actions.return_value = [action]
        api_state.executor = mock_ex

        resp = client.get("/autonomous/pending")
        assert resp.status_code == 200
        assert len(resp.json()["actions"]) == 1

    def test_approve_action_success(self, client, api_state):
        action = MagicMock()
        action.to_dict.return_value = {"id": "a-1", "status": "approved"}
        mock_ex = MagicMock()
        mock_ex.approve_action.return_value = action
        api_state.executor = mock_ex

        resp = client.post("/autonomous/actions/a-1/approve")
        assert resp.status_code == 200

    def test_approve_action_not_found(self, client, api_state):
        mock_ex = MagicMock()
        mock_ex.approve_action.return_value = None
        api_state.executor = mock_ex

        resp = client.post("/autonomous/actions/a-bad/approve")
        assert resp.status_code == 404

    def test_approve_action_no_executor(self, client, api_state):
        api_state.executor = None
        resp = client.post("/autonomous/actions/a-1/approve")
        assert resp.status_code == 404

    def test_deny_action_success(self, client, api_state):
        action = MagicMock()
        action.to_dict.return_value = {"id": "a-1", "status": "denied"}
        mock_ex = MagicMock()
        mock_ex.deny_action.return_value = action
        api_state.executor = mock_ex

        resp = client.post("/autonomous/actions/a-1/deny")
        assert resp.status_code == 200

    def test_deny_action_not_found(self, client, api_state):
        mock_ex = MagicMock()
        mock_ex.deny_action.return_value = None
        api_state.executor = mock_ex

        resp = client.post("/autonomous/actions/a-bad/deny")
        assert resp.status_code == 404

    def test_deny_action_no_executor(self, client, api_state):
        api_state.executor = None
        resp = client.post("/autonomous/actions/a-1/deny")
        assert resp.status_code == 404

    def test_autonomous_stats_no_executor(self, client, api_state):
        api_state.executor = None
        resp = client.get("/autonomous/stats")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_autonomous_stats_with_executor(self, client, api_state):
        mock_ex = MagicMock()
        mock_ex.get_statistics.return_value = {"actions_taken": 10}
        api_state.executor = mock_ex

        resp = client.get("/autonomous/stats")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True


# ===================================================================
# memory.py — LocalMemoryStore edge cases
# ===================================================================


class TestLocalMemoryStoreCoverage:
    def test_update_not_found(self, tmp_path):
        from animus.memory import LocalMemoryStore, Memory, MemoryType

        store = LocalMemoryStore(tmp_path)
        m = Memory.create(content="test", memory_type=MemoryType.SEMANTIC)
        assert store.update(m) is False

    def test_delete_not_found(self, tmp_path):
        from animus.memory import LocalMemoryStore

        store = LocalMemoryStore(tmp_path)
        deleted = store.delete("nonexistent")
        assert deleted is False

    def test_search_with_type_filter(self, tmp_path):
        from animus.memory import LocalMemoryStore, Memory, MemoryType

        store = LocalMemoryStore(tmp_path)
        store.store(Memory.create(content="hello world", memory_type=MemoryType.SEMANTIC))
        store.store(Memory.create(content="hello episodic", memory_type=MemoryType.EPISODIC))

        results = store.search("hello", memory_type=MemoryType.SEMANTIC)
        assert len(results) == 1
        assert results[0].memory_type == MemoryType.SEMANTIC

    def test_search_with_limit(self, tmp_path):
        from animus.memory import LocalMemoryStore, Memory, MemoryType

        store = LocalMemoryStore(tmp_path)
        for i in range(10):
            store.store(Memory.create(content=f"item {i} hello", memory_type=MemoryType.SEMANTIC))

        results = store.search("hello", limit=3)
        assert len(results) == 3


# ===================================================================
# memory.py — MemoryLayer edge cases
# ===================================================================


class TestMemoryLayerCoverage:
    def test_missing_chroma_does_not_open_a_different_store(self, tmp_path):
        """A missing optional backend must not silently hide existing memories."""
        from animus.memory import MemoryLayer

        with (
            patch("animus.memory.ChromaMemoryStore", side_effect=ImportError("no chroma")),
            patch("animus.memory.LocalMemoryStore") as local_store,
            pytest.raises(RuntimeError, match="no fallback store was opened"),
        ):
            MemoryLayer(tmp_path, backend="chroma")
        local_store.assert_not_called()

    def test_get_memory_partial_match(self, tmp_path):
        """Lines 865-867: partial ID match via startswith."""
        from animus.memory import MemoryLayer, MemoryType

        ml = MemoryLayer(tmp_path, backend="json")
        m = ml.remember("test content", memory_type=MemoryType.SEMANTIC)

        # Partial match with first 8 chars
        found = ml.get_memory(m.id[:8])
        assert found is not None
        assert found.id == m.id

    def test_add_tag_not_found(self, tmp_path):
        """Line 881: add_tag returns False for missing memory."""
        from animus.memory import MemoryLayer

        ml = MemoryLayer(tmp_path, backend="json")
        assert ml.add_tag("nonexistent", "tag1") is False

    def test_remove_tag_not_found(self, tmp_path):
        """Line 889: remove_tag returns False for missing memory."""
        from animus.memory import MemoryLayer

        ml = MemoryLayer(tmp_path, backend="json")
        assert ml.remove_tag("nonexistent", "tag1") is False

    def test_remove_tag_not_present(self, tmp_path):
        """Line 889: remove_tag returns False when tag not on memory."""
        from animus.memory import MemoryLayer, MemoryType

        ml = MemoryLayer(tmp_path, backend="json")
        m = ml.remember("test", memory_type=MemoryType.SEMANTIC, tags=["existing"])

        assert ml.remove_tag(m.id, "not_on_memory") is False

    def test_forget_with_entity_cleanup(self, tmp_path):
        """Lines 904-905: forget calls entity_memory cleanup."""
        from animus.memory import MemoryLayer, MemoryType

        mock_em = MagicMock()
        ml = MemoryLayer(tmp_path, backend="json", entity_memory=mock_em)
        m = ml.remember("test", memory_type=MemoryType.SEMANTIC)

        ml.forget(m.id)
        mock_em.remove_interactions_for_memory.assert_called_once_with(m.id)

    def test_forget_entity_cleanup_exception(self, tmp_path):
        """Lines 904-905: entity cleanup exception is swallowed."""
        from animus.memory import MemoryLayer, MemoryType

        mock_em = MagicMock()
        mock_em.remove_interactions_for_memory.side_effect = RuntimeError("DB error")
        ml = MemoryLayer(tmp_path, backend="json", entity_memory=mock_em)
        m = ml.remember("test", memory_type=MemoryType.SEMANTIC)

        # Should not raise
        assert ml.forget(m.id) is True

    def test_import_entity_linking_exception(self, tmp_path):
        """Lines 980-981: entity linking exception during import."""
        import json

        from animus.memory import MemoryLayer, MemoryType

        mock_em = MagicMock()
        mock_em.extract_and_link.side_effect = RuntimeError("NER failed")
        ml = MemoryLayer(tmp_path, backend="json", entity_memory=mock_em)

        # Export then import
        ml.remember("test entity", memory_type=MemoryType.SEMANTIC)
        memories = ml.store.list_all()
        exported = json.dumps([mem.to_dict() for mem in memories])

        # Create a fresh layer for import
        ml2 = MemoryLayer(tmp_path / "import_dest", backend="json", entity_memory=mock_em)
        count = ml2.import_memories(exported)
        assert count >= 1

    def test_backup_no_zip_suffix(self, tmp_path):
        """Lines 994-997: backup appends .zip if missing."""
        from animus.memory import MemoryLayer

        ml = MemoryLayer(tmp_path / "data", backend="json")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)

        backup_path = tmp_path / "my_backup"
        with patch.object(shutil, "make_archive") as mock_archive:
            ml.backup(backup_path)
            # Should have appended .zip
            call_args = mock_archive.call_args
            assert str(call_args[0][0]).endswith("my_backup")
            assert call_args[0][1] == "zip"

    def test_backup_with_zip_suffix(self, tmp_path):
        """Lines 994-997: backup with .zip suffix stays as-is."""
        from animus.memory import MemoryLayer

        ml = MemoryLayer(tmp_path / "data", backend="json")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)

        backup_path = tmp_path / "my_backup.zip"
        with patch.object(shutil, "make_archive") as mock_archive:
            ml.backup(backup_path)
            call_args = mock_archive.call_args
            assert str(call_args[0][0]).endswith("my_backup")

    def test_statistics_with_subtypes(self, tmp_path):
        """Line 1014: get_statistics counts subtypes."""
        from animus.memory import MemoryLayer, MemoryType

        ml = MemoryLayer(tmp_path, backend="json")
        ml.remember("fact 1", memory_type=MemoryType.SEMANTIC, subtype="fact")
        ml.remember("pref 1", memory_type=MemoryType.SEMANTIC, subtype="preference")
        ml.remember("no subtype", memory_type=MemoryType.EPISODIC)

        stats = ml.get_statistics()
        assert stats["by_subtype"]["fact"] == 1
        assert stats["by_subtype"]["preference"] == 1
        assert stats["total"] == 3
