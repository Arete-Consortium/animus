"""Dry-run-first importer for explicitly approved bootstrap memory sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from animus_bootstrap.intelligence.memory_backends.sqlite_backend import SQLiteMemoryBackend

MAX_SOURCE_BYTES = 1_048_576
VALID_MEMORY_TYPES = frozenset(SQLiteMemoryBackend.VALID_TYPES)


@dataclass(frozen=True)
class ImportCandidate:
    source_name: str
    memory_type: str
    content: str
    metadata: dict[str, Any]
    source_sha256: str
    fingerprint: str


@dataclass(frozen=True)
class ImportResult:
    source_name: str
    fingerprint: str
    action: str
    memory_id: str | None = None


def load_candidate(source: Path | str, memory_type: str) -> ImportCandidate:
    path = Path(source)
    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"invalid memory type: {memory_type}")
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise ValueError(f"source must be a regular non-symlink file: {path}")
    size = path.stat().st_size
    if size == 0:
        raise ValueError(f"source is empty: {path}")
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} bytes: {path}")
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"source is not UTF-8: {path}") from exc
    if not content:
        raise ValueError(f"source is empty after trimming: {path}")

    source_sha256 = hashlib.sha256(raw).hexdigest()
    metadata = {
        "importer": "bootstrap_memory_import_v1",
        "source_name": path.name,
        "source_sha256": source_sha256,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            {"type": memory_type, "content": content},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ImportCandidate(path.name, memory_type, content, metadata, source_sha256, fingerprint)


async def import_candidates(
    db_path: Path | str,
    candidates: list[ImportCandidate],
    *,
    apply: bool = False,
) -> list[ImportResult]:
    """Plan or apply candidates; writes occur only when ``apply`` is true."""
    path = Path(db_path).expanduser()
    backend: SQLiteMemoryBackend | None = None
    readonly: sqlite3.Connection | None = None
    if apply:
        backend = SQLiteMemoryBackend(path)
    elif path.exists():
        readonly = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
    try:
        seen: set[str] = set()
        results: list[ImportResult] = []
        for candidate in candidates:
            if candidate.fingerprint in seen:
                results.append(
                    ImportResult(candidate.source_name, candidate.fingerprint, "duplicate")
                )
                continue
            seen.add(candidate.fingerprint)
            existing = (
                await backend.find_exact(candidate.memory_type, candidate.content)
                if backend is not None
                else _find_exact_readonly(readonly, candidate.memory_type, candidate.content)
            )
            if existing is not None:
                results.append(
                    ImportResult(
                        candidate.source_name, candidate.fingerprint, "duplicate", existing["id"]
                    )
                )
                continue
            if apply:
                assert backend is not None
                memory_id = await backend.store(
                    candidate.memory_type, candidate.content, candidate.metadata
                )
                results.append(
                    ImportResult(
                        candidate.source_name, candidate.fingerprint, "imported", memory_id
                    )
                )
            else:
                results.append(
                    ImportResult(candidate.source_name, candidate.fingerprint, "planned")
                )
        return results
    finally:
        if backend is not None:
            backend.close()
        if readonly is not None:
            readonly.close()


def _find_exact_readonly(
    connection: sqlite3.Connection | None,
    memory_type: str,
    content: str,
) -> dict | None:
    if connection is None:
        return None
    row = connection.execute(
        "SELECT id FROM memories WHERE type = ? AND content = ? ORDER BY updated_at LIMIT 1",
        (memory_type, content),
    ).fetchone()
    return {"id": row[0]} if row else None


def import_candidates_sync(
    db_path: Path | str,
    candidates: list[ImportCandidate],
    *,
    apply: bool = False,
) -> list[ImportResult]:
    return asyncio.run(import_candidates(db_path, candidates, apply=apply))
