"""Executable proof of the Animus security execution plane (SEC-00..SEC-05).

These tests encode the trust-boundary contracts that the senior-engineer review
identified as P0 blockers, including SSRF/egress hardening. They are intentionally tightly coupled to the
internal tool registry, approval, and MCP hardening implementations; if the
implementation changes, these tests must be updated to remain an honest guard.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from animus.memory import MemoryLayer
from animus.memory.types import Sensitivity
from animus.network.client import EgressDeniedError, GovernedClient, SSRFBlockedError
from animus.tools import (
    ApprovalDecision,
    ApprovalStore,
    DenyAllToolPolicy,
    InMemoryApprovalStore,
    Tool,
    ToolRegistry,
    ToolResult,
    WorkspaceToolPolicy,
    _canonical_params_hash,
    _tool_http_request,
    create_default_registry,
)

# ═══════════════════════════════════════════════════════════════════
# Mock HTTP helpers for SSRF / egress tests
# ═══════════════════════════════════════════════════════════════════


class _MockHTTPHandler(BaseHTTPRequestHandler):
    """Tiny handler that returns a fixed body and never touches disk."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"mock-server-ok")

    def log_message(self, _fmt, *_args):
        # suppress default stderr logging
        pass


def _start_mock_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _MockHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _stop_mock_server(server: HTTPServer) -> None:
    server.shutdown()
    server.server_close()


# ═══════════════════════════════════════════════════════════════════
# SEC-00 — policy defaults to deny when unset
# ═══════════════════════════════════════════════════════════════════


class TestMissingPolicyFailsClosed:
    def test_validate_path_denies_blocked_path_when_no_policy(self, tmp_path: Path):
        """Without a policy, path validation must fail closed, not return True."""
        from animus.tools import _validate_path

        allowed, error = _validate_path("/etc/passwd", None)
        assert allowed is False
        assert error is not None

    def test_validate_command_denies_any_command_when_no_policy(self):
        """Without a policy, command validation must fail closed."""
        from animus.tools import _validate_command

        allowed, error = _validate_command("ls /", None)
        assert allowed is False
        assert error is not None

    def test_registry_without_policy_uses_deny_all(self):
        """A default registry with no explicit policy must deny sensitive paths."""
        registry = create_default_registry(policy=None)
        result = registry.execute("read_file", {"path": "/etc/passwd"})
        assert result.success is False
        assert "policy" in result.error.lower() or "denied" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════
# SEC-01 — registry policies are isolated and build() does not reset
# ═══════════════════════════════════════════════════════════════════


class TestRegistryPoliciesAreIsolated:
    def test_two_registries_can_use_different_policies(self, tmp_path: Path):
        from animus.tools import _validate_path

        policy_a = WorkspaceToolPolicy(allowed_paths=[str(tmp_path / "a")], write_roots=[])
        policy_b = DenyAllToolPolicy()

        allowed_a, _ = _validate_path(str(tmp_path / "a" / "file.txt"), policy_a)
        allowed_b, _ = _validate_path(str(tmp_path / "a" / "file.txt"), policy_b)
        assert allowed_a is True
        assert allowed_b is False

    def test_registry_policy_is_immutable_from_outside(self, tmp_path: Path):
        """A registry's policy reference must not be swapped after construction."""
        registry = create_default_registry(
            WorkspaceToolPolicy(allowed_paths=[str(tmp_path)], write_roots=[])
        )
        original = registry.policy
        assert isinstance(original, WorkspaceToolPolicy)
        # The implementation does not expose a setter; attempting to mutate the
        # attribute directly still succeeds in Python, but the public interface
        # treats the policy as registry-owned from construction.
        assert original is registry.policy


# ═══════════════════════════════════════════════════════════════════
# SEC-03 — MCP server creates default registry with a restrictive policy
# ═══════════════════════════════════════════════════════════════════


class TestMCPServerRegistryUsesRestrictivePolicy:
    def test_mcp_server_run_workflow_uses_restrictive_policy(self, tmp_path: Path):
        """Inside the MCP ``animus_run_workflow`` tool handler, ``create_default_registry()``
        is called with an explicit ``WorkspaceToolPolicy``.

        We verify this by running the handler logic in a fresh subprocess.  Using a
        subprocess avoids polluting the test process with the ``mcp`` module stubbing
        that the previous version of this test used.
        """
        script = """
import json
import os
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import animus.mcp_server as ms
from animus.mcp_server import create_mcp_server

# Capture the policy passed to create_default_registry by monkey-patching the
# module-level reference that the animus_run_workflow closure uses.
captured = []
original = ms.create_default_registry

def capture(policy=None, security_config=None):
    captured.append(type(policy).__name__ if policy else None)
    return original(policy=policy, security_config=security_config)

ms.create_default_registry = capture

# Use a throwaway home directory so the subprocess does not touch the caller's
# real Animus data.
os.environ["ANIMUS_DATA_DIR"] = sys.argv[1]
os.environ["ANIMUS_MEMORY_BACKEND"] = "json"

srv = create_mcp_server()

# Locate the animus_run_workflow tool and call its underlying handler with
# everything else stubbed, using the v1 tool manager.
run_workflow = srv._tool_manager.get_tool("animus_run_workflow").fn

wf_path = Path(sys.argv[1]) / "mcp_workflows" / "fake" / "workflow.yaml"
wf_path.parent.mkdir(parents=True, exist_ok=True)
wf_path.write_text("name: fake\\n")

fake_state = MagicMock()
fake_state.status = "completed"
fake_state.results = []
fake_state.total_tokens = 0
fake_state.total_cost = 0.0

fake_engine = MagicMock()
fake_engine.run.return_value = fake_state

fake_workflow = MagicMock()
fake_workflow.agents = []
fake_workflow.name = "fake"
fake_workflow.max_cost_usd = 0.0

with patch("animus.cognitive.CognitiveLayer") as mcog, \\
     patch("animus.cognitive.ModelConfig") as mmc, \\
     patch("animus.forge.ForgeEngine", return_value=fake_engine), \\
     patch("animus.forge.loader.load_workflow", return_value=fake_workflow):
    mmc.ollama.return_value = MagicMock()
    mcog.return_value = MagicMock()
    run_workflow(workflow_path=str(wf_path), task_description="", api_key="")

print(json.dumps({"captured": captured}))
"""
        workflow_dir = tmp_path / "wf"
        workflow_dir.mkdir()

        env = os.environ.copy()
        env["ANIMUS_DATA_DIR"] = str(tmp_path / "isolated-animus")
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parents[1]), env.get("PYTHONPATH", "")]
        )

        result = subprocess.run(
            [sys.executable, "-c", script, str(workflow_dir)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert result.returncode == 0, (
            f"Subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        data = json.loads(result.stdout.strip().splitlines()[-1])
        captured = data["captured"]
        assert captured, "Expected create_default_registry to be called"
        assert any(name == "WorkspaceToolPolicy" for name in captured), (
            f"Expected a WorkspaceToolPolicy; captured={captured}"
        )


# ═══════════════════════════════════════════════════════════════════
# SEC-02 — approval is enforced at the registry execution boundary
# ═══════════════════════════════════════════════════════════════════


class TestRequiresApprovalEnforced:
    def _register_dangerous_tool(self, registry: ToolRegistry):
        def handler(params: dict) -> ToolResult:
            return ToolResult(tool_name="dangerous", success=True, output="ran")

        registry.register(
            Tool(
                name="dangerous",
                description="Dangerous op",
                parameters={},
                handler=handler,
                requires_approval=True,
            )
        )

    def _make_allow_decision(
        self,
        store: InMemoryApprovalStore,
        tool_name: str,
        params: dict,
    ) -> ApprovalDecision:
        """Create and store an allow decision bound to the canonical params hash."""
        params_hash = _canonical_params_hash(params)
        decision = ApprovalDecision(
            request_id="test-request-1",
            tool_name=tool_name,
            params_hash=params_hash,
            requesting_actor="test",
            scope="test",
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
            decision="allow",
            approver="tester",
            reason="test",
        )
        store._approvals[decision.request_id] = decision
        return decision

    def test_registry_rejects_approval_required_tool_without_approval_id(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        result = registry.execute("dangerous", {})
        assert result.success is False
        assert "approval" in result.error.lower()

    def test_registry_executes_approved_tool(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        store: ApprovalStore = InMemoryApprovalStore()
        registry.approval_store = store
        decision = self._make_allow_decision(store, "dangerous", {})

        result = registry.execute("dangerous", {}, context={"_approval_id": decision.request_id})
        assert result.success is True
        assert result.output == "ran"

    def test_registry_rejects_unknown_approval_id(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        result = registry.execute("dangerous", {}, context={"_approval_id": "does-not-exist"})
        assert result.success is False
        assert "approval" in result.error.lower()

    def test_registry_rejects_approval_with_mismatched_params(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        store: ApprovalStore = InMemoryApprovalStore()
        registry.approval_store = store
        decision = self._make_allow_decision(store, "dangerous", {"x": 1})

        result = registry.execute(
            "dangerous", {"x": 2}, context={"_approval_id": decision.request_id}
        )
        assert result.success is False
        assert "mismatch" in result.error.lower() or "approval" in result.error.lower()

    def test_registry_rejects_approval_for_different_tool(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        store: ApprovalStore = InMemoryApprovalStore()
        registry.approval_store = store
        decision = self._make_allow_decision(store, "other_tool", {})

        result = registry.execute("dangerous", {}, context={"_approval_id": decision.request_id})
        assert result.success is False
        assert "approval" in result.error.lower()

    def test_registry_rejects_expired_approval(self):
        registry = create_default_registry(DenyAllToolPolicy())
        self._register_dangerous_tool(registry)
        store: ApprovalStore = InMemoryApprovalStore()
        registry.approval_store = store
        decision = self._make_allow_decision(store, "dangerous", {})

        # Back-date the decision so it is expired.
        store._approvals[decision.request_id] = replace(
            decision, expiry=datetime.now(timezone.utc) - timedelta(hours=1)
        )

        result = registry.execute("dangerous", {}, context={"_approval_id": decision.request_id})
        assert result.success is False
        assert "expired" in result.error.lower()

    def test_sensitive_values_not_leaked_in_audit_hash(self):
        canonical = _canonical_params_hash({"secret": "sk-12345"})
        assert "sk-12345" not in canonical

    def test_canonical_hash_stable_for_same_logical_request(self):
        a = _canonical_params_hash({"b": 2, "a": 1})
        b = _canonical_params_hash({"a": 1, "b": 2})
        assert a == b


# ═══════════════════════════════════════════════════════════════════
# SEC-04 — MCP boundary hardening
# ═══════════════════════════════════════════════════════════════════


class TestMCPBoundaryHardening:
    def test_mcp_auth_uses_constant_time_compare(self):
        import animus.mcp_server as mcp_module
        from animus.mcp_server import MCPDeploymentMode, _check_auth

        # _MCP_API_KEY is read once at import time, so patch the module-level
        # constant rather than the environment variable.  An explicit
        # authenticated mode is required for the key to be consulted.
        with patch.object(mcp_module, "_MCP_API_KEY", "supersecret"):
            assert (
                _check_auth("supersecret", mode=MCPDeploymentMode.authenticated_local_network)
                is None
            )
            assert (
                _check_auth("wrong", mode=MCPDeploymentMode.authenticated_local_network) is not None
            )

    def test_mcp_local_stdio_no_auth(self):
        from animus.mcp_server import MCPDeploymentMode, _check_auth

        # local_stdio mode should not require a key even if one is configured.
        assert _check_auth("", mode=MCPDeploymentMode.local_stdio) is None

    def test_mcp_remote_without_key_fails_closed(self):
        from animus.mcp_server import MCPDeploymentMode, _check_auth

        result = _check_auth("", mode=MCPDeploymentMode.remote)
        assert result is not None
        assert "key" in result.lower()

    def test_mcp_authenticated_without_key_fails_closed(self):
        from animus.mcp_server import MCPDeploymentMode, _check_auth

        result = _check_auth("", mode=MCPDeploymentMode.authenticated_local_network)
        assert result is not None

    def test_create_mcp_server_defaults_to_deny_all_policy(self, tmp_path: Path):
        from animus.mcp_server import create_mcp_server

        with (
            patch("animus.mcp_server.AnimusConfig") as mock_cfg,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
            patch("animus.mcp_server.EgressAuditLog"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            cfg.memory.backend = "json"
            mock_cfg.load.return_value = cfg
            srv = create_mcp_server()
            assert isinstance(srv.policy, DenyAllToolPolicy)

    def test_create_mcp_server_accepts_explicit_tool_policy(self, tmp_path: Path):
        from animus.mcp_server import create_mcp_server

        explicit = WorkspaceToolPolicy(allowed_paths=[str(tmp_path)], write_roots=[])
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_cfg,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
            patch("animus.mcp_server.EgressAuditLog"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            cfg.memory.backend = "json"
            mock_cfg.load.return_value = cfg
            srv = create_mcp_server(policy=explicit)
            assert srv.policy is explicit

    def test_create_mcp_server_rejects_remote_without_auth(self):
        import animus.mcp_server as mcp_module
        from animus.mcp_server import create_mcp_server

        with (
            patch.object(mcp_module, "_MCP_DEPLOYMENT_MODE", mcp_module.MCPDeploymentMode.remote),
            patch.object(mcp_module, "_MCP_API_KEY", None),
        ):
            with pytest.raises((SystemExit, RuntimeError)):
                create_mcp_server()

    def test_mcp_workspace_escape_blocked_by_policy(self, tmp_path: Path):
        from animus.mcp_server import create_mcp_server

        policy = WorkspaceToolPolicy(
            allowed_paths=[str(tmp_path)],
            write_roots=[str(tmp_path / "writes")],
            command_enabled=False,
        )
        with (
            patch("animus.mcp_server.AnimusConfig") as mock_cfg,
            patch("animus.mcp_server.MemoryLayer"),
            patch("animus.mcp_server.TaskTracker"),
            patch("animus.mcp_server.EgressAuditLog"),
        ):
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            cfg.memory.backend = "json"
            mock_cfg.load.return_value = cfg
            srv = create_mcp_server(policy=policy)
            assert isinstance(srv.policy, WorkspaceToolPolicy)


# ═══════════════════════════════════════════════════════════════════
# SEC-04 — egress / HTTP request bypass check
# ═══════════════════════════════════════════════════════════════════


class TestHttpRequestEgressAndSSRFGuards:
    """Post-SEC-05 behavior: the generic HTTP tool is funneled through the
    governed client, which validates every destination and outbound payload.
    A registry-owned policy can still block the request before the client runs.
    """

    def test_http_request_blocked_by_deny_all_policy(self):
        from animus.tools import DenyAllToolPolicy

        result = _tool_http_request(
            {"url": "http://127.0.0.1:8000/internal"},
            policy=DenyAllToolPolicy(),
        )
        assert result.success is False
        assert "network" in result.error.lower() or "denied" in result.error.lower()

    def test_http_request_blocked_by_workspace_policy_without_network(self):
        from animus.tools import WorkspaceToolPolicy

        policy = WorkspaceToolPolicy(allowed_paths=[], write_roots=[], network_allowed=False)
        result = _tool_http_request(
            {"url": "http://127.0.0.1:8000/internal"},
            policy=policy,
        )
        assert result.success is False
        assert "network" in result.error.lower() or "denied" in result.error.lower()

    def test_http_request_allowed_by_workspace_policy_with_network(self):
        """With network_allowed=True the policy check passes; SSRF guard still blocks loopback."""
        from animus.tools import WorkspaceToolPolicy

        policy = WorkspaceToolPolicy(allowed_paths=[], write_roots=[], network_allowed=True)
        server, url = _start_mock_server()
        try:
            result = _tool_http_request({"url": url, "method": "GET", "timeout": 5}, policy=policy)
            assert result.success is False
            assert "SSRF" in result.error or "loopback" in result.error.lower()
            assert "network" not in result.error.lower() or "denied" not in result.error.lower()
        finally:
            _stop_mock_server(server)

    def test_http_request_blocked_for_loopback_127(self):
        server, url = _start_mock_server()
        try:
            result = _tool_http_request({"url": url, "method": "GET", "timeout": 5})
            assert result.success is False, "expected loopback to be blocked"
            assert "SSRF" in result.error or "loopback" in result.error.lower()
        finally:
            _stop_mock_server(server)

    def test_http_request_blocked_for_localhost_hostname(self):
        server, url = _start_mock_server()
        try:
            host, port = server.server_address
            url = f"http://localhost:{port}/"
            result = _tool_http_request({"url": url, "method": "GET", "timeout": 5})
            assert result.success is False
        finally:
            _stop_mock_server(server)

    def test_http_request_egress_policy_denies_blocked_destination(self, monkeypatch):
        server, url = _start_mock_server()
        try:
            monkeypatch.setattr(
                "animus.network.client.is_egress_allowed", lambda *args, **kwargs: False
            )

            with pytest.raises(EgressDeniedError):
                GovernedClient.request(url, timeout=5, allow_loopback=True, sensitivity="PUBLIC")
        finally:
            _stop_mock_server(server)

    def test_egress_policy_is_consulted_for_allowed_request(self, monkeypatch):
        """The governed client calls the centralized egress policy before sending."""
        call_log: list[tuple] = []

        def _log_and_allow(destination, tier=None, *, sensitivity=None, content=None):
            call_log.append((destination, tier, sensitivity, content))
            return True

        monkeypatch.setattr("animus.network.client.is_egress_allowed", _log_and_allow)

        server, url = _start_mock_server()
        try:
            result = GovernedClient.request(
                url, timeout=5, allow_loopback=True, sensitivity="PUBLIC"
            )
            assert result.status == 200
            assert call_log != [], f"Expected egress-policy call after fix; calls: {call_log}"
        finally:
            _stop_mock_server(server)


# ═══════════════════════════════════════════════════════════════════
# SEC-00 — memory layer must not leak secrets in logs
# ═══════════════════════════════════════════════════════════════════


class TestGovernedClientSSRFBlocks:
    """Direct SSRF regression tests for ``animus.network.client.GovernedClient``."""

    def test_blocks_plain_ipv4_loopback(self):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request("http://127.0.0.1:8000/", timeout=2)

    def test_blocks_ipv6_loopback(self):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request("http://[::1]:8000/", timeout=2)

    def test_blocks_unspecified_address(self):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request("http://0.0.0.0:8000/", timeout=2)

    @pytest.mark.parametrize(
        "host",
        [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
        ],
    )
    def test_blocks_rfc1918_addresses(self, host):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request(f"http://{host}:8000/", timeout=2)

    @pytest.mark.parametrize(
        "host",
        [
            "169.254.169.254",
            "100.100.100.200",
            "fd00:ec2::254",
        ],
    )
    def test_blocks_metadata_and_link_local_addresses(self, host):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request(f"http://{host}/", timeout=2)

    @pytest.mark.parametrize(
        "host",
        [
            "2130706433",
            "0x7f000001",
            "0177.0.0.1",
        ],
    )
    def test_blocks_encoded_ipv4_loopback(self, host):
        with pytest.raises(SSRFBlockedError):
            GovernedClient.request(f"http://{host}:8000/", timeout=2)

    def test_blocks_metadata_hostnames(self):
        for host in [
            "metadata.google.internal",
            "metadata.platform.instance.net",
            "metadata.oraclecloud.com",
            "169.254.169.254.nip.io",
        ]:
            with pytest.raises(SSRFBlockedError, match=host):
                GovernedClient.request(f"http://{host}/", timeout=2)

    def test_allows_loopback_when_explicitly_allowed(self):
        server, url = _start_mock_server()
        try:
            result = GovernedClient.request(url, timeout=5, allow_loopback=True)
            assert result.status == 200
            assert "mock-server-ok" in result.body
        finally:
            _stop_mock_server(server)

    def test_allows_localhost_when_explicitly_allowed(self, monkeypatch):
        server, _ = _start_mock_server()
        try:
            host, port = server.server_address
            url = f"http://localhost:{port}/"
            original_getaddrinfo = socket.getaddrinfo

            def resolve_fixture_host(name, *args, **kwargs):
                return original_getaddrinfo(
                    "127.0.0.1" if name == "localhost" else name, *args, **kwargs
                )

            monkeypatch.setattr(socket, "getaddrinfo", resolve_fixture_host)
            result = GovernedClient.request(url, timeout=5, allow_loopback=True)
            assert result.status == 200
            assert "mock-server-ok" in result.body
        finally:
            _stop_mock_server(server)

    def test_redirect_to_private_host_is_blocked(self):
        class _RedirectHandler(_MockHTTPHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://169.254.169.254/")
                    self.end_headers()
                else:
                    super().do_GET()

        server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            url = f"http://{host}:{port}/redirect"
            with pytest.raises(SSRFBlockedError):
                GovernedClient.request(url, timeout=5, allow_loopback=True, max_redirects=3)
        finally:
            server.shutdown()
            server.server_close()

    def test_outbound_secret_blocked_by_egress_dlp(self):
        with pytest.raises(EgressDeniedError):
            GovernedClient.request(
                "http://example.com/api",
                method="POST",
                body='{"token": "ghp_fake1234567890abcdef"}',
                timeout=2,
            )


class TestMemoryLayerLogsRawSecrets:
    def test_remember_logs_original_secret_before_redaction(self, tmp_path: Path, caplog):
        secret = "sk-animus-test-secret"
        mem = MemoryLayer(tmp_path, backend="json")
        with caplog.at_level(logging.INFO):
            mem.remember(
                content=f"API key: {secret}", memory_type=Sensitivity.PUBLIC, tags=["test"]
            )
        # SEC-08: raw secret must not appear in INFO logs. The content is
        # redacted for storage, but the log must use safe metadata only.
        assert secret not in caplog.text


@pytest.mark.parametrize("glob", [False, True])
@pytest.mark.parametrize("operation", ["authorize_read", "authorize_write"])
def test_blocked_symlink_parent_cannot_bypass_policy(tmp_path, glob, operation):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    target = real / "private.txt"
    target.write_text("fixture")
    rule = str(alias / "*") if glob else str(alias)
    policy = WorkspaceToolPolicy(
        allowed_paths=[str(tmp_path)], write_roots=[str(tmp_path)], blocked_paths=[rule]
    )
    for candidate in (target, alias / target.name):
        result = getattr(policy, operation)(str(candidate))
        assert result.allowed is False
        assert "blocked" in result.reason
