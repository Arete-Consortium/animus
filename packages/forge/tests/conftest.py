"""Pytest configuration and fixtures."""

import gc
import resource
import sys
from itertools import count
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Exclude benchmark tests from normal collection (requires pytest-benchmark).
# Benchmark CI job runs them explicitly via: pytest tests/test_benchmarks.py --benchmark-only
collect_ignore = [
    "test_benchmarks.py",
    "test_self_improve_ollama_integration.py",
    "test_evolution_loop_ollama.py",
]

# --- OOM protection ---
# Cap virtual memory at 32GB to prevent runaway tests from crashing the machine.
# Python over-allocates virtual memory so this needs headroom above actual RSS.
_MEMORY_LIMIT_GB = 32
try:
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    _limit = _MEMORY_LIMIT_GB * 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (_limit, hard))
except (OSError, ValueError):
    pass  # Some environments don't support RLIMIT_AS


_gc_cycles = count(1)


@pytest.fixture(autouse=True)
def _force_gc():
    """Reclaim test cycles without scanning all collected tests after every case.

    Collect young objects each time and the full heap every 25 tests. The
    32 GB process limit above remains in force for runaway allocations.
    """
    yield
    gc.collect(2 if next(_gc_cycles) % 25 == 0 else 0)


@pytest.fixture
def lease_test_records(backend):
    """Parents for low-level lease tests that use readable, fixed identifiers."""
    from animus_forge.missions.store import MissionLedger

    MissionLedger(backend)
    with backend.transaction():
        for mission_id in ("mission-1", "m"):
            backend.execute(
                "INSERT INTO missions (mission_id, repository, objective, created_at, updated_at) "
                "VALUES (?, 'test/repo', 'Lease fixture', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (mission_id,),
            )
        for task_id in ("task-1", "t1", "t2", "t3", "t-expired", "t-kill"):
            backend.execute(
                "INSERT INTO tasks (task_id, mission_id, citizen_role, description, created_at, "
                "updated_at) VALUES (?, ?, 'builder', 'Lease fixture', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (task_id, "mission-1" if task_id == "task-1" else "m"),
            )
