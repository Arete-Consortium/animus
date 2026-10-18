"""Tests for ContainerManager (Phase 6 container isolation).

These tests verify command generation and error handling without requiring
an actual Docker or Podman installation.
"""

from __future__ import annotations

import json
import uuid

import pytest

from animus_forge.scheduler.containers import ContainerConfig, ContainerManager


class FakeCompletedProcess:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestContainerConfig:
    def test_defaults(self):
        c = ContainerConfig()
        assert c.image == "python:3.12-slim"
        assert c.runtime == "auto"
        assert c.workspace_mount is None
        assert c.extra_volumes == []
        assert c.env == {}
        assert c.timeout_seconds == 300
        assert c.remove is True
        assert c.network == "none"

    def test_post_init_lists(self):
        c = ContainerConfig()
        assert c.extra_volumes is not None
        assert c.env is not None


class TestContainerManagerDetection:
    def test_no_runtime_found(self, monkeypatch):
        """When neither docker nor podman is on PATH, is_available is False."""
        monkeypatch.setattr("shutil.which", lambda _cmd: None)
        cm = ContainerManager(ContainerConfig(runtime="auto"))
        assert cm.is_available() is False
        assert cm._runtime_cmd is None

    def test_docker_detected(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager(ContainerConfig(runtime="auto"))
        assert cm.is_available() is True
        assert cm._runtime_cmd == "docker"

    def test_podman_detected_when_docker_missing(self, monkeypatch):
        def _which(cmd):
            if cmd == "docker":
                return None
            if cmd == "podman":
                return "/usr/bin/podman"
            return None

        monkeypatch.setattr("shutil.which", _which)
        cm = ContainerManager(ContainerConfig(runtime="auto"))
        assert cm.is_available() is True
        assert cm._runtime_cmd == "podman"


class TestContainerManagerCommandGeneration:
    @pytest.fixture
    def cm(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        return ContainerManager(
            ContainerConfig(
                image="test-img:latest",
                workspace_mount="/host/workspace",
                extra_volumes=["/host/cache:/cache"],
                env={"FOO": "bar"},
                network="host",
                remove=False,
            )
        )

    def test_build_command_structure(self, cm):
        cmd = cm._build_command("/tmp/payload.json")
        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--network" in cmd
        assert "host" in cmd
        # Should NOT include --rm because remove=False
        assert "--rm" not in cmd
        # Volume mounts
        assert "/tmp/payload.json:/tmp/task_payload.json:ro" in cmd
        assert "/host/workspace:/workspace" in cmd
        assert "/host/cache:/cache" in cmd
        # Environment
        assert "-e" in cmd
        assert "FOO=bar" in cmd
        # Image
        assert "test-img:latest" in cmd
        # Inline runner via python -c
        assert "python" in cmd
        assert "-c" in cmd

    def test_build_command_filters_empty_strings(self, cm):
        # With remove=False, --rm becomes "" and must be filtered
        cmd = cm._build_command("/tmp/payload.json")
        assert "" not in cmd


class TestContainerManagerRunTask:
    def test_runtime_unavailable_returns_failure(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _cmd: None)
        cm = ContainerManager()
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={},
        )
        assert result["status"] == "failed"
        assert "No container runtime available" in result["summary"]

    def test_timeout_returns_failure(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager(ContainerConfig(timeout_seconds=1))

        def _slow_run(*_args, **_kwargs):
            import subprocess

            raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

        monkeypatch.setattr("subprocess.run", _slow_run)
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={},
        )
        assert result["status"] == "failed"
        assert "timeout" in result["summary"].lower()

    def test_nonzero_returncode_returns_failure(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager()
        fake = FakeCompletedProcess(returncode=1, stdout="", stderr="bad image")
        monkeypatch.setattr("subprocess.run", lambda *_a, **_k: fake)
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={},
        )
        assert result["status"] == "failed"
        assert "Container exit 1" in result["summary"]

    def test_empty_stdout_returns_failure(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager()
        fake = FakeCompletedProcess(returncode=0, stdout="   \n  \n")
        monkeypatch.setattr("subprocess.run", lambda *_a, **_k: fake)
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={},
        )
        assert result["status"] == "failed"
        assert "Empty container output" in result["summary"]

    def test_successful_json_output(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager()
        payload = {
            "status": "success",
            "summary": "it worked",
            "changed_files": [],
            "evidence": [],
            "risks": [],
            "confidence": 0.95,
        }
        fake = FakeCompletedProcess(returncode=0, stdout=json.dumps(payload))
        monkeypatch.setattr("subprocess.run", lambda *_a, **_k: fake)
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={"checkpoint": None, "task_description": "hello"},
        )
        assert result["status"] == "success"
        assert result["summary"] == "it worked"

    def test_malformed_json_returns_failure(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        )
        cm = ContainerManager()
        fake = FakeCompletedProcess(returncode=0, stdout="not json {{")
        monkeypatch.setattr("subprocess.run", lambda *_a, **_k: fake)
        result = cm.run_task(
            task_id=str(uuid.uuid4()),
            mission_id=str(uuid.uuid4()),
            citizen_role="builder",
            description="test",
            context_json={},
        )
        assert result["status"] == "failed"
        assert "Invalid JSON" in result["summary"]
