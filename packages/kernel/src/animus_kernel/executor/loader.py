"""YAML Workflow Loader and Validator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml

from animus_kernel.errors import ValidationError
from animus_kernel.utils.validation import validate_safe_path

logger = logging.getLogger(__name__)


@dataclass
class ConditionConfig:
    """Condition for step execution."""

    field: str
    operator: Literal[
        "equals",
        "not_equals",
        "contains",
        "greater_than",
        "less_than",
        "in",
        "not_empty",
    ]
    value: Any = None

    def evaluate(self, context: dict) -> bool:
        """Evaluate condition against context."""
        actual = context.get(self.field)
        if actual is None:
            return False

        if self.operator == "equals":
            return actual == self.value
        elif self.operator == "not_equals":
            return actual != self.value
        elif self.operator == "contains":
            return self.value in actual if isinstance(actual, (str, list)) else False
        elif self.operator == "greater_than":
            return actual > self.value if isinstance(actual, (int, float)) else False
        elif self.operator == "less_than":
            return actual < self.value if isinstance(actual, (int, float)) else False
        elif self.operator == "in":
            return actual in self.value if isinstance(self.value, (list, str)) else False
        elif self.operator == "not_empty":
            return bool(actual)
        return False


@dataclass
class FallbackConfig:
    """Configuration for step fallback behavior."""

    type: Literal["default_value", "alternate_step", "callback"]
    value: Any = None  # For default_value: the value to use
    step: dict | None = None  # For alternate_step: step config to execute
    callback: str | None = None  # For callback: callback name to invoke

    @classmethod
    def from_dict(cls, data: dict) -> FallbackConfig:
        return cls(
            type=data.get("type", "default_value"),
            value=data.get("value"),
            step=data.get("step"),
            callback=data.get("callback"),
        )


@dataclass
class WorkflowSettings:
    """Global settings for workflow execution."""

    auto_parallel: bool = False
    auto_parallel_max_workers: int = 4

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowSettings:
        return cls(
            auto_parallel=data.get("auto_parallel", False),
            auto_parallel_max_workers=data.get("auto_parallel_max_workers", 4),
        )


@dataclass
class StepConfig:
    """Configuration for a workflow step."""

    id: str
    type: Literal[
        "claude_code",
        "openai",
        "shell",
        "parallel",
        "checkpoint",
        "fan_out",
        "fan_in",
        "map_reduce",
        "branch",
        "loop",
        "mcp_tool",
        "approval",
        "autonomy",
        "handoff",
        "cost_audit",
        "github",
        "notion",
        "gmail",
        "slack",
        "calendar",
        "browser",
        "skill",
    ]
    params: dict = field(default_factory=dict)
    condition: ConditionConfig | None = None
    on_failure: Literal["abort", "skip", "retry", "fallback", "continue_with_default"] = "abort"
    max_retries: int = 3
    timeout_seconds: int = 300
    outputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    fallback: FallbackConfig | None = None
    default_output: dict = field(default_factory=dict)  # For continue_with_default mode
    circuit_breaker_key: str | None = None  # Key for circuit breaker tracking

    # Top-level keys recognized by from_dict. Any other key in the
    # YAML step block is treated as a step-handler param and merged
    # into ``params`` (issue #37 — fleet-*.yaml workflows had been
    # silently dropping ``model:`` and ``prompt:`` fields).
    _RECOGNIZED_TOP_LEVEL: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "type",
            "params",
            "condition",
            "on_failure",
            "max_retries",
            "timeout_seconds",
            "outputs",
            "depends_on",
            "fallback",
            "default_output",
            "circuit_breaker_key",
            "description",  # Documentation field, ignored by executor
        }
    )

    @classmethod
    def from_dict(cls, data: dict) -> StepConfig:
        """Create StepConfig from dictionary.

        Unknown top-level keys are normalized into ``params`` rather
        than dropped silently. Explicit ``params:`` entries take
        precedence — if a user writes both ``prompt: A`` at top
        level and ``params: {prompt: B}``, B wins.

        See issue #37 for the silent-drop bug this fixes.
        """
        condition = None
        if "condition" in data:
            cond_data = data["condition"]
            condition = ConditionConfig(
                field=cond_data["field"],
                operator=cond_data["operator"],
                value=cond_data.get("value"),
            )

        # Parse depends_on - supports string or list
        depends_on = data.get("depends_on", [])
        if isinstance(depends_on, str):
            depends_on = [depends_on]

        # Parse fallback config
        fallback = None
        if "fallback" in data:
            fallback = FallbackConfig.from_dict(data["fallback"])

        # Normalize unknown top-level keys into params. Explicit
        # ``params:`` wins over top-level for the same key.
        explicit_params = data.get("params", {})
        promoted: dict = {}
        for key, value in data.items():
            if key in cls._RECOGNIZED_TOP_LEVEL:
                continue
            if key in explicit_params:
                # Explicit nested wins; warn so the duplication is
                # auditable.
                logger.warning(
                    "Step %r: top-level key %r overridden by params.%s",
                    data.get("id", "<unnamed>"),
                    key,
                    key,
                )
                continue
            promoted[key] = value
        if promoted:
            logger.debug(
                "Step %r: promoted %d top-level key(s) into params: %s",
                data.get("id", "<unnamed>"),
                len(promoted),
                sorted(promoted.keys()),
            )
        merged_params = {**promoted, **explicit_params}

        return cls(
            id=data["id"],
            type=data["type"],
            params=merged_params,
            condition=condition,
            on_failure=data.get("on_failure", "abort"),
            max_retries=data.get("max_retries", 3),
            timeout_seconds=data.get("timeout_seconds", 300),
            outputs=data.get("outputs", []),
            depends_on=depends_on,
            fallback=fallback,
            default_output=data.get("default_output", {}),
            circuit_breaker_key=data.get("circuit_breaker_key"),
        )


@dataclass
class WorkflowConfig:
    """Configuration for a complete workflow."""

    name: str
    version: str
    description: str
    steps: list[StepConfig]
    inputs: dict = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    token_budget: int = 100000
    timeout_seconds: int = 3600
    settings: WorkflowSettings = field(default_factory=WorkflowSettings)

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowConfig:
        """Create WorkflowConfig from dictionary."""
        steps = [StepConfig.from_dict(s) for s in data.get("steps", [])]
        settings = WorkflowSettings.from_dict(data.get("settings", {}))

        return cls(
            name=data["name"],
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            steps=steps,
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", []),
            metadata=data.get("metadata", {}),
            token_budget=data.get("token_budget", 100000),
            timeout_seconds=data.get("timeout_seconds", 3600),
            settings=settings,
        )

    def get_step(self, step_id: str) -> StepConfig | None:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


# YAML workflow schema for validation
WORKFLOW_SCHEMA = {
    "type": "object",
    "required": ["name", "steps"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "token_budget": {"type": "integer", "minimum": 1000},
        "timeout_seconds": {"type": "integer", "minimum": 60},
        "inputs": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "required": {"type": "boolean"},
                    "default": {},
                    "description": {"type": "string"},
                },
            },
        },
        "outputs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "type"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {
                        "type": "string",
                        "enum": [
                            "claude_code",
                            "openai",
                            "shell",
                            "parallel",
                            "checkpoint",
                            "fan_out",
                            "fan_in",
                            "map_reduce",
                            "branch",
                            "loop",
                            "mcp_tool",
                            "approval",
                            "github",
                            "notion",
                            "gmail",
                            "slack",
                            "calendar",
                            "browser",
                            "cost_audit",
                        ],
                    },
                    "params": {"type": "object"},
                    "condition": {
                        "type": "object",
                        "required": ["field", "operator"],
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {
                                "type": "string",
                                "enum": [
                                    "equals",
                                    "not_equals",
                                    "contains",
                                    "greater_than",
                                    "less_than",
                                    "in",
                                    "not_empty",
                                ],
                            },
                            "value": {},
                        },
                    },
                    "on_failure": {
                        "type": "string",
                        "enum": ["abort", "skip", "retry"],
                    },
                    "max_retries": {"type": "integer", "minimum": 0},
                    "timeout_seconds": {"type": "integer", "minimum": 1},
                    "outputs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "depends_on": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ]
                    },
                },
            },
        },
        "metadata": {"type": "object"},
    },
}


def _get_workflows_dir() -> Path:
    """Get the trusted workflows directory from settings."""
    try:
        from animus_kernel.config import get_settings

        return get_settings().workflows_dir
    except Exception:
        # Fallback if settings not available
        return Path(__file__).parent.parent / "workflows"


def load_workflow(
    path: str | Path,
    trusted_dir: str | Path | None = None,
    validate_path: bool = True,
) -> WorkflowConfig:
    """Load workflow from YAML file.

    Security: By default, paths are validated to prevent loading arbitrary files.
    The workflow file must be within trusted_dir (defaults to settings.workflows_dir).

    Args:
        path: Path to YAML workflow file
        trusted_dir: Base directory for path validation (default: settings.workflows_dir)
        validate_path: If True, validate path is within trusted_dir (default: True)

    Returns:
        WorkflowConfig object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid or schema validation fails
        ValidationError: If path escapes trusted directory
    """
    path = Path(path)

    # Validate path if enabled
    if validate_path:
        base_dir = Path(trusted_dir) if trusted_dir else _get_workflows_dir()
        try:
            path = validate_safe_path(
                path,
                base_dir,
                must_exist=True,
                allow_absolute=True,
            )
        except ValidationError:
            raise
    elif not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"Workflow file must contain a YAML mapping: {path}")

    # Validate schema
    errors = validate_workflow(data)
    if errors:
        raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")

    return WorkflowConfig.from_dict(data)


def _validate_workflow_steps(data: dict) -> list[str]:
    """Validate workflow steps field."""
    if "steps" not in data:
        return ["Missing required field: steps"]
    if not isinstance(data["steps"], list):
        return ["Field 'steps' must be a list"]
    if len(data["steps"]) == 0:
        return ["Workflow must have at least one step"]

    errors = []
    step_ids: set[str] = set()
    for i, step in enumerate(data["steps"]):
        errors.extend(_validate_step(step, i))
        step_id = step.get("id")
        if step_id in step_ids:
            errors.append(f"Duplicate step ID: {step_id}")
        elif step_id:
            step_ids.add(step_id)
    return errors


def _validate_workflow_optional_fields(data: dict) -> list[str]:
    """Validate optional workflow fields (inputs, outputs, budget, timeout)."""
    errors = []

    if "inputs" in data and not isinstance(data["inputs"], dict):
        errors.append("Field 'inputs' must be an object")

    if "outputs" in data:
        if not isinstance(data["outputs"], list):
            errors.append("Field 'outputs' must be a list")
        elif not all(isinstance(o, str) for o in data["outputs"]):
            errors.append("All output names must be strings")

    if "token_budget" in data:
        if not isinstance(data["token_budget"], int) or data["token_budget"] < 1000:
            errors.append("token_budget must be an integer >= 1000")

    if "timeout_seconds" in data:
        if not isinstance(data["timeout_seconds"], int) or data["timeout_seconds"] < 60:
            errors.append("timeout_seconds must be an integer >= 60")

    return errors


def validate_workflow(data: dict) -> list[str]:
    """Validate workflow data against schema.

    Args:
        data: Workflow dictionary

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate name field
    if "name" not in data:
        errors.append("Missing required field: name")
    elif not isinstance(data["name"], str) or not data["name"].strip():
        errors.append("Field 'name' must be a non-empty string")

    errors.extend(_validate_workflow_steps(data))
    errors.extend(_validate_workflow_optional_fields(data))

    return errors


VALID_STEP_TYPES = frozenset(
    {
        "claude_code",
        "openai",
        "ollama",
        "shell",
        "parallel",
        "checkpoint",
        "fan_out",
        "fan_in",
        "map_reduce",
        "branch",
        "loop",
        "mcp_tool",
        "approval",
        "github",
        "notion",
        "gmail",
        "slack",
        "calendar",
        "browser",
        "cost_audit",
        # Arete Tool step types
        "signal_audit",
        "autopsy_analyze",
        "verdict_capture",
        # Agent step types
        "autonomy",
        "handoff",
    }
)
VALID_OPERATORS = frozenset(
    {"equals", "not_equals", "contains", "greater_than", "less_than", "in", "not_empty"}
)
VALID_ON_FAILURE = frozenset({"abort", "skip", "retry"})


def _validate_step_condition(step: dict, prefix: str) -> list[str]:
    """Validate step condition if present."""
    if "condition" not in step:
        return []

    errors = []
    cond = step["condition"]
    if not isinstance(cond, dict):
        return [f"{prefix}: condition must be an object"]

    for req in ("field", "operator"):
        if req not in cond:
            errors.append(f"{prefix}: condition missing '{req}'")

    # 'value' is required for all operators except 'not_empty'
    if cond.get("operator") != "not_empty" and "value" not in cond:
        errors.append(f"{prefix}: condition missing 'value'")

    if "operator" in cond and cond["operator"] not in VALID_OPERATORS:
        errors.append(f"{prefix}: invalid condition operator '{cond['operator']}'")

    return errors


def _validate_step_optional_fields(step: dict, prefix: str) -> list[str]:
    """Validate optional step fields (on_failure, max_retries, timeout, depends_on)."""
    errors = []

    if "on_failure" in step and step["on_failure"] not in VALID_ON_FAILURE:
        errors.append(f"{prefix}: invalid on_failure value '{step['on_failure']}'")

    if "max_retries" in step:
        if not isinstance(step["max_retries"], int) or step["max_retries"] < 0:
            errors.append(f"{prefix}: max_retries must be a non-negative integer")

    if "timeout_seconds" in step:
        if not isinstance(step["timeout_seconds"], int) or step["timeout_seconds"] < 1:
            errors.append(f"{prefix}: timeout_seconds must be a positive integer")

    if "depends_on" in step:
        deps = step["depends_on"]
        if isinstance(deps, str):
            deps = [deps]
        if not isinstance(deps, list):
            errors.append(f"{prefix}: depends_on must be a string or list of strings")
        elif not all(isinstance(d, str) for d in deps):
            errors.append(f"{prefix}: all depends_on values must be strings")

    return errors


def _validate_step(step: dict, index: int) -> list[str]:
    """Validate a single workflow step."""
    prefix = f"Step {index + 1}"

    if not isinstance(step, dict):
        return [f"{prefix}: must be an object"]

    errors = []

    # Validate id field
    if "id" not in step:
        errors.append(f"{prefix}: missing required field 'id'")
    elif not isinstance(step["id"], str) or not step["id"].strip():
        errors.append(f"{prefix}: 'id' must be a non-empty string")
    else:
        prefix = f"Step '{step['id']}'"

    # Validate type field
    if "type" not in step:
        errors.append(f"{prefix}: missing required field 'type'")
    elif step["type"] not in VALID_STEP_TYPES:
        errors.append(f"{prefix}: invalid type '{step['type']}'")

    errors.extend(_validate_step_condition(step, prefix))
    errors.extend(_validate_step_optional_fields(step, prefix))

    # Approval-specific validation
    if step.get("type") == "approval":
        params = step.get("params", {})
        if "prompt" not in params:
            errors.append(f"{prefix}: approval step requires 'prompt' in params")
        preview_from = params.get("preview_from")
        if preview_from is not None and not isinstance(preview_from, list):
            errors.append(f"{prefix}: 'preview_from' must be a list of step IDs")

    return errors


def list_workflows(directory: str | Path = "workflows") -> list[dict]:
    """List all workflow files in a directory.

    Args:
        directory: Directory to search for .yaml files

    Returns:
        List of workflow summaries with name, path, and description
    """
    directory = Path(directory)
    if not directory.exists():
        return []

    workflows = []
    for yaml_file in directory.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                workflows.append(
                    {
                        "path": str(yaml_file),
                        "name": data.get("name", yaml_file.stem),
                        "version": data.get("version", "1.0"),
                        "description": data.get("description", ""),
                    }
                )
        except Exception:
            # Skip invalid files
            pass

    return sorted(workflows, key=lambda w: w["name"])
