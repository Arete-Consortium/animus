"""Standalone worker entry point for subprocess citizen execution.

Reads a JSON task payload from stdin, runs the requested citizen, and writes
the resulting ``CitizenOutput`` as JSON to stdout.  Designed to be invoked as:

    python -m animus_forge.scheduler.worker_main

The parent process (``CitizenWorkerPool``) manages the worker's lifecycle;
this module only performs the execution and returns a serialisable result.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from typing import Any

from animus_forge.citizens.base import Citizen
from animus_forge.citizens.builder import BuilderCitizen
from animus_forge.citizens.planner import PlannerCitizen
from animus_forge.citizens.reviewer import ReviewerCitizen
from animus_forge.missions.domain import Task, TaskContext

logger = logging.getLogger(__name__)

# Map of role → citizen class.  Keep in sync with CitizenWorkerPool.
_CITIZEN_REGISTRY: dict[str, type[Citizen]] = {
    "planner": PlannerCitizen,
    "builder": BuilderCitizen,
    "reviewer": ReviewerCitizen,
}


def _make_error_output(
    summary: str, detail: str | None = None, *, usage_complete: bool = True
) -> dict[str, Any]:
    return {
        "status": "failed",
        "summary": summary,
        "usage_complete": usage_complete,
        "changed_files": [],
        "evidence": [{"type": "worker_error", "detail": detail or summary}],
        "risks": [{"severity": "critical", "description": detail or summary}],
        "confidence": 0.0,
        "artifacts": [],
    }


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the citizen described by *payload* and return a JSON-able dict."""
    role = payload.get("citizen_role")
    citizen_cls = _CITIZEN_REGISTRY.get(role)
    if citizen_cls is None:
        return _make_error_output(f"Unknown citizen role: {role}")

    try:
        task = Task(
            task_id=uuid.UUID(payload["task_id"]),
            mission_id=uuid.UUID(payload["mission_id"]),
            citizen_role=role,
            description=payload.get("description", ""),
        )
        ctx = TaskContext(**payload.get("context", {}))
    except Exception as exc:
        logger.error("Failed to parse worker payload: %s", exc)
        return _make_error_output(f"Payload parse error: {exc}", detail=str(exc))

    try:
        citizen = citizen_cls()
        output = citizen.run(task=task, context=ctx)
        return output.model_dump(mode="json")
    except Exception as exc:
        logger.error("Worker exception for task %s: %s", task.task_id, exc)
        return _make_error_output(f"Worker crashed: {exc}", detail=str(exc), usage_complete=False)


def main() -> None:
    """Read stdin, run citizen, write stdout, exit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        raw = sys.stdin.read()
        if not raw:
            result = _make_error_output("Empty worker payload on stdin")
        else:
            payload = json.loads(raw)
            result = _run(payload)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON on stdin: %s", exc)
        result = _make_error_output(f"Invalid JSON payload: {exc}", detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected worker main error: %s", exc)
        result = _make_error_output(
            f"Unexpected worker error: {exc}", detail=str(exc), usage_complete=False
        )

    # Write exactly one JSON line to stdout.
    print(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
