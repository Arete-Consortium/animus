"""ContainerManager — sandbox citizen execution via Docker or Podman.

Provides an alternative to explicit subprocess workers for stronger isolation.
Mounts the workspace into a throwaway container, runs the citizen, and
returns the structured output.  Also exposes async execution and kill helpers
so the pool can terminate a running container.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContainerConfig:
    """Tuning for container-based execution."""

    image: str = "python:3.12-slim"
    runtime: str = "auto"  # "docker", "podman", or "auto"
    workspace_mount: str | None = None  # host path; defaults to cwd
    extra_volumes: list[str] = None  # ["/host:/container", ...]
    env: dict[str, str] = None
    timeout_seconds: int = 300
    remove: bool = True
    network: str = "none"  # "none", "host", or bridge name

    def __post_init__(self):
        if self.extra_volumes is None:
            self.extra_volumes = []
        if self.env is None:
            self.env = {}


@dataclass
class ContainerTask:
    """Handle to a running container task."""

    container_id: str
    process: asyncio.subprocess.Process


class ContainerManager:
    """Run citizen tasks inside ephemeral containers.

    Detects the container runtime (docker → podman → None) and builds the
    appropriate CLI invocation.  If no runtime is available, ``is_available``
    returns ``False`` and the caller should fall back to process isolation.
    """

    def __init__(self, config: ContainerConfig | None = None):
        self.config = config or ContainerConfig()
        self._runtime_cmd = self._detect_runtime()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return self._runtime_cmd is not None

    def run_task(
        self,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        description: str,
        context_json: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a citizen task inside a container (blocking).

        Returns:
            CitizenOutput-shaped dict.  On success the dict includes the
            ``_container_id`` key so callers can correlate the result with
            the container that produced it.
        """
        if not self._runtime_cmd:
            return self._no_runtime_result()

        payload = {
            "task_id": task_id,
            "mission_id": mission_id,
            "citizen_role": citizen_role,
            "description": description,
            "context": context_json,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            payload_path = f.name

        try:
            return self._run_container_sync(payload_path)
        finally:
            try:
                os.unlink(payload_path)
            except OSError:
                pass

    async def run_task_async(
        self,
        task_id: str,
        mission_id: str,
        citizen_role: str,
        description: str,
        context_json: dict[str, Any],
    ) -> ContainerTask:
        """Start a container task asynchronously and return a handle.

        The caller is responsible for awaiting ``process.wait()`` and for
        calling ``kill_container`` if the task needs to be stopped early.
        """
        if not self._runtime_cmd:
            # Return a synthetic "process" that immediately yields the no-runtime result.
            proc = await self._synthetic_failed_process("No container runtime available")
            return ContainerTask(container_id="unavailable", process=proc)

        payload = {
            "task_id": task_id,
            "mission_id": mission_id,
            "citizen_role": citizen_role,
            "description": description,
            "context": context_json,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            payload_path = f.name

        # Use a cidfile so we can read the container id reliably.
        cidfile_fd, cidfile_path = tempfile.mkstemp(suffix=".cid")
        os.close(cidfile_fd)

        cmd = self._build_command(payload_path, cidfile=cidfile_path)
        logger.info("Container task async: %s", " ".join(self._safe_cmd_for_log(cmd)))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Poll the cidfile briefly until the runtime writes it.
            container_id = await self._wait_for_cid(cidfile_path, process)
            if container_id is None:
                logger.warning(
                    "Could not read container id for task %s; falling back to pid",
                    task_id,
                )
                container_id = f"pid-{process.pid}"

            return ContainerTask(container_id=container_id, process=process)
        except Exception:
            self._unlink(payload_path, cidfile_path)
            raise

    async def kill_container(self, container_id: str) -> bool:
        """Kill and remove a running container.

        Returns:
            ``True`` if the kill command completed without error.
        """
        if (
            not self._runtime_cmd
            or container_id.startswith("pid-")
            or container_id == "unavailable"
        ):
            return False

        cmd = [self._runtime_cmd, "rm", "-f", container_id]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
            return proc.returncode == 0
        except Exception as exc:
            logger.warning("Failed to kill container %s: %s", container_id, exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_runtime(self) -> str | None:
        """Return ``'docker'`` or ``'podman'`` if available, else ``None``."""
        if self.config.runtime in ("docker", "podman"):
            if shutil.which(self.config.runtime):
                return self.config.runtime
            logger.warning("Configured runtime %s not found", self.config.runtime)
            return None

        for cmd in ["docker", "podman"]:
            if shutil.which(cmd):
                logger.info("Container runtime detected: %s", cmd)
                return cmd
        logger.warning("No container runtime found (docker or podman)")
        return None

    def _build_command(self, payload_path: str, *, cidfile: str | None = None) -> list[str]:
        """Build the container run command."""
        cmd = [
            self._runtime_cmd,
            "run",
        ]
        if cidfile:
            cmd += ["--cidfile", cidfile]
        if self.config.remove:
            cmd.append("--rm")
        cmd += ["--network", self.config.network]
        cmd += ["-v", f"{payload_path}:/tmp/task_payload.json:ro"]

        ws = self.config.workspace_mount or os.getcwd()
        cmd += ["-v", f"{ws}:/workspace"]

        for vol in self.config.extra_volumes:
            cmd += ["-v", vol]

        for k, v in self.config.env.items():
            cmd += ["-e", f"{k}={v}"]

        cmd += [
            self.config.image,
            "python",
            "-c",
            self._INLINE_RUNNER,
        ]
        return [c for c in cmd if c]

    @staticmethod
    def _safe_cmd_for_log(cmd: list[str]) -> list[str]:
        """Return a copy of ``cmd`` with ``-e`` / ``--env`` values masked."""
        safe: list[str] = []
        skip_next = False
        for arg in cmd:
            if skip_next:
                if "=" in arg:
                    key, _ = arg.split("=", 1)
                    safe.append(f"{key}=[REDACTED]")
                else:
                    safe.append(f"{arg}=[REDACTED]")
                skip_next = False
            elif arg in ("-e", "--env"):
                safe.append(arg)
                skip_next = True
            elif arg.startswith("--env="):
                key, _ = arg.split("=", 1)
                safe.append(f"{key}=[REDACTED]")
            else:
                safe.append(arg)
        return safe

    def _run_container_sync(self, payload_path: str) -> dict[str, Any]:
        """Run container synchronously and parse the result."""
        cmd = self._build_command(payload_path)
        logger.info("Container task: %s", " ".join(self._safe_cmd_for_log(cmd)))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "summary": f"Container timeout after {self.config.timeout_seconds}s",
                "changed_files": [],
                "evidence": [],
                "risks": [{"severity": "critical", "description": "Container timeout"}],
                "confidence": 0.0,
                "_container_id": None,
            }

        container_id = None  # sync path does not capture cid
        if result.returncode != 0:
            logger.error("Container stderr: %s", result.stderr)
            return {
                "status": "failed",
                "summary": f"Container exit {result.returncode}: {result.stderr[:200]}",
                "changed_files": [],
                "evidence": [],
                "risks": [{"severity": "critical", "description": result.stderr[:500]}],
                "confidence": 0.0,
                "_container_id": container_id,
            }

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return {
                "status": "failed",
                "summary": "Empty container output",
                "changed_files": [],
                "evidence": [],
                "risks": [{"severity": "critical", "description": "No JSON output from container"}],
                "confidence": 0.0,
                "_container_id": container_id,
            }

        try:
            data = json.loads(lines[-1])
            data["_container_id"] = container_id
            return data
        except json.JSONDecodeError as exc:
            return {
                "status": "failed",
                "summary": f"Invalid JSON from container: {exc}",
                "changed_files": [],
                "evidence": [{"type": "raw_output", "detail": result.stdout[:500]}],
                "risks": [{"severity": "critical", "description": str(exc)}],
                "confidence": 0.0,
                "_container_id": container_id,
            }

    async def _wait_for_cid(
        self,
        cidfile_path: str,
        process: asyncio.subprocess.Process,
        max_wait_seconds: float = 5.0,
    ) -> str | None:
        """Poll the cidfile until the runtime writes a container id."""
        deadline = asyncio.get_event_loop().time() + max_wait_seconds
        while asyncio.get_event_loop().time() < deadline:
            if process.returncode is not None:
                # Container already exited; no id needed.
                return None
            try:
                with open(cidfile_path) as f:
                    cid = f.read().strip()
                if cid:
                    return cid
            except OSError:
                pass
            await asyncio.sleep(0.1)
        return None

    async def _synthetic_failed_process(self, message: str) -> asyncio.subprocess.Process:
        """Create a subprocess that immediately exits with an error-like JSON result."""
        script = f"import json, sys; print(json.dumps({{'status':'failed','summary':'{message}','confidence':0.0,'changed_files':[],'evidence':[],'risks':[{{'severity':'critical','description':'{message}'}}],'artifacts':[]}})); sys.exit(0)"
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def _no_runtime_result(self) -> dict[str, Any]:
        return {
            "status": "failed",
            "summary": "No container runtime available",
            "changed_files": [],
            "evidence": [],
            "risks": [{"severity": "critical", "description": "docker/podman not found"}],
            "confidence": 0.0,
            "_container_id": None,
        }

    @staticmethod
    def _unlink(*paths: str) -> None:
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    _INLINE_RUNNER = """
import json, sys, os, uuid
sys.path.insert(0, "/workspace/src")

from animus_forge.citizens.base import Citizen
from animus_forge.citizens.builder import BuilderCitizen
from animus_forge.citizens.planner import PlannerCitizen
from animus_forge.citizens.reviewer import ReviewerCitizen
from animus_forge.missions.domain import Task, TaskContext

_REGISTRY = {
    "planner": PlannerCitizen,
    "builder": BuilderCitizen,
    "reviewer": ReviewerCitizen,
}

with open("/tmp/task_payload.json") as f:
    payload = json.load(f)

task = Task(
    task_id=uuid.UUID(payload["task_id"]),
    mission_id=uuid.UUID(payload["mission_id"]),
    citizen_role=payload["citizen_role"],
    description=payload["description"],
)
ctx = TaskContext(**payload["context"])

cls = _REGISTRY.get(payload["citizen_role"])
if cls is None:
    print(json.dumps({
        "status": "failed",
        "summary": f"Unknown role: {payload['citizen_role']}",
        "confidence": 0.0,
    }))
    sys.exit(0)

try:
    output = cls().run(task=task, context=ctx)
    print(json.dumps(output.model_dump(mode="json")))
except Exception as exc:
    print(json.dumps({
        "status": "failed",
        "summary": str(exc),
        "confidence": 0.0,
    }))
"""
