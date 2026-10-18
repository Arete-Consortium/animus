"""Shared test fixtures for Animus test suite."""

from __future__ import annotations

import gc
import resource
from pathlib import Path

import pytest

from animus.cognitive import CognitiveLayer, ModelConfig

# Exclude benchmark tests from normal collection (requires pytest-benchmark).
# Benchmark CI job runs them explicitly via: pytest tests/test_benchmarks.py --benchmark-only
collect_ignore = ["test_benchmarks.py"]

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


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Temp directory for test isolation."""
    data_dir = tmp_path / "animus_data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def mock_cognitive() -> CognitiveLayer:
    """CognitiveLayer backed by a deterministic mock model."""
    return CognitiveLayer(
        ModelConfig.mock(
            default_response="Mock response.",
            response_map={},
        )
    )


@pytest.fixture
def mock_cognitive_factory():
    """Factory for creating CognitiveLayer with custom responses."""

    def _make(
        default_response: str = "Mock response.",
        response_map: dict[str, str] | None = None,
    ) -> CognitiveLayer:
        return CognitiveLayer(
            ModelConfig.mock(
                default_response=default_response,
                response_map=response_map or {},
            )
        )

    return _make


@pytest.fixture(autouse=True)
def _isolate_core_home(monkeypatch, tmp_path):
    """Default-path tests must not read or write the operator's actual memory."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
