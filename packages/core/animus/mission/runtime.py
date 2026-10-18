"""AgentRuntime — abstraction over execution environments for citizen missions.

Design: Protocol (duck-typed) so adapters need not inherit from a base class.
LocalRuntime is the default adapter. External frameworks (ADK, LangGraph, etc.)
implement the same interface as replaceable adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from animus.logging import get_logger

if TYPE_CHECKING:
    from animus.mission.order import MissionOrder

logger = get_logger("mission.runtime")


@dataclass
class RuntimeCapabilities:
    """Capabilities advertised by a runtime."""

    supports_async: bool = True
    supports_scheduling: bool = False
    supports_checkpointing: bool = True
    supports_network: bool = True
    supports_filesystem_write: bool = True
    max_concurrent_missions: int = 1
    supported_tool_types: list[str] = field(default_factory=lambda: ["python", "bash", "file"])

    def can_handle(self, mission_type: str) -> bool:
        """Check if this runtime can handle a mission type."""
        # Default: all mission types unless explicitly restricted
        return True


class AgentRuntime(Protocol):
    """Abstract interface for citizen execution environments.

    Methods:
        spawn(order) -> runtime_handle: Initialize a new mission context.
        message(handle, payload) -> response: Send a message to the running mission.
        schedule(handle, task, delay) -> task_id: Schedule a future task.
        tool_call(handle, tool_name, params) -> result: Execute a tool in the mission context.
        checkpoint(handle) -> state: Capture current mission state.
        terminate(handle, reason) -> result: Gracefully end the mission.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> RuntimeCapabilities: ...

    def spawn(self, order: MissionOrder) -> str:
        """Spawn a new mission context. Returns a runtime handle."""
        ...

    def message(self, handle: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a message to the mission context. Returns response."""
        ...

    def schedule(
        self,
        handle: str,
        task: dict[str, Any],
        delay_seconds: float = 0.0,
    ) -> str:
        """Schedule a task for future execution. Returns task_id."""
        ...

    def tool_call(self, handle: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool in the mission context. Returns result."""
        ...

    def checkpoint(self, handle: str) -> dict[str, Any]:
        """Capture current mission state. Returns state dict."""
        ...

    def terminate(self, handle: str, reason: str = "complete") -> dict[str, Any]:
        """Gracefully end the mission. Returns final state."""
        ...


class LocalRuntime:
    """Default runtime: executes missions in the local Python process.

    Suitable for:
    - Code analysis and review tasks
    - Local file operations
    - Tool execution within Animus process boundaries

    Not suitable for:
    - Long-running blocking tasks (use daemon scheduling instead)
    - Untrusted code execution (use sandboxed runtime instead)
    """

    def __init__(self):
        self._handles: dict[str, dict[str, Any]] = {}
        self._capabilities = RuntimeCapabilities(
            supports_async=True,
            supports_scheduling=True,
            supports_checkpointing=True,
            supports_network=True,
            supports_filesystem_write=True,
            max_concurrent_missions=5,
        )

    @property
    def name(self) -> str:
        return "local"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    def spawn(self, order: MissionOrder) -> str:
        import uuid

        handle = f"local-{uuid.uuid4().hex[:8]}"
        self._handles[handle] = {
            "order_id": order.id,
            "citizen_id": order.citizen_id,
            "mission_type": order.mission_type,
            "objectives": dict(order.objectives),
            "state": "spawned",
            "spawned_at": datetime.now().isoformat(),
            "messages": [],
            "tool_calls": [],
            "checkpoints": [],
        }
        logger.info(f"LocalRuntime spawned mission {order.id} as {handle}")
        return handle

    def message(self, handle: str, payload: dict[str, Any]) -> dict[str, Any]:
        ctx = self._handles.get(handle)
        if ctx is None:
            return {"error": f"Handle {handle} not found", "status": "error"}

        ctx["messages"].append(
            {"direction": "in", "payload": payload, "timestamp": datetime.now().isoformat()}
        )

        # Simple dispatch: echo structured response based on payload type
        response = self._dispatch_message(ctx, payload)

        ctx["messages"].append(
            {"direction": "out", "payload": response, "timestamp": datetime.now().isoformat()}
        )
        return response

    def _dispatch_message(self, ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        msg_type = payload.get("type", "unknown")
        if msg_type == "status":
            return {"type": "status", "state": ctx["state"], "handle": ctx.get("handle", "")}
        elif msg_type == "objective_progress":
            obj_id = payload.get("objective_id", "")
            return {"type": "progress", "objective_id": obj_id, "status": "acknowledged"}
        elif msg_type == "result":
            # Citizen is reporting partial results
            ctx["state"] = "running"
            return {"type": "ack", "received": True}
        return {"type": "ack", "message_type": msg_type, "received": True}

    def schedule(
        self,
        handle: str,
        task: dict[str, Any],
        delay_seconds: float = 0.0,
    ) -> str:
        ctx = self._handles.get(handle)
        if ctx is None:
            return ""
        import uuid

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        ctx.setdefault("scheduled_tasks", []).append(
            {
                "task_id": task_id,
                "task": task,
                "delay_seconds": delay_seconds,
                "scheduled_at": datetime.now().isoformat(),
            }
        )
        return task_id

    def tool_call(self, handle: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        ctx = self._handles.get(handle)
        if ctx is None:
            return {"error": f"Handle {handle} not found", "status": "error"}

        ctx["tool_calls"].append(
            {
                "tool_name": tool_name,
                "params": params,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Simulate tool execution
        result = self._simulate_tool(tool_name, params, ctx)
        return result

    def _simulate_tool(
        self, tool_name: str, params: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        # Default simulation: return params as structured result
        # Subclasses or real adapters override this
        if tool_name == "read_file":
            path = params.get("path", "")
            return {"tool": tool_name, "path": path, "content": f"<simulated content of {path}>"}
        elif tool_name == "write_file":
            path = params.get("path", "")
            if "write" not in str(ctx.get("order_id", "")):  # crude authority check placeholder
                pass  # LocalRuntime does not enforce authority; MissionSystem does
            return {"tool": tool_name, "path": path, "written": True}
        elif tool_name == "execute_bash":
            cmd = params.get("command", "")
            return {"tool": tool_name, "command": cmd, "exit_code": 0, "stdout": "", "stderr": ""}
        return {"tool": tool_name, "params": params, "status": "simulated"}

    def checkpoint(self, handle: str) -> dict[str, Any]:
        ctx = self._handles.get(handle)
        if ctx is None:
            return {"error": f"Handle {handle} not found", "status": "error"}

        state = {
            "handle": handle,
            "state": ctx["state"],
            "message_count": len(ctx["messages"]),
            "tool_call_count": len(ctx["tool_calls"]),
            "checkpointed_at": datetime.now().isoformat(),
        }
        ctx["checkpoints"].append(state)
        return state

    def terminate(self, handle: str, reason: str = "complete") -> dict[str, Any]:
        ctx = self._handles.get(handle)
        if ctx is None:
            return {"error": f"Handle {handle} not found", "status": "error"}

        ctx["state"] = f"terminated:{reason}"
        final = {
            "handle": handle,
            "reason": reason,
            "message_count": len(ctx["messages"]),
            "tool_call_count": len(ctx["tool_calls"]),
            "checkpoint_count": len(ctx["checkpoints"]),
            "terminated_at": datetime.now().isoformat(),
        }
        logger.info(f"LocalRuntime terminated {handle}: {reason}")
        return final
