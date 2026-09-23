"""Pytest configuration and fixtures."""

import gc
import resource

import pytest

# --- OOM protection ---
_MEMORY_LIMIT_GB = 32
try:
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    _limit = _MEMORY_LIMIT_GB * 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (_limit, hard))
except (OSError, ValueError):
    pass


@pytest.fixture(autouse=True)
def _force_gc():
    """Force garbage collection after every test to prevent memory accumulation."""
    yield
    gc.collect()


@pytest.fixture(autouse=True)
def _isolate_animus_secrets(monkeypatch, tmp_path_factory):
    """Point ANIMUS_SECRETS_FILE at a non-existent path so
    ApiSection's secrets-file fallback cannot leak the developer's
    real ~/.local/share/animus/secrets.env into tests that
    construct ApiSection() without explicit isolation.

    Tests that exercise the secrets-file path explicitly set
    ANIMUS_SECRETS_FILE themselves and override this fixture's
    value via the monkeypatch context they create.
    """
    isolated = tmp_path_factory.mktemp("isolated") / "no-secrets.env"
    monkeypatch.setenv("ANIMUS_SECRETS_FILE", str(isolated))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch):
    """Keep dashboard and task-store globals from leaking between tests."""
    from animus_bootstrap.dashboard.app import app
    from animus_bootstrap.dashboard.routers.tools import clear_pending_approvals
    from animus_bootstrap.intelligence.proactive.checks import tasks

    original_state = app.state._state.copy()
    app.state.runtime = None
    monkeypatch.setattr(tasks, "_task_store", None)
    clear_pending_approvals()
    try:
        yield
    finally:
        clear_pending_approvals()
        app.state._state.clear()
        app.state._state.update(original_state)
