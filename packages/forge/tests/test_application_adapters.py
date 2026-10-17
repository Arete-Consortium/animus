"""Verify Forge owns application clients across the Kernel boundary."""

from unittest.mock import MagicMock, patch

import pytest
from animus_kernel.executor.executor_agents import AgentStepHandlerMixin as KernelAgents
from animus_kernel.executor.executor_integrations import (
    IntegrationHandlersMixin as KernelIntegrations,
)
from animus_kernel.executor.loader import VALID_STEP_TYPES, WORKFLOW_SCHEMA, StepConfig

from animus_forge.workflow.executor import WorkflowExecutor


def test_kernel_requires_application_adapters():
    with pytest.raises(RuntimeError, match="application adapter"):
        KernelIntegrations()._integration_dependency("api_clients", "GitHubClient")
    with pytest.raises(RuntimeError, match="application adapter"):
        KernelAgents()._create_autonomy_loop(provider=object())


def test_kernel_integration_dry_run_does_not_need_client():
    host = KernelIntegrations()
    host.dry_run = True
    result = host._execute_github(StepConfig(id="github", type="github"), {})
    assert result["dry_run"] is True


def test_forge_executor_uses_application_client_and_settings():
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.dry_run = False
    client = MagicMock()
    client.is_configured.return_value = True
    client.list_repositories.return_value = [{"name": "fixture"}]
    with patch("animus_forge.api_clients.GitHubClient", return_value=client) as factory:
        executor._execute_github(
            StepConfig(id="github", type="github", params={"action": "list_repos"}), {}
        )
    factory.assert_called_once_with()
    client.list_repositories.assert_called_once()
    with patch("animus_forge.config.get_settings") as settings:
        assert executor._integration_settings() is settings.return_value


def test_forge_executor_constructs_forge_autonomy_loop():
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    provider = object()
    with patch("animus_forge.agents.autonomy.AutonomyLoop") as loop:
        assert executor._create_autonomy_loop(provider=provider) is loop.return_value
    loop.assert_called_once_with(provider=provider)


def test_shell_working_directory_is_separate_from_command(tmp_path):
    directory = tmp_path / "project with spaces"
    directory.mkdir()
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.dry_run = False
    step = StepConfig(
        id="shell",
        type="shell",
        params={"command": "pwd", "working_directory": "${project}"},
    )
    result = executor._execute_shell(step, {"project": str(directory)})
    assert result["stdout"].strip() == str(directory.resolve())


def test_working_directory_does_not_enable_shell_chaining(tmp_path):
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.dry_run = False
    step = StepConfig(
        id="shell",
        type="shell",
        params={"command": "pwd && echo unsafe", "working_directory": str(tmp_path)},
    )
    with pytest.raises(ValueError, match="shell metacharacters"):
        executor._execute_shell(step, {})


@pytest.mark.parametrize(
    "step_type", ["github", "notion", "gmail", "slack", "calendar", "browser", "cost_audit"]
)
def test_registered_integration_steps_are_valid(step_type):
    assert step_type in VALID_STEP_TYPES
    assert (
        step_type in WORKFLOW_SCHEMA["properties"]["steps"]["items"]["properties"]["type"]["enum"]
    )


def test_dashboard_and_executor_share_parallel_tracker():
    from animus_kernel.monitoring.parallel_tracker import get_parallel_tracker as kernel_tracker

    from animus_forge.monitoring.parallel_tracker import get_parallel_tracker as forge_tracker

    assert forge_tracker() is kernel_tracker()
