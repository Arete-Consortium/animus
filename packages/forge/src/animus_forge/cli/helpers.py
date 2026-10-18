"""Shared helpers for CLI modules — client factories, parsing, tracker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from rich.console import Console

if TYPE_CHECKING:
    from animus_forge.api_clients import ClaudeCodeClient
    from animus_forge.monitoring.tracker import ExecutionTracker
    from animus_forge.orchestrator import WorkflowEngineAdapter
    from animus_forge.workflow.executor import WorkflowExecutor

console = Console()


def get_workflow_engine() -> WorkflowEngineAdapter:
    """Lazy import workflow engine with real managers for production use."""
    try:
        from animus_forge.budget import BudgetManager
        from animus_forge.orchestrator import WorkflowEngineAdapter
        from animus_forge.state.checkpoint import CheckpointManager

        execution_mgr = _create_cli_execution_manager()
        return WorkflowEngineAdapter(
            checkpoint_manager=CheckpointManager(),
            budget_manager=BudgetManager(),
            execution_manager=execution_mgr,
        )
    except ImportError as e:
        console.print(f"[red]Missing dependencies:[/red] {e}")
        console.print("Run: pip install pydantic-settings")
        raise typer.Exit(1)


def get_claude_client() -> ClaudeCodeClient:
    """Get Claude Code client for direct agent execution."""
    try:
        from animus_forge.api_clients import ClaudeCodeClient

        client = ClaudeCodeClient()
        if not client.is_configured():
            console.print("[red]Claude not configured.[/red]")
            console.print("Set ANTHROPIC_API_KEY environment variable.")
            raise typer.Exit(1)
        return client
    except ImportError as e:
        console.print(f"[red]Missing dependencies:[/red] {e}")
        raise typer.Exit(1)


def get_workflow_executor(dry_run: bool = False) -> WorkflowExecutor:
    """Get workflow executor with checkpoint and budget managers."""
    try:
        from animus_kernel.executor.arete_hooks import get_arete_hooks

        from animus_forge.budget import BudgetManager
        from animus_forge.state.checkpoint import CheckpointManager
        from animus_forge.workflow.executor import WorkflowExecutor

        checkpoint_mgr = CheckpointManager()
        budget_mgr = BudgetManager()

        return WorkflowExecutor(
            checkpoint_manager=checkpoint_mgr,
            budget_manager=budget_mgr,
            dry_run=dry_run,
            arete_hooks=get_arete_hooks(),
        )
    except ImportError as e:
        console.print(f"[red]Missing dependencies:[/red] {e}")
        raise typer.Exit(1)


def _create_cli_execution_manager():
    """Create a lightweight ExecutionManager for CLI --live mode.

    Returns None if dependencies unavailable (graceful degradation).
    """
    try:
        from animus_forge.executions import ExecutionManager
        from animus_forge.state.backends import SQLiteBackend
        from animus_forge.state.migrations import run_migrations

        backend = SQLiteBackend(db_path=":memory:")
        run_migrations(backend)
        return ExecutionManager(backend=backend)
    except Exception:
        return None


def get_tracker() -> ExecutionTracker | None:
    """Lazy import execution tracker."""
    try:
        from animus_forge.monitoring.tracker import get_tracker as _get_tracker

        return _get_tracker()
    except ImportError:
        return None


def get_supervisor():
    """Create a SupervisorAgent with provider, budget, and coordination."""
    try:
        import os

        from animus_forge.agents import SupervisorAgent, create_agent_provider

        provider_type = os.environ.get("DEFAULT_PROVIDER", "ollama")
        provider = create_agent_provider(provider_type)

        # Optional: budget manager
        budget_mgr = None
        try:
            from animus_forge.budget import BudgetManager

            budget_mgr = BudgetManager()
        except Exception:
            pass  # Budget module not available — run without budget tracking

        # Optional: convergence checker
        checker = None
        try:
            from animus_forge.agents.convergence import create_checker

            checker = create_checker()
        except Exception:
            pass  # Convergence module not installed — run without convergence

        # Optional: coordination bridge
        bridge = None
        try:
            from animus_forge import api_state

            bridge = getattr(api_state, "coordination_bridge", None)
        except Exception:
            pass  # API state not initialized — run without coordination

        # Optional: tool registry for builder/tester/reviewer agents
        tool_registry = None
        try:
            from animus_forge.tools.registry import ForgeToolRegistry

            require_approval = os.environ.get("FORGE_WRITE_APPROVAL", "").lower() in (
                "1",
                "true",
                "on",
            )
            tool_registry = ForgeToolRegistry(
                enable_shell=True,
                require_write_approval=require_approval,
                budget_manager=budget_mgr,
            )
        except Exception:
            pass  # Tool registry not available — run without tools

        # Load agent configs from YAML if available
        agent_configs = None
        try:
            from animus_forge.agents.config_loader import load_agent_configs

            agent_configs = load_agent_configs()
        except Exception:
            pass

        sup = SupervisorAgent(
            provider,
            convergence_checker=checker,
            coordination_bridge=bridge,
            budget_manager=budget_mgr,
            tool_registry=tool_registry,
            agent_configs=agent_configs,
        )

        # Wire TaskRunner so delegated agents get tools + memory
        try:
            from animus_forge.agents.task_runner import AgentTaskRunner

            runner = AgentTaskRunner(
                provider=provider,
                tool_registry=tool_registry,
            )
            # Add agent memory if available
            try:
                from animus_forge.state.agent_memory import AgentMemory

                runner.agent_memory = AgentMemory()
            except Exception:
                pass
            sup.set_task_runner(runner)
        except Exception:
            pass  # TaskRunner not available — supervisor runs with direct provider

        return sup
    except Exception as e:
        console.print(f"[red]Could not create supervisor agent:[/red] {e}")
        console.print("Ensure a provider is available (Ollama running, or ANTHROPIC_API_KEY set).")
        raise typer.Exit(1)


def _parse_cli_variables(var: list[str]) -> dict:
    """Parse CLI variables in key=value format."""
    variables = {}
    for v in var:
        if "=" in v:
            key, value = v.split("=", 1)
            variables[key] = value
        else:
            console.print(f"[red]Invalid variable format: {v}[/red]")
            console.print("Use: --var key=value")
            raise typer.Exit(1)
    return variables
