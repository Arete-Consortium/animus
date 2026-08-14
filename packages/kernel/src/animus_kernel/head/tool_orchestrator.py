"""Tool orchestrator for Animus Head.

Bridges model-generated tool_calls to actual tool execution, combining
ForgeToolRegistry filesystem tools with custom Head tools (memory, shell)
and optional MCP server tools.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from animus_kernel.memory.stores.local import LocalMemoryStore
from animus_kernel.memory.types import Memory, MemoryTier, MemoryType
from animus_kernel.tools.registry import ForgeToolRegistry, ToolDefinition

logger = logging.getLogger(__name__)

# Lazy import MCP — gracefully degrade if unavailable
_MCP_AVAILABLE = False
try:
    from animus_kernel.mcp.client import call_mcp_tool
    from animus_kernel.mcp.manager import MCPConnectorManager
    from animus_kernel.state.database import get_database

    _MCP_AVAILABLE = True
except ImportError:
    pass


class HeadToolOrchestrator:
    """Manages tool registration and execution for Head REPL.

    Combines:
    - Filesystem tools from ForgeToolRegistry
    - Shell execution (controlled)
    - Semantic memory (remember/recall via LocalMemoryStore)
    - MCP server tools (optional, discovered at runtime)
    """

    def __init__(
        self,
        project_root: str | Path | None = None,
        memory_dir: str | Path | None = None,
        enable_shell: bool = True,
        allowed_commands: list[str] | None = None,
        enable_mcp: bool = True,
    ) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.enable_shell = enable_shell
        self.enable_mcp = enable_mcp
        self.allowed_commands = set(
            allowed_commands
            or [
                "python",
                "python3",
                "pytest",
                "ruff",
                "git",
                "ls",
                "cat",
                "grep",
                "find",
                "pip",
                "poetry",
                "cargo",
                "npm",
                "node",
                "make",
                "mkdir",
                "touch",
                "head",
                "tail",
                "wc",
                "pwd",
                "cd",
            ]
        )

        # Forge registry for filesystem tools
        self._forge = ForgeToolRegistry(
            project_root=self.project_root,
            enable_shell=False,  # We handle shell separately with stricter gates
            require_write_approval=True,
        )

        # Memory store
        if memory_dir is None:
            memory_dir = Path.home() / ".animus" / "memory"
        self._memory = LocalMemoryStore(data_dir=Path(memory_dir))

        # MCP tools (populated lazily)
        self._mcp_tools: dict[str, ToolDefinition] = {}
        self._mcp_server_map: dict[str, str] = {}  # tool_name -> server_ref

        # Register custom Head tools
        self._register_head_tools()

        # Discover MCP tools if available
        if self.enable_mcp:
            self._discover_mcp_tools()

    # ------------------------------------------------------------------
    # MCP discovery
    # ------------------------------------------------------------------

    def _discover_mcp_tools(self) -> None:
        """Discover tools from configured MCP servers.

        Gracefully degrades if MCP infrastructure is unavailable.
        """
        if not _MCP_AVAILABLE:
            logger.debug("MCP not available — skipping discovery")
            return

        try:
            db = get_database()
            manager = MCPConnectorManager(db)
            servers = manager.list_servers()

            for server in servers:
                try:
                    tools = manager.list_tools(server.id)
                    for tool in tools:
                        tool_name = f"mcp_{tool.name}"
                        self._mcp_tools[tool_name] = ToolDefinition(
                            name=tool_name,
                            description=tool.description or f"MCP tool {tool.name}",
                            parameters=tool.input_schema or {"type": "object"},
                            handler=lambda args, s=server.id, t=tool.name: self._handle_mcp_tool(
                                s, t, args
                            ),
                        )
                        self._mcp_server_map[tool_name] = server.id
                except Exception:
                    logger.debug("Failed to list tools for MCP server %s", server.id, exc_info=True)

            if self._mcp_tools:
                logger.info("Discovered %d MCP tool(s)", len(self._mcp_tools))
        except Exception:
            logger.debug("MCP discovery failed", exc_info=True)

    def _handle_mcp_tool(self, server_id: str, tool_name: str, args: dict) -> str:
        """Execute an MCP tool via the client."""
        if not _MCP_AVAILABLE:
            return "[ERROR: MCP client not available]"
        try:
            result = call_mcp_tool(
                server_type="sse",  # Default; could be dynamic
                server_url=server_id,
                tool_name=tool_name,
                arguments=args,
            )
            return result.get("content", "[MCP: no content]")
        except Exception as exc:
            return f"[ERROR: MCP tool failed: {exc}]"

    # ------------------------------------------------------------------
    # Schema exposure
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """Return all tool schemas in Ollama/OpenAI-compatible format."""
        tools: list[dict] = []

        # Forge filesystem tools
        for _name, tool_def in self._forge._tools.items():
            tools.append(tool_def.to_ollama())

        # Head custom tools
        for _name, tool_def in self._head_tools.items():
            tools.append(tool_def.to_ollama())

        # MCP tools
        for _name, tool_def in self._mcp_tools.items():
            tools.append(tool_def.to_ollama())

        return tools

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name with arguments.

        Returns:
            Tool result as a string (max 8000 chars).
        """
        logger.info("Tool call: %s(keys=%s)", name, ", ".join(arguments.keys()))

        # Forge tools first
        if name in self._forge._tools:
            return self._execute_forge(name, arguments)

        # Head tools
        if name in self._head_tools:
            return self._execute_head(name, arguments)

        # MCP tools
        if name in self._mcp_tools:
            return self._execute_head(name, arguments)

        return f"[ERROR: Unknown tool '{name}']"

    def _execute_forge(self, name: str, arguments: dict) -> str:
        """Execute a Forge-registered tool."""
        tool_def = self._forge._tools[name]
        try:
            result = tool_def.handler(arguments)
            return self._truncate(result)
        except Exception as exc:
            logger.exception("Forge tool %s failed", name)
            return f"[ERROR executing {name}: {exc}]"

    def _execute_head(self, name: str, arguments: dict) -> str:
        """Execute a Head-specific tool."""
        tool_def = self._head_tools[name]
        try:
            result = tool_def.handler(arguments)
            return self._truncate(result)
        except Exception as exc:
            logger.exception("Head tool %s failed", name)
            return f"[ERROR executing {name}: {exc}]"

    @staticmethod
    def _truncate(result: Any, max_len: int = 8000) -> str:
        """Truncate tool output to avoid context bloat."""
        text = str(result)
        if len(text) > max_len:
            return text[:max_len] + f"\n\n[... truncated {len(text) - max_len} chars]"
        return text

    # ------------------------------------------------------------------
    # Head tool definitions
    # ------------------------------------------------------------------

    def _register_head_tools(self) -> None:
        """Register custom Head tools."""
        self._head_tools: dict[str, ToolDefinition] = {}

        self._head_tools["run_shell"] = ToolDefinition(
            name="run_shell",
            description=(
                "Run a shell command safely. Only allowed commands are permitted. "
                "Returns stdout/stderr and exit code. Use for git, pytest, ls, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (default: project root)",
                    },
                },
                "required": ["command"],
            },
            handler=self._handle_run_shell,
        )

        self._head_tools["remember"] = ToolDefinition(
            name="remember",
            description=(
                "Store a semantic memory in Animus. Use to save facts, discoveries, "
                "decisions, or lessons learned during the session."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The memory content to store",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (e.g., ['sqlite', 'bugfix'])",
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["semantic", "episodic", "procedural"],
                        "description": "Type of memory",
                    },
                },
                "required": ["content"],
            },
            handler=self._handle_remember,
        )

        self._head_tools["recall"] = ToolDefinition(
            name="recall",
            description=(
                "Search semantic memories in Animus. Use to retrieve prior knowledge, "
                "decisions, or context relevant to the current task."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (substring match)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags to filter by",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 5)",
                    },
                },
                "required": ["query"],
            },
            handler=self._handle_recall,
        )

        self._head_tools["list_tasks"] = ToolDefinition(
            name="list_tasks",
            description=(
                "List active tasks from Animus TODO tracking. "
                "Useful for understanding current work items."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "all"],
                        "description": "Filter by task status",
                    },
                },
                "required": [],
            },
            handler=self._handle_list_tasks,
        )

        self._head_tools["create_task"] = ToolDefinition(
            name="create_task",
            description="Create a new task in Animus task tracking.",
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Task description",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-10 (1=highest)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the task",
                    },
                },
                "required": ["description"],
            },
            handler=self._handle_create_task,
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    # Characters that enable shell parsing when they appear in a command
    # string.  Rejecting them before shlex.split prevents chaining, pipes,
    # redirections, command substitution, newline injection, and backslash
    # escapes from reaching the subprocess invocation.
    _SHELL_INJECTION_CHARS: frozenset[str] = frozenset(";&|`$<>\\\n\r")

    # Interpreter binaries that can execute arbitrary code from an argument.
    _INTERPRETER_COMMANDS: frozenset[str] = frozenset(
        {"python", "python3", "node", "nodejs", "ruby", "perl", "php"}
    )
    _INTERPRETER_CODE_FLAGS: frozenset[str] = frozenset({"-c", "--command", "-e", "--eval"})

    def _handle_run_shell(self, args: dict) -> str:
        """Safely execute a shell command.

        Runs with shell=False and an argv list.  Shell metacharacters are
        rejected, only bare command names from the allowlist are permitted,
        and the working directory is constrained to the project root.
        """
        command = args.get("command", "").strip()
        if not command:
            return "[ERROR: Empty command]"

        if any(ch in command for ch in self._SHELL_INJECTION_CHARS):
            return "[ERROR: Command contains forbidden shell metacharacters]"

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"[ERROR: Invalid command syntax: {exc}]"

        if not argv:
            return "[ERROR: Empty command]"

        raw_base = argv[0]
        if "/" in raw_base or "\\" in raw_base or raw_base.startswith(".."):
            return f"[ERROR: Command must be a bare name, not a path: {raw_base}]"

        base_cmd = raw_base
        if base_cmd not in self.allowed_commands:
            return (
                f"[ERROR: Command '{base_cmd}' not in allowed list. "
                f"Allowed: {sorted(self.allowed_commands)}]"
            )

        # Interpreter code-execution defense: reject flags like python -c or
        # node -e that evaluate arbitrary code from an argument.
        if base_cmd in self._INTERPRETER_COMMANDS:
            if any(flag in argv for flag in self._INTERPRETER_CODE_FLAGS):
                return f"[ERROR: Command '{base_cmd}' code-execution flag is not allowed]"

        # Controlled cwd: must be a subdirectory of the project root.
        cwd_arg = args.get("cwd")
        if cwd_arg:
            try:
                cwd_path = Path(cwd_arg).resolve()
                cwd_path.relative_to(self.project_root.resolve())
            except (ValueError, OSError):
                return f"[ERROR: Working directory outside project root: {cwd_arg}]"
        else:
            cwd_path = self.project_root

        if not cwd_path.exists():
            return f"[ERROR: Working directory does not exist: {cwd_path}]"

        # Cap timeout to a reasonable maximum.
        max_timeout = 300
        try:
            timeout = int(args.get("timeout", 30))
        except (TypeError, ValueError):
            timeout = 30
        timeout = min(max(timeout, 1), max_timeout)

        try:
            result = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                cwd=str(cwd_path),
                timeout=timeout,
            )
            output = []
            if result.stdout:
                stdout = result.stdout
                if len(stdout) > 8000:
                    stdout = stdout[:8000] + "\n... [STDOUT TRUNCATED]"
                output.append(f"STDOUT:\n{stdout}")
            if result.stderr:
                stderr = result.stderr
                if len(stderr) > 8000:
                    stderr = stderr[:8000] + "\n... [STDERR TRUNCATED]"
                output.append(f"STDERR:\n{stderr}")
            output.append(f"EXIT CODE: {result.returncode}")
            return "\n\n".join(output)
        except subprocess.TimeoutExpired:
            return f"[ERROR: Command timed out after {timeout}s]"
        except Exception as exc:
            return f"[ERROR: {exc}]"

    def _handle_remember(self, args: dict) -> str:
        """Store a semantic memory."""
        content = args.get("content", "")
        tags = args.get("tags", [])
        memory_type_str = args.get("memory_type", "semantic")

        if not content:
            return "[ERROR: content is required]"

        try:
            mem_type = MemoryType(memory_type_str.upper())
        except ValueError:
            mem_type = MemoryType.SEMANTIC

        from datetime import datetime

        memory = Memory(
            id=f"head-{datetime.now().timestamp()}",
            content=content,
            memory_type=mem_type,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={},
            tags=tags,
            source="stated",
            confidence=1.0,
            tier=MemoryTier.WARM,
        )
        self._memory.store(memory)
        return f"Stored memory with tags {tags or '(none)'}: {content[:100]}..."

    def _handle_recall(self, args: dict) -> str:
        """Search semantic memories."""
        query = args.get("query", "")
        tags = args.get("tags")
        limit = args.get("limit", 5)

        if not query:
            return "[ERROR: query is required]"

        memories = self._memory.search(query, tags=tags, limit=limit)
        if not memories:
            return "No memories found."

        lines = [f"Found {len(memories)} memory/ies:"]
        for i, mem in enumerate(memories, 1):
            tag_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
            lines.append(f"{i}. {mem.content[:200]}{tag_str}")
        return "\n".join(lines)

    def _handle_list_tasks(self, args: dict) -> str:
        """List tasks from TODO.md if present, otherwise return stub."""
        todo_path = self.project_root / "TODO.md"
        if not todo_path.exists():
            todo_path = self.project_root.parent / "TODO.md"
        if not todo_path.exists():
            return "No TODO.md found in project. Create one to track tasks."

        try:
            content = todo_path.read_text()
            lines = content.splitlines()
            # Extract markdown checkboxes
            tasks = []
            for line in lines:
                line = line.strip()
                if line.startswith("- [ ]") or line.startswith("- [x]"):
                    tasks.append(line)
            if not tasks:
                return "TODO.md exists but no checkbox tasks found."
            return f"Active tasks from {todo_path}:\n" + "\n".join(tasks[:20])
        except Exception as exc:
            return f"[ERROR reading TODO.md: {exc}]"

    def _handle_create_task(self, args: dict) -> str:
        """Append a task to TODO.md."""
        description = args.get("description", "")
        priority = args.get("priority", 5)
        tags = args.get("tags", [])

        if not description:
            return "[ERROR: description is required]"

        todo_path = self.project_root / "TODO.md"
        if not todo_path.exists():
            todo_path = self.project_root.parent / "TODO.md"

        tag_str = f" — {', '.join(tags)}" if tags else ""
        task_line = f"- [ ] {description} (P{priority}){tag_str}\n"

        try:
            if todo_path.exists():
                with open(todo_path, "a") as f:
                    f.write(task_line)
            else:
                with open(todo_path, "w") as f:
                    f.write("# TODO\n\n")
                    f.write(task_line)
            return f"Task added to {todo_path}: {description[:80]}"
        except Exception as exc:
            return f"[ERROR writing TODO.md: {exc}]"
