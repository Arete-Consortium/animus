"""
Animus Tool Framework

Provides tool definitions, registry, and built-in tools for agentic capabilities.
"""

import asyncio
import fnmatch
import glob as glob_module
import hashlib
import inspect
import json
import re
import shlex
import subprocess
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from animus.logging import get_logger
from animus.network.client import GovernedClient

logger = get_logger("tools")


# =============================================================================
# Tool policy layer
# =============================================================================


@dataclass(frozen=True)
class AuthorizationResult:
    """Structured result of a policy authorization check.

    ``reason`` must be present when ``allowed`` is False so callers and logs
    can explain why an action was denied without leaking sensitive data.
    """

    allowed: bool
    reason: str | None = None


class ToolPolicy(ABC):
    """Immutable, registry-owned security policy for executable tools.

    Every ``ToolRegistry`` instance must own a concrete policy. Missing or
    ``None`` policy defaults to ``DenyAllToolPolicy`` so the registry fails
    closed. Multiple registries in the same process can safely hold different
    policies because no mutable module-level state is consulted at runtime.
    """

    @abstractmethod
    def authorize_read(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        """Authorize reading from ``path``."""
        ...

    @abstractmethod
    def authorize_write(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        """Authorize writing to ``path``."""
        ...

    @abstractmethod
    def authorize_command(
        self, argv: list[str], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        """Authorize executing ``argv`` (already tokenized)."""
        ...

    @abstractmethod
    def authorize_network(
        self, request: dict[str, Any], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        """Authorize a network ``request`` dict (url, method, ...)."""
        ...


class DenyAllToolPolicy(ToolPolicy):
    """Default, fail-closed policy: every sensitive action is denied."""

    def authorize_read(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(
            allowed=False,
            reason="Access denied: no tool policy configured for this registry",
        )

    def authorize_write(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(
            allowed=False,
            reason="Write denied: no tool policy configured for this registry",
        )

    def authorize_command(
        self, argv: list[str], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(
            allowed=False,
            reason="Command execution denied: no tool policy configured for this registry",
        )

    def authorize_network(
        self, request: dict[str, Any], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(
            allowed=False,
            reason="Network access denied: no tool policy configured for this registry",
        )


class WorkspaceToolPolicy(ToolPolicy):
    """Workspace-scoped policy for filesystem, command, and network tools.

    Reads are restricted to ``allowed_paths`` minus ``blocked_paths``. Writes
    are further restricted to ``write_roots`` when configured. Commands are
    allowed only when ``command_enabled`` is True and pass the
    ``command_blocklist``/``command_allowlist`` checks. Destructive commands
    (rm, mv, cp, chmod, chown) with path arguments are sandboxed to
    ``write_roots``. Network requests are denied by default; callers must
    explicitly allow them with ``network_allowed=True``.
    """

    def __init__(
        self,
        *,
        allowed_paths: list[str] | None = None,
        blocked_paths: list[str] | None = None,
        write_roots: list[str] | None = None,
        command_enabled: bool = False,
        command_allowlist: list[str] | None = None,
        command_blocklist: list[str] | None = None,
        command_timeout_seconds: int = 30,
        network_allowed: bool = False,
    ) -> None:
        # Normalize paths immediately so the policy object is immutable after
        # construction. Paths with globs are preserved as-is for fnmatch.
        self.allowed_paths = allowed_paths or []
        self.blocked_paths = blocked_paths or []
        self.write_roots = write_roots or []
        self.command_enabled = command_enabled
        self.command_allowlist = command_allowlist or []
        self.command_blocklist = command_blocklist or []
        self.command_timeout_seconds = command_timeout_seconds
        self.network_allowed = network_allowed

    @classmethod
    def from_tools_security_config(cls, config) -> "WorkspaceToolPolicy":
        """Build a workspace policy from a ``ToolsSecurityConfig`` instance.

        This is a migration helper: legacy config dataclass attributes are
        translated into the immutable policy object without retaining any
        reference to mutable global state.
        """
        return cls(
            allowed_paths=list(config.allowed_paths),
            blocked_paths=list(config.blocked_paths),
            write_roots=list(config.write_roots),
            command_enabled=bool(config.command_enabled),
            command_blocklist=list(config.command_blocklist),
            command_timeout_seconds=int(config.command_timeout_seconds),
        )

    def _resolve(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    def _is_blocked(self, resolved: Path) -> str | None:
        for blocked in self.blocked_paths:
            try:
                # Match the same canonical path used for the requested file.
                # resolve() preserves wildcard components while resolving a
                # symlinked parent, e.g. /etc/* -> /private/etc/* on macOS.
                blocked_resolved = Path(blocked).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                return "Access denied: invalid blocked path rule"
            if "*" in blocked:
                if fnmatch.fnmatch(str(resolved), str(blocked_resolved)):
                    return f"Access denied: path matches blocked pattern '{blocked}'"
            elif resolved == blocked_resolved or blocked_resolved in resolved.parents:
                return "Access denied: path is blocked"
        return None

    def _in_allowed(self, resolved: Path) -> bool:
        for allowed in self.allowed_paths:
            allowed_resolved = Path(allowed).expanduser().resolve()
            if resolved == allowed_resolved or allowed_resolved in resolved.parents:
                return True
        return False

    def _in_write_roots(self, resolved: Path) -> bool:
        for root in self.write_roots:
            root_resolved = Path(root).expanduser().resolve()
            if resolved == root_resolved or root_resolved in resolved.parents:
                return True
        return False

    def authorize_read(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        try:
            resolved = self._resolve(path)
        except (OSError, ValueError):
            return AuthorizationResult(
                allowed=False, reason=f"Access denied: invalid path '{path}'"
            )

        blocked_reason = self._is_blocked(resolved)
        if blocked_reason:
            return AuthorizationResult(allowed=False, reason=blocked_reason)

        if not self._in_allowed(resolved):
            return AuthorizationResult(
                allowed=False, reason="Access denied: path not in allowed directories"
            )

        return AuthorizationResult(allowed=True)

    def authorize_write(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        read_result = self.authorize_read(path)
        if not read_result.allowed:
            return read_result

        if self.write_roots:
            try:
                resolved = self._resolve(path)
            except (OSError, ValueError):
                return AuthorizationResult(
                    allowed=False, reason=f"Write denied: invalid path '{path}'"
                )
            if not self._in_write_roots(resolved):
                return AuthorizationResult(
                    allowed=False,
                    reason=f"Write denied: path not in write_roots ({self.write_roots})",
                )

        return AuthorizationResult(allowed=True)

    def authorize_command(
        self, argv: list[str], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        if not self.command_enabled:
            return AuthorizationResult(allowed=False, reason="Command execution is disabled")

        if not argv:
            return AuthorizationResult(
                allowed=False, reason="Command execution denied: empty command"
            )

        command = " ".join(argv)
        normalized = re.sub(r"\s+", " ", command.strip())

        dangerous_patterns = [
            r"\$\(",
            r"`[^`]+`",
            r"\|\s*sh\b",
            r"\|\s*bash\b",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return AuthorizationResult(
                    allowed=False, reason="Command contains disallowed shell constructs"
                )

        for pattern in self.command_blocklist:
            if re.search(pattern, normalized, re.IGNORECASE):
                return AuthorizationResult(
                    allowed=False, reason="Command blocked by security policy"
                )

        if self.command_allowlist:
            allowed = False
            for pattern in self.command_allowlist:
                if re.search(pattern, normalized, re.IGNORECASE):
                    allowed = True
                    break
            if not allowed:
                return AuthorizationResult(allowed=False, reason="Command not in allowlist")

        if self.write_roots:
            destructive_cmds = ("rm", "mv", "cp", "chmod", "chown")
            parts = normalized.split()
            if parts and parts[0] in destructive_cmds:
                for arg in parts[1:]:
                    if arg.startswith("-"):
                        continue
                    try:
                        arg_path = Path(arg).expanduser().resolve()
                    except (OSError, ValueError):
                        return AuthorizationResult(
                            allowed=False, reason=f"Command targets invalid path: {arg}"
                        )
                    if not self._in_write_roots(arg_path):
                        return AuthorizationResult(
                            allowed=False,
                            reason=f"Command targets path outside sandbox: {arg}",
                        )

        return AuthorizationResult(allowed=True)

    def authorize_network(
        self, request: dict[str, Any], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        if not self.network_allowed:
            return AuthorizationResult(
                allowed=False,
                reason="Network access denied by workspace policy",
            )
        return AuthorizationResult(allowed=True)


class ExplicitUnrestrictedDevelopmentPolicy(ToolPolicy):
    """Opt-in, alarmingly named policy that allows all tool actions.

    This policy exists only for explicit local development scenarios where the
    operator deliberately chooses to bypass all execution-plane restrictions.
    It must be constructed explicitly; it is never the default.
    """

    def __init__(self) -> None:
        logger.warning(
            "ExplicitUnrestrictedDevelopmentPolicy is active: all tool security checks are disabled"
        )

    def authorize_read(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(allowed=True)

    def authorize_write(
        self, path: str, context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(allowed=True)

    def authorize_command(
        self, argv: list[str], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(allowed=True)

    def authorize_network(
        self, request: dict[str, Any], context: dict[str, Any] | None = None
    ) -> AuthorizationResult:
        return AuthorizationResult(allowed=True)


# =============================================================================
# Approval layer
# =============================================================================


@dataclass(frozen=True)
class ApprovalDecision:
    """Immutable record of a human/operator approval decision for a tool call.

    The decision binds a specific tool name and a stable hash of the logical
    parameters.  Sensitive parameter values are never stored verbatim; only
    the opaque ``params_hash`` is retained so approvals cannot be replayed with
    different inputs.
    """

    request_id: str
    tool_name: str
    params_hash: str
    requesting_actor: str
    scope: str
    expiry: datetime
    decision: Literal["allow", "deny"]
    approver: str
    reason: str

    def is_expired(self, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        return now > self.expiry


class ApprovalStore(ABC):
    """Persistent or in-memory backing store for approval decisions.

    Implementations must be able to create, lookup, and expire approvals.
    Verification logic (allow vs. deny, expiry, tool/parameter match) lives on
    the store so it can be reused by custom backends.
    """

    @abstractmethod
    def request_approval(
        self,
        tool_name: str,
        params_hash: str,
        requesting_actor: str,
        scope: str,
        expiry: datetime,
        decision: Literal["allow", "deny"],
        approver: str,
        reason: str,
    ) -> ApprovalDecision:
        """Record a new approval decision and return it."""
        ...

    @abstractmethod
    def lookup(self, request_id: str) -> ApprovalDecision | None:
        """Fetch an approval decision by id."""
        ...

    @abstractmethod
    def verify(
        self,
        decision: ApprovalDecision,
        tool_name: str,
        params_hash: str,
    ) -> tuple[bool, str]:
        """Return (is_valid, reason) for using ``decision`` to run ``tool_name``
        with ``params_hash``.
        """
        ...

    @abstractmethod
    def expire_approvals(self, now: datetime | None = None) -> int:
        """Remove expired approvals.  Returns the number deleted."""
        ...


class InMemoryApprovalStore(ApprovalStore):
    """Default, process-local approval store."""

    def __init__(self) -> None:
        self._approvals: dict[str, ApprovalDecision] = {}

    def request_approval(
        self,
        tool_name: str,
        params_hash: str,
        requesting_actor: str,
        scope: str,
        expiry: datetime,
        decision: Literal["allow", "deny"],
        approver: str,
        reason: str,
    ) -> ApprovalDecision:
        request_id = str(uuid.uuid4())
        decision_obj = ApprovalDecision(
            request_id=request_id,
            tool_name=tool_name,
            params_hash=params_hash,
            requesting_actor=requesting_actor,
            scope=scope,
            expiry=expiry,
            decision=decision,
            approver=approver,
            reason=reason,
        )
        self._approvals[request_id] = decision_obj
        return decision_obj

    def lookup(self, request_id: str) -> ApprovalDecision | None:
        return self._approvals.get(request_id)

    def verify(
        self,
        decision: ApprovalDecision,
        tool_name: str,
        params_hash: str,
    ) -> tuple[bool, str]:
        if decision.decision != "allow":
            return False, "Approval decision is deny"
        if decision.is_expired():
            return False, "Approval expired"
        if decision.tool_name != tool_name:
            return False, "Approval tool mismatch"
        if decision.params_hash != params_hash:
            return False, "Approval parameter mismatch"
        return True, ""

    def expire_approvals(self, now: datetime | None = None) -> int:
        if now is None:
            now = datetime.now(timezone.utc)
        expired_ids = [
            request_id
            for request_id, decision in self._approvals.items()
            if decision.is_expired(now)
        ]
        for request_id in expired_ids:
            del self._approvals[request_id]
        return len(expired_ids)


class ApprovalGate(ABC):
    """External authority that grants or denies approval for dangerous tools.

    An approval gate is the bridge between the execution plane and a human
    operator, ticketing system, or policy service.  The execution plane creates
    a pending approval request, then awaits the gate's decision.  The gate is
    responsible for producing an ``ApprovalDecision`` whose ``params_hash``
    matches the logical parameters of the requested call.
    """

    @abstractmethod
    async def request_decision(
        self,
        approval_store: ApprovalStore,
        tool_name: str,
        params: dict,
        params_hash: str,
        request_id: str,
    ) -> ApprovalDecision:
        """Return an ``ApprovalDecision`` from an external authority.

        Implementations may block until a human/operator decision is available.
        The returned decision must be an ``allow`` decision that matches
        ``tool_name`` and ``params_hash``.

        Args:
            approval_store: Store backing the registry that created the pending
                request.  The gate may record the final decision here.
            tool_name: Name of the tool awaiting approval.
            params: Logical parameters of the requested call (internal execution
                keys already stripped).
            params_hash: Canonical hash of ``params``.
            request_id: Identifier of the pending request created by the caller;
                useful for correlation with an external system.
        """
        ...


# Internal execution-control parameters that must not reach the tool handler or
# be included in the canonical parameter hash.
_INTERNAL_PARAM_KEYS = {"_approval_id", "approval_id"}

# Keys whose values are considered sensitive.  Their canonical representation is
# replaced by a short one-way hash so the approval hash binds to the exact
# secret without leaking it in logs or the approval store.
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[^a-z0-9])(password|secret|token|credential|private|api[_-]?key|auth[_-]?value|bearer|apikey)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


def _canonical_params_hash(params: Any) -> str:
    """Return a stable SHA-256 hash of the logical tool parameters.

    * Dict keys are sorted recursively for deterministic serialization.
    * Internal control keys (e.g. ``_approval_id``) are stripped.
    * Values for sensitive-looking keys are replaced by a one-way hash so the
      canonical hash binds to the secret without exposing it.
    """

    def _mask_sensitive(key: str, value: Any) -> Any:
        if _SENSITIVE_KEY_RE.search(key):
            # Use a stable keyed-like representation: hash the canonical form
            # of the value so different secrets produce different parameter
            # hashes, but the secret itself is not stored or logged.
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
            return f"__redacted_{digest}"
        return value

    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: _normalize(_mask_sensitive(k, v))
                for k, v in sorted(value.items())
                if k not in _INTERNAL_PARAM_KEYS
            }
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    normalized = _normalize(params)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Legacy helpers used by direct callers and tests. When no policy is provided,
# the registry default (DenyAllToolPolicy) is used, which makes missing policy
# fail closed.


def _policy_or_deny(policy: ToolPolicy | None) -> ToolPolicy:
    return policy if policy is not None else DenyAllToolPolicy()


def _validate_path(path: str, policy: ToolPolicy | None = None) -> tuple[bool, str | None]:
    """
    Validate a file path against the supplied policy.

    Returns:
        (is_valid, error_message)
    """
    result = _policy_or_deny(policy).authorize_read(path)
    return result.allowed, result.reason


def _validate_write_path(path: str, policy: ToolPolicy | None = None) -> tuple[bool, str | None]:
    """Validate a path for write operations (write_file, edit_file)."""
    result = _policy_or_deny(policy).authorize_write(path)
    return result.allowed, result.reason


def _validate_command(command: str, policy: ToolPolicy | None = None) -> tuple[bool, str | None]:
    """
    Validate a shell command against the supplied policy.

    Returns:
        (is_valid, error_message)
    """
    argv = shlex.split(command)
    result = _policy_or_deny(policy).authorize_command(argv)
    return result.allowed, result.reason


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_name: str
    success: bool
    output: Any
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }

    def to_context(self) -> str:
        """Format for injection into model context."""
        if self.success:
            return f"[Tool: {self.tool_name}]\n{self.output}"
        else:
            return f"[Tool: {self.tool_name} - ERROR]\n{self.error}"


@dataclass
class Tool:
    """Definition of an executable tool."""

    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    handler: Callable[[dict], ToolResult]
    requires_approval: bool = False
    category: str = "general"

    def get_schema(self) -> dict:
        """Get JSON Schema representation for model context."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "requires_approval": self.requires_approval,
        }

    def get_compact_schema(self) -> dict:
        """Get compact schema: name, description, param names only.

        Used by lazy schema loading to keep token costs low while still
        making the model aware of all available tools. Full schemas are
        loaded on-demand for top-ranked tools.
        """
        param_names = []
        if self.parameters and isinstance(self.parameters, dict):
            props = self.parameters.get("properties", {})
            param_names = list(props.keys())
        return {
            "name": self.name,
            "description": self.description,
            "params": param_names,
        }


class ToolRegistry:
    """
    Registry for managing and executing tools.

    Provides tool registration, lookup, and execution with error handling.
    Each registry owns an immutable ``ToolPolicy``; no module-level mutable
    state is consulted during execution.
    """

    _MAX_INTENT_CACHE = 50  # Prevent unbounded growth

    def __init__(
        self,
        policy: ToolPolicy | None = None,
        approval_store: ApprovalStore | None = None,
    ):
        self._tools: dict[str, Tool] = {}
        self._tool_history: dict[str, list[dict]] = {}
        # Session-scoped intent cache: intent string -> sorted list of (score, tool_name)
        self._intent_cache: dict[str, list[tuple[float, str]]] = {}
        self.policy = policy if policy is not None else DenyAllToolPolicy()
        self.approval_store = (
            approval_store if approval_store is not None else InMemoryApprovalStore()
        )
        logger.debug("ToolRegistry initialized")

    def request_approval(
        self,
        tool_name: str,
        params: dict,
        *,
        requesting_actor: str = "system",
        scope: str = "execution",
        expiry_seconds: int = 300,
        decision: Literal["allow", "deny"] = "allow",
        approver: str = "human",
        reason: str = "Interactive approval",
    ) -> str:
        """Create an approval decision for ``tool_name`` with ``params``.

        Returns the ``request_id`` that must be supplied to ``execute()`` via
        the ``_approval_id`` execution parameter or the ``context`` dict.
        """
        params_hash = _canonical_params_hash(params)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
        decision_obj = self.approval_store.request_approval(
            tool_name=tool_name,
            params_hash=params_hash,
            requesting_actor=requesting_actor,
            scope=scope,
            expiry=expiry,
            decision=decision,
            approver=approver,
            reason=reason,
        )
        return decision_obj.request_id

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a tool. Returns True if removed."""
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def record_tool_use(self, name: str, success: bool) -> None:
        """Record a tool execution outcome for history-aware routing."""
        if name not in self._tool_history:
            self._tool_history[name] = []
        self._tool_history[name].append(
            {"success": success, "timestamp": datetime.now().isoformat()}
        )
        # Keep last 20 entries to prevent unbounded growth
        self._tool_history[name] = self._tool_history[name][-20:]

    def get_schema(
        self,
        intent: str | None = None,
        lazy: bool = True,
        max_full_schemas: int = 5,
    ) -> list[dict]:
        """Get JSON Schema for tools with optional lazy loading.

        When lazy=True, returns compact schemas for all tools and
        full schemas only for the top-N tools ranked by ISO score.

        Session-scoped intent cache: repeated calls with the same intent
        reuse ISO scores without recomputation.

        Args:
            intent: User prompt or task description for ISO scoring.
            lazy: If True, use two-phase lazy schema loading.
            max_full_schemas: Max number of tools to return full schemas for.

        Returns:
            List of tool schemas (compact or full depending on ranking).
        """
        if not lazy or not intent:
            # Fallback: return full schemas for all tools
            return [tool.get_schema() for tool in self._tools.values()]

        cache_key = intent.strip().lower()
        cached = self._intent_cache.get(cache_key)

        if cached is not None:
            # Reuse cached scores; still need to look up Tool objects
            scored: list[tuple[float, Tool]] = []
            for score, name in cached:
                tool = self._tools.get(name)
                if tool:
                    scored.append((score, tool))
        else:
            # Score all tools by ISO + history boost
            scored = []
            for tool in self._tools.values():
                score = self._iso_score(intent, tool)
                score = self._apply_history_boost(score, tool.name)
                scored.append((score, tool))
            # Sort descending by score
            scored.sort(key=lambda x: x[0], reverse=True)
            # Store in cache with size limit
            if len(self._intent_cache) >= self._MAX_INTENT_CACHE:
                # Evict oldest entry (simple FIFO)
                oldest = next(iter(self._intent_cache))
                del self._intent_cache[oldest]
            self._intent_cache[cache_key] = [(round(score, 4), tool.name) for score, tool in scored]

        # Build result: compact for all, full for top-N
        results: list[dict] = []
        for i, (score, tool) in enumerate(scored):
            if i < max_full_schemas:
                # Full schema for top-ranked tools
                full = tool.get_schema()
                full["_iso_score"] = round(score, 3)
                results.append(full)
            else:
                # Compact schema for remaining tools
                compact = tool.get_compact_schema()
                compact["_iso_score"] = round(score, 3)
                results.append(compact)

        logger.debug(
            f"Lazy schema load: {len(results)} tools, "
            f"{min(max_full_schemas, len(scored))} full, "
            f"{max(0, len(scored) - max_full_schemas)} compact"
        )
        return results

    def get_schema_text(
        self,
        intent: str | None = None,
        lazy: bool = True,
        max_full_schemas: int = 5,
    ) -> str:
        """Get formatted text description with optional lazy loading.

        Args:
            intent: User prompt or task description for ISO scoring.
            lazy: If True, use two-phase lazy schema loading.
            max_full_schemas: Max number of tools to return full schemas for.

        Returns:
            Formatted text describing available tools.
        """
        if not lazy or not intent:
            lines = ["Available tools:"]
            for tool in self._tools.values():
                lines.append(f"\n- {tool.name}: {tool.description}")
                if tool.parameters.get("properties"):
                    lines.append("  Parameters:")
                    for param, spec in tool.parameters["properties"].items():
                        required = param in tool.parameters.get("required", [])
                        req_marker = " (required)" if required else ""
                        lines.append(
                            f"    - {param}: {spec.get('description', spec.get('type', 'any'))}{req_marker}"
                        )
            return "\n".join(lines)

        # Score all tools
        scored: list[tuple[float, Tool]] = []
        for tool in self._tools.values():
            score = self._iso_score(intent, tool)
            score = self._apply_history_boost(score, tool.name)
            scored.append((score, tool))
        scored.sort(key=lambda x: x[0], reverse=True)

        lines = ["Available tools:"]
        for i, (score, tool) in enumerate(scored):
            if i < max_full_schemas:
                lines.append(f"\n- {tool.name} [relevance: {score:.2f}]: {tool.description}")
                if tool.parameters.get("properties"):
                    lines.append("  Parameters:")
                    for param, spec in tool.parameters["properties"].items():
                        required = param in tool.parameters.get("required", [])
                        req_marker = " (required)" if required else ""
                        lines.append(
                            f"    - {param}: {spec.get('description', spec.get('type', 'any'))}{req_marker}"
                        )
            else:
                # Compact entry
                param_hint = ""
                props = tool.parameters.get("properties", {}) if tool.parameters else {}
                if props:
                    param_hint = f" (params: {', '.join(props.keys())})"
                lines.append(
                    f"\n- {tool.name} [relevance: {score:.2f}]: {tool.description}{param_hint}"
                )
        return "\n".join(lines)

    def _iso_score(self, intent: str, tool: Tool) -> float:
        """Score tool relevance to user intent using keyword overlap.

        Lightweight Intent-Schema Overlap (ISO) scoring. Tokenizes the
        intent and tool metadata (name, description, param names) into
        normalized keyword sets, then computes Jaccard similarity.

        Args:
            intent: User prompt or current task description.
            tool: Tool to score.

        Returns:
            Relevance score between 0.0 and 1.0.
        """
        if not intent:
            return 0.5  # Neutral when no intent provided

        def _tokenize(text: str) -> set[str]:
            return set(re.sub(r"[^a-z0-9]", "", w.lower()) for w in text.split() if len(w) > 2)

        intent_tokens = _tokenize(intent)
        tool_text = f"{tool.name} {tool.description}"
        if tool.parameters and isinstance(tool.parameters, dict):
            props = tool.parameters.get("properties", {})
            for param_name in props.keys():
                tool_text += f" {param_name}"
            for spec in props.values():
                if isinstance(spec, dict):
                    tool_text += f" {spec.get('description', '')}"
        tool_tokens = _tokenize(tool_text)

        if not intent_tokens or not tool_tokens:
            return 0.0

        overlap = len(intent_tokens & tool_tokens)
        union = len(intent_tokens | tool_tokens)
        return overlap / union if union > 0 else 0.0

    def _apply_history_boost(self, score: float, tool_name: str) -> float:
        """Boost score based on recent tool usage history.

        Successful recent uses get a small boost; recent failures get
        a penalty. This enables history-aware routing without requiring
        a separate routing graph (see ACE-Router for future enhancement).

        Args:
            score: Base ISO score.
            tool_name: Name of the tool.

        Returns:
            Adjusted score.
        """
        history = self._tool_history.get(tool_name, [])
        if not history:
            return score

        # Weight recent history more heavily
        boost = 0.0
        total_weight = 0.0
        for i, entry in enumerate(history[-5:]):
            weight = (i + 1) / 5.0  # More recent = higher weight
            total_weight += weight
            if entry.get("success"):
                boost += weight * 0.15
            else:
                boost -= weight * 0.10

        if total_weight > 0:
            score += boost / total_weight
        return max(0.0, min(1.0, score))

    def get_numbered_menu(self) -> tuple[str, dict[int, str]]:
        """Get a numbered tool menu for constrained selection.

        Returns:
            (menu_text, number_to_name_map) where menu_text is a formatted
            string and number_to_name_map maps 1-based indices to tool names.
        """
        tools = list(self._tools.values())
        number_map: dict[int, str] = {}
        lines = ["Pick a tool by number (or 0 for no tool):"]
        lines.append("  0: No tool needed — answer directly")
        for i, tool in enumerate(tools, 1):
            number_map[i] = tool.name
            params_hint = ""
            required = tool.parameters.get("required", [])
            if required:
                params_hint = f" ({', '.join(required)})"
            lines.append(f"  {i}: {tool.name}{params_hint} — {tool.description[:80]}")
        return "\n".join(lines), number_map

    def execute(
        self,
        name: str,
        params: dict,
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """
        Execute a tool by name with given parameters.

        If the tool has ``requires_approval=True``, the caller must supply a
        valid ``_approval_id`` either in the ``context`` dict or in ``params``.
        The approval decision is verified against the canonical hash of the
        logical parameters.  Approval failures produce a structured denial
        without invoking the tool handler.

        Args:
            name: Tool name
            params: Parameters to pass to the tool
            context: Optional execution context (may contain ``_approval_id``)

        Returns:
            ToolResult with success/failure and output
        """
        tool = self.get(name)
        if not tool:
            logger.warning(f"Tool not found: {name}")
            return ToolResult(
                tool_name=name,
                success=False,
                output=None,
                error=f"Tool '{name}' not found",
            )

        # Strip internal execution-control keys before hashing or passing to the
        # tool handler so they cannot leak into tool logic or the audit log.
        handler_params: Any
        if isinstance(params, dict):
            handler_params = {k: v for k, v in params.items() if k not in _INTERNAL_PARAM_KEYS}
        else:
            handler_params = params

        if tool.requires_approval:
            approval_id: str | None = None
            if context is not None:
                approval_id = context.get("_approval_id") or context.get("approval_id")
            if not approval_id and isinstance(params, dict):
                approval_id = params.get("_approval_id") or params.get("approval_id")

            if not approval_id:
                logger.warning(f"Approval required but no approval_id provided for tool '{name}'")
                return ToolResult(
                    tool_name=name,
                    success=False,
                    output=None,
                    error="Approval required but no approval_id provided",
                )

            decision = self.approval_store.lookup(approval_id)
            if decision is None:
                logger.warning(f"Approval '{approval_id}' not found for tool '{name}'")
                return ToolResult(
                    tool_name=name,
                    success=False,
                    output=None,
                    error=f"Approval '{approval_id}' not found",
                )

            params_hash = _canonical_params_hash(handler_params)
            allowed, reason = self.approval_store.verify(decision, tool.name, params_hash)
            if not allowed:
                logger.warning(f"Approval verification failed for tool '{name}': {reason}")
                return ToolResult(
                    tool_name=name,
                    success=False,
                    output=None,
                    error=f"Approval verification failed: {reason}",
                )

            logger.info(
                f"Approval allowed: tool={name} request_id={approval_id} "
                f"actor={decision.requesting_actor} approver={decision.approver} "
                f"reason={decision.reason}"
            )

        try:
            logger.debug(f"Executing tool: {name} with param keys: {list(handler_params.keys())}")
            result = tool.handler(handler_params)
            logger.debug(f"Tool {name} completed: success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed with exception: {e}")
            return ToolResult(
                tool_name=name,
                success=False,
                output=None,
                error=str(e),
            )

    async def execute_async(
        self,
        name: str,
        params: dict,
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Async wrapper for tool execution."""
        return await asyncio.to_thread(self.execute, name, params, context)


# =============================================================================
# Built-in Tools
# =============================================================================


def _tool_get_datetime(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Get current date and time."""
    format_str = params.get("format", "%Y-%m-%d %H:%M:%S")
    try:
        now = datetime.now()
        formatted = now.strftime(format_str)
        return ToolResult(
            tool_name="get_datetime",
            success=True,
            output=formatted,
        )
    except Exception as e:
        return ToolResult(
            tool_name="get_datetime",
            success=False,
            output=None,
            error=str(e),
        )


def _tool_read_file(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Read contents of a local file."""
    path = params.get("path")
    if not path:
        return ToolResult(
            tool_name="read_file",
            success=False,
            output=None,
            error="Missing required parameter: path",
        )

    # Security validation
    is_valid, error = _validate_path(path, policy)
    if not is_valid:
        logger.warning(f"Path validation failed for '{path}': {error}")
        return ToolResult(
            tool_name="read_file",
            success=False,
            output=None,
            error=error,
        )

    try:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return ToolResult(
                tool_name="read_file",
                success=False,
                output=None,
                error=f"File not found: {path}",
            )

        if not file_path.is_file():
            return ToolResult(
                tool_name="read_file",
                success=False,
                output=None,
                error=f"Not a file: {path}",
            )

        # Limit file size to prevent memory issues
        max_size = params.get("max_size", 100_000)  # 100KB default
        if file_path.stat().st_size > max_size:
            return ToolResult(
                tool_name="read_file",
                success=False,
                output=None,
                error=f"File too large (>{max_size} bytes)",
            )

        content = file_path.read_text()
        return ToolResult(
            tool_name="read_file",
            success=True,
            output=content,
        )
    except Exception as e:
        return ToolResult(
            tool_name="read_file",
            success=False,
            output=None,
            error=str(e),
        )


def _tool_list_files(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """List files matching a pattern."""
    pattern = params.get("pattern", "*")
    directory = params.get("directory", ".")

    # Security validation
    is_valid, error = _validate_path(directory, policy)
    if not is_valid:
        logger.warning(f"Path validation failed for '{directory}': {error}")
        return ToolResult(
            tool_name="list_files",
            success=False,
            output=None,
            error=error,
        )

    try:
        base_path = Path(directory).expanduser().resolve()
        if not base_path.exists():
            return ToolResult(
                tool_name="list_files",
                success=False,
                output=None,
                error=f"Directory not found: {directory}",
            )

        full_pattern = str(base_path / pattern)
        matches = glob_module.glob(full_pattern, recursive=True)

        # Limit results
        max_results = params.get("max_results", 100)
        matches = matches[:max_results]

        # Format output
        result_list = []
        for match in sorted(matches):
            p = Path(match)
            prefix = "d" if p.is_dir() else "f"
            result_list.append(f"[{prefix}] {match}")

        return ToolResult(
            tool_name="list_files",
            success=True,
            output="\n".join(result_list) if result_list else "No matches found",
        )
    except Exception as e:
        return ToolResult(
            tool_name="list_files",
            success=False,
            output=None,
            error=str(e),
        )


def _tool_run_command(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Execute a shell command (requires approval)."""
    command = params.get("command")
    if not command:
        return ToolResult(
            tool_name="run_command",
            success=False,
            output=None,
            error="Missing required parameter: command",
        )

    # Security validation
    is_valid, error = _validate_command(command, policy)
    if not is_valid:
        logger.warning(f"Command validation failed for '{command}': {error}")
        return ToolResult(
            tool_name="run_command",
            success=False,
            output=None,
            error=error,
        )

    try:
        timeout = params.get("timeout", 30)
        cwd = None
        active_policy = _policy_or_deny(policy)
        if isinstance(active_policy, WorkspaceToolPolicy):
            timeout = min(timeout, active_policy.command_timeout_seconds)
            if active_policy.write_roots:
                cwd = active_policy.write_roots[0]

        result = subprocess.run(
            shlex.split(command),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"

        return ToolResult(
            tool_name="run_command",
            success=result.returncode == 0,
            output=output,
            error=f"Exit code: {result.returncode}" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="run_command",
            success=False,
            output=None,
            error=f"Command timed out after {timeout} seconds",
        )
    except Exception as e:
        return ToolResult(
            tool_name="run_command",
            success=False,
            output=None,
            error=str(e),
        )


def _tool_write_file(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Write content to a file (creates or overwrites). Requires approval."""
    path = params.get("path")
    content = params.get("content")
    if not path:
        return ToolResult(
            tool_name="write_file",
            success=False,
            output=None,
            error="Missing required parameter: path",
        )
    if content is None:
        return ToolResult(
            tool_name="write_file",
            success=False,
            output=None,
            error="Missing required parameter: content",
        )

    is_valid, error = _validate_write_path(path, policy)
    if not is_valid:
        return ToolResult(tool_name="write_file", success=False, output=None, error=error)

    try:
        file_path = Path(path).expanduser().resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        lines = len(content.splitlines())
        return ToolResult(
            tool_name="write_file",
            success=True,
            output=f"Wrote {lines} lines to {path}",
        )
    except PermissionError:
        return ToolResult(
            tool_name="write_file",
            success=False,
            output=None,
            error=f"Permission denied: {path}",
        )
    except OSError as e:
        return ToolResult(tool_name="write_file", success=False, output=None, error=str(e))


def _tool_edit_file(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Replace specific text in a file (find and replace). Requires approval."""
    path = params.get("path")
    old_text = params.get("old_text")
    new_text = params.get("new_text")
    if not path:
        return ToolResult(
            tool_name="edit_file",
            success=False,
            output=None,
            error="Missing required parameter: path",
        )
    if old_text is None or new_text is None:
        return ToolResult(
            tool_name="edit_file",
            success=False,
            output=None,
            error="Missing required parameters: old_text and new_text",
        )

    is_valid, error = _validate_write_path(path, policy)
    if not is_valid:
        return ToolResult(tool_name="edit_file", success=False, output=None, error=error)

    try:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return ToolResult(
                tool_name="edit_file",
                success=False,
                output=None,
                error=f"File not found: {path}",
            )
        content = file_path.read_text()
        if old_text not in content:
            return ToolResult(
                tool_name="edit_file",
                success=False,
                output=None,
                error=f"Could not find the specified text in {path}",
            )
        count = content.count(old_text)
        if count > 1:
            return ToolResult(
                tool_name="edit_file",
                success=False,
                output=None,
                error=f"Text matches {count} locations in {path}. Provide more context to make it unique.",
            )
        content = content.replace(old_text, new_text, 1)
        file_path.write_text(content)
        return ToolResult(tool_name="edit_file", success=True, output=f"Edited {path}")
    except PermissionError:
        return ToolResult(
            tool_name="edit_file",
            success=False,
            output=None,
            error=f"Permission denied: {path}",
        )
    except OSError as e:
        return ToolResult(tool_name="edit_file", success=False, output=None, error=str(e))


def _tool_http_request(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Make an HTTP request to a REST API endpoint."""
    url = params.get("url")
    if not url:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output=None,
            error="Missing required parameter: url",
        )

    method = params.get("method", "GET").upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return ToolResult(
            tool_name="http_request",
            success=False,
            output=None,
            error=f"Unsupported HTTP method: {method}",
        )

    timeout = min(params.get("timeout", 30), 60)

    # Network authorization enforced by the registry-owned policy.
    if policy is not None:
        authz = policy.authorize_network({"url": url, "method": method})
        if not authz.allowed:
            return ToolResult(
                tool_name="http_request",
                success=False,
                output=None,
                error=authz.reason,
            )

    # Build headers
    headers = params.get("headers", {}) or {}

    # Apply auth
    auth_type = params.get("auth_type", "none").lower()
    auth_value = params.get("auth_value", "")
    if auth_type == "bearer" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_type == "basic" and auth_value:
        import base64

        encoded = base64.b64encode(auth_value.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif auth_type == "api_key" and auth_value:
        headers["X-API-Key"] = auth_value

    # Build request body
    body_str = params.get("body")
    if body_str and method in ("POST", "PUT", "PATCH"):
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

    # The generic HTTP tool defaults to PUBLIC data.  Callers may override via
    # the ``sensitivity`` parameter; the governed client rejects CONFIDENTIAL
    # and SECRET destinations regardless.
    sensitivity = params.get("sensitivity")

    try:
        response = GovernedClient.request(
            url,
            method=method,
            headers=headers,
            body=body_str,
            timeout=timeout,
            sensitivity=sensitivity,
            content=body_str,
        )
    except Exception as e:
        logger.debug("http_request failed: %s", e)
        return ToolResult(
            tool_name="http_request",
            success=False,
            output=None,
            error=str(e),
        )

    output = f"HTTP {response.status}\n"
    for hdr_key, hdr_val in response.headers.items():
        output += f"{hdr_key}: {hdr_val}\n"
    output += f"\n{response.body}"

    return ToolResult(
        tool_name="http_request",
        success=200 <= response.status < 400,
        output=output,
        error=None if 200 <= response.status < 400 else f"HTTP {response.status}",
    )


def _tool_web_search(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
    """Search the web using DuckDuckGo Instant Answer API."""
    query = params.get("query")
    if not query:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output=None,
            error="Missing required parameter: query",
        )

    # Sanitize query: strip control characters
    query = re.sub(r"[\x00-\x1f\x7f]", "", query)
    if len(query) > 500:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output=None,
            error="Query too long (max 500 characters)",
        )

    try:
        import urllib.parse

        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1"

        response = GovernedClient.request(
            url,
            method="GET",
            timeout=10,
            sensitivity="PUBLIC",
            content=query,
        )
        data = json.loads(response.body)

        # Extract relevant information
        results = []

        # Abstract (main answer)
        if data.get("Abstract"):
            results.append(f"**Summary**: {data['Abstract']}")
            if data.get("AbstractSource"):
                results.append(f"Source: {data['AbstractSource']}")

        # Related topics
        if data.get("RelatedTopics"):
            results.append("\n**Related:**")
            for topic in data["RelatedTopics"][:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"- {topic['Text'][:200]}")

        if not results:
            return ToolResult(
                tool_name="web_search",
                success=True,
                output=f"No instant answer found for '{query}'. Try a more specific query.",
            )

        return ToolResult(
            tool_name="web_search",
            success=True,
            output="\n".join(results),
        )
    except Exception as e:
        logger.debug("web_search failed: %s", e)
        return ToolResult(
            tool_name="web_search",
            success=False,
            output=None,
            error=str(e),
        )


# Tool definitions
BUILTIN_TOOLS = [
    Tool(
        name="get_datetime",
        description="Get the current date and time",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "strftime format string (default: %Y-%m-%d %H:%M:%S)",
                }
            },
            "required": [],
        },
        handler=_tool_get_datetime,
        category="utility",
    ),
    Tool(
        name="read_file",
        description="Read the contents of a local file",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "max_size": {
                    "type": "integer",
                    "description": "Maximum file size in bytes (default: 100000)",
                },
            },
            "required": ["path"],
        },
        handler=_tool_read_file,
        category="filesystem",
    ),
    Tool(
        name="list_files",
        description="List files in a directory matching a glob pattern",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Base directory (default: current directory)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (default: *). Use ** for recursive.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 100)",
                },
            },
            "required": [],
        },
        handler=_tool_list_files,
        category="filesystem",
    ),
    Tool(
        name="run_command",
        description="Execute a shell command. Use with caution.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        },
        handler=_tool_run_command,
        requires_approval=True,
        category="system",
    ),
    Tool(
        name="write_file",
        description="Write content to a file (creates or overwrites)",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write",
                },
            },
            "required": ["path", "content"],
        },
        handler=_tool_write_file,
        requires_approval=True,
        category="filesystem",
    ),
    Tool(
        name="edit_file",
        description="Replace specific text in a file (find and replace)",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find (must be unique in the file)",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
        handler=_tool_edit_file,
        requires_approval=True,
        category="filesystem",
    ),
    Tool(
        name="web_search",
        description="Search the web for information using DuckDuckGo",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
            },
            "required": ["query"],
        },
        handler=_tool_web_search,
        category="web",
    ),
    Tool(
        name="http_request",
        description="Make an HTTP request to a REST API endpoint",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to request",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method: GET, POST, PUT, PATCH, DELETE (default: GET)",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs",
                },
                "body": {
                    "type": "string",
                    "description": "Request body (JSON string for POST/PUT/PATCH)",
                },
                "auth_type": {
                    "type": "string",
                    "description": "Auth type: none, bearer, basic, api_key (default: none)",
                },
                "auth_value": {
                    "type": "string",
                    "description": "Auth token/key value",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30, max: 60)",
                },
            },
            "required": ["url"],
        },
        handler=_tool_http_request,
        requires_approval=True,
        category="web",
    ),
]


def _handler_accepts_policy(handler: Callable) -> bool:
    """Return True if the callable has a ``policy`` keyword parameter."""
    try:
        sig = inspect.signature(handler)
    except (ValueError, TypeError):
        return False
    return "policy" in sig.parameters


def _bind_tool(registry: ToolRegistry, tool: Tool) -> Tool:
    """Return a copy of ``tool`` whose handler receives the registry's policy.

    Handlers that do not accept a ``policy`` keyword are left untouched so
    external integrations and dynamically registered tools keep working.
    """
    if not _handler_accepts_policy(tool.handler):
        return tool

    def bound_handler(params: dict) -> ToolResult:
        return tool.handler(params, policy=registry.policy)

    return Tool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        handler=bound_handler,
        requires_approval=tool.requires_approval,
        category=tool.category,
    )


def tools_to_anthropic_format(
    registry: ToolRegistry,
    intent: str | None = None,
    lazy: bool = True,
    max_full_schemas: int = 5,
) -> list[dict]:
    """Convert ToolRegistry to Anthropic tool_use format with lazy loading.

    Anthropic expects ``input_schema`` instead of ``parameters``.
    Tool.parameters is already JSON Schema, so this is a key rename.

    When lazy=True, returns compact schemas for low-relevance tools
    to reduce per-turn token overhead (per Tool Attention paper).

    Args:
        registry: ToolRegistry to convert.
        intent: User prompt for ISO scoring.
        lazy: Enable two-phase lazy schema loading.
        max_full_schemas: Max tools with full input_schema.

    Returns:
        List of Anthropic-format tool definitions.
    """
    result = []

    # Get ranked schemas from registry
    schemas = registry.get_schema(intent=intent, lazy=lazy, max_full_schemas=max_full_schemas)

    for schema in schemas:
        name = schema["name"]
        description = schema["description"]
        # Compact schemas use "params" key; full schemas use "parameters"
        params = schema.get("parameters") or schema.get("params", {})
        result.append(
            {
                "name": name,
                "description": description,
                "input_schema": params,
            }
        )
    return result


def create_default_registry(
    policy: ToolPolicy | None = None,
    security_config: Any = None,
) -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered.

    Args:
        policy: Explicit ``ToolPolicy`` for the registry. Defaults to
            ``DenyAllToolPolicy`` when omitted.
        security_config: Legacy ``ToolsSecurityConfig`` (deprecated, retained
            as a migration convenience). If provided and ``policy`` is not,
            it is converted to a ``WorkspaceToolPolicy``.
    """
    if policy is not None and security_config is not None:
        raise ValueError("Specify either policy or security_config, not both")

    if policy is None and security_config is not None:
        policy = WorkspaceToolPolicy.from_tools_security_config(security_config)
        logger.info("Tools security config converted to workspace policy")

    registry = ToolRegistry(policy=policy)
    for tool in BUILTIN_TOOLS:
        registry.register(_bind_tool(registry, tool))

    # Register Lugh repo harvester tool
    from animus.lugh.repos import HARVEST_TOOL

    registry.register(_bind_tool(registry, HARVEST_TOOL))

    # Register Lugh watchlist tools
    from animus.lugh.watchlist_tools import (
        WATCHLIST_ADD_TOOL,
        WATCHLIST_LIST_TOOL,
        WATCHLIST_REMOVE_TOOL,
        WATCHLIST_SCAN_TOOL,
    )

    registry.register(_bind_tool(registry, WATCHLIST_ADD_TOOL))
    registry.register(_bind_tool(registry, WATCHLIST_REMOVE_TOOL))
    registry.register(_bind_tool(registry, WATCHLIST_LIST_TOOL))
    registry.register(_bind_tool(registry, WATCHLIST_SCAN_TOOL))

    # Register Forge integration tools
    from animus.forge_tools import FORGE_TOOLS

    for tool in FORGE_TOOLS:
        registry.register(_bind_tool(registry, tool))

    logger.info(f"Created default registry with {len(registry.list_tools())} tools")
    return registry


def create_memory_tools(memory_layer, policy: ToolPolicy | None = None) -> list[Tool]:
    """
    Create memory-related tools that require a MemoryLayer instance.

    Args:
        memory_layer: MemoryLayer instance to use for memory operations
        policy: Optional policy parameter for signature compatibility with
            bound handlers; ignored by these tools.

    Returns:
        List of Tool objects for memory operations
    """
    from animus.memory import MemoryType

    def _tool_search_memory(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
        """Search memories."""
        query = params.get("query")
        if not query:
            return ToolResult(
                tool_name="search_memory",
                success=False,
                output=None,
                error="Missing required parameter: query",
            )

        try:
            limit = params.get("limit", 5)
            tags = params.get("tags")
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            memories = memory_layer.recall(query, tags=tags, limit=limit)

            if not memories:
                return ToolResult(
                    tool_name="search_memory",
                    success=True,
                    output=f"No memories found for '{query}'",
                )

            results = []
            for mem in memories:
                tags_str = f" [tags: {', '.join(mem.tags)}]" if mem.tags else ""
                results.append(f"- {mem.content[:200]}...{tags_str}")

            return ToolResult(
                tool_name="search_memory",
                success=True,
                output="\n".join(results),
            )
        except Exception as e:
            return ToolResult(
                tool_name="search_memory",
                success=False,
                output=None,
                error=str(e),
            )

    def _tool_save_memory(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
        """Save a new memory."""
        content = params.get("content")
        if not content:
            return ToolResult(
                tool_name="save_memory",
                success=False,
                output=None,
                error="Missing required parameter: content",
            )

        try:
            tags = params.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            memory_type_str = params.get("type", "semantic")
            memory_type = MemoryType(memory_type_str)

            memory = memory_layer.remember(content, memory_type=memory_type, tags=tags)

            return ToolResult(
                tool_name="save_memory",
                success=True,
                output=f"Saved memory with ID: {memory.id[:8]}",
            )
        except Exception as e:
            return ToolResult(
                tool_name="save_memory",
                success=False,
                output=None,
                error=str(e),
            )

    return [
        Tool(
            name="search_memory",
            description="Search through stored memories",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 5)",
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags to filter by",
                    },
                },
                "required": ["query"],
            },
            handler=_tool_search_memory,
            category="memory",
        ),
        Tool(
            name="save_memory",
            description="Save new information to memory",
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Content to remember",
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags",
                    },
                    "type": {
                        "type": "string",
                        "description": "Memory type: episodic, semantic, procedural",
                    },
                },
                "required": ["content"],
            },
            handler=_tool_save_memory,
            category="memory",
        ),
    ]


def create_local_think_tool(cognitive_layer, policy: ToolPolicy | None = None) -> Tool:
    """Create a tool that delegates subtasks to the local/cheap model.

    When Claude is the primary model, this tool lets it offload cheap
    subtasks (summarization, formatting, data extraction) to Ollama
    instead of doing them itself and burning API tokens.

    Only useful when dual models are configured (cloud primary + local fallback).
    """

    def _tool_local_think(params: dict, policy: ToolPolicy | None = None) -> ToolResult:
        """Run a subtask on the local model."""
        prompt = params.get("prompt")
        if not prompt:
            return ToolResult(
                tool_name="local_think",
                success=False,
                output=None,
                error="Missing required parameter: prompt",
            )

        system = params.get("system")
        try:
            result = cognitive_layer.delegate_to_local(prompt, system)
            return ToolResult(
                tool_name="local_think",
                success=True,
                output=result,
            )
        except Exception as e:
            return ToolResult(
                tool_name="local_think",
                success=False,
                output=None,
                error=str(e),
            )

    return Tool(
        name="local_think",
        description=(
            "Delegate a simple subtask to the local model (Ollama) to save API costs. "
            "Use for: summarizing text, reformatting output, extracting data from text, "
            "simple Q&A, translating formats. Do NOT use for: planning, code generation, "
            "debugging, complex reasoning, or tool selection."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The subtask prompt to send to the local model",
                },
                "system": {
                    "type": "string",
                    "description": "Optional system prompt for the local model",
                },
            },
            "required": ["prompt"],
        },
        handler=_tool_local_think,
        category="cognitive",
    )
