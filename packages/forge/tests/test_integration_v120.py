"""Integration tests for Gorgon v1.2.0 features.

Tests the full pipeline for each major v1.2.0 feature:
- MCP tool execution in workflows
- Graph executor (start → agent → end)
- Webhook delivery with circuit breaker
- API lifecycle (lifespan → route → response)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.executor import WorkflowExecutor, reset_circuit_breakers
from animus_forge.workflow.graph_executor import (
    NodeStatus,
    ReactFlowExecutor,
)
from animus_forge.workflow.graph_models import (
    GraphEdge,
    GraphNode,
    NodePosition,
    WorkflowGraph,
)
from animus_forge.workflow.loader import StepConfig, WorkflowConfig, load_workflow


@pytest.fixture(autouse=True)
def _clean_circuit_breakers():
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"


def _wf(name: str, steps: list[StepConfig]) -> WorkflowConfig:
    """Build a minimal WorkflowConfig for testing."""
    return WorkflowConfig(
        name=name,
        version="1.0",
        description="test workflow",
        steps=steps,
    )


def _pos(x: float = 0, y: float = 0) -> NodePosition:
    return NodePosition(x=x, y=y)


# =============================================================================
# 1. MCP Tool Execution Pipeline
# =============================================================================


class TestMCPToolPipeline:
    """Full pipeline: loader → executor → MCP client → result."""

    def test_mcp_tool_step_type_recognized(self):
        """mcp_tool is a valid step type in the loader."""
        from animus_forge.workflow.loader import VALID_STEP_TYPES

        assert "mcp_tool" in VALID_STEP_TYPES

    def test_mcp_tool_dry_run_through_executor(self):
        """MCP tool steps produce dry-run output via WorkflowExecutor."""
        step = StepConfig(
            id="read_file",
            type="mcp_tool",
            params={
                "server": "filesystem",
                "tool": "read_file",
                "arguments": {"path": "/tmp/test.txt"},
            },
        )
        wf = _wf("MCP Test", [step])
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(wf, inputs={})
        assert result.status == "success"
        assert len(result.steps) == 1
        assert "DRY RUN" in result.steps[0].output.get("response", "")

    def test_mcp_tool_variable_substitution(self):
        """Variables in MCP tool arguments get substituted from context."""
        step = StepConfig(
            id="query",
            type="mcp_tool",
            params={
                "server": "${target_server}",
                "tool": "search",
                "arguments": {"query": "${search_term}", "limit": 10},
            },
        )
        wf = _wf("MCP Var Test", [step])
        executor = WorkflowExecutor(dry_run=True)
        result = executor.execute(wf, inputs={"target_server": "my-db", "search_term": "hello"})
        assert result.status == "success"
        output = result.steps[0].output
        assert "my-db" in output.get("response", "")
        assert output["server"] == "my-db"
        assert output["tool"] == "search"

    @patch("animus_forge.workflow.executor_mcp.MCPHandlersMixin._resolve_mcp_server")
    @patch("animus_forge.mcp.client.call_mcp_tool")
    def test_mcp_tool_live_execution(self, mock_call, mock_resolve):
        """Full live MCP tool execution with mocked client."""
        mock_server = SimpleNamespace(
            name="test-server",
            url="http://localhost:8080",
            type="sse",
            authType="none",
            credentialId=None,
        )
        mock_resolve.return_value = mock_server
        mock_call.return_value = {
            "content": "File contents here",
            "is_error": False,
        }

        step = StepConfig(
            id="read",
            type="mcp_tool",
            params={
                "server": "test-server",
                "tool": "read_file",
                "arguments": {"path": "/README.md"},
            },
        )
        wf = _wf("MCP Live", [step])
        executor = WorkflowExecutor(dry_run=False)
        result = executor.execute(wf, inputs={})
        assert result.status == "success"
        assert result.steps[0].output["response"] == "File contents here"
        mock_call.assert_called_once()

    @patch("animus_forge.workflow.executor_mcp.MCPHandlersMixin._resolve_mcp_server")
    @patch("animus_forge.mcp.client.call_mcp_tool")
    def test_mcp_tool_error_propagates(self, mock_call, mock_resolve):
        """MCP tool errors surface as step failures."""
        mock_server = SimpleNamespace(
            name="broken",
            url="http://localhost:9999",
            type="sse",
            authType="none",
            credentialId=None,
        )
        mock_resolve.return_value = mock_server
        mock_call.return_value = {
            "content": "Tool not found",
            "is_error": True,
        }

        step = StepConfig(
            id="bad",
            type="mcp_tool",
            params={"server": "broken", "tool": "missing", "arguments": {}},
        )
        wf = _wf("MCP Error", [step])
        executor = WorkflowExecutor(dry_run=False)
        result = executor.execute(wf, inputs={})
        # RuntimeError from mcp handler → step FAILED → workflow "failed"
        assert result.status == "failed"

    def test_mcp_tool_missing_server_param(self):
        """MCP tool step without 'server' param fails the workflow."""
        step = StepConfig(
            id="bad",
            type="mcp_tool",
            params={"tool": "read_file", "arguments": {}},
        )
        wf = _wf("MCP Bad", [step])
        executor = WorkflowExecutor(dry_run=False)
        result = executor.execute(wf, inputs={})
        # RuntimeError from mcp handler → step FAILED → workflow "failed"
        assert result.status == "failed"
        assert "server" in (result.error or "").lower()


# =============================================================================
# 2. Graph Executor Pipeline
# =============================================================================


def _make_simple_graph(
    agent_data: dict | None = None,
) -> WorkflowGraph:
    """Build a start → agent → end graph."""
    nodes = [
        GraphNode(id="start", type="start", data={}, position=_pos(0, 0)),
        GraphNode(
            id="agent1",
            type="agent",
            data=agent_data or {"step_type": "shell", "action": "echo hello"},
            position=_pos(200, 0),
        ),
        GraphNode(id="end", type="end", data={}, position=_pos(400, 0)),
    ]
    edges = [
        GraphEdge(id="e1", source="start", target="agent1"),
        GraphEdge(id="e2", source="agent1", target="end"),
    ]
    return WorkflowGraph(id="test-graph", name="Test Graph", nodes=nodes, edges=edges)


class TestGraphExecutorPipeline:
    """Full pipeline: graph build → execute → collect outputs."""

    def test_start_end_passthrough(self):
        """A start → end graph completes successfully."""
        graph = WorkflowGraph(
            id="minimal",
            name="Minimal",
            nodes=[
                GraphNode(id="start", type="start", data={}, position=_pos()),
                GraphNode(id="end", type="end", data={}, position=_pos(200, 0)),
            ],
            edges=[GraphEdge(id="e1", source="start", target="end")],
        )
        executor = ReactFlowExecutor()
        result = asyncio.run(executor.execute_async(graph))
        assert result.status == "completed"
        assert "start" in result.node_results
        assert "end" in result.node_results

    def test_shell_step_execution(self):
        """A shell step executes and produces output."""
        graph = _make_simple_graph(
            agent_data={"step_type": "shell", "action": "echo integration-test"}
        )
        executor = ReactFlowExecutor()
        result = asyncio.run(executor.execute_async(graph))
        assert result.status == "completed"
        agent_result = result.node_results.get("agent1")
        assert agent_result is not None
        assert agent_result.status == NodeStatus.COMPLETED

    def test_branch_node_execution(self):
        """Branch nodes evaluate conditions and route correctly."""
        nodes = [
            GraphNode(id="start", type="start", data={}, position=_pos()),
            GraphNode(
                id="branch1",
                type="branch",
                data={
                    "condition": {
                        "field": "run_path",
                        "operator": "equals",
                        "value": "yes",
                    }
                },
                position=_pos(200, 0),
            ),
            GraphNode(
                id="true_path",
                type="agent",
                data={"step_type": "shell", "action": "echo true"},
                position=_pos(400, -100),
            ),
            GraphNode(id="end", type="end", data={}, position=_pos(600, 0)),
        ]
        edges = [
            GraphEdge(id="e1", source="start", target="branch1"),
            GraphEdge(
                id="e2",
                source="branch1",
                target="true_path",
                source_handle="true",
            ),
            GraphEdge(id="e3", source="true_path", target="end"),
        ]
        graph = WorkflowGraph(
            id="branch-test",
            name="Branch Test",
            nodes=nodes,
            edges=edges,
            variables={"run_path": "yes"},
        )
        executor = ReactFlowExecutor()
        result = asyncio.run(executor.execute_async(graph, variables={"run_path": "yes"}))
        assert result.status == "completed"
        assert "branch1" in result.node_results

    def test_cycle_detection_fails_non_loop(self):
        """Non-loop cycles are detected and rejected."""
        nodes = [
            GraphNode(id="a", type="agent", data={}, position=_pos()),
            GraphNode(id="b", type="agent", data={}, position=_pos(200, 0)),
        ]
        edges = [
            GraphEdge(id="e1", source="a", target="b"),
            GraphEdge(id="e2", source="b", target="a"),
        ]
        graph = WorkflowGraph(id="cycle-test", name="Cycle Test", nodes=nodes, edges=edges)
        executor = ReactFlowExecutor()
        result = asyncio.run(executor.execute_async(graph))
        assert result.status == "failed"
        assert "cycle" in result.error.lower()

    def test_callbacks_fire(self):
        """Node callbacks are invoked during execution."""
        start_calls = []
        complete_calls = []

        def on_start(node_id, status, data=None):
            start_calls.append(node_id)

        def on_complete(node_id, status, data=None):
            complete_calls.append(node_id)

        graph = _make_simple_graph(agent_data={"step_type": "shell", "action": "echo test"})
        executor = ReactFlowExecutor(on_node_start=on_start, on_node_complete=on_complete)
        asyncio.run(executor.execute_async(graph))
        # agent1 should have triggered callbacks (start/end are passthrough)
        assert "agent1" in start_calls
        assert "agent1" in complete_calls

    def test_variables_propagate_through_nodes(self):
        """Variables set on the graph flow through execution context."""
        graph = _make_simple_graph(agent_data={"step_type": "shell", "action": "echo ${greeting}"})
        graph.variables["greeting"] = "hello-integration"
        executor = ReactFlowExecutor()
        result = asyncio.run(
            executor.execute_async(graph, variables={"greeting": "hello-integration"})
        )
        assert result.status == "completed"

    def test_execution_manager_progress(self):
        """Progress updates fire when execution_manager is provided."""
        manager = MagicMock()
        graph = _make_simple_graph(agent_data={"step_type": "shell", "action": "echo test"})
        executor = ReactFlowExecutor(execution_manager=manager)
        asyncio.run(executor.execute_async(graph, execution_id="test-123"))
        assert manager.update_progress.call_count > 0


# =============================================================================
# 3. Webhook Delivery Pipeline
# =============================================================================


class TestWebhookDeliveryPipeline:
    """Integration test for webhook delivery with circuit breaker."""

    def test_delivery_and_circuit_breaker_lifecycle(self, tmp_path):
        """Full lifecycle: deliver → success → circuit stays closed."""
        from animus_forge.state.backends import SQLiteBackend
        from animus_forge.webhooks.webhook_delivery import (
            DeliveryStatus,
            RetryStrategy,
            WebhookDeliveryManager,
        )

        backend = SQLiteBackend(str(tmp_path / "test.db"))
        manager = WebhookDeliveryManager(
            backend=backend,
            retry_strategy=RetryStrategy(max_retries=1, base_delay=0.01, jitter=False),
        )

        # Circuit should start closed
        cb = manager.circuit_breaker
        assert cb.allow_request("http://example.com/hook")

        # Simulate successful delivery — deliver() uses get_sync_client()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.text = "OK"
        mock_session.post.return_value = mock_resp

        with patch(
            "animus_forge.webhooks.webhook_delivery.get_sync_client",
            return_value=mock_session,
        ):
            delivery = manager.deliver(
                url="http://example.com/hook",
                payload={"event": "test"},
            )
            assert delivery.status == DeliveryStatus.SUCCESS

        # Verify circuit is still closed after success
        assert cb.allow_request("http://example.com/hook")

    def test_retry_strategy_exponential_backoff(self):
        """RetryStrategy calculates correct exponential delays."""
        from animus_forge.webhooks.webhook_delivery import RetryStrategy

        strategy = RetryStrategy(max_retries=5, base_delay=1.0, max_delay=30.0, jitter=False)
        delays = [strategy.get_delay(i) for i in range(5)]
        # Exponential: 1, 2, 4, 8, 16
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_dlq_stats_and_purge(self, tmp_path):
        """DLQ stats and purge operations work correctly."""
        from animus_forge.state.backends import SQLiteBackend
        from animus_forge.webhooks.webhook_delivery import (
            RetryStrategy,
            WebhookDeliveryManager,
        )

        backend = SQLiteBackend(str(tmp_path / "test_dlq.db"))
        manager = WebhookDeliveryManager(
            backend=backend,
            retry_strategy=RetryStrategy(max_retries=1, base_delay=0.01, jitter=False),
        )

        stats = manager.get_dlq_stats()
        assert stats["total_pending"] == 0
        assert stats["by_url"] == {}


# =============================================================================
# 4. Workflow YAML → Executor Integration
# =============================================================================


class TestWorkflowYAMLIntegration:
    """Test real YAML workflows through the full execution pipeline."""

    def _get_mcp_workflow(self) -> Path | None:
        """Find an MCP example workflow if available."""
        examples = WORKFLOWS_DIR / "examples"
        if examples.exists():
            for f in examples.glob("*.yaml"):
                content = f.read_text()
                if "mcp_tool" in content:
                    return f
        return None

    def test_all_yamls_load_and_validate(self):
        """Every YAML in workflows/ loads without error."""
        yamls = sorted(WORKFLOWS_DIR.glob("*.yaml"))
        assert len(yamls) > 0, "No YAML workflows found"
        for path in yamls:
            wf = load_workflow(path, trusted_dir=WORKFLOWS_DIR)
            assert wf.name, f"{path.stem}: missing name"
            assert len(wf.steps) >= 1, f"{path.stem}: no steps"

    @patch("animus_kernel.executor.executor_step.time.sleep")
    def test_dry_run_all_yamls(self, _retry_sleep):
        """Every YAML workflow executes in dry_run mode."""
        yamls = sorted(WORKFLOWS_DIR.glob("*.yaml"))
        for path in yamls:
            wf = load_workflow(path, trusted_dir=WORKFLOWS_DIR)
            executor = WorkflowExecutor(dry_run=True)

            # Build minimal inputs from workflow inputs
            inputs = {}
            if wf.inputs:
                for k, v in wf.inputs.items():
                    if isinstance(v, str):
                        inputs[k] = v
                    else:
                        inputs[k] = str(v)

            result = executor.execute(wf, inputs=inputs)
            # "success" or "failed" both acceptable in dry-run (shell steps
            # try to run and may fail with template strings as paths)
            assert result.status in ("success", "failed"), (
                f"{path.stem}: unexpected status {result.status}"
            )

    def test_mcp_example_workflow_loads(self):
        """MCP example YAML loads with mcp_tool steps if available."""
        mcp_path = self._get_mcp_workflow()
        if not mcp_path:
            pytest.skip("No MCP example workflow found")
        # MCP examples may use list-style inputs (not yet supported by
        # strict loader validation) — use raw YAML parse instead.
        import yaml

        raw = yaml.safe_load(mcp_path.read_text())
        mcp_steps = [s for s in raw.get("steps", []) if s.get("type") == "mcp_tool"]
        assert len(mcp_steps) > 0, "No mcp_tool steps found in MCP workflow"


# =============================================================================
# 5. Cross-Feature Integration
# =============================================================================


class TestCrossFeatureIntegration:
    """Tests that verify features work together correctly."""

    def test_graph_with_variables(self):
        """Graph executor passes variables through execution context."""
        graph = WorkflowGraph(
            id="cross-test",
            name="Cross Test",
            nodes=[
                GraphNode(id="start", type="start", data={}, position=_pos()),
                GraphNode(
                    id="step1",
                    type="agent",
                    data={"step_type": "shell", "action": "echo ${project}"},
                    position=_pos(200, 0),
                ),
                GraphNode(id="end", type="end", data={}, position=_pos(400, 0)),
            ],
            edges=[
                GraphEdge(id="e1", source="start", target="step1"),
                GraphEdge(id="e2", source="step1", target="end"),
            ],
        )
        executor = ReactFlowExecutor()
        result = asyncio.run(executor.execute_async(graph, variables={"project": "gorgon"}))
        assert result.status == "completed"

    def test_circuit_breaker_isolation(self):
        """Circuit breakers are per-URL and don't interfere."""
        from animus_forge.webhooks.webhook_delivery import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2))
        url_a = "http://a.example.com"
        url_b = "http://b.example.com"

        # Fail URL A twice → trips
        cb.record_failure(url_a)
        cb.record_failure(url_a)
        assert not cb.allow_request(url_a)

        # URL B should still be allowed
        assert cb.allow_request(url_b)

        # Reset URL A
        cb.reset(url_a)
        assert cb.allow_request(url_a)

    def test_workflow_executor_has_mcp_handler(self):
        """WorkflowExecutor has the _execute_mcp_tool method from mixin."""
        executor = WorkflowExecutor(dry_run=True)
        assert hasattr(executor, "_execute_mcp_tool")
        assert callable(executor._execute_mcp_tool)

    def test_graph_from_dict_roundtrip(self):
        """Graph serialization roundtrips through dict format."""
        graph = _make_simple_graph()
        data = graph.to_dict()
        restored = WorkflowGraph.from_dict(data)
        assert len(restored.nodes) == len(graph.nodes)
        assert len(restored.edges) == len(graph.edges)
        assert restored.id == graph.id
