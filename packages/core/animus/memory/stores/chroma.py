"""ChromaDB-backed memory store with optional BM25 hybrid search."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from animus.logging import get_logger
from animus.memory.fusion import _rrf_fuse
from animus.memory.stores.base import MemoryStore
from animus.memory.types import Memory, MemoryTier, MemoryType, Sensitivity

logger = get_logger("memory")


class ChromaMemoryStore(MemoryStore):
    """
    Vector-based memory store using ChromaDB with optional BM25 hybrid search.

    Provides semantic search using embeddings, optionally fused with BM25
    keyword search via Reciprocal Rank Fusion (RRF).
    """

    @staticmethod
    def prewarm() -> bool:
        """
        Pre-download the sentence-transformer model used by ChromaDB.

        Call this during setup/install to avoid the ~3s cold-start delay
        on first use. Safe to call multiple times (no-op if already cached).

        Returns:
            True if model is ready, False on error
        """
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Pre-warming ChromaDB embedding model...")
            SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("ChromaDB embedding model ready")
            return True
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "ChromaDB will download the model on first use."
            )
            return False
        except Exception as e:
            logger.warning(f"Failed to pre-warm ChromaDB model: {e}")
            return False

    def __init__(self, data_dir: Path, collection_name: str = "animus_memories"):
        self.data_dir = data_dir
        self.collection_name = collection_name
        self._memories: dict[str, Memory] = {}  # Local cache for metadata
        self._bm25 = None  # Lazy-initialized BM25 index
        self._bm25_ids: list[str] = []  # ID ordering matching BM25 corpus
        self._bm25_dirty = True  # Rebuild flag

        try:
            import chromadb

            self.chroma_dir = data_dir / "chroma"
            self.chroma_dir.mkdir(parents=True, exist_ok=True)

            # Prefer server mode for multi-process safety.  PersistentClient
            # opens the SQLite DB and HNSW index directly in this process;
            # multiple processes hitting the same path corrupt the index
            # (observed: "Error executing plan: Internal error: Error finding id").
            # HttpClient talks to a single ChromaDB server over HTTP.
            #
            # To enable server mode:
            #   systemctl --user enable --now chromadb.service
            # To fall back to local file mode, stop the service.
            try:
                self.client = chromadb.HttpClient(
                    host="localhost",
                    port=8787,
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )
                logger.info("ChromaDB connected via HttpClient (localhost:8787)")
            except Exception as e:
                logger.warning(
                    f"ChromaDB server not available ({e}), falling back to PersistentClient"
                )
                self.client = chromadb.PersistentClient(
                    path=str(self.chroma_dir),
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )
                logger.info("ChromaDB initialized in local file mode")

            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ChromaDB ready at {self.chroma_dir} with {self.collection.count()} documents"
            )
        except ImportError as e:
            raise ImportError(
                "ChromaDB not installed. Install with: pip install 'animus-core[chroma]'"
            ) from e
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise

        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load memory metadata from ChromaDB."""
        try:
            results = self.collection.get(include=["metadatas", "documents"])
            for i, mem_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                content = results["documents"][i] if results["documents"] else ""

                # Parse tags from JSON string
                tags_json = metadata.get("tags", "[]")
                try:
                    tags = json.loads(tags_json) if isinstance(tags_json, str) else []
                except json.JSONDecodeError:
                    tags = []

                self._memories[mem_id] = Memory(
                    id=mem_id,
                    content=content,
                    memory_type=MemoryType(metadata.get("memory_type", "semantic")),
                    created_at=datetime.fromisoformat(
                        metadata.get("created_at", datetime.now().isoformat())
                    ),
                    updated_at=datetime.fromisoformat(
                        metadata.get("updated_at", datetime.now().isoformat())
                    ),
                    metadata={
                        k: v
                        for k, v in metadata.items()
                        if k
                        not in (
                            "memory_type",
                            "created_at",
                            "updated_at",
                            "tags",
                            "source",
                            "confidence",
                            "subtype",
                            "version",
                            "parent_id",
                            "change_summary",
                            "provenance",
                            "sensitivity",
                            "tier",
                            "access_count",
                            "last_accessed",
                        )
                    },
                    tags=tags,
                    source=metadata.get("source", "stated"),
                    confidence=float(metadata.get("confidence", 1.0)),
                    subtype=metadata.get("subtype"),
                    version=int(metadata.get("version", 1)),
                    parent_id=metadata.get("parent_id") or None,
                    change_summary=metadata.get("change_summary") or None,
                    provenance=metadata.get("provenance", "direct"),
                    sensitivity=Sensitivity(metadata.get("sensitivity", Sensitivity.PUBLIC.value)),
                    tier=MemoryTier(metadata.get("tier", MemoryTier.WARM.value)),
                    access_count=int(metadata.get("access_count", 0)),
                    last_accessed=(
                        datetime.fromisoformat(metadata["last_accessed"])
                        if metadata.get("last_accessed")
                        else None
                    ),
                )
        except Exception as e:
            logger.warning(f"Failed to load metadata from ChromaDB: {e}")

    def _rebuild_bm25(self) -> None:
        """Rebuild BM25 index from in-memory cache."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.debug("rank_bm25 not installed — hybrid search disabled")
            self._bm25 = None
            self._bm25_dirty = False
            return

        self._bm25_ids = list(self._memories.keys())
        corpus = [self._memories[mid].content.lower().split() for mid in self._bm25_ids]
        if corpus:
            self._bm25 = BM25Okapi(corpus)
            logger.debug(f"BM25 index rebuilt with {len(corpus)} documents")
        else:
            self._bm25 = None
        self._bm25_dirty = False

    def _bm25_search(self, query: str, limit: int) -> list[str]:
        """Return memory IDs ranked by BM25 keyword relevance."""
        if self._bm25_dirty:
            self._rebuild_bm25()
        if not self._bm25 or not self._bm25_ids:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._bm25_ids[i] for i in ranked[:limit] if scores[i] > 0]

    def _build_chroma_metadata(self, memory: Memory) -> dict:
        """Build ChromaDB-compatible metadata dict."""
        metadata = {
            "memory_type": memory.memory_type.value,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
            "tags": json.dumps(memory.tags),  # Store as JSON string
            "source": memory.source,
            "confidence": memory.confidence,
            "version": str(memory.version),
            "provenance": memory.provenance,
            "sensitivity": memory.sensitivity.value,
            "tier": memory.tier.value,
            "access_count": memory.access_count,
            "last_accessed": memory.last_accessed.isoformat() if memory.last_accessed else "",
        }
        if memory.subtype:
            metadata["subtype"] = memory.subtype
        if memory.parent_id:
            metadata["parent_id"] = memory.parent_id
        if memory.change_summary:
            metadata["change_summary"] = memory.change_summary
        # Add custom metadata (convert to strings)
        for k, v in memory.metadata.items():
            metadata[k] = str(v)
        return metadata

    def store(self, memory: Memory) -> None:
        """Store memory with embedding."""
        metadata = self._build_chroma_metadata(memory)

        self.collection.upsert(
            ids=[memory.id],
            documents=[memory.content],
            metadatas=[metadata],
        )
        self._memories[memory.id] = memory
        self._bm25_dirty = True
        logger.debug(f"Stored memory {memory.id[:8]} in ChromaDB")

    def update(self, memory: Memory) -> bool:
        """Update an existing memory."""
        if memory.id in self._memories:
            self.store(memory)  # Upsert handles update
            return True
        return False

    def retrieve(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def search(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        allowed_tiers: set[Sensitivity] | None = None,
    ) -> list[Memory]:
        """Hybrid search: dense vector (ChromaDB) + BM25 keyword, fused with RRF.

        Falls back to vector-only if rank_bm25 is not installed.

        ``allowed_tiers`` restricts results to memories whose sensitivity is
        in the set (gates MCP egress in Stage 2.C). ``None`` skips the filter
        — backward-compat for pre-Stage-2.B callers.
        """
        fetch_limit = limit * 3 if tags else limit * 2

        # Build where clause for ChromaDB
        where_conditions = []
        if memory_type:
            where_conditions.append({"memory_type": memory_type.value})
        if source:
            where_conditions.append({"source": source})
        if min_confidence > 0:
            where_conditions.append({"confidence": {"$gte": min_confidence}})
        if allowed_tiers is not None:
            tier_values = [t.value for t in allowed_tiers]
            where_conditions.append({"sensitivity": {"$in": tier_values}})

        where_filter = None
        if len(where_conditions) == 1:
            where_filter = where_conditions[0]
        elif len(where_conditions) > 1:
            where_filter = {"$and": where_conditions}

        try:
            # --- Dense vector search ---
            results = self.collection.query(
                query_texts=[query],
                n_results=fetch_limit,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
            dense_ids = list(results["ids"][0]) if results["ids"] else []

            # --- BM25 keyword search ---
            bm25_ids = self._bm25_search(query, limit=fetch_limit)

            # --- RRF fusion ---
            if bm25_ids:
                fused_ids = _rrf_fuse([dense_ids, bm25_ids])
                logger.debug(
                    f"Hybrid search: {len(dense_ids)} dense + {len(bm25_ids)} BM25 "
                    f"→ {len(fused_ids)} fused"
                )
            else:
                fused_ids = dense_ids  # Fallback to dense-only

            # Build a lookup for metadata from the ChromaDB results
            chroma_meta = {}
            chroma_docs = {}
            for i, mem_id in enumerate(results["ids"][0]):
                chroma_meta[mem_id] = results["metadatas"][0][i] if results["metadatas"] else {}
                chroma_docs[mem_id] = results["documents"][0][i] if results["documents"] else ""

            memories = []
            for mem_id in fused_ids:
                memory = self._memories.get(mem_id)
                if not memory and mem_id in chroma_meta:
                    # Reconstruct from ChromaDB results
                    metadata = chroma_meta[mem_id]
                    content = chroma_docs.get(mem_id, "")
                    tags_json = metadata.get("tags", "[]")
                    try:
                        mem_tags = json.loads(tags_json) if isinstance(tags_json, str) else []
                    except json.JSONDecodeError:
                        mem_tags = []

                    memory = Memory(
                        id=mem_id,
                        content=content,
                        memory_type=MemoryType(metadata.get("memory_type", "semantic")),
                        created_at=datetime.fromisoformat(
                            metadata.get("created_at", datetime.now().isoformat())
                        ),
                        updated_at=datetime.fromisoformat(
                            metadata.get("updated_at", datetime.now().isoformat())
                        ),
                        metadata={},
                        tags=mem_tags,
                        source=metadata.get("source", "stated"),
                        confidence=float(metadata.get("confidence", 1.0)),
                        subtype=metadata.get("subtype"),
                        version=int(metadata.get("version", 1)),
                        parent_id=metadata.get("parent_id") or None,
                        change_summary=metadata.get("change_summary") or None,
                        provenance=metadata.get("provenance", "direct"),
                        sensitivity=Sensitivity(
                            metadata.get("sensitivity", Sensitivity.PUBLIC.value)
                        ),
                    )
                elif not memory:
                    continue  # BM25-only result not in ChromaDB response

                # Apply tag filter (ChromaDB can't filter JSON arrays)
                if tags and not all(t in memory.tags for t in tags):
                    continue

                memories.append(memory)
                if len(memories) >= limit:
                    break

            logger.debug("Search found %d results", len(memories))
            return memories

        except Exception as e:
            logger.error(f"ChromaDB search failed: {e}")
            return []

    def delete(self, memory_id: str) -> bool:
        try:
            self.collection.delete(ids=[memory_id])
            if memory_id in self._memories:
                del self._memories[memory_id]
            logger.debug(f"Deleted memory {memory_id[:8]} from ChromaDB")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    def list_all(self, memory_type: MemoryType | None = None) -> list[Memory]:
        if memory_type:
            return [m for m in self._memories.values() if m.memory_type == memory_type]
        return list(self._memories.values())

    def get_all_tags(self) -> dict[str, int]:
        """Get all tags with counts."""
        tag_counts: dict[str, int] = {}
        for memory in self._memories.values():
            for tag in memory.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts
