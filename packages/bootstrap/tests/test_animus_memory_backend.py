"""Tests for AnimusMemoryBackend — delegates to animus core's MemoryLayer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import animus.memory  # noqa: F401

    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False

pytestmark = pytest.mark.skipif(not _HAS_CORE, reason="animus-core not installed")

from animus_bootstrap.intelligence.memory_backends.animus_backend import (  # noqa: E402
    AnimusMemoryBackend,
)

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture()
def backend(tmp_path: Path) -> AnimusMemoryBackend:
    """Create a fresh AnimusMemoryBackend with isolated data_dir."""
    b = AnimusMemoryBackend(data_dir=tmp_path / "animus_memory")
    yield b
    b.close()


# ======================================================================
# Constructor
# ======================================================================


class TestConstructor:
    def test_creates_backend_with_valid_data_dir(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "mem"
        b = AnimusMemoryBackend(data_dir=data_dir)
        assert data_dir.exists()
        assert data_dir.is_dir()
        b.close()

    def test_creates_backend_with_string_path(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path / "mem_str")
        b = AnimusMemoryBackend(data_dir=data_dir)
        assert Path(data_dir).exists()
        b.close()

    def test_raises_runtime_error_when_core_not_installed(self, tmp_path: Path) -> None:
        with patch.dict("sys.modules", {"animus.memory": None, "animus": None}):
            with pytest.raises(RuntimeError, match="animus-core is not installed"):
                AnimusMemoryBackend(data_dir=tmp_path / "no_core")


# ======================================================================
# store()
# ======================================================================


class TestStore:
    def test_store_returns_string_id(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("episodic", "test content", {"key": "val"}))
        assert isinstance(mem_id, str)
        assert len(mem_id) > 0

    def test_store_episodic(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("episodic", "had a meeting", {}))
        assert isinstance(mem_id, str)

    def test_store_semantic(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("semantic", "python is a language", {}))
        assert isinstance(mem_id, str)

    def test_store_procedural(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("procedural", "to deploy, run make", {}))
        assert isinstance(mem_id, str)

    def test_store_with_invalid_memory_type_raises_value_error(
        self, backend: AnimusMemoryBackend
    ) -> None:
        with pytest.raises(ValueError, match="Invalid memory type"):
            asyncio.run(backend.store("bogus_type", "content", {}))

    def test_store_with_metadata_tags(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(
            backend.store(
                "semantic",
                "cats are great",
                {"tags": ["animals", "facts"], "source": "stated"},
            )
        )
        assert isinstance(mem_id, str)

    def test_store_with_confidence_and_subtype(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(
            backend.store(
                "semantic",
                "probably true",
                {"confidence": 0.7, "subtype": "inference"},
            )
        )
        assert isinstance(mem_id, str)


# ======================================================================
# search()
# ======================================================================


class TestSearch:
    def test_search_returns_list_of_dicts(self, backend: AnimusMemoryBackend) -> None:
        results = asyncio.run(backend.search("anything"))
        assert isinstance(results, list)

    def test_search_with_memory_type_all(self, backend: AnimusMemoryBackend) -> None:
        asyncio.run(backend.store("episodic", "event one", {}))
        asyncio.run(backend.store("semantic", "fact one", {}))
        results = asyncio.run(backend.search("one", memory_type="all"))
        assert isinstance(results, list)

    def test_search_with_specific_memory_type_filters(self, backend: AnimusMemoryBackend) -> None:
        asyncio.run(backend.store("episodic", "episodic event alpha", {}))
        asyncio.run(backend.store("semantic", "semantic fact beta", {}))
        results = asyncio.run(backend.search("alpha beta", memory_type="episodic", limit=10))
        assert isinstance(results, list)
        for r in results:
            assert r["type"] == "episodic"

    def test_search_result_dict_keys(self, backend: AnimusMemoryBackend) -> None:
        asyncio.run(backend.store("semantic", "searchable content", {}))
        results = asyncio.run(backend.search("searchable"))
        if results:
            expected_keys = {"id", "type", "content", "metadata", "created_at", "updated_at"}
            assert expected_keys == set(results[0].keys())

    def test_search_respects_limit(self, backend: AnimusMemoryBackend) -> None:
        for i in range(5):
            asyncio.run(backend.store("semantic", f"memory number {i}", {}))
        results = asyncio.run(backend.search("memory", limit=2))
        assert len(results) <= 2


# ======================================================================
# delete()
# ======================================================================


class TestDelete:
    def test_delete_returns_true_for_existing_memory(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("episodic", "to be deleted", {}))
        deleted = asyncio.run(backend.delete(mem_id))
        assert deleted is True

    def test_delete_nonexistent_id_does_not_raise(self, backend: AnimusMemoryBackend) -> None:
        # ChromaDB backend returns True even for missing IDs (silent no-op).
        # LocalMemoryStore returns False. Either way, no exception.
        result = asyncio.run(backend.delete("nonexistent-id-12345"))
        assert isinstance(result, bool)


# ======================================================================
# get_by_id()
# ======================================================================


class TestGetById:
    def test_get_by_id_returns_stored_memory(self, backend: AnimusMemoryBackend) -> None:
        mem_id = asyncio.run(backend.store("semantic", "lookup content", {}))

        result = asyncio.run(backend.get_by_id(mem_id))

        assert result is not None
        assert result["id"] == mem_id
        assert result["content"] == "lookup content"

    def test_get_by_id_returns_none_for_missing_memory(self, backend: AnimusMemoryBackend) -> None:
        assert asyncio.run(backend.get_by_id("missing-memory-id")) is None


# ======================================================================
# get_stats()
# ======================================================================


class TestGetStats:
    def test_get_stats_returns_dict_with_expected_keys(self, backend: AnimusMemoryBackend) -> None:
        stats = asyncio.run(backend.get_stats())
        assert isinstance(stats, dict)
        assert "total_memories" in stats
        assert "by_type" in stats
        assert "backend" in stats
        assert "data_dir" in stats

    def test_get_stats_counts_stored_memories(self, backend: AnimusMemoryBackend) -> None:
        asyncio.run(backend.store("episodic", "event", {}))
        asyncio.run(backend.store("semantic", "fact", {}))
        stats = asyncio.run(backend.get_stats())
        assert stats["total_memories"] >= 2
        assert stats["by_type"]["episodic"] >= 1
        assert stats["by_type"]["semantic"] >= 1

    def test_get_stats_backend_name(self, backend: AnimusMemoryBackend) -> None:
        stats = asyncio.run(backend.get_stats())
        assert stats["backend"] == "animus-core"


# ======================================================================
# close()
# ======================================================================


class TestClose:
    def test_close_does_not_raise(self, backend: AnimusMemoryBackend) -> None:
        backend.close()  # Should not raise

    def test_close_idempotent(self, backend: AnimusMemoryBackend) -> None:
        backend.close()
        backend.close()  # Double close should be fine


# ======================================================================
# Round-trip
# ======================================================================


class TestRoundTrip:
    def test_store_then_search_finds_content(self, backend: AnimusMemoryBackend) -> None:
        content = "unique findable content for round trip test"
        asyncio.run(backend.store("semantic", content, {}))
        results = asyncio.run(backend.search("unique findable content"))
        assert len(results) >= 1
        found = any(r["content"] == content for r in results)
        assert found, f"Stored content not found in search results: {results}"

    def test_store_delete_search_gone(self, backend: AnimusMemoryBackend) -> None:
        content = "ephemeral memory for deletion test"
        mem_id = asyncio.run(backend.store("episodic", content, {}))
        deleted = asyncio.run(backend.delete(mem_id))
        assert deleted is True
        results = asyncio.run(backend.search("ephemeral memory"))
        found_ids = [r["id"] for r in results]
        assert mem_id not in found_ids
