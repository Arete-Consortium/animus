"""Core module coverage tests.

Covers remaining gaps in: learning/__init__.py, tools.py, proactive.py,
integrations/oauth.py, integrations/webhooks.py, cognitive.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from animus.tools import WorkspaceToolPolicy

# ===================================================================
# Learning Layer
# ===================================================================


class TestLearningLayer:
    """Tests for LearningLayer orchestration."""

    def _make_layer(self, tmp_path: Path):
        from animus.learning import LearningLayer

        mock_memory = MagicMock()
        mock_memory.recall.return_value = []
        return LearningLayer(
            memory=mock_memory,
            data_dir=tmp_path,
            min_pattern_occurrences=1,
            min_pattern_confidence=0.3,
        )

    def test_init(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert (tmp_path / "learning").is_dir()
        assert layer._learned_items == {}

    def test_load_learned_items_from_file(self, tmp_path: Path):
        items_dir = tmp_path / "learning"
        items_dir.mkdir(parents=True, exist_ok=True)
        items_file = items_dir / "learned_items.json"
        items_file.write_text(
            json.dumps(
                [
                    {
                        "id": "item-1",
                        "category": "preference",
                        "content": "User prefers dark mode",
                        "confidence": 0.9,
                        "evidence": ["m1"],
                        "source_pattern_id": "p1",
                        "applied": False,
                        "applied_at": None,
                        "created_at": "2025-01-01T00:00:00",
                        "updated_at": "2025-01-01T00:00:00",
                    }
                ]
            )
        )

        layer = self._make_layer(tmp_path)
        assert len(layer._learned_items) == 1
        assert "item-1" in layer._learned_items

    def test_load_learned_items_corrupt_file(self, tmp_path: Path):
        items_dir = tmp_path / "learning"
        items_dir.mkdir(parents=True, exist_ok=True)
        items_file = items_dir / "learned_items.json"
        items_file.write_text("not valid json")
        # Should not raise
        layer = self._make_layer(tmp_path)
        assert layer._learned_items == {}

    def test_save_learned_items(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Test item",
            confidence=0.8,
            evidence=["m1"],
            source_pattern_id="p1",
        )
        layer._learned_items[item.id] = item
        layer._save_learned_items()

        items_file = tmp_path / "learning" / "learned_items.json"
        assert items_file.exists()
        data = json.loads(items_file.read_text())
        assert len(data) == 1

    def test_scan_and_learn_no_patterns(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        patterns = layer.scan_and_learn()
        assert patterns == []

    def test_scan_and_learn_with_pattern(self, tmp_path: Path):
        from animus.learning.categories import LearningCategory
        from animus.learning.patterns import DetectedPattern, PatternType

        layer = self._make_layer(tmp_path)
        pattern = DetectedPattern.create(
            pattern_type=PatternType.PREFERENCE,
            description="User prefers dark mode",
            occurrences=5,
            confidence=0.9,
            evidence=["m1", "m2"],
            first_seen=datetime(2025, 1, 1),
            last_seen=datetime(2025, 1, 15),
            suggested_learning="User prefers dark mode",
            suggested_category=LearningCategory.PREFERENCE,
        )
        layer.pattern_detector.scan_for_patterns = MagicMock(return_value=[pattern])

        patterns = layer.scan_and_learn()
        assert len(patterns) == 1
        # Should have created a learned item
        assert len(layer._learned_items) >= 1

    def test_process_pattern_blocked_by_guardrail(self, tmp_path: Path):
        from animus.learning.categories import LearningCategory
        from animus.learning.patterns import DetectedPattern, PatternType

        layer = self._make_layer(tmp_path)
        layer.guardrails.check_learning = MagicMock(
            return_value=(False, "Blocked by identity guardrail")
        )

        pattern = DetectedPattern.create(
            pattern_type=PatternType.PREFERENCE,
            description="Change identity",
            occurrences=5,
            confidence=0.9,
            evidence=["m1"],
            first_seen=datetime(2025, 1, 1),
            last_seen=datetime(2025, 1, 15),
            suggested_learning="Change my name",
            suggested_category=LearningCategory.PREFERENCE,
        )
        result = layer._process_pattern(pattern)
        assert result is None

    def test_apply_learning(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Test learning",
            confidence=0.8,
            evidence=["m1"],
            source_pattern_id=None,
        )
        layer._apply_learning(item)
        assert item.applied is True

    def test_apply_learning_with_pattern(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory
        from animus.learning.patterns import DetectedPattern, PatternType

        layer = self._make_layer(tmp_path)
        pattern = DetectedPattern.create(
            pattern_type=PatternType.PREFERENCE,
            description="Test",
            occurrences=3,
            confidence=0.8,
            evidence=["m1"],
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            suggested_learning="test",
            suggested_category=LearningCategory.PREFERENCE,
        )
        layer.pattern_detector._detected_patterns[pattern.id] = pattern

        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Test learning",
            confidence=0.8,
            evidence=["m1"],
            source_pattern_id=pattern.id,
        )
        layer._apply_learning(item)
        assert item.applied is True

    def test_get_pattern_found(self, tmp_path: Path):
        from animus.learning.categories import LearningCategory
        from animus.learning.patterns import DetectedPattern, PatternType

        layer = self._make_layer(tmp_path)
        pattern = DetectedPattern.create(
            pattern_type=PatternType.FREQUENCY,
            description="Test",
            occurrences=3,
            confidence=0.8,
            evidence=["m1"],
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            suggested_learning="test",
            suggested_category=LearningCategory.FACT,
        )
        layer.pattern_detector._detected_patterns[pattern.id] = pattern

        result = layer._get_pattern(pattern.id)
        assert result is not None

    def test_get_pattern_not_found(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert layer._get_pattern("nonexistent") is None

    def test_approve_learning(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Approve me",
            confidence=0.8,
            evidence=["m1"],
        )
        layer._learned_items[item.id] = item
        assert layer.approve_learning(item.id) is True
        assert item.applied is True

    def test_approve_learning_not_found(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert layer.approve_learning("nonexistent") is False

    def test_approve_learning_already_applied(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Already applied",
            confidence=0.8,
            evidence=["m1"],
        )
        item.apply()
        layer._learned_items[item.id] = item
        assert layer.approve_learning(item.id) is False

    def test_reject_learning(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Reject me",
            confidence=0.8,
            evidence=["m1"],
        )
        layer._learned_items[item.id] = item
        assert layer.reject_learning(item.id, "bad pattern") is True
        assert item.id not in layer._learned_items

    def test_reject_learning_not_found(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert layer.reject_learning("nonexistent") is False

    def test_unlearn(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Unlearn me",
            confidence=0.8,
            evidence=["m1"],
        )
        item.apply()
        layer._learned_items[item.id] = item
        assert layer.unlearn(item.id, "changed mind") is True
        assert item.id not in layer._learned_items

    def test_unlearn_not_found(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert layer.unlearn("nonexistent") is False

    def test_create_checkpoint(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        checkpoint = layer.create_checkpoint("test checkpoint")
        assert checkpoint.description == "test checkpoint"

    def test_rollback_to_no_items(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        success, unlearned = layer.rollback_to("nonexistent")
        assert success is False
        assert unlearned == []

    def test_get_active_learnings(self, tmp_path: Path):
        from animus.learning.categories import LearnedItem, LearningCategory

        layer = self._make_layer(tmp_path)
        item = LearnedItem.create(
            category=LearningCategory.PREFERENCE,
            content="Active",
            confidence=0.8,
            evidence=["m1"],
        )
        item.apply()
        layer._learned_items[item.id] = item

        pending = LearnedItem.create(
            category=LearningCategory.FACT,
            content="Pending",
            confidence=0.5,
            evidence=["m2"],
        )
        layer._learned_items[pending.id] = pending

        assert len(layer.get_active_learnings()) == 1
        assert len(layer.get_pending_learnings()) == 1
        assert len(layer.get_all_learnings()) == 2
        assert layer.get_learning(item.id) is not None
        assert layer.get_learning("nonexistent") is None

    def test_get_dashboard_data(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        data = layer.get_dashboard_data()
        assert data is not None

    def test_get_preferences(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        prefs = layer.get_preferences()
        assert isinstance(prefs, list)

    def test_apply_preferences_to_context(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        ctx = layer.apply_preferences_to_context({"key": "val"}, "code")
        assert isinstance(ctx, dict)

    def test_add_user_guardrail(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        guardrail = layer.add_user_guardrail("no swearing", "Block profanity")
        assert guardrail is not None

    def test_get_statistics(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        stats = layer.get_statistics()
        assert "learned_items" in stats
        assert "patterns" in stats
        assert "preferences" in stats

    def test_start_stop_auto_scan(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        layer.start_auto_scan(interval_hours=0.001)
        assert layer._scan_timer is not None
        layer.stop_auto_scan()
        assert layer._scan_timer is None

    def test_auto_scan_running_property(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        assert layer.auto_scan_running is False

    def test_schedule_next_scan_disabled(self, tmp_path: Path):
        layer = self._make_layer(tmp_path)
        layer._scan_interval_seconds = 0
        layer._schedule_next_scan()
        assert layer._scan_timer is None


# ===================================================================
# Tools
# ===================================================================


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_unregister(self):
        from animus.tools import Tool, ToolRegistry

        registry = ToolRegistry()
        tool = Tool(name="t1", description="test", parameters={}, handler=lambda p: None)
        registry.register(tool)
        assert registry.unregister("t1") is True
        assert registry.unregister("t1") is False

    def test_get_schema(self):
        from animus.tools import Tool, ToolRegistry

        registry = ToolRegistry()
        tool = Tool(name="t1", description="test", parameters={}, handler=lambda p: None)
        registry.register(tool)
        schema = registry.get_schema()
        assert len(schema) == 1

    def test_get_schema_text(self):
        from animus.tools import Tool, ToolRegistry

        registry = ToolRegistry()
        tool = Tool(
            name="t1",
            description="A test tool",
            parameters={
                "properties": {
                    "query": {"type": "string", "description": "search query"},
                },
                "required": ["query"],
            },
            handler=lambda p: None,
        )
        registry.register(tool)
        text = registry.get_schema_text()
        assert "t1" in text
        assert "query" in text
        assert "(required)" in text

    def test_execute_not_found(self):
        from animus.tools import ToolRegistry

        registry = ToolRegistry()
        result = registry.execute("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error

    def test_execute_handler_exception(self):
        from animus.tools import Tool, ToolRegistry

        def bad_handler(params):
            raise RuntimeError("boom")

        registry = ToolRegistry()
        tool = Tool(name="bad", description="bad", parameters={}, handler=bad_handler)
        registry.register(tool)
        result = registry.execute("bad", {})
        assert result.success is False
        assert "boom" in result.error

    def test_execute_async(self):
        from animus.tools import Tool, ToolRegistry, ToolResult

        def handler(params):
            return ToolResult(tool_name="ok", success=True, output="done")

        registry = ToolRegistry()
        tool = Tool(name="ok", description="ok", parameters={}, handler=handler)
        registry.register(tool)
        result = asyncio.run(registry.execute_async("ok", {}))
        assert result.success is True

    def test_tool_result_to_context(self):
        from animus.tools import ToolResult

        r_ok = ToolResult(tool_name="t", success=True, output="hello")
        assert "hello" in r_ok.to_context()

        r_err = ToolResult(tool_name="t", success=False, output=None, error="fail")
        assert "ERROR" in r_err.to_context()


class TestBuiltinTools:
    """Tests for built-in tool functions."""

    def _make_policy(self, tmp_path: Path, **kwargs) -> WorkspaceToolPolicy:
        defaults = {
            "allowed_paths": [str(tmp_path)],
            "write_roots": [str(tmp_path)],
            "command_enabled": True,
        }
        defaults.update(kwargs)
        return WorkspaceToolPolicy(**defaults)

    def test_get_datetime_error(self):
        from animus.tools import _tool_get_datetime

        result = _tool_get_datetime({"format": "%Q"})  # Invalid format char
        # Depending on Python version, %Q may succeed or fail
        # Just ensure it doesn't crash
        assert result.tool_name == "get_datetime"

    def test_read_file_missing_path(self):
        from animus.tools import _tool_read_file

        result = _tool_read_file({})
        assert result.success is False
        assert "Missing" in result.error

    def test_read_file_not_found(self, tmp_path: Path):
        from animus.tools import _tool_read_file

        policy = self._make_policy(tmp_path)
        result = _tool_read_file({"path": str(tmp_path / "missing.txt")}, policy=policy)
        assert result.success is False
        assert "not found" in result.error

    def test_read_file_is_directory(self, tmp_path: Path):
        from animus.tools import _tool_read_file

        policy = self._make_policy(tmp_path)
        result = _tool_read_file({"path": str(tmp_path)}, policy=policy)
        assert result.success is False
        assert "Not a file" in result.error

    def test_read_file_too_large(self, tmp_path: Path):
        from animus.tools import _tool_read_file

        policy = self._make_policy(tmp_path)
        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * 200)
        result = _tool_read_file({"path": str(big_file), "max_size": 100}, policy=policy)
        assert result.success is False
        assert "too large" in result.error

    def test_read_file_success(self, tmp_path: Path):
        from animus.tools import _tool_read_file

        policy = self._make_policy(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        result = _tool_read_file({"path": str(test_file)}, policy=policy)
        assert result.success is True
        assert result.output == "hello world"

    def test_read_file_blocked_path(self, tmp_path: Path):
        from animus.tools import WorkspaceToolPolicy, _tool_read_file

        policy = WorkspaceToolPolicy(
            allowed_paths=["/tmp"],
            blocked_paths=[str(tmp_path)],
        )
        result = _tool_read_file({"path": str(tmp_path / "test.txt")}, policy=policy)
        assert result.success is False
        assert "blocked" in result.error.lower() or "denied" in result.error.lower()

    def test_list_files_not_found(self, tmp_path: Path):
        from animus.tools import _tool_list_files

        policy = self._make_policy(tmp_path)
        result = _tool_list_files({"directory": str(tmp_path / "missing")}, policy=policy)
        assert result.success is False
        assert "not found" in result.error

    def test_list_files_success(self, tmp_path: Path):
        from animus.tools import _tool_list_files

        policy = self._make_policy(tmp_path)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = _tool_list_files({"directory": str(tmp_path), "pattern": "*.txt"}, policy=policy)
        assert result.success is True
        assert "a.txt" in result.output

    def test_list_files_no_matches(self, tmp_path: Path):
        from animus.tools import _tool_list_files

        policy = self._make_policy(tmp_path)
        result = _tool_list_files({"directory": str(tmp_path), "pattern": "*.xyz"}, policy=policy)
        assert result.success is True
        assert "No matches" in result.output

    def test_run_command_missing(self):
        from animus.tools import _tool_run_command

        result = _tool_run_command({})
        assert result.success is False
        assert "Missing" in result.error

    def test_run_command_success(self, tmp_path: Path):
        from animus.tools import _tool_run_command

        policy = self._make_policy(tmp_path)
        result = _tool_run_command({"command": "echo hello"}, policy=policy)
        assert result.success is True
        assert "hello" in result.output

    def test_run_command_failure(self, tmp_path: Path):
        from animus.tools import _tool_run_command

        policy = self._make_policy(tmp_path)
        result = _tool_run_command({"command": "false"}, policy=policy)
        assert result.success is False

    def test_run_command_timeout(self, tmp_path: Path):
        from animus.tools import _tool_run_command

        policy = self._make_policy(tmp_path)
        result = _tool_run_command({"command": "sleep 60", "timeout": 1}, policy=policy)
        assert result.success is False
        assert "timed out" in result.error

    def test_run_command_with_policy(self, tmp_path: Path):
        from animus.tools import WorkspaceToolPolicy, _tool_run_command

        policy = WorkspaceToolPolicy(
            command_enabled=True,
            command_blocklist=[],
            command_timeout_seconds=5,
        )
        result = _tool_run_command({"command": "echo test", "timeout": 30}, policy=policy)
        assert result.success is True

    def test_run_command_disabled(self, tmp_path: Path):
        from animus.tools import WorkspaceToolPolicy, _tool_run_command

        policy = WorkspaceToolPolicy(command_enabled=False)
        result = _tool_run_command({"command": "echo test"}, policy=policy)
        assert result.success is False
        assert "disabled" in result.error

    # --- write_file tests ---

    def test_write_file_success(self, tmp_path: Path):
        from animus.tools import _tool_write_file

        policy = self._make_policy(tmp_path)
        target = tmp_path / "output.txt"
        result = _tool_write_file({"path": str(target), "content": "hello\nworld"}, policy=policy)
        assert result.success is True
        assert "2 lines" in result.output
        assert target.read_text() == "hello\nworld"

    def test_write_file_creates_parent_dirs(self, tmp_path: Path):
        from animus.tools import _tool_write_file

        policy = self._make_policy(tmp_path)
        target = tmp_path / "sub" / "dir" / "file.txt"
        result = _tool_write_file({"path": str(target), "content": "nested"}, policy=policy)
        assert result.success is True
        assert target.read_text() == "nested"

    def test_write_file_missing_path(self):
        from animus.tools import _tool_write_file

        result = _tool_write_file({"content": "data"})
        assert result.success is False
        assert "path" in result.error.lower()

    def test_write_file_missing_content(self, tmp_path: Path):
        from animus.tools import _tool_write_file

        policy = self._make_policy(tmp_path)
        result = _tool_write_file({"path": str(tmp_path / "f.txt")}, policy=policy)
        assert result.success is False
        assert "content" in result.error.lower()

    def test_write_file_blocked_path(self, tmp_path: Path):
        from animus.tools import WorkspaceToolPolicy, _tool_write_file

        policy = WorkspaceToolPolicy(
            allowed_paths=["/tmp"],
            blocked_paths=[str(tmp_path)],
            write_roots=["/tmp"],
        )
        result = _tool_write_file(
            {"path": str(tmp_path / "blocked.txt"), "content": "x"}, policy=policy
        )
        assert result.success is False
        assert "denied" in result.error.lower() or "blocked" in result.error.lower()

    # --- edit_file tests ---

    def test_edit_file_success(self, tmp_path: Path):
        from animus.tools import _tool_edit_file

        policy = self._make_policy(tmp_path)
        target = tmp_path / "code.py"
        target.write_text("def hello():\n    return 'world'\n")
        result = _tool_edit_file(
            {
                "path": str(target),
                "old_text": "return 'world'",
                "new_text": "return 'universe'",
            },
            policy=policy,
        )
        assert result.success is True
        assert "universe" in target.read_text()

    def test_edit_file_text_not_found(self, tmp_path: Path):
        from animus.tools import _tool_edit_file

        policy = self._make_policy(tmp_path)
        target = tmp_path / "code.py"
        target.write_text("hello world")
        result = _tool_edit_file(
            {
                "path": str(target),
                "old_text": "missing text",
                "new_text": "replacement",
            },
            policy=policy,
        )
        assert result.success is False
        assert "Could not find" in result.error

    def test_edit_file_multiple_matches(self, tmp_path: Path):
        from animus.tools import _tool_edit_file

        policy = self._make_policy(tmp_path)
        target = tmp_path / "code.py"
        target.write_text("foo\nfoo\nbar")
        result = _tool_edit_file(
            {
                "path": str(target),
                "old_text": "foo",
                "new_text": "baz",
            },
            policy=policy,
        )
        assert result.success is False
        assert "2 locations" in result.error

    def test_edit_file_not_found(self, tmp_path: Path):
        from animus.tools import _tool_edit_file

        policy = self._make_policy(tmp_path)
        result = _tool_edit_file(
            {
                "path": str(tmp_path / "missing.py"),
                "old_text": "a",
                "new_text": "b",
            },
            policy=policy,
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_file_missing_params(self):
        from animus.tools import _tool_edit_file

        result = _tool_edit_file({"path": "/tmp/x.py"})
        assert result.success is False
        assert "old_text" in result.error.lower()

    def test_edit_file_blocked_path(self, tmp_path: Path):
        from animus.tools import WorkspaceToolPolicy, _tool_edit_file

        policy = WorkspaceToolPolicy(
            allowed_paths=["/tmp"],
            blocked_paths=[str(tmp_path)],
            write_roots=["/tmp"],
        )
        result = _tool_edit_file(
            {
                "path": str(tmp_path / "blocked.py"),
                "old_text": "a",
                "new_text": "b",
            },
            policy=policy,
        )
        assert result.success is False
        assert "denied" in result.error.lower() or "blocked" in result.error.lower()

    def test_web_search_missing_query(self):
        from animus.tools import _tool_web_search

        result = _tool_web_search({})
        assert result.success is False
        assert "Missing" in result.error

    def test_web_search_too_long(self):
        from animus.tools import _tool_web_search

        result = _tool_web_search({"query": "x" * 501})
        assert result.success is False
        assert "too long" in result.error

    def test_web_search_network_error(self):
        from animus.tools import _tool_web_search

        with patch("urllib.request.urlopen", side_effect=ConnectionError("offline")):
            result = _tool_web_search({"query": "test"})
        assert result.success is False

    def test_web_search_success(self):
        from animus.tools import _tool_web_search

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = json.dumps(
            {
                "Abstract": "Test abstract",
                "AbstractSource": "Wikipedia",
                "RelatedTopics": [{"Text": "Related topic 1"}],
            }
        ).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _tool_web_search({"query": "test"})
        assert result.success is True
        assert "Test abstract" in result.output

    def test_web_search_no_results(self):
        from animus.tools import _tool_web_search

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = json.dumps(
            {
                "Abstract": "",
                "RelatedTopics": [],
            }
        ).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _tool_web_search({"query": "gibberish123"})
        assert result.success is True
        assert "No instant answer" in result.output

    def test_http_request_missing_url(self):
        from animus.tools import _tool_http_request

        result = _tool_http_request({})
        assert result.success is False
        assert "Missing" in result.error

    def test_http_request_bad_method(self):
        from animus.tools import _tool_http_request

        result = _tool_http_request({"url": "https://example.com", "method": "INVALID"})
        assert result.success is False
        assert "Unsupported" in result.error

    def test_http_request_bad_scheme(self):
        from animus.tools import _tool_http_request

        result = _tool_http_request({"url": "ftp://example.com"})
        assert result.success is False
        assert "scheme" in result.error.lower()

    def test_http_request_basic_auth(self):
        from animus.tools import _tool_http_request

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"ok"
        mock_response.status = 200
        mock_response.headers = {}

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _tool_http_request(
                {
                    "url": "https://api.example.com",
                    "auth_type": "basic",
                    "auth_value": "user:pass",
                }
            )
        assert result.success is True

    def test_http_request_api_key_auth(self):
        from animus.tools import _tool_http_request

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"ok"
        mock_response.status = 200
        mock_response.headers = {}

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _tool_http_request(
                {
                    "url": "https://api.example.com",
                    "auth_type": "api_key",
                    "auth_value": "my-key",
                }
            )
        assert result.success is True

    def test_http_request_http_error(self):
        from urllib.error import HTTPError

        from animus.tools import _tool_http_request

        error = HTTPError(
            "https://example.com", 404, "Not Found", {}, MagicMock(read=lambda: b"error body")
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = _tool_http_request({"url": "https://example.com"})
        assert result.success is False
        assert "404" in result.error


class TestCreateDefaultRegistry:
    """Tests for create_default_registry."""

    def test_with_security_config(self):
        from animus.tools import create_default_registry

        mock_config = MagicMock()
        mock_config.blocked_paths = []
        mock_config.allowed_paths = ["/tmp"]
        mock_config.command_enabled = True
        mock_config.command_blocklist = []
        mock_config.command_timeout_seconds = 30
        mock_config.write_roots = []

        registry = create_default_registry(security_config=mock_config)
        assert len(registry.list_tools()) >= 6


class TestMemoryTools:
    """Tests for create_memory_tools."""

    def test_search_memory_missing_query(self):
        from animus.tools import create_memory_tools

        mock_memory = MagicMock()
        tools = create_memory_tools(mock_memory)
        search_tool = [t for t in tools if t.name == "search_memory"][0]
        result = search_tool.handler({})
        assert result.success is False
        assert "Missing" in result.error

    def test_search_memory_no_results(self):
        from animus.tools import create_memory_tools

        mock_memory = MagicMock()
        mock_memory.recall.return_value = []
        tools = create_memory_tools(mock_memory)
        search_tool = [t for t in tools if t.name == "search_memory"][0]
        result = search_tool.handler({"query": "test"})
        assert result.success is True
        assert "No memories" in result.output

    def test_search_memory_with_results(self):
        from animus.tools import create_memory_tools

        mock_mem = MagicMock()
        mock_mem.content = "Hello world" * 50
        mock_mem.tags = ["tag1"]
        mock_memory = MagicMock()
        mock_memory.recall.return_value = [mock_mem]
        tools = create_memory_tools(mock_memory)
        search_tool = [t for t in tools if t.name == "search_memory"][0]
        result = search_tool.handler({"query": "hello", "tags": "tag1,tag2"})
        assert result.success is True

    def test_search_memory_exception(self):
        from animus.tools import create_memory_tools

        mock_memory = MagicMock()
        mock_memory.recall.side_effect = RuntimeError("db error")
        tools = create_memory_tools(mock_memory)
        search_tool = [t for t in tools if t.name == "search_memory"][0]
        result = search_tool.handler({"query": "test"})
        assert result.success is False

    def test_save_memory_missing_content(self):
        from animus.tools import create_memory_tools

        mock_memory = MagicMock()
        tools = create_memory_tools(mock_memory)
        save_tool = [t for t in tools if t.name == "save_memory"][0]
        result = save_tool.handler({})
        assert result.success is False

    def test_save_memory_success(self):
        from animus.tools import create_memory_tools

        mock_mem = MagicMock()
        mock_mem.id = "mem-123456789"
        mock_memory = MagicMock()
        mock_memory.remember.return_value = mock_mem
        tools = create_memory_tools(mock_memory)
        save_tool = [t for t in tools if t.name == "save_memory"][0]
        result = save_tool.handler(
            {"content": "Remember this", "tags": "tag1,tag2", "type": "semantic"}
        )
        assert result.success is True
        assert "mem-1234" in result.output

    def test_save_memory_exception(self):
        from animus.tools import create_memory_tools

        mock_memory = MagicMock()
        mock_memory.remember.side_effect = ValueError("bad type")
        tools = create_memory_tools(mock_memory)
        save_tool = [t for t in tools if t.name == "save_memory"][0]
        result = save_tool.handler({"content": "test"})
        assert result.success is False


# ===================================================================
# Proactive Engine
# ===================================================================


class TestProactiveEngine:
    """Tests for ProactiveEngine remaining gaps."""

    def _make_engine(self, tmp_path: Path, cognitive=None, executor=None):
        from animus.proactive import ProactiveEngine

        mock_memory = MagicMock()
        mock_memory.recall.return_value = []
        mock_memory.store.list_all.return_value = []
        return ProactiveEngine(
            data_dir=tmp_path,
            memory=mock_memory,
            cognitive=cognitive,
            executor=executor,
        )

    def test_load_nudges_from_file(self, tmp_path: Path):
        nudges_file = tmp_path / "nudges.json"
        nudges_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "nudge_type": "morning_brief",
                        "priority": "medium",
                        "title": "Test",
                        "content": "Content",
                        "created_at": "2025-01-01T00:00:00",
                        "expires_at": None,
                        "dismissed": False,
                        "acted_on": False,
                        "source_memory_ids": [],
                        "metadata": {},
                    }
                ]
            )
        )

        engine = self._make_engine(tmp_path)
        assert len(engine._nudges) == 1

    def test_emit_nudge_with_callback_error(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)

        def bad_cb(nudge):
            raise RuntimeError("callback error")

        engine.add_callback(bad_cb)
        nudge = Nudge(
            id="n1",
            nudge_type=NudgeType.PATTERN_INSIGHT,
            priority=NudgePriority.LOW,
            title="Test",
            content="Content",
            created_at=datetime.now(),
        )
        # Should not raise
        engine._emit_nudge(nudge)
        assert len(engine._nudges) == 1

    def test_emit_nudge_with_executor(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        mock_executor = MagicMock()
        engine = self._make_engine(tmp_path, executor=mock_executor)
        nudge = Nudge(
            id="n1",
            nudge_type=NudgeType.DEADLINE_WARNING,
            priority=NudgePriority.HIGH,
            title="Deadline",
            content="Due tomorrow",
            created_at=datetime.now(),
        )
        engine._emit_nudge(nudge)
        mock_executor.handle_nudge.assert_called_once_with(nudge)

    def test_emit_nudge_executor_error(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        mock_executor = MagicMock()
        mock_executor.handle_nudge.side_effect = RuntimeError("exec error")
        engine = self._make_engine(tmp_path, executor=mock_executor)
        nudge = Nudge(
            id="n1",
            nudge_type=NudgeType.DEADLINE_WARNING,
            priority=NudgePriority.HIGH,
            title="Deadline",
            content="Due tomorrow",
            created_at=datetime.now(),
        )
        # Should not raise
        engine._emit_nudge(nudge)

    def test_generate_morning_brief_with_data(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "Worked on feature X"
        mock_mem.created_at = datetime.now() - timedelta(hours=2)
        mock_mem.memory_type = MagicMock(value="episodic")
        mock_mem.subtype = "task"
        mock_mem.tags = ["deadline"]
        engine.memory.store.list_all.return_value = [mock_mem]

        nudge = engine.generate_morning_brief()
        assert nudge.nudge_type.value == "morning_brief"

    def test_generate_morning_brief_with_cognitive(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.return_value = "- Task 1\n- Task 2"
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "important task"
        mock_mem.created_at = datetime.now() - timedelta(hours=2)
        mock_mem.memory_type = MagicMock(value="episodic")
        mock_mem.subtype = "note"
        mock_mem.tags = []
        engine.memory.store.list_all.return_value = [mock_mem]

        nudge = engine.generate_morning_brief()
        assert "Task 1" in nudge.content

    def test_scan_deadlines_with_memories(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "urgent deadline tomorrow"
        mock_mem.created_at = datetime.now()
        mock_mem.tags = ["deadline"]
        engine.memory.recall.return_value = [mock_mem]

        nudges = engine.scan_deadlines()
        assert len(nudges) >= 1
        assert nudges[0].priority.value == "urgent"

    def test_scan_deadlines_already_nudged(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "deadline this week"
        mock_mem.created_at = datetime.now()
        mock_mem.tags = ["deadline"]
        engine.memory.recall.return_value = [mock_mem]

        # Add existing active nudge for this memory
        existing_nudge = Nudge(
            id="existing",
            nudge_type=NudgeType.DEADLINE_WARNING,
            priority=NudgePriority.MEDIUM,
            title="Existing",
            content="Already nudged",
            created_at=datetime.now(),
            source_memory_ids=["m1"],
        )
        engine._nudges.append(existing_nudge)

        nudges = engine.scan_deadlines()
        assert len(nudges) == 0

    def test_scan_deadlines_with_cognitive(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.return_value = "Summarized deadline"
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "soon deadline"
        mock_mem.created_at = datetime.now()
        mock_mem.tags = ["deadline"]
        engine.memory.recall.return_value = [mock_mem]

        nudges = engine.scan_deadlines()
        assert len(nudges) >= 1

    def test_prepare_meeting_context_no_memories(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        engine.memory.recall.return_value = []
        nudge = engine.prepare_meeting_context("Alice")
        assert "No prior context" in nudge.content

    def test_prepare_meeting_context_with_cognitive(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.return_value = "Meeting summary"
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "Discussed project X with Alice"
        mock_mem.created_at = datetime(2025, 1, 1)
        engine.memory.recall.return_value = [mock_mem]

        nudge = engine.prepare_meeting_context("Alice")
        assert "Meeting summary" in nudge.content

    def test_prepare_meeting_context_cognitive_failure(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.side_effect = RuntimeError("LLM down")
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "Old convo with Bob"
        mock_mem.created_at = datetime(2025, 1, 1)
        engine.memory.recall.return_value = [mock_mem]

        nudge = engine.prepare_meeting_context("Bob")
        assert "Bob" in nudge.content

    def test_scan_follow_ups(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "I need to follow up on the proposal"
        mock_mem.created_at = datetime.now() - timedelta(days=4)
        mock_mem.memory_type = MagicMock(value="episodic")
        mock_mem.tags = []
        engine.memory.store.list_all.return_value = [mock_mem]

        nudges = engine.scan_follow_ups()
        assert len(nudges) >= 1
        # 4 days old -> HIGH priority
        assert nudges[0].priority.value == "high"

    def test_scan_follow_ups_with_cognitive(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.return_value = "Follow up: send email"
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "remind me to check on this"
        mock_mem.created_at = datetime.now() - timedelta(days=1)
        mock_mem.memory_type = MagicMock(value="episodic")
        mock_mem.tags = []
        engine.memory.store.list_all.return_value = [mock_mem]

        nudges = engine.scan_follow_ups()
        assert len(nudges) >= 1

    def test_generate_context_nudge_no_related(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        engine.memory.recall.return_value = []
        result = engine.generate_context_nudge("random topic")
        assert result is None

    def test_generate_context_nudge_too_recent(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.created_at = datetime.now()  # Just now — too recent
        engine.memory.recall.return_value = [mock_mem]
        result = engine.generate_context_nudge("test")
        assert result is None

    def test_generate_context_nudge_success(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "Previous discussion about deployment"
        mock_mem.created_at = datetime.now() - timedelta(days=5)
        engine.memory.recall.return_value = [mock_mem]
        result = engine.generate_context_nudge("deployment strategy")
        assert result is not None
        assert result.nudge_type.value == "context_recall"

    def test_generate_context_nudge_with_cognitive(self, tmp_path: Path):
        mock_cognitive = MagicMock()
        mock_cognitive.think.return_value = "You discussed this before"
        engine = self._make_engine(tmp_path, cognitive=mock_cognitive)
        mock_mem = MagicMock()
        mock_mem.id = "m1"
        mock_mem.content = "Previous convo"
        mock_mem.created_at = datetime.now() - timedelta(days=3)
        engine.memory.recall.return_value = [mock_mem]
        result = engine.generate_context_nudge("same topic")
        assert result is not None

    def test_run_scheduled_checks(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        # All checks are due (last_run is None)
        results = engine.run_scheduled_checks()
        assert isinstance(results, list)

    def test_run_scheduled_checks_not_due(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        # Mark all checks as just run
        for check in engine._checks:
            check.last_run = datetime.now()
        results = engine.run_scheduled_checks()
        assert results == []

    def test_start_stop_background(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        engine.start_background(interval_seconds=1)
        assert engine.is_running is True
        # Start again — should warn but not crash
        engine.start_background(interval_seconds=1)
        engine.stop_background()
        assert engine.is_running is False

    def test_dismiss_nudge(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        nudge = Nudge(
            id="n1",
            nudge_type=NudgeType.PATTERN_INSIGHT,
            priority=NudgePriority.LOW,
            title="Test",
            content="Content",
            created_at=datetime.now(),
        )
        engine._nudges.append(nudge)
        assert engine.dismiss_nudge("n1") is True
        assert engine.dismiss_nudge("nonexistent") is False

    def test_act_on_nudge(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        nudge = Nudge(
            id="n1",
            nudge_type=NudgeType.FOLLOW_UP,
            priority=NudgePriority.MEDIUM,
            title="Follow up",
            content="Do the thing",
            created_at=datetime.now(),
        )
        engine._nudges.append(nudge)
        assert engine.act_on_nudge("n1") is True
        assert nudge.acted_on is True
        assert engine.act_on_nudge("nonexistent") is False

    def test_dismiss_all(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        for i in range(3):
            engine._nudges.append(
                Nudge(
                    id=f"n{i}",
                    nudge_type=NudgeType.PATTERN_INSIGHT,
                    priority=NudgePriority.LOW,
                    title=f"Nudge {i}",
                    content="Content",
                    created_at=datetime.now(),
                )
            )
        count = engine.dismiss_all()
        assert count == 3

    def test_get_nudges_by_type(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        engine._nudges.append(
            Nudge(
                id="n1",
                nudge_type=NudgeType.FOLLOW_UP,
                priority=NudgePriority.MEDIUM,
                title="Follow up",
                content="Content",
                created_at=datetime.now(),
            )
        )
        results = engine.get_nudges_by_type(NudgeType.FOLLOW_UP)
        assert len(results) == 1

    def test_get_nudges_by_priority(self, tmp_path: Path):
        from animus.proactive import Nudge, NudgePriority, NudgeType

        engine = self._make_engine(tmp_path)
        engine._nudges.append(
            Nudge(
                id="n1",
                nudge_type=NudgeType.DEADLINE_WARNING,
                priority=NudgePriority.URGENT,
                title="Urgent",
                content="Content",
                created_at=datetime.now(),
            )
        )
        engine._nudges.append(
            Nudge(
                id="n2",
                nudge_type=NudgeType.PATTERN_INSIGHT,
                priority=NudgePriority.LOW,
                title="Low",
                content="Content",
                created_at=datetime.now(),
            )
        )
        results = engine.get_nudges_by_priority(NudgePriority.HIGH)
        assert len(results) == 1  # Only urgent

    def test_get_statistics(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        stats = engine.get_statistics()
        assert "total_nudges" in stats
        assert "checks" in stats


# ===================================================================
# Security validation
# ===================================================================


class TestSecurityValidation:
    """Tests for path and command security validation."""

    def test_validate_path_glob_blocked(self):
        from animus.tools import WorkspaceToolPolicy, _validate_path

        policy = WorkspaceToolPolicy(allowed_paths=["/"], blocked_paths=["/etc/*"])
        valid, error = _validate_path("/etc/passwd", policy=policy)
        assert valid is False
        assert "blocked" in error.lower()

    def test_validate_path_not_allowed(self):
        from animus.tools import WorkspaceToolPolicy, _validate_path

        policy = WorkspaceToolPolicy(allowed_paths=["/tmp"])
        valid, error = _validate_path("/home/secret", policy=policy)
        assert valid is False
        assert "not in allowed" in error.lower()

    def test_validate_command_dangerous_patterns(self):
        from animus.tools import WorkspaceToolPolicy, _validate_command

        policy = WorkspaceToolPolicy(command_enabled=True)
        valid, error = _validate_command("echo $(whoami)", policy=policy)
        assert valid is False
        assert "disallowed" in error.lower()

    def test_validate_command_blocklist(self):
        from animus.tools import WorkspaceToolPolicy, _validate_command

        policy = WorkspaceToolPolicy(command_enabled=True, command_blocklist=[r"\brm\b"])
        valid, error = _validate_command("rm -rf /", policy=policy)
        assert valid is False
        assert "blocked" in error.lower()
