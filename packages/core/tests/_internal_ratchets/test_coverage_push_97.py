"""Coverage push — ChromaMemoryStore, MemoryLayer edges, cognitive providers, bootstrap loop.

Targets ~125 missed lines across memory.py, cognitive.py, bootstrap_loop.py to push
Core coverage from 95% to 97%.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from animus.memory import (
    ChromaMemoryStore,
    Memory,
    MemoryLayer,
    MemoryType,
)

# ---------------------------------------------------------------------------
# Helpers — Mock ChromaDB
# ---------------------------------------------------------------------------


class MockChromaCollection:
    """In-memory chromadb collection mock."""

    def __init__(self):
        self._docs: dict[str, dict] = {}

    def count(self) -> int:
        return len(self._docs)

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]):
        for i, doc_id in enumerate(ids):
            self._docs[doc_id] = {
                "id": doc_id,
                "document": documents[i],
                "metadata": metadatas[i],
            }

    def get(self, include: list[str] | None = None):
        ids = list(self._docs.keys())
        metadatas = [d["metadata"] for d in self._docs.values()]
        documents = [d["document"] for d in self._docs.values()]
        return {"ids": ids, "metadatas": metadatas, "documents": documents}

    def query(
        self,
        query_texts: list[str],
        n_results: int = 10,
        where: dict | None = None,
        include: list[str] | None = None,
    ):
        # Return all docs wrapped in the nested list structure chromadb uses
        ids = list(self._docs.keys())[:n_results]
        metadatas = [self._docs[i]["metadata"] for i in ids]
        documents = [self._docs[i]["document"] for i in ids]
        distances = [0.1 * (j + 1) for j in range(len(ids))]
        return {
            "ids": [ids],
            "metadatas": [metadatas],
            "documents": [documents],
            "distances": [distances],
        }

    def delete(self, ids: list[str]):
        for doc_id in ids:
            self._docs.pop(doc_id, None)


class MockChromaClient:
    def __init__(self, path: str | None = None, settings: object | None = None):
        self._collections: dict[str, MockChromaCollection] = {}

    def get_or_create_collection(self, name: str, metadata: dict | None = None):
        if name not in self._collections:
            self._collections[name] = MockChromaCollection()
        return self._collections[name]


def _make_mock_chromadb():
    """Return a mock chromadb module with PersistentClient."""
    mod = MagicMock()
    mod.PersistentClient = MockChromaClient
    mod.HttpClient.side_effect = Exception("no chromadb server")
    mod.Settings = MagicMock()
    return mod


def _make_memory(
    tags: list[str] | None = None,
    memory_type: MemoryType = MemoryType.SEMANTIC,
    subtype: str | None = None,
    content: str = "test content",
    confidence: float = 1.0,
    source: str = "stated",
    days_old: int = 0,
) -> Memory:
    ts = datetime.now() - timedelta(days=days_old)
    return Memory(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        content=content,
        memory_type=memory_type,
        created_at=ts,
        updated_at=ts,
        metadata={},
        tags=tags or [],
        source=source,
        confidence=confidence,
        subtype=subtype,
    )


# ===================================================================
# 1. ChromaMemoryStore Tests
# ===================================================================


class TestChromaMemoryStorePrewarm:
    """ChromaMemoryStore.prewarm() — lines 436-451."""

    def test_prewarm_success(self):
        mock_st = MagicMock()
        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            result = ChromaMemoryStore.prewarm()
        assert result is True
        mock_st.SentenceTransformer.assert_called_once_with("all-MiniLM-L6-v2")

    def test_prewarm_import_error(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            result = ChromaMemoryStore.prewarm()
        assert result is False

    def test_prewarm_generic_error(self):
        mock_st = MagicMock()
        mock_st.SentenceTransformer.side_effect = RuntimeError("model fail")
        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            result = ChromaMemoryStore.prewarm()
        assert result is False


class TestChromaMemoryStoreInit:
    """ChromaMemoryStore.__init__ — lines 453-479."""

    def test_init_success(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        assert store.collection is not None
        assert store._memories == {}

    def test_init_import_error(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": None}):
            with pytest.raises(ImportError, match="ChromaDB not installed"):
                ChromaMemoryStore(tmp_data_dir)

    def test_init_generic_error(self, tmp_data_dir):
        bad_mod = MagicMock()
        bad_mod.HttpClient.side_effect = Exception("no server")
        bad_mod.PersistentClient.side_effect = RuntimeError("db corrupt")
        with patch.dict(sys.modules, {"chromadb": bad_mod}):
            with pytest.raises(RuntimeError, match="db corrupt"):
                ChromaMemoryStore(tmp_data_dir)


class TestChromaLoadMetadata:
    """ChromaMemoryStore._load_metadata — lines 481-526."""

    def _make_store(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            return ChromaMemoryStore(tmp_data_dir)

    def test_load_metadata_basic(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        # Seed collection directly
        now = datetime.now().isoformat()
        store.collection.upsert(
            ids=["m1"],
            documents=["hello world"],
            metadatas=[
                {
                    "memory_type": "semantic",
                    "created_at": now,
                    "updated_at": now,
                    "tags": '["tag1", "tag2"]',
                    "source": "stated",
                    "confidence": 0.9,
                }
            ],
        )
        store._memories.clear()
        store._load_metadata()
        assert "m1" in store._memories
        assert store._memories["m1"].tags == ["tag1", "tag2"]
        assert store._memories["m1"].confidence == 0.9

    def test_load_metadata_json_decode_error(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        now = datetime.now().isoformat()
        store.collection.upsert(
            ids=["m2"],
            documents=["bad tags"],
            metadatas=[
                {
                    "memory_type": "semantic",
                    "created_at": now,
                    "updated_at": now,
                    "tags": "NOT_VALID_JSON{{{",
                    "source": "stated",
                    "confidence": 1.0,
                }
            ],
        )
        store._memories.clear()
        store._load_metadata()
        assert store._memories["m2"].tags == []

    def test_load_metadata_exception(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        store.collection.get = MagicMock(side_effect=RuntimeError("db error"))
        store._memories.clear()
        store._load_metadata()
        assert store._memories == {}


class TestChromaBuildMetadata:
    """ChromaMemoryStore._build_chroma_metadata — lines 528-543."""

    def _make_store(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            return ChromaMemoryStore(tmp_data_dir)

    def test_build_metadata_with_subtype(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(subtype="conversation")
        meta = store._build_chroma_metadata(mem)
        assert meta["subtype"] == "conversation"

    def test_build_metadata_without_subtype(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(subtype=None)
        meta = store._build_chroma_metadata(mem)
        assert "subtype" not in meta

    def test_build_metadata_custom_fields(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory()
        mem.metadata = {"custom_key": 42, "another": True}
        meta = store._build_chroma_metadata(mem)
        assert meta["custom_key"] == "42"
        assert meta["another"] == "True"


class TestChromaStoreUpdateRetrieve:
    """ChromaMemoryStore store/update/retrieve — lines 545-565."""

    def _make_store(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            return ChromaMemoryStore(tmp_data_dir)

    def test_store(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="stored item")
        store.store(mem)
        assert mem.id in store._memories
        assert store.collection.count() == 1

    def test_update_exists(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="original")
        store.store(mem)
        mem.content = "updated"
        assert store.update(mem) is True

    def test_update_not_exists(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="ghost")
        assert store.update(mem) is False

    def test_retrieve(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="findme")
        store.store(mem)
        found = store.retrieve(mem.id)
        assert found is not None
        assert found.content == "findme"

    def test_retrieve_missing(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        assert store.retrieve("nonexistent") is None


class TestChromaSearch:
    """ChromaMemoryStore.search — lines 567-643."""

    def _make_store_with_data(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        mem1 = _make_memory(content="python programming", tags=["python", "code"])
        mem2 = _make_memory(content="rust systems", tags=["rust", "code"])
        mem3 = _make_memory(content="cooking recipes", tags=["food"])
        store.store(mem1)
        store.store(mem2)
        store.store(mem3)
        return store

    def test_search_no_filters(self, tmp_data_dir):
        store = self._make_store_with_data(tmp_data_dir)
        results = store.search("programming")
        assert len(results) > 0

    def test_search_memory_type_filter(self, tmp_data_dir):
        store = self._make_store_with_data(tmp_data_dir)
        results = store.search("test", memory_type=MemoryType.SEMANTIC)
        assert isinstance(results, list)

    def test_search_multiple_filters(self, tmp_data_dir):
        store = self._make_store_with_data(tmp_data_dir)
        results = store.search(
            "test",
            memory_type=MemoryType.SEMANTIC,
            source="stated",
            min_confidence=0.5,
        )
        assert isinstance(results, list)

    def test_search_tag_filter(self, tmp_data_dir):
        store = self._make_store_with_data(tmp_data_dir)
        results = store.search("code", tags=["python"])
        # Only memories with "python" tag should survive
        for r in results:
            assert "python" in r.tags

    def test_search_tag_filter_excludes(self, tmp_data_dir):
        store = self._make_store_with_data(tmp_data_dir)
        results = store.search("test", tags=["nonexistent_tag"])
        assert len(results) == 0

    def test_search_reconstruct_from_results(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        mem = _make_memory(content="will be forgotten")
        store.store(mem)
        # Remove from cache but keep in collection
        del store._memories[mem.id]
        results = store.search("forgotten")
        assert len(results) > 0
        assert results[0].content == "will be forgotten"

    def test_search_json_decode_in_results(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        # Directly seed collection with bad tags JSON
        now = datetime.now().isoformat()
        store.collection.upsert(
            ids=["bad-tags"],
            documents=["bad tags mem"],
            metadatas=[
                {
                    "memory_type": "semantic",
                    "created_at": now,
                    "updated_at": now,
                    "tags": "{{{INVALID",
                    "source": "stated",
                    "confidence": 1.0,
                }
            ],
        )
        # Clear cache so reconstruct path is taken
        store._memories.pop("bad-tags", None)
        results = store.search("bad tags")
        found = [r for r in results if r.id == "bad-tags"]
        assert len(found) == 1
        assert found[0].tags == []

    def test_search_exception(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        store.collection.query = MagicMock(side_effect=RuntimeError("query fail"))
        results = store.search("anything")
        assert results == []

    def test_search_limit_respected(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            store = ChromaMemoryStore(tmp_data_dir)
        for i in range(10):
            store.store(_make_memory(content=f"item {i}", days_old=i))
        results = store.search("item", limit=3)
        assert len(results) <= 3


class TestChromaDelete:
    """ChromaMemoryStore.delete — lines 645-654."""

    def _make_store(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            return ChromaMemoryStore(tmp_data_dir)

    def test_delete_success(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="delete me")
        store.store(mem)
        result = store.delete(mem.id)
        assert result is True
        assert mem.id not in store._memories

    def test_delete_not_in_cache(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        mem = _make_memory(content="only in collection")
        store.store(mem)
        del store._memories[mem.id]
        result = store.delete(mem.id)
        assert result is True

    def test_delete_exception(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        store.collection.delete = MagicMock(side_effect=RuntimeError("delete fail"))
        result = store.delete("some-id")
        assert result is False


class TestChromaListAllGetTags:
    """ChromaMemoryStore list_all / get_all_tags — lines 656-667."""

    def _make_store(self, tmp_data_dir):
        with patch.dict(sys.modules, {"chromadb": _make_mock_chromadb()}):
            return ChromaMemoryStore(tmp_data_dir)

    def test_list_all_no_filter(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        store.store(_make_memory(content="a"))
        store.store(_make_memory(content="b"))
        assert len(store.list_all()) == 2

    def test_list_all_with_type(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        store.store(_make_memory(content="sem", memory_type=MemoryType.SEMANTIC))
        store.store(_make_memory(content="epi", memory_type=MemoryType.EPISODIC))
        semantic = store.list_all(memory_type=MemoryType.SEMANTIC)
        assert all(m.memory_type == MemoryType.SEMANTIC for m in semantic)

    def test_get_all_tags(self, tmp_data_dir):
        store = self._make_store(tmp_data_dir)
        store.store(_make_memory(content="a", tags=["python", "code"]))
        store.store(_make_memory(content="b", tags=["python", "rust"]))
        tags = store.get_all_tags()
        assert tags["python"] == 2
        assert tags["code"] == 1
        assert tags["rust"] == 1


# ===================================================================
# 2. MemoryLayer Edge Cases
# ===================================================================


class TestMemoryLayerExport:
    """MemoryLayer.export_memories — lines 938-954."""

    def test_export_jsonl(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("fact one", tags=["a"])
        ml.remember("fact two", tags=["b"])
        output = ml.export_memories(format="jsonl")
        lines = [x for x in output.strip().split("\n") if x.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "content" in parsed

    def test_export_json(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("fact one")
        output = ml.export_memories(format="json")
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_export_empty(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        jsonl_out = ml.export_memories(format="jsonl")
        assert jsonl_out == ""
        json_out = ml.export_memories(format="json")
        assert json.loads(json_out) == []


class TestMemoryLayerImport:
    """MemoryLayer.import_memories — lines 956-990."""

    def test_import_jsonl(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("original")
        exported = ml.export_memories(format="jsonl")
        # Import into fresh layer
        ml2 = MemoryLayer(data_dir=tmp_data_dir / "import_target", backend="json")
        count = ml2.import_memories(exported, format="jsonl")
        assert count == 1

    def test_import_with_entity_memory(self, tmp_data_dir):
        mock_em = MagicMock()
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json", entity_memory=mock_em)
        data = json.dumps([Memory.create("entity test", tags=["test"]).to_dict()])
        count = ml.import_memories(data, format="json")
        assert count == 1
        mock_em.extract_and_link.assert_called_once()

    def test_import_entity_link_failure(self, tmp_data_dir):
        mock_em = MagicMock()
        mock_em.extract_and_link.side_effect = RuntimeError("link fail")
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json", entity_memory=mock_em)
        data = json.dumps([Memory.create("entity fail test").to_dict()])
        count = ml.import_memories(data, format="json")
        assert count == 1  # import continues despite link failure


class TestMemoryLayerBackup:
    """MemoryLayer.backup — lines 992-1004."""

    def test_backup_adds_zip_suffix(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("backup test")
        backup_path = tmp_data_dir / "backups" / "test_backup"
        ml.backup(backup_path)
        assert (backup_path.with_suffix(".zip")).exists()

    def test_backup_keeps_zip_suffix(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("backup test")
        backup_path = tmp_data_dir / "backups" / "test_backup.zip"
        ml.backup(backup_path)
        assert backup_path.exists()
        # Verify no double .zip.zip
        assert not (backup_path.with_suffix(".zip.zip")).exists()


class TestMemoryLayerStatistics:
    """MemoryLayer.get_statistics — lines 1006-1031."""

    def test_statistics_with_subtypes(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("a", subtype="fact", tags=["x"])
        ml.remember("b", subtype="preference", tags=["y"])
        stats = ml.get_statistics()
        assert stats["total"] == 2
        assert "fact" in stats["by_subtype"]
        assert "preference" in stats["by_subtype"]

    def test_statistics_empty(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        stats = ml.get_statistics()
        assert stats["total"] == 0
        assert stats["avg_confidence"] == 0

    def test_statistics_top_tags(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("a", tags=["python", "code"])
        ml.remember("b", tags=["python", "rust"])
        ml.remember("c", tags=["python"])
        stats = ml.get_statistics()
        assert stats["top_tags"][0][0] == "python"
        assert stats["top_tags"][0][1] == 3


class TestMemoryLayerConsolidate:
    """MemoryLayer.consolidate — lines 1033-1112."""

    def _add_old_episodic(self, ml, content, tags, days_old=100):
        mem = Memory.create(
            content=content,
            memory_type=MemoryType.EPISODIC,
            tags=tags,
        )
        mem.created_at = datetime.now() - timedelta(days=days_old)
        mem.updated_at = mem.created_at
        ml.store.store(mem)
        return mem

    def test_consolidate_basic(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        for i in range(4):
            self._add_old_episodic(ml, f"event {i}", ["work"], days_old=100 + i)
        count = ml.consolidate(max_age_days=90, min_group_size=3)
        assert count == 4

    def test_consolidate_min_group_size(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        self._add_old_episodic(ml, "event 1", ["work"], days_old=100)
        self._add_old_episodic(ml, "event 2", ["work"], days_old=101)
        count = ml.consolidate(max_age_days=90, min_group_size=3)
        assert count == 0

    def test_consolidate_no_old_memories(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("recent", memory_type=MemoryType.EPISODIC, tags=["work"])
        count = ml.consolidate(max_age_days=90)
        assert count == 0

    def test_consolidate_untagged_group(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        for i in range(3):
            self._add_old_episodic(ml, f"untagged {i}", [], days_old=100 + i)
        count = ml.consolidate(max_age_days=90, min_group_size=3)
        assert count == 3

    def test_consolidate_entity_cleanup(self, tmp_data_dir):
        mock_em = MagicMock()
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json", entity_memory=mock_em)
        for i in range(3):
            self._add_old_episodic(ml, f"entity event {i}", ["ent"], days_old=100 + i)
        ml.consolidate(max_age_days=90, min_group_size=3)
        assert mock_em.remove_interactions_for_memory.call_count == 3

    def test_consolidate_entity_cleanup_error(self, tmp_data_dir):
        mock_em = MagicMock()
        mock_em.remove_interactions_for_memory.side_effect = RuntimeError("cleanup fail")
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json", entity_memory=mock_em)
        for i in range(3):
            self._add_old_episodic(ml, f"error event {i}", ["err"], days_old=100 + i)
        count = ml.consolidate(max_age_days=90, min_group_size=3)
        assert count == 3  # continues despite cleanup errors


class TestMemoryLayerExportCSV:
    """MemoryLayer.export_memories_csv — lines 1114-1158."""

    def test_csv_export_basic(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("csv test", tags=["a", "b"])
        csv = ml.export_memories_csv()
        lines = csv.strip().split("\n")
        assert lines[0].startswith("id,content")
        assert len(lines) == 2

    def test_csv_export_tags_semicolon(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("tagged", tags=["alpha", "beta"])
        csv = ml.export_memories_csv()
        assert "alpha;beta" in csv

    def test_csv_export_null_subtype(self, tmp_data_dir):
        ml = MemoryLayer(data_dir=tmp_data_dir, backend="json")
        ml.remember("no subtype", subtype=None)
        csv = ml.export_memories_csv()
        # Last field should be empty for None subtype
        lines = csv.strip().split("\n")
        # The row should end with a comma or empty field
        assert lines[1].rstrip().endswith(",")


# ===================================================================
# 3. Cognitive Provider Error Tests
# ===================================================================


class TestOllamaModel:
    """OllamaModel error paths — lines 279-314."""

    def _make_model(self):
        from animus.cognitive import ModelConfig, OllamaModel

        return OllamaModel(ModelConfig.ollama())

    def test_ollama_import_error(self):
        model = self._make_model()
        with patch.dict(sys.modules, {"ollama": None}):
            result = model.generate("hello")
        assert "[Error: ollama package not installed]" in result

    def test_ollama_connection_error(self):
        model = self._make_model()
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("refused")
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = model.generate("hello")
        assert "[Error communicating with Ollama" in result

    def test_ollama_timeout(self):
        model = self._make_model()
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = TimeoutError("timed out")
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = model.generate("hello")
        assert "[Error communicating with Ollama" in result

    def test_ollama_generate_with_tools(self):
        model = self._make_model()
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {"message": {"content": "tool response"}}
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            resp = model.generate_with_tools(
                messages=[{"role": "user", "content": "use tools"}],
                tools=[{"name": "test_tool"}],
            )
        assert resp.content[0].type == "text"
        assert resp.content[0].text == "tool response"
        assert resp.stop_reason == "end_turn"

    def test_ollama_generate_stream(self):
        model = self._make_model()
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {"message": {"content": "streamed"}}
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            chunks = asyncio.run(self._collect_stream(model, "hello"))
        assert "".join(chunks) == "streamed"

    def test_ollama_generate_with_stream_callback(self):
        """stream_callback receives each token chunk."""
        model = self._make_model()
        mock_ollama = MagicMock()
        # Simulate streaming: chat returns an iterable of chunks
        mock_ollama.chat.return_value = iter(
            [
                {"message": {"content": "Hello"}},
                {"message": {"content": " world"}},
            ]
        )
        received: list[str] = []
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = model.generate("hi", stream_callback=received.append)
        assert result == "Hello world"
        assert received == ["Hello", " world"]
        # Verify stream=True was passed
        mock_ollama.chat.assert_called_once()
        _, kwargs = mock_ollama.chat.call_args
        assert kwargs.get("stream") is True

    @staticmethod
    async def _collect_stream(model, prompt):
        chunks = []
        async for chunk in model.generate_stream(prompt):
            chunks.append(chunk)
        return chunks


class TestAnthropicModel:
    """AnthropicModel error paths — lines 325-401."""

    def _make_model(self):
        from animus.cognitive import AnthropicModel, ModelConfig

        return AnthropicModel(ModelConfig.anthropic())

    def test_anthropic_get_client_caching(self):
        model = self._make_model()
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            client1 = model._get_client()
            client2 = model._get_client()
        assert client1 is client2
        mock_anthropic.Anthropic.assert_called_once()

    def test_anthropic_import_error(self):
        model = self._make_model()
        with patch.dict(sys.modules, {"anthropic": None}):
            result = model.generate("hello")
        assert "[Error: anthropic package not installed]" in result

    def test_anthropic_connection_error(self):
        model = self._make_model()
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("refused")
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            result = model.generate("hello")
        assert "[Error communicating with Anthropic" in result

    def test_anthropic_generate_with_tools_exception(self):
        model = self._make_model()
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("tool error")
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            # Reset cached client so it picks up our mock
            model._client = None
            with pytest.raises(RuntimeError, match="tool error"):
                model.generate_with_tools(
                    messages=[{"role": "user", "content": "test"}],
                )

    def test_anthropic_generate_with_tools_import_error(self):
        model = self._make_model()
        model._client = None
        with patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(ImportError):
                model.generate_with_tools(
                    messages=[{"role": "user", "content": "test"}],
                )

    def test_anthropic_generate_stream(self):
        model = self._make_model()
        mock_anthropic = MagicMock()
        mock_msg = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "streamed result"
        mock_msg.content = [mock_block]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_msg
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            model._client = None
            chunks = asyncio.run(self._collect_stream(model, "test"))
        assert "streamed result" in "".join(chunks)

    def test_anthropic_generate_with_stream_callback(self):
        """stream_callback receives each token chunk via Anthropic streaming."""
        model = self._make_model()
        mock_anthropic = MagicMock()
        mock_client = MagicMock()

        # Simulate the context manager from client.messages.stream()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["Hello", " from", " Claude"])
        mock_client.messages.stream.return_value = mock_stream_ctx
        mock_anthropic.Anthropic.return_value = mock_client

        received: list[str] = []
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            model._client = None
            result = model.generate("hi", stream_callback=received.append)
        assert result == "Hello from Claude"
        assert received == ["Hello", " from", " Claude"]
        mock_client.messages.stream.assert_called_once()

    @staticmethod
    async def _collect_stream(model, prompt):
        chunks = []
        async for chunk in model.generate_stream(prompt):
            chunks.append(chunk)
        return chunks


class TestMarkdownToolLoop:
    """Cover _think_with_tools_markdown (lines 952-1007)."""

    def test_markdown_tool_loop_no_tools(self):
        """Markdown loop with no tool calls returns response directly."""
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        cognitive = CognitiveLayer(ModelConfig.mock(default_response="Just text, no tools."))
        registry = ToolRegistry()
        registry.register(
            Tool(
                name="test_tool",
                description="Test",
                parameters={},
                handler=lambda p: ToolResult(tool_name="test_tool", success=True, output="ok"),
            )
        )
        result = cognitive._think_with_tools_markdown("hello", tools=registry)
        assert result == "Just text, no tools."

    def test_markdown_tool_loop_with_tool_call(self):
        """Markdown loop executes tool and produces final answer."""
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        call_count = {"n": 0}

        def sequenced(prompt, system=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '```tool\n{"tool": "greet", "params": {"name": "world"}}\n```'
            return "Hello world!"

        cognitive = CognitiveLayer(ModelConfig.mock())
        cognitive.primary.generate = sequenced

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="greet",
                description="Greet",
                parameters={"name": "string"},
                handler=lambda p: ToolResult(
                    tool_name="greet", success=True, output=f"Hi {p.get('name')}"
                ),
            )
        )
        result = cognitive._think_with_tools_markdown("say hi", tools=registry)
        assert "Hello world!" in result

    def test_markdown_tool_loop_max_iterations(self):
        """Markdown loop respects max_iterations."""
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        # Always return tool calls — should hit max iterations
        cognitive = CognitiveLayer(ModelConfig.mock())
        cognitive.primary.generate = lambda p, s=None: (
            '```tool\n{"tool": "loop", "params": {}}\n```'
        )

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="loop",
                description="Loop",
                parameters={},
                handler=lambda p: ToolResult(tool_name="loop", success=True, output="again"),
            )
        )
        result = cognitive._think_with_tools_markdown("go", tools=registry, max_iterations=2)
        assert isinstance(result, str)

    def test_markdown_tool_loop_unknown_tool(self):
        """Markdown loop handles unknown tool name."""
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        call_count = {"n": 0}

        def sequenced(prompt, system=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '```tool\n{"tool": "nonexistent", "params": {}}\n```'
            return "Done"

        cognitive = CognitiveLayer(ModelConfig.mock())
        cognitive.primary.generate = sequenced

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="real",
                description="Real",
                parameters={},
                handler=lambda p: ToolResult(tool_name="real", success=True, output="ok"),
            )
        )
        result = cognitive._think_with_tools_markdown("test", tools=registry)
        assert result == "Done"

    def test_markdown_tool_loop_approval_denied(self):
        """Markdown loop handles approval denial."""
        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        call_count = {"n": 0}

        def sequenced(prompt, system=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '```tool\n{"tool": "danger", "params": {}}\n```'
            return "Cancelled"

        cognitive = CognitiveLayer(ModelConfig.mock())
        cognitive.primary.generate = sequenced

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="danger",
                description="Dangerous",
                parameters={},
                handler=lambda p: ToolResult(tool_name="danger", success=True, output="boom"),
                requires_approval=True,
            )
        )
        result = cognitive._think_with_tools_markdown(
            "do it",
            tools=registry,
            approval_callback=lambda name, params: False,
        )
        assert result == "Cancelled"


class TestRemoveToolBlocks:
    """Cover _remove_tool_blocks (lines 1205-1206)."""

    def test_removes_tool_blocks(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        cognitive = CognitiveLayer(ModelConfig.mock())
        text = 'Before\n```tool\n{"tool":"x"}\n```\nAfter'
        result = cognitive._remove_tool_blocks(text)
        assert "Before" in result
        assert "After" in result
        assert "tool" not in result.lower() or "tool" not in result

    def test_no_tool_blocks(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        cognitive = CognitiveLayer(ModelConfig.mock())
        result = cognitive._remove_tool_blocks("Plain text")
        assert result == "Plain text"


class TestConstrainedUnknownTool:
    """Cover unknown tool path in constrained loop (lines 1077-1079)."""

    def test_constrained_unknown_tool_continues(self):
        """When _parse_constrained_tool returns a name not in registry, loop continues."""
        from unittest.mock import patch

        from animus.cognitive import CognitiveLayer, ModelConfig
        from animus.tools import Tool, ToolRegistry, ToolResult

        call_count = {"n": 0}

        def sequenced(prompt, system=None, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "TOOL: 1\n"
            return "TOOL: 0\nRecovered."

        cognitive = CognitiveLayer(ModelConfig.mock())
        cognitive.primary.generate = sequenced

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="real_tool",
                description="Real tool",
                parameters={},
                handler=lambda p: ToolResult(tool_name="real_tool", success=True, output="ok"),
            )
        )

        # Patch _parse_constrained_tool to return a name not in registry on first call
        original_parse = CognitiveLayer._parse_constrained_tool
        parse_count = {"n": 0}

        @staticmethod
        def fake_parse(response, number_map):
            parse_count["n"] += 1
            if parse_count["n"] == 1:
                return ("ghost_tool", {})  # Name not in registry
            return original_parse(response, number_map)

        with patch.object(CognitiveLayer, "_parse_constrained_tool", fake_parse):
            result = cognitive._think_with_tools_constrained("test", tools=registry)
        assert "Recovered" in result


class TestOpenAIModel:
    """OpenAIModel error paths — lines 404-480."""

    def _make_model(self, base_url=None):
        from animus.cognitive import ModelConfig, ModelProvider, OpenAIModel

        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="gpt-test",
            api_key="test-key",
            base_url=base_url,
        )
        return OpenAIModel(config)

    def test_openai_import_error(self):
        model = self._make_model()
        with patch.dict(sys.modules, {"openai": None}):
            result = model.generate("hello")
        assert "[Error: openai package not installed" in result

    def test_openai_connection_error(self):
        model = self._make_model()
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value.chat.completions.create.side_effect = ConnectionError(
            "refused"
        )
        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = model.generate("hello")
        assert "[Error communicating with OpenAI" in result

    def test_openai_with_base_url(self):
        model = self._make_model(base_url="http://localhost:8080/v1")
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "local result"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_response
        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = model.generate("hello")
        mock_openai.OpenAI.assert_called_once_with(
            api_key="test-key", base_url="http://localhost:8080/v1"
        )
        assert result == "local result"

    def test_openai_generate_with_tools(self):
        model = self._make_model()
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "tool response"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_response
        with patch.dict(sys.modules, {"openai": mock_openai}):
            resp = model.generate_with_tools(
                messages=[{"role": "user", "content": "use tools"}],
                tools=[{"name": "test"}],
            )
        assert resp.content[0].type == "text"
        assert resp.content[0].text == "tool response"
        assert resp.stop_reason == "end_turn"

    def test_openai_generate_stream(self):
        model = self._make_model()
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "streamed"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_response
        with patch.dict(sys.modules, {"openai": mock_openai}):
            chunks = asyncio.run(self._collect_stream(model, "hello"))
        assert "".join(chunks) == "streamed"

    def test_openai_generate_with_stream_callback(self):
        """stream_callback receives each token chunk via OpenAI streaming."""
        model = self._make_model()
        mock_openai = MagicMock()

        # Simulate streaming chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        mock_openai.OpenAI.return_value.chat.completions.create.return_value = iter(
            [chunk1, chunk2]
        )

        received: list[str] = []
        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = model.generate("hi", stream_callback=received.append)
        assert result == "Hello world"
        assert received == ["Hello", " world"]
        # Verify stream=True was passed
        _, kwargs = mock_openai.OpenAI.return_value.chat.completions.create.call_args
        assert kwargs.get("stream") is True

    @staticmethod
    async def _collect_stream(model, prompt):
        chunks = []
        async for chunk in model.generate_stream(prompt):
            chunks.append(chunk)
        return chunks


class TestWriteRootsSandbox:
    """Test write_roots sandbox behavior via WorkspaceToolPolicy."""

    def test_write_file_blocked_outside_write_roots(self, tmp_path):
        from animus.config import ToolsSecurityConfig
        from animus.tools import WorkspaceToolPolicy, _tool_write_file

        config = ToolsSecurityConfig(
            allowed_paths=[str(tmp_path)],
            write_roots=[str(tmp_path / "sandbox")],
        )
        policy = WorkspaceToolPolicy.from_tools_security_config(config)

        # Write inside sandbox — should succeed
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        result = _tool_write_file(
            {"path": str(sandbox / "ok.txt"), "content": "hello"}, policy=policy
        )
        assert result.success

        # Write outside sandbox — should fail
        result = _tool_write_file(
            {"path": str(tmp_path / "outside.txt"), "content": "nope"}, policy=policy
        )
        assert not result.success
        assert "write_roots" in result.error.lower() or "Write denied" in result.error

    def test_edit_file_blocked_outside_write_roots(self, tmp_path):
        from animus.config import ToolsSecurityConfig
        from animus.tools import WorkspaceToolPolicy, _tool_edit_file

        # Create a file outside sandbox
        target = tmp_path / "real.py"
        target.write_text("old content")

        config = ToolsSecurityConfig(
            allowed_paths=[str(tmp_path)],
            write_roots=[str(tmp_path / "sandbox")],
        )
        policy = WorkspaceToolPolicy.from_tools_security_config(config)

        result = _tool_edit_file(
            {"path": str(target), "old_text": "old", "new_text": "new"}, policy=policy
        )
        assert not result.success
        assert "Write denied" in result.error
        # File should be unchanged
        assert target.read_text() == "old content"

    def test_no_write_roots_allows_all(self, tmp_path):
        from animus.config import ToolsSecurityConfig
        from animus.tools import WorkspaceToolPolicy, _tool_write_file

        config = ToolsSecurityConfig(
            allowed_paths=[str(tmp_path)],
            write_roots=[],  # No restriction
        )
        policy = WorkspaceToolPolicy.from_tools_security_config(config)

        result = _tool_write_file(
            {"path": str(tmp_path / "anywhere.txt"), "content": "ok"}, policy=policy
        )
        assert result.success


class TestMockModelWithTools:
    """MockModel.generate_with_tools — lines 223-247."""

    def test_mock_generate_with_tools(self):
        from animus.cognitive import MockModel, ModelConfig

        config = ModelConfig.mock(
            default_response="mock tool output",
            response_map={"special": "special output"},
        )
        model = MockModel(config)
        resp = model.generate_with_tools(
            messages=[{"role": "user", "content": "do something"}],
            tools=[{"name": "test_tool"}],
        )
        assert resp.content[0].type == "text"
        assert resp.content[0].text == "mock tool output"
        assert resp.stop_reason == "end_turn"

    def test_mock_generate_with_tools_response_map(self):
        from animus.cognitive import MockModel, ModelConfig

        config = ModelConfig.mock(
            default_response="default",
            response_map={"special": "matched"},
        )
        model = MockModel(config)
        resp = model.generate_with_tools(
            messages=[{"role": "user", "content": "special request"}],
        )
        assert resp.content[0].text == "matched"


# ===================================================================
# 4. CognitiveLayer Enrichment Tests
# ===================================================================


class TestCognitiveLayerSystemPrompt:
    """CognitiveLayer._build_system_prompt enrichment — lines 625-657."""

    def test_system_prompt_with_learning_prefs(self):
        from animus.cognitive import CognitiveLayer, ModelConfig, ReasoningMode

        mock_learning = MagicMock()
        mock_pref = MagicMock()
        mock_pref.confidence = 0.9
        mock_pref.value = "Be concise"
        mock_learning.get_preferences.return_value = [mock_pref]

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            learning=mock_learning,
        )
        prompt = cl._build_system_prompt(None, ReasoningMode.QUICK)
        assert "Be concise" in prompt

    def test_system_prompt_with_low_confidence_prefs(self):
        from animus.cognitive import CognitiveLayer, ModelConfig, ReasoningMode

        mock_learning = MagicMock()
        mock_pref = MagicMock()
        mock_pref.confidence = 0.3  # Below 0.6 threshold
        mock_pref.value = "Should not appear"
        mock_learning.get_preferences.return_value = [mock_pref]

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            learning=mock_learning,
        )
        prompt = cl._build_system_prompt(None, ReasoningMode.QUICK)
        assert "Should not appear" not in prompt

    def test_system_prompt_with_tools_schema(self):
        from animus.cognitive import CognitiveLayer, ModelConfig, ReasoningMode

        cl = CognitiveLayer(primary_config=ModelConfig.mock())
        prompt = cl._build_system_prompt(
            None,
            ReasoningMode.QUICK,
            tools_schema="Available tools: [search, calculate]",
        )
        assert "Available tools" in prompt
        assert "tool_name" in prompt  # template instructions


class TestCognitiveLayerEnrichContext:
    """CognitiveLayer._enrich_context — lines 582-610."""

    def test_enrich_with_entity_memory(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_em = MagicMock()
        mock_em.get_context_for_text.return_value = "Entity: John is a developer"

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            entity_memory=mock_em,
        )
        result = cl._enrich_context("Tell me about John", None)
        assert "John is a developer" in result

    def test_enrich_entity_memory_error(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_em = MagicMock()
        mock_em.get_context_for_text.side_effect = RuntimeError("entity fail")

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            entity_memory=mock_em,
        )
        result = cl._enrich_context("test", "existing context")
        assert result == "existing context"

    def test_enrich_with_proactive_nudge(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_proactive = MagicMock()
        nudge = MagicMock()
        nudge.content = "You discussed this topic yesterday"
        mock_proactive.generate_context_nudge.return_value = nudge

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            proactive=mock_proactive,
        )
        result = cl._enrich_context("remind me", None)
        assert "discussed this topic yesterday" in result

    def test_enrich_proactive_error(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_proactive = MagicMock()
        mock_proactive.generate_context_nudge.side_effect = RuntimeError("nudge fail")

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            proactive=mock_proactive,
        )
        result = cl._enrich_context("test", None)
        assert result is None

    def test_enrich_appends_to_existing_context(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_em = MagicMock()
        mock_em.get_context_for_text.return_value = "entity info"

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            entity_memory=mock_em,
        )
        result = cl._enrich_context("query", "prior context")
        assert "prior context" in result
        assert "entity info" in result


class TestCognitiveLayerThinkEntityExtraction:
    """CognitiveLayer.think() entity extraction — lines 573-578."""

    def test_think_entity_extraction(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_em = MagicMock()
        mock_em.get_context_for_text.return_value = None

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            entity_memory=mock_em,
        )
        cl.think("Tell me about Python")
        mock_em.extract_and_link.assert_called_once_with("Tell me about Python")

    def test_think_entity_extraction_failure(self):
        from animus.cognitive import CognitiveLayer, ModelConfig

        mock_em = MagicMock()
        mock_em.get_context_for_text.return_value = None
        mock_em.extract_and_link.side_effect = RuntimeError("extraction fail")

        cl = CognitiveLayer(
            primary_config=ModelConfig.mock(),
            entity_memory=mock_em,
        )
        # Should not raise — error is swallowed
        result = cl.think("test query")
        assert isinstance(result, str)


# ===================================================================
# 5. Bootstrap Loop Tests
# ===================================================================


class TestRunConsensus:
    """run_consensus with convergent — lines 147-207."""

    def test_consensus_with_convergent_approve(self):
        from animus.bootstrap_loop import run_consensus

        # Mock all convergent imports
        mock_config = MagicMock()
        mock_identity = MagicMock()
        mock_vote = MagicMock()
        mock_choice = MagicMock()
        mock_store = MagicMock()
        mock_scorer = MagicMock()
        mock_triumvirate_cls = MagicMock()

        mock_triumvirate = MagicMock()
        mock_triumvirate_cls.return_value = mock_triumvirate

        mock_request = MagicMock()
        mock_request.request_id = "test-req"
        mock_triumvirate.create_request.return_value = mock_request

        mock_decision = MagicMock()
        mock_decision.outcome.value = "approved"
        mock_decision.total_weighted_approve = 0.8
        mock_decision.total_weighted_reject = 0.1
        mock_decision.votes = [
            MagicMock(reasoning="good analysis"),
            MagicMock(reasoning="good review"),
        ]
        mock_triumvirate.evaluate.return_value = mock_decision

        with patch.dict(
            sys.modules,
            {
                "convergent": MagicMock(),
                "animus_quorum.coordination_config": MagicMock(CoordinationConfig=mock_config),
                "animus_quorum.protocol": MagicMock(
                    AgentIdentity=mock_identity,
                    Vote=mock_vote,
                    VoteChoice=mock_choice,
                ),
                "animus_quorum.score_store": MagicMock(ScoreStore=mock_store),
                "animus_quorum.scoring": MagicMock(PhiScorer=mock_scorer),
                "animus_quorum.triumvirate": MagicMock(Triumvirate=mock_triumvirate_cls),
            },
        ):
            result = run_consensus(
                question="Accept?",
                context="Code looks good",
            )

        assert result.approved is True
        assert result.approve_weight == 0.8
        assert result.decision_id == "test-req"

    def test_consensus_with_convergent_reject(self):
        from animus.bootstrap_loop import run_consensus

        mock_triumvirate_cls = MagicMock()
        mock_triumvirate = MagicMock()
        mock_triumvirate_cls.return_value = mock_triumvirate

        mock_request = MagicMock()
        mock_request.request_id = "test-req-2"
        mock_triumvirate.create_request.return_value = mock_request

        mock_decision = MagicMock()
        mock_decision.outcome.value = "rejected"
        mock_decision.total_weighted_approve = 0.2
        mock_decision.total_weighted_reject = 0.7
        mock_decision.votes = [
            MagicMock(reasoning="risky"),
            MagicMock(reasoning="not ready"),
        ]
        mock_triumvirate.evaluate.return_value = mock_decision

        with patch.dict(
            sys.modules,
            {
                "convergent": MagicMock(),
                "animus_quorum.coordination_config": MagicMock(CoordinationConfig=MagicMock()),
                "animus_quorum.protocol": MagicMock(
                    AgentIdentity=MagicMock(),
                    Vote=MagicMock(),
                    VoteChoice=MagicMock(),
                ),
                "animus_quorum.score_store": MagicMock(ScoreStore=MagicMock()),
                "animus_quorum.scoring": MagicMock(PhiScorer=MagicMock()),
                "animus_quorum.triumvirate": MagicMock(Triumvirate=mock_triumvirate_cls),
            },
        ):
            result = run_consensus(
                question="Accept?",
                context="Code is risky",
                agent_a_vote="reject",
                agent_b_vote="reject",
            )

        assert result.approved is False
        assert result.reject_weight == 0.7

    def test_consensus_import_error_fallback(self):
        from animus.bootstrap_loop import run_consensus

        with patch.dict(
            sys.modules,
            {
                "convergent": None,
                "animus_quorum.coordination_config": None,
                "animus_quorum.protocol": None,
                "animus_quorum.score_store": None,
                "animus_quorum.scoring": None,
                "animus_quorum.triumvirate": None,
            },
        ):
            result = run_consensus(
                question="Accept?",
                context="test",
                agent_a_vote="approve",
                agent_a_confidence=0.8,
                agent_b_vote="approve",
                agent_b_confidence=0.7,
            )

        assert result.approved is True
        assert result.approve_weight > 0


class TestBootstrapLoopInit:
    """BootstrapLoop non-mock provider init — lines 311-325."""

    def test_bootstrap_loop_non_mock_provider(self, tmp_path):
        from animus.bootstrap_loop import BootstrapLoop
        from animus.identity import AnimusIdentity

        identity = AnimusIdentity(codebase_root=str(tmp_path))

        # Mock the ModelConfig import path used in the non-mock branch
        loop = BootstrapLoop(
            identity=identity,
            data_dir=tmp_path / "data",
            provider="anthropic",
            model="claude-test",
        )

        assert loop.provider == "anthropic"
        assert loop.cognitive is not None

    def test_bootstrap_loop_with_data_dir(self, tmp_path):
        from animus.bootstrap_loop import BootstrapLoop
        from animus.identity import AnimusIdentity

        data_dir = tmp_path / "custom_data"
        identity = AnimusIdentity(codebase_root=str(tmp_path))
        loop = BootstrapLoop(identity=identity, data_dir=data_dir)
        # Memory should use the provided data_dir, not identity.root / ".animus"
        assert loop.memory.data_dir == data_dir


class TestBootstrapLoopProperties:
    """BootstrapLoop properties — lines 477-489."""

    def _make_loop(self, tmp_path):
        from animus.bootstrap_loop import BootstrapLoop
        from animus.identity import AnimusIdentity

        identity = AnimusIdentity(codebase_root=str(tmp_path))
        return BootstrapLoop(identity=identity, data_dir=tmp_path / "data")

    def test_cycle_count_property(self, tmp_path):
        loop = self._make_loop(tmp_path)
        assert loop.cycle_count == loop._cycle_count

    def test_results_property(self, tmp_path):
        loop = self._make_loop(tmp_path)
        results = loop.results
        assert isinstance(results, list)
        assert results is not loop._results  # should be a copy

    def test_get_history(self, tmp_path):
        from animus.bootstrap_loop import BootstrapResult, ConsensusResult

        loop = self._make_loop(tmp_path)
        loop._results.append(
            BootstrapResult(
                cycle=1,
                files_reviewed=["test.py"],
                analysis="good",
                suggestions="none",
                consensus=ConsensusResult(approved=True, approve_weight=0.8),
                improvements_written=True,
            )
        )
        history = loop.get_history()
        assert len(history) == 1
        assert history[0]["cycle"] == 1
        assert history[0]["consensus_approved"] is True
