"""SEC-00 — execution-plane security regression tests for animus forge containers.

Reproduces defect SEC-09 from ``security/SEC-00-threat-model.md``:

- Container mode fails closed when its manager is absent.
- Default workspace mount is read-write.
- Default image is unpinned.
- No runtime resource limits are generated.
- Container command logs redact environment values.

No Docker/Podman runtime is required; all tests monkeypatch runtime detection
and ``subprocess.run``.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from animus_forge.missions.domain import TaskContext
from animus_forge.scheduler.containers import ContainerConfig, ContainerManager
from animus_forge.scheduler.worker_pool import CitizenWorkerPool, PoolConfig

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_worker_pool(lease_manager, isolation_mode: str = "container", container_manager=None):
    return CitizenWorkerPool(
        lease_manager,
        config=PoolConfig(max_workers=1, isolation_mode=isolation_mode),
        container_manager=container_manager,
    )


# ═══════════════════════════════════════════════════════════════════
# SEC-09a — container mode silently falls back to process mode
# ═══════════════════════════════════════════════════════════════════


class TestContainerModeSilentFallback:
    @pytest.mark.asyncio
    async def test_container_mode_without_manager_fails_closed(self):
        """Container isolation must never silently become a host process."""
        lease_manager = MagicMock()
        pool = _make_worker_pool(lease_manager, isolation_mode="container", container_manager=None)
        await pool.start()
        try:
            with patch("animus_forge.scheduler.worker_pool.WorkerProcess") as worker:
                ctx = TaskContext(mission_objective="o", task_description="d", repository="r")
                lease_id = await pool.submit(str(uuid4()), "planner", ctx, mission_id="m")
            assert lease_id is None
            worker.assert_not_called()
            lease_manager.acquire.assert_not_called()
            assert pool.active_count() == 0
        finally:
            await pool.stop()


# ═══════════════════════════════════════════════════════════════════
# SEC-09b — default workspace mount is read-write and image is unpinned
# ═══════════════════════════════════════════════════════════════════


class TestContainerCommandSecurity:
    def test_default_workspace_mount_is_read_write(self, monkeypatch):
        """ContainerManager._build_command mounts the workspace without ':ro'."""
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager(ContainerConfig(workspace_mount="/host/ws"))
        cmd = cm._build_command("/tmp/payload.json")

        ws_mounts = [part for part in cmd if "/host/ws:/workspace" in part]
        assert ws_mounts, f"workspace mount missing from command: {cmd}"
        assert ":ro" not in ws_mounts[0], (
            f"Expected workspace mount to be read-write before fix; got {ws_mounts[0]}"
        )

    def test_default_image_is_unpinned(self):
        """ContainerConfig defaults to a floating tag, not a digest-pinned image."""
        config = ContainerConfig()
        assert "@sha256:" not in config.image, (
            f"Expected unpinned image before fix; got {config.image}"
        )
        assert config.image == "python:3.12-slim"


# ═══════════════════════════════════════════════════════════════════
# SEC-09c — no runtime resource limits in generated command
# ═══════════════════════════════════════════════════════════════════


class TestContainerRuntimeLimitsMissing:
    def test_build_command_lacks_resource_limits(self, monkeypatch):
        """Generated 'docker run' command does not include --memory, --cpus, or
        pids-limit."""
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager(ContainerConfig())
        cmd = cm._build_command("/tmp/payload.json")

        limit_flags = {"--memory", "--memory-swap", "--cpus", "--pids-limit"}
        present = limit_flags & set(cmd)
        assert not present, (
            f"Expected no runtime resource limits before fix; found {present} in {cmd}"
        )


# ═══════════════════════════════════════════════════════════════════
# SEC-09d — environment values are logged in container command
# ═══════════════════════════════════════════════════════════════════


class TestContainerEnvLogging:
    def test_run_container_redacts_environment_values(self, monkeypatch, caplog):
        """Container command logging retains names while masking environment values."""
        fake_secret = "secret123-not-real"
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )

        def _fake_subprocess_run(cmd, **kwargs):
            return MagicMock(returncode=0, stdout="{}")

        with caplog.at_level(logging.INFO, logger="animus_forge.scheduler.containers"):
            with patch("subprocess.run", side_effect=_fake_subprocess_run):
                cm = ContainerManager(ContainerConfig(env={"FAKE_API_KEY": fake_secret}))
                cm._run_container_sync("/tmp/payload.json")

        logged = "\n".join(record.message for record in caplog.records)
        assert fake_secret not in logged
        assert "FAKE_API_KEY=[REDACTED]" in logged
