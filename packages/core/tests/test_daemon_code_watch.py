"""Tests for ``animus.daemon.code_watch`` — file-watched incremental reindex."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from animus.daemon.code_watch import _DEBOUNCE_SECONDS, CodeIndexReindexer
from animus.daemon.events import EventType, FileWatchEvent
from animus.memory import MemoryLayer


class TestCodeIndexReindexer:
    def test_add_codebase(self, tmp_path: Path):
        reindexer = CodeIndexReindexer()
        reindexer.add_codebase(tmp_path, tags=["test"])
        watched = reindexer.list_watched()
        assert len(watched) == 1
        assert watched[0]["root"] == str(tmp_path)
        assert watched[0]["tags"] == ["test"]

    def test_add_codebase_not_a_directory(self, tmp_path: Path):
        reindexer = CodeIndexReindexer()
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("nope")
        with pytest.raises(ValueError, match="Not a directory"):
            reindexer.add_codebase(file_path)

    def test_remove_codebase(self, tmp_path: Path):
        reindexer = CodeIndexReindexer()
        reindexer.add_codebase(tmp_path)
        assert reindexer.remove_codebase(tmp_path) is True
        assert reindexer.remove_codebase(tmp_path) is False
        assert reindexer.list_watched() == []

    def test_on_file_event_no_matching_root(self, tmp_path: Path):
        reindexer = CodeIndexReindexer()
        reindexer.add_codebase(tmp_path)
        event = FileWatchEvent(
            event_type=EventType.FILE_WATCH,
            path="/some/other/file.py",
            change_type="modified",
        )
        result = reindexer.on_file_event(event)
        assert result["action"] == "ignored"

    def test_on_file_event_debounce(self, tmp_path: Path):
        memory = MemoryLayer(tmp_path / "data", backend="local")
        reindexer = CodeIndexReindexer(memory=memory)

        # Create a small codebase
        (tmp_path / "main.py").write_text("def hello(): pass\n")
        reindexer.add_codebase(tmp_path, tags=["test"])

        event = FileWatchEvent(
            event_type=EventType.FILE_WATCH,
            path=str(tmp_path / "main.py"),
            change_type="modified",
        )

        # First event should reindex
        r1 = reindexer.on_file_event(event)
        assert r1["action"] == "reindexed"

        # Immediate second event should be debounced
        r2 = reindexer.on_file_event(event)
        assert r2["action"] == "debounced"

    def test_on_file_event_triggers_ingest(self, tmp_path: Path):
        memory = MemoryLayer(tmp_path / "data", backend="local")
        reindexer = CodeIndexReindexer(memory=memory)

        (tmp_path / "main.py").write_text("def hello(): pass\n")
        reindexer.add_codebase(tmp_path, tags=["demo"])

        event = FileWatchEvent(
            event_type=EventType.FILE_WATCH,
            path=str(tmp_path / "main.py"),
            change_type="modified",
        )

        result = reindexer.on_file_event(event)
        assert result["action"] == "reindexed"
        assert result["root"] == str(tmp_path)
        # Should have stored at least one chunk
        assert int(result["stored"]) >= 1

    def test_handler_list_updates_with_additions(self, tmp_path: Path):
        reindexer = CodeIndexReindexer()
        assert reindexer.handlers == []
        reindexer.add_codebase(tmp_path)
        assert len(reindexer.handlers) == 1
        assert isinstance(reindexer.handlers[0].watch_path, Path)


class TestDaemonIntegration:
    """Test that AnimusDaemon exposes watch_codebase correctly."""

    def test_daemon_watch_codebase(self, tmp_path: Path):
        from animus.daemon.core import AnimusDaemon, DaemonConfig

        config = DaemonConfig(
            persistence_dir=tmp_path / "daemon",
            sessions_dir=tmp_path / "sessions",
            scheduler_dir=tmp_path / "scheduler",
            enable_file_watch=True,
        )
        daemon = AnimusDaemon(config=config)

        cb = tmp_path / "myapp"
        cb.mkdir()
        (cb / "main.py").write_text("def main(): pass\n")

        daemon.watch_codebase(cb, tags=["myapp"])
        watched = daemon.code_reindexer.list_watched()
        assert len(watched) == 1
        assert watched[0]["root"] == str(cb)
        assert watched[0]["tags"] == ["myapp"]

    def test_daemon_tick_scans_code_watchers(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        from animus.daemon.core import AnimusDaemon, DaemonConfig

        config = DaemonConfig(
            persistence_dir=tmp_path / "daemon",
            sessions_dir=tmp_path / "sessions",
            scheduler_dir=tmp_path / "scheduler",
            tick_interval=0.01,
            file_scan_interval=0.01,
            enable_file_watch=True,
        )
        daemon = AnimusDaemon(config=config)

        cb = tmp_path / "myapp"
        cb.mkdir()
        (cb / "main.py").write_text("def main(): pass\n")

        daemon.watch_codebase(cb, tags=["myapp"])

        # First tick — should detect the file as "created"
        # We need to run in an async context
        import asyncio

        async def tick():
            daemon._tick_count = 0
            daemon._last_file_scan = 0
            await daemon._tick()

        asyncio.run(tick())

        # After tick, the file should have been scanned
        # The handler's _last_seen should contain the file
        handler = daemon.code_reindexer.handlers[0]
        assert len(handler._last_seen) >= 1

    def test_debounce_respected_after_delay(self, tmp_path: Path):
        memory = MemoryLayer(tmp_path / "data", backend="local")
        reindexer = CodeIndexReindexer(memory=memory)

        (tmp_path / "main.py").write_text("def hello(): pass\n")
        reindexer.add_codebase(tmp_path, tags=["test"])

        event = FileWatchEvent(
            event_type=EventType.FILE_WATCH,
            path=str(tmp_path / "main.py"),
            change_type="modified",
        )

        r1 = reindexer.on_file_event(event)
        assert r1["action"] == "reindexed"

        # Wait past debounce
        time.sleep(_DEBOUNCE_SECONDS + 0.1)

        # Modify the file so it's not skipped
        (tmp_path / "main.py").write_text("def hello(): pass\ndef world(): pass\n")
        r2 = reindexer.on_file_event(event)
        assert r2["action"] == "reindexed"
