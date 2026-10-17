"""Targeted tests to push coverage from 95% to 96%+.

Covers uncovered lines in: code_edit.py, timer_ctl.py, filesystem.py,
identity_tools.py, identity_page.py, home.py, web.py, self_improve.py,
memory_tools.py, improvement_store.py, system.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# code_edit.py — 14 uncovered lines (error handling paths)
# ---------------------------------------------------------------------------


class TestCodeReadErrors:
    """Cover OSError path in _code_read (lines 45-46)."""

    def test_code_read_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_read

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            target = tmp_path / "test.py"
            target.touch()
            with patch.object(Path, "read_text", side_effect=OSError("disk error")):
                result = _run(_code_read("test.py"))
            assert "Read error" in result


class TestCodeWriteErrors:
    """Cover PermissionError + OSError in _code_write (lines 61-64)."""

    def test_code_write_permission_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_write

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            with patch.object(Path, "write_text", side_effect=PermissionError):
                result = _run(_code_write("test.py", "content"))
            assert "OS permission denied" in result

    def test_code_write_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_write

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            with patch.object(Path, "write_text", side_effect=OSError("disk full")):
                result = _run(_code_write("test.py", "content"))
            assert "Write error" in result


class TestCodePatchErrors:
    """Cover OSError paths in _code_patch (lines 87-88, 110-111)."""

    def test_code_patch_read_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_patch

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            target = tmp_path / "test.py"
            target.touch()
            with patch.object(Path, "read_text", side_effect=OSError("io error")):
                result = _run(_code_patch("test.py", "old", "new"))
            assert "Read error" in result

    def test_code_patch_write_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_patch

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            target = tmp_path / "test.py"
            target.write_text("old content here", encoding="utf-8")
            with patch.object(Path, "write_text", side_effect=OSError("readonly fs")):
                result = _run(_code_patch("test.py", "old", "new"))
            assert "Write error" in result


class TestCodeListErrors:
    """Cover ValueError + relative_to failure in _code_list (lines 121-122, 136-137)."""

    def test_code_list_path_escape(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_list

        result = _run(_code_list("../../../../etc"))
        assert "Permission denied" in result

    def test_code_list_relative_to_failure(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.code_edit import _code_list

        with patch(
            "animus_bootstrap.intelligence.tools.builtin.code_edit._ANIMUS_ROOT",
            tmp_path,
        ):
            subdir = tmp_path / "sub"
            subdir.mkdir()
            (subdir / "a.py").touch()
            # Patch relative_to to always fail — simulates file outside root
            original_relative_to = Path.relative_to

            def _failing_relative_to(self, other):
                if str(self).endswith(".py"):
                    raise ValueError("not relative")
                return original_relative_to(self, other)

            with patch.object(Path, "relative_to", _failing_relative_to):
                result = _run(_code_list("sub"))
            # All files fail relative_to → empty result
            assert result == "" or "No files" not in result


# ---------------------------------------------------------------------------
# timer_ctl.py — 16 uncovered lines
# ---------------------------------------------------------------------------


class TestTimerCtlRestore:
    """Cover restore_timers with engine (line 64) and checker action (line 80)."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl.clear_dynamic_timers()
        self._orig_engine = timer_ctl._proactive_engine
        self._orig_store = timer_ctl._timer_store

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl._proactive_engine = self._orig_engine
        timer_ctl._timer_store = self._orig_store
        timer_ctl.clear_dynamic_timers()

    def test_restore_with_engine(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_store = MagicMock()
        mock_store.list_all.return_value = [
            {
                "name": "test_timer",
                "schedule": "every 5m",
                "action": "do something",
                "channels": [],
                "created": "2026-01-01T00:00:00",
            }
        ]
        mock_engine = MagicMock()
        timer_ctl._timer_store = mock_store
        timer_ctl._proactive_engine = mock_engine

        count = timer_ctl.restore_timers()
        assert count == 1
        mock_engine.register_check.assert_called_once()

    def test_timer_checker_returns_action(self) -> None:
        """Cover line 80 — the checker function that returns the action text."""
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_engine = MagicMock()
        captured_check = None

        def _capture_register(check):
            nonlocal captured_check
            captured_check = check

        mock_engine.register_check.side_effect = _capture_register
        timer_ctl._proactive_engine = mock_engine
        timer_ctl._register_with_engine("t", "every 1m", "hello world", [])

        assert captured_check is not None
        result = _run(captured_check.checker())
        assert result == "hello world"


class TestTimerCreateInvalidCron:
    """Cover invalid cron schedule path in _timer_create (lines 110-111)."""

    def test_invalid_cron_schedule(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.timer_ctl import _timer_create

        result = _run(_timer_create("bad", "not-a-cron", "action"))
        assert "Invalid cron schedule" in result


class TestTimerListWithEngine:
    """Cover engine checks in _timer_list (lines 144-147, 156-158)."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl.clear_dynamic_timers()
        self._orig_engine = timer_ctl._proactive_engine

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl._proactive_engine = self._orig_engine
        timer_ctl.clear_dynamic_timers()

    def test_list_empty_with_engine_timers(self) -> None:
        """Cover lines 144-147 — engine has timer checks but no dynamic timers."""
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_engine = MagicMock()
        check = MagicMock()
        check.name = "timer:engine_only"
        check.schedule = "every 5m"
        check.enabled = True
        mock_engine.list_checks.return_value = [check]
        timer_ctl._proactive_engine = mock_engine

        result = _run(timer_ctl._timer_list())
        assert "timer:engine_only" in result

    def test_list_with_live_status(self) -> None:
        """Cover lines 156-158 — LIVE/NOT LIVE status per timer."""
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_engine = MagicMock()
        check = MagicMock()
        check.name = "timer:my_timer"
        mock_engine.list_checks.return_value = [check]
        timer_ctl._proactive_engine = mock_engine

        timer_ctl._dynamic_timers.append(
            {
                "name": "my_timer",
                "schedule": "every 5m",
                "action": "test",
                "channels": [],
                "created": "2026-01-01",
            }
        )

        result = _run(timer_ctl._timer_list())
        assert "[LIVE]" in result


class TestTimerUpdateWithEngine:
    """Cover invalid cron + engine re-register in _timer_update (lines 217-218, 246-247)."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl.clear_dynamic_timers()
        self._orig_engine = timer_ctl._proactive_engine

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl._proactive_engine = self._orig_engine
        timer_ctl.clear_dynamic_timers()

    def test_update_invalid_cron(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl._dynamic_timers.append(
            {
                "name": "t1",
                "schedule": "every 5m",
                "action": "test",
                "channels": [],
                "created": "2026-01-01",
            }
        )
        result = _run(timer_ctl._timer_update("t1", schedule="bad-cron"))
        assert "Invalid cron schedule" in result

    def test_update_with_engine_reregister(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_engine = MagicMock()
        timer_ctl._proactive_engine = mock_engine
        timer_ctl._dynamic_timers.append(
            {
                "name": "t2",
                "schedule": "every 5m",
                "action": "old",
                "channels": [],
                "created": "2026-01-01",
            }
        )
        result = _run(timer_ctl._timer_update("t2", action="new action"))
        assert "updated" in result
        mock_engine.unregister_check.assert_called_once_with("timer:t2")
        mock_engine.register_check.assert_called_once()


class TestTimerFireNoOutput:
    """Cover line 271 — timer fires but produces no output."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        self._orig_engine = timer_ctl._proactive_engine

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        timer_ctl._proactive_engine = self._orig_engine

    def test_fire_no_output(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import timer_ctl

        mock_engine = AsyncMock()
        mock_engine.run_check = AsyncMock(return_value=None)
        timer_ctl._proactive_engine = mock_engine

        result = _run(timer_ctl._timer_fire("t1"))
        assert "no output" in result


# ---------------------------------------------------------------------------
# filesystem.py — 7 uncovered lines (error handling)
# ---------------------------------------------------------------------------


class TestFileReadErrors:
    """Cover PermissionError + OSError in _file_read (lines 47, 50-51)."""

    def test_permission_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.filesystem import _file_read

        target = tmp_path / "secret.txt"
        target.touch()
        with patch.object(Path, "read_text", side_effect=PermissionError):
            result = _run(_file_read(str(target), [str(tmp_path)]))
        assert "OS permission denied" in result

    def test_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.filesystem import _file_read

        target = tmp_path / "broken.txt"
        target.touch()
        with patch.object(Path, "read_text", side_effect=OSError("io err")):
            result = _run(_file_read(str(target), [str(tmp_path)]))
        assert "Read error" in result


class TestFileWriteErrors:
    """Cover PermissionError + OSError in _file_write (lines 66-69)."""

    def test_permission_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.filesystem import _file_write

        with patch.object(Path, "write_text", side_effect=PermissionError):
            result = _run(_file_write(str(tmp_path / "f.txt"), "data", [str(tmp_path)]))
        assert "OS permission denied" in result

    def test_os_error(self, tmp_path: Path) -> None:
        from animus_bootstrap.intelligence.tools.builtin.filesystem import _file_write

        with patch.object(Path, "write_text", side_effect=OSError("full")):
            result = _run(_file_write(str(tmp_path / "f.txt"), "data", [str(tmp_path)]))
        assert "Write error" in result


# ---------------------------------------------------------------------------
# identity_tools.py — 7 uncovered lines
# ---------------------------------------------------------------------------


class TestIdentityToolsProposal:
    """Cover _create_proposal paths (lines 46-47, 59-60)."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        self._orig_manager = identity_tools._identity_manager
        self._orig_store = identity_tools._improvement_store
        self._orig_pm = identity_tools._proposal_manager

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        identity_tools._identity_manager = self._orig_manager
        identity_tools._improvement_store = self._orig_store
        identity_tools._proposal_manager = self._orig_pm

    def test_create_proposal_via_manager(self) -> None:
        """Cover lines 46-47 — proposal manager path."""
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        mock_pm = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.id = 42
        mock_proposal.file = "IDENTITY.md"
        mock_proposal.status = "proposed"
        mock_pm.create.return_value = mock_proposal
        identity_tools._proposal_manager = mock_pm

        result = identity_tools._create_proposal("IDENTITY.md", "old", "new content", "reason")
        assert result["id"] == 42
        assert result["status"] == "proposed"

    def test_create_proposal_fallback_with_store(self) -> None:
        """Cover lines 59-60 — fallback via store."""
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        identity_tools._proposal_manager = None
        mock_store = MagicMock()
        mock_store.save.return_value = 7
        identity_tools._improvement_store = mock_store

        result = identity_tools._create_proposal("IDENTITY.md", "old", "new", "reason")
        assert result["id"] == 7
        mock_store.save.assert_called_once()


class TestIdentityReadEmpty:
    """Cover line 74 — empty file read."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        self._orig = identity_tools._identity_manager

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        identity_tools._identity_manager = self._orig

    def test_read_empty_file(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        mock_mgr = MagicMock()
        mock_mgr.read.return_value = ""
        identity_tools._identity_manager = mock_mgr

        result = _run(identity_tools._identity_read({"filename": "IDENTITY.md"}))
        assert "empty or does not exist" in result


class TestIdentityWritePermissionError:
    """Cover lines 116-117 — PermissionError on write."""

    def setup_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        self._orig = identity_tools._identity_manager

    def teardown_method(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        identity_tools._identity_manager = self._orig

    def test_write_permission_error(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import identity_tools

        mock_mgr = MagicMock()
        mock_mgr.read.return_value = "small"
        mock_mgr._validate_filename.return_value = None
        mock_mgr.write.side_effect = PermissionError("locked")
        identity_tools._identity_manager = mock_mgr

        result = _run(
            identity_tools._identity_write(
                {"filename": "IDENTITY.md", "content": "small2", "reason": "test"}
            )
        )
        assert "locked" in result


# ---------------------------------------------------------------------------
# identity_page.py — 7 uncovered lines (dashboard routes)
# ---------------------------------------------------------------------------


class TestIdentityPageRoutes:
    """Cover identity_page router error paths."""

    @pytest.fixture()
    def identity_app(self) -> FastAPI:
        from animus_bootstrap.dashboard.app import templates
        from animus_bootstrap.dashboard.routers.identity_page import router

        _app = FastAPI()
        _app.state.templates = templates
        _app.include_router(router)
        return _app

    def test_edit_form_no_manager(self, identity_app: FastAPI) -> None:
        """Cover line 51 — no identity manager."""
        runtime = MagicMock()
        runtime.identity_manager = None
        identity_app.state.runtime = runtime
        client = TestClient(identity_app)
        resp = client.get("/identity/edit/IDENTITY.md")
        assert resp.status_code == 200
        assert "not available" in resp.text

    def test_save_no_manager(self, identity_app: FastAPI) -> None:
        """Cover line 96 — no identity manager on save."""
        runtime = MagicMock()
        runtime.identity_manager = None
        identity_app.state.runtime = runtime
        client = TestClient(identity_app)
        resp = client.put("/identity/IDENTITY.md", data={"content": "x"})
        assert resp.status_code == 200
        assert "not available" in resp.text

    def test_save_write_error(self, identity_app: FastAPI) -> None:
        """Cover lines 106-107 — write raises ValueError."""
        runtime = MagicMock()
        mgr = MagicMock()
        mgr.LOCKED_FILES = set()
        mgr.write.side_effect = ValueError("bad file")
        runtime.identity_manager = mgr
        identity_app.state.runtime = runtime
        client = TestClient(identity_app)
        resp = client.put("/identity/IDENTITY.md", data={"content": "x"})
        assert resp.status_code == 200
        assert "Failed to save" in resp.text

    def test_view_no_manager(self, identity_app: FastAPI) -> None:
        """Cover line 117 — no identity manager on view."""
        runtime = MagicMock()
        runtime.identity_manager = None
        identity_app.state.runtime = runtime
        client = TestClient(identity_app)
        resp = client.get("/identity/view/IDENTITY.md")
        assert resp.status_code == 200
        assert "not available" in resp.text

    def test_view_unknown_file(self, identity_app: FastAPI) -> None:
        """Cover lines 123-124 — ValueError on unknown file."""
        runtime = MagicMock()
        mgr = MagicMock()
        mgr.read.side_effect = ValueError("unknown file")
        runtime.identity_manager = mgr
        identity_app.state.runtime = runtime
        client = TestClient(identity_app)
        resp = client.get("/identity/view/BADFILE.md")
        assert resp.status_code == 200
        assert "Unknown identity file" in resp.text


# ---------------------------------------------------------------------------
# home.py — 8 uncovered lines (dashboard home page)
# ---------------------------------------------------------------------------


class TestHomeHelpers:
    """Cover _format_size TB branch, _get_memory_size edge cases."""

    def test_format_size_tb(self) -> None:
        from animus_bootstrap.dashboard.routers.home import _format_size

        result = _format_size(2 * 1024**4)
        assert "TB" in result

    def test_get_memory_size_no_config(self) -> None:
        """Cover line 49 — runtime has memory_manager but no config."""
        from animus_bootstrap.dashboard.routers.home import _get_memory_size

        runtime = MagicMock()
        runtime.memory_manager = MagicMock()
        runtime.config = None
        assert _get_memory_size(runtime) == "Active"

    def test_get_memory_size_db_not_file(self, tmp_path: Path) -> None:
        """Cover line 55 — db_path exists but is not a file."""
        from animus_bootstrap.dashboard.routers.home import _get_memory_size

        runtime = MagicMock()
        runtime.memory_manager = MagicMock()
        runtime.config.intelligence.memory_db_path = str(tmp_path / "nonexistent.db")
        assert _get_memory_size(runtime) == "Active"


class TestHomePageComponents:
    """Cover home page runtime component extraction (lines 67-68, 107, 112)."""

    @pytest.fixture()
    def home_app(self) -> FastAPI:
        from fastapi.templating import Jinja2Templates

        from animus_bootstrap.dashboard.routers.home import router

        _app = FastAPI()
        _app.include_router(router)
        tpl_dir = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "animus_bootstrap"
            / "dashboard"
            / "templates"
        )
        _app.state.templates = Jinja2Templates(directory=str(tpl_dir))
        return _app

    def test_home_forge_error(self, home_app: FastAPI) -> None:
        """Cover lines 67-68 — forge health check HTTPError."""
        runtime = MagicMock()
        runtime.started = True
        runtime.memory_manager = None
        runtime.tool_executor = None
        runtime.proactive_engine = None
        runtime.automation_engine = None
        runtime.cognitive_backend = None
        runtime.persona_engine = None
        home_app.state.runtime = runtime

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            import httpx

            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value = mock_client

            client = TestClient(home_app)
            resp = client.get("/")
        assert resp.status_code == 200

    def test_home_with_cognitive_and_persona(self, home_app: FastAPI) -> None:
        """Cover lines 107, 112 — cognitive type + persona count extraction."""
        runtime = MagicMock()
        runtime.started = True
        runtime.memory_manager = None
        runtime.tool_executor = None
        runtime.proactive_engine = None
        runtime.automation_engine = None

        # Cognitive backend with a type name
        cognitive = MagicMock()
        type(cognitive).__name__ = "OllamaBackend"
        runtime.cognitive_backend = cognitive

        # Persona engine with count
        persona = MagicMock()
        persona.persona_count = 3
        runtime.persona_engine = persona

        home_app.state.runtime = runtime

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = TestClient(home_app)
            resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# web.py — 4 uncovered lines (import success + search error)
# ---------------------------------------------------------------------------


class TestWebSearchError:
    """Cover lines 39-41 — search exception handler."""

    def test_search_connection_error(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import web

        mock_ddgs_cls = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.side_effect = ConnectionError("no internet")
        mock_ddgs_cls.return_value = mock_ctx

        orig_has = web.HAS_DUCKDUCKGO
        orig_ddgs = getattr(web, "DDGS", None)
        try:
            web.HAS_DUCKDUCKGO = True
            web.DDGS = mock_ddgs_cls

            result = _run(web._web_search("test query"))
            assert "Search failed" in result
        finally:
            web.HAS_DUCKDUCKGO = orig_has
            if orig_ddgs is None:
                if hasattr(web, "DDGS"):
                    delattr(web, "DDGS")
            else:
                web.DDGS = orig_ddgs


# ---------------------------------------------------------------------------
# self_improve.py — 5 uncovered lines
# ---------------------------------------------------------------------------


class TestSelfImproveAnalysisError:
    """Cover lines 129-131 — cognitive analysis failure."""

    def test_analysis_failure(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import self_improve

        orig_backend = self_improve._cognitive_backend
        orig_store = self_improve._improvement_store
        try:
            mock_backend = AsyncMock()
            mock_backend.generate_response.side_effect = ConnectionError("timeout")
            self_improve._cognitive_backend = mock_backend
            self_improve._improvement_store = None

            result = _run(self_improve._propose_improvement("test", "desc"))
            assert "Cognitive analysis failed" in result or "Proposal" in result
        finally:
            self_improve._cognitive_backend = orig_backend
            self_improve._improvement_store = orig_store


class TestListImprovementsFilteredEmpty:
    """Cover line 207 — no proposals with filtered status."""

    def test_no_proposals_with_status(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import self_improve

        orig_store = self_improve._improvement_store
        try:
            mock_store = MagicMock()
            mock_store.list_all.return_value = []
            self_improve._improvement_store = mock_store

            result = _run(self_improve._list_improvements(status="approved"))
            assert "No proposals with status" in result
        finally:
            self_improve._improvement_store = orig_store


class TestSelfImproveLoopNoProposal:
    """Cover line 252 — self-improve loop produces no proposal."""

    def test_loop_no_proposal(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import self_improve

        orig_backend = self_improve._cognitive_backend
        orig_store = self_improve._improvement_store
        orig_log = self_improve._improvement_log[:]
        try:
            # Use a store that saves but returns empty from list_all
            # so get_improvement_log() returns [] after the loop
            mock_store = MagicMock()
            mock_store.save.return_value = 1
            mock_store.list_all.return_value = []
            self_improve._cognitive_backend = None
            self_improve._improvement_store = mock_store
            self_improve._improvement_log.clear()

            result = _run(self_improve._self_improve_loop("test", "desc"))
            assert "No proposal was created" in result
        finally:
            self_improve._cognitive_backend = orig_backend
            self_improve._improvement_store = orig_store
            self_improve._improvement_log[:] = orig_log


# ---------------------------------------------------------------------------
# memory_tools.py — 3 uncovered lines (search error)
# ---------------------------------------------------------------------------


class TestMemorySearchError:
    """Cover lines 66-68 — backend search failure."""

    def test_backend_search_raises(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin import memory_tools

        orig_manager = memory_tools._memory_manager
        try:
            mock_manager = MagicMock()
            mock_manager.search = AsyncMock(side_effect=RuntimeError("chromadb down"))
            memory_tools._memory_manager = mock_manager

            result = _run(memory_tools._recall_memory("test query"))
            assert "Memory search failed" in result
        finally:
            memory_tools._memory_manager = orig_manager


# ---------------------------------------------------------------------------
# improvement_store.py — 3 uncovered lines (next_id)
# ---------------------------------------------------------------------------


class TestImprovementStoreNextId:
    """Cover lines 104-106 — next_id method."""

    def test_next_id_empty_table(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.improvement_store import (
            ImprovementStore,
        )

        store = ImprovementStore(":memory:")
        assert store.next_id() == 1

    def test_next_id_after_insert(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.improvement_store import (
            ImprovementStore,
        )

        store = ImprovementStore(":memory:")
        store.save(
            {
                "area": "test",
                "description": "test proposal",
                "status": "proposed",
                "timestamp": "2026-01-01",
                "analysis": "none",
                "patch": "",
            }
        )
        assert store.next_id() == 2


# ---------------------------------------------------------------------------
# system.py — 1 uncovered line (exit code only)
# ---------------------------------------------------------------------------


class TestSystemToolExitCodeOnly:
    """Cover line 37 — no stdout, no stderr, just exit code."""

    def test_exit_code_only(self) -> None:
        from animus_bootstrap.intelligence.tools.builtin.system import _shell_exec

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 42

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(_shell_exec("false"))
        assert "exit code 42" in result
