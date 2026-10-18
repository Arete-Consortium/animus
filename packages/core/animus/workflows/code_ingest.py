"""``animus.workflows.code_ingest`` — local codebase → semantic memory pipeline.

Extracted from memboot's indexing layer. Stores chunks through the supported
Animus ``MemoryLayer`` interface. Retrieval behavior follows the explicitly
selected supported backend; this workflow does not select or install a vector
store.

Usage::

    from animus.workflows.code_ingest import ingest_codebase
    from animus.memory import MemoryLayer

    memory = MemoryLayer(Path("~/.animus"))
    result = ingest_codebase(
        Path("~/projects/myapp"),
        memory=memory,
        tags=["myapp", "v1.0"],
    )
    print(f"Stored {result.stored_count} chunks")
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from animus.code.chunking import ChunkingConfig, CodeChunk, chunk_codebase
from animus.logging import get_logger
from animus.memory import MemoryLayer
from animus.memory.types import MemoryType, Sensitivity

logger = get_logger("workflows.code_ingest")

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestError:
    """One recoverable failure inside the codebase ingestion pipeline."""

    stage: str
    path: str
    message: str


@dataclass
class CodeIngestResult:
    """Outcome of a single ``ingest_codebase()`` call."""

    stored_count: int = 0
    skipped_count: int = 0
    errors: list[IngestError] = field(default_factory=list)
    manifest_path: Path | None = None

    @property
    def success(self) -> bool:
        """True if at least one chunk was stored and no fatal errors occurred."""
        return self.stored_count > 0 and not any(e.stage == "fatal" for e in self.errors)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def ingest_codebase(
    root: Path,
    *,
    memory: MemoryLayer | None = None,
    tags: list[str] | None = None,
    globs: list[str] | None = None,
    exclude: list[str] | None = None,
    config: ChunkingConfig | None = None,
    write_manifest: bool = True,
    manifest_dir: Path | None = None,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    skip_existing: bool = True,
) -> CodeIngestResult:
    """Ingest a local codebase into Animus memory.

    Chunks are stored as ``MemoryType.SEMANTIC`` memories with metadata
    carrying chunk type, line numbers, and source path. This enables
    precise "where did I see this function?" recall.

    Args:
        root: Base directory of the codebase.
        memory: Animus ``MemoryLayer`` instance. If ``None``, one is created
            from the default config.
        tags: Tags applied to every stored memory (e.g. ``["projectname"]``).
        globs: Filename patterns to include.
        exclude: Patterns to skip.
        config: Chunking parameters.
        write_manifest: Whether to write a JSON manifest of what was stored.
        manifest_dir: Where to write the manifest. Defaults to ``root``.
        sensitivity: Disclosure tier for stored memories.
        skip_existing: If True, compute a content hash per file and skip
            re-ingesting files whose hash matches the last manifest.

    Returns:
        ``CodeIngestResult`` with counts and any errors.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return CodeIngestResult(errors=[IngestError("fatal", str(root), "Not a directory")])

    if memory is None:
        from animus.config import AnimusConfig

        cfg = AnimusConfig.load()
        memory = MemoryLayer(cfg.data_dir, backend=cfg.memory.backend)

    tags = tags if tags is not None else []
    config = config or ChunkingConfig()
    manifest_dir = manifest_dir or root

    # Load previous manifest for skip-existing
    prev_manifest: dict = {}
    manifest_path = manifest_dir / ".animus_ingest_manifest.json"
    if skip_existing and manifest_path.exists():
        try:
            prev_manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    # Chunk the codebase
    try:
        by_path = chunk_codebase(
            root,
            globs=globs,
            exclude=exclude,
            config=config,
            redact_credentials=True,
        )
    except Exception as exc:
        logger.exception("Chunking failed for %s", root)
        return CodeIngestResult(errors=[IngestError("fatal", str(root), f"chunking failed: {exc}")])

    stored = 0
    skipped = 0
    errors: list[IngestError] = []
    manifest_entries: dict[str, dict] = {}

    for rel_path, chunks in by_path.items():
        file_path = root / rel_path
        file_hash = _hash_file(file_path)

        prev_file = prev_manifest.get("files", {}).get(rel_path, {})
        if skip_existing and prev_file.get("hash") == file_hash:
            skipped += len(chunks)
            continue

        for chunk in chunks:
            try:
                _store_chunk(
                    memory=memory,
                    chunk=chunk,
                    tags=tags,
                    sensitivity=sensitivity,
                )
                stored += 1
            except Exception as exc:
                logger.warning("Store failed for %s:%s: %s", rel_path, chunk.start_line, exc)
                errors.append(IngestError("store", f"{rel_path}:{chunk.start_line}", str(exc)))

        mtime = file_path.stat().st_mtime if file_path.exists() else 0.0
        manifest_entries[rel_path] = {
            "hash": file_hash,
            "chunk_count": len(chunks),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "mtime": mtime,
        }

    # Write manifest with summary statistics
    if write_manifest:
        total_chunks = sum(e["chunk_count"] for e in manifest_entries.values())
        full_manifest = {
            "version": "1.1",
            "root": str(root),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_scanned_files": len(by_path),
                "total_chunked_files": len(
                    [e for e in manifest_entries.values() if e["chunk_count"] > 0]
                ),
                "total_chunks": total_chunks,
            },
            "files": manifest_entries,
        }
        try:
            manifest_path.write_text(json.dumps(full_manifest, indent=2))
        except OSError as exc:
            logger.warning("Failed to write manifest: %s", exc)

    return CodeIngestResult(
        stored_count=stored,
        skipped_count=skipped,
        errors=errors,
        manifest_path=manifest_path if write_manifest else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store_chunk(
    memory: MemoryLayer,
    chunk: CodeChunk,
    tags: list[str],
    sensitivity: Sensitivity,
) -> None:
    """Store a single CodeChunk as a semantic memory."""
    # Build embedding-boosted text: repeat identifiers so dense retrieval
    # weights them higher.
    embedding_text = chunk.content
    meta = dict(chunk.metadata)
    names = [v for k, v in meta.items() if k in ("name", "class", "header", "key")]
    if names:
        embedding_text = f"{' '.join(names)}\n{names[0]}\n{chunk.content}"

    all_tags = list(tags)
    all_tags.append(f"chunk:{chunk.chunk_type.value}")

    memory.remember(
        content=embedding_text,
        memory_type=MemoryType.SEMANTIC,
        metadata=chunk.to_memory_payload(),
        tags=all_tags,
        source="code_ingest",
        provenance="code_ingest",
        sensitivity=sensitivity,
    )


def _hash_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()[:16]
