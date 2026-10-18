"""
Secure, Code-Aware Episodic Memory with Chroma

Archived standalone reference implementation. It is not a supported Animus Core
backend or dependency path. Running it requires an independently reviewed Chroma
installation; do not use it for live Core data or configuration.

Usage:
    python code_aware_memory.py ~/projects/myapp
    python code_aware_memory.py ~/projects/myapp "feature/auth-refactor"

This script demonstrates:
  - AST-aware chunking (function/class granularity for Python, headers for Markdown)
  - Ingest-time credential redaction (API keys, tokens, PEM blocks)
  - Chroma persistent collection with metadata-filtered semantic search
  - Incremental reindex via SHA-256 manifest
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chromadb

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class _ChunkType:
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    MARKDOWN_SECTION = "markdown_section"
    YAML_KEY = "yaml_key"
    JSON_KEY = "json_key"
    WINDOW = "window"


@dataclass(frozen=True)
class _CodeChunk:
    content: str
    chunk_type: str
    start_line: int
    end_line: int
    source_path: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class _ChunkingConfig:
    max_chunk_tokens: int = 512
    overlap_tokens: int = 50

    @property
    def chars_per_chunk(self) -> int:
        # Rough estimate: ~4 chars per token
        return self.max_chunk_tokens * 4

    @property
    def overlap_chars(self) -> int:
        return self.overlap_tokens * 4


# ---------------------------------------------------------------------------
# Chunkers by language
# ---------------------------------------------------------------------------


def _chunk_python(content: str, config: _ChunkingConfig) -> list[_CodeChunk]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _chunk_window(content, config)

    lines = content.splitlines(keepends=True)
    chunks: list[_CodeChunk] = []
    covered: set[int] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s, e = node.lineno, node.end_lineno or node.lineno
            chunks.append(
                _CodeChunk(
                    content="".join(lines[s - 1 : e]).rstrip(),
                    chunk_type=_ChunkType.FUNCTION,
                    start_line=s,
                    end_line=e,
                    metadata={"name": node.name},
                )
            )
            covered.update(range(s, e + 1))

        elif isinstance(node, ast.ClassDef):
            s, e = node.lineno, node.end_lineno or node.lineno
            methods = [
                n
                for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            # Split large classes into method-level chunks + header
            if methods and (e - s + 1) * 25 > config.chars_per_chunk:
                for m in methods:
                    ms, me = m.lineno, m.end_lineno or m.lineno
                    chunks.append(
                        _CodeChunk(
                            content="".join(lines[ms - 1 : me]).rstrip(),
                            chunk_type=_ChunkType.METHOD,
                            start_line=ms,
                            end_line=me,
                            metadata={"class": node.name, "name": m.name},
                        )
                    )
                    covered.update(range(ms, me + 1))
                fm = min(m.lineno for m in methods)
                if fm > s + 1:
                    hdr = "".join(lines[s - 1 : fm - 1])
                    if hdr.strip():
                        chunks.append(
                            _CodeChunk(
                                content=hdr.rstrip(),
                                chunk_type=_ChunkType.CLASS,
                                start_line=s,
                                end_line=fm - 1,
                                metadata={"name": node.name},
                            )
                        )
                covered.update(range(s, e + 1))
            else:
                chunks.append(
                    _CodeChunk(
                        content="".join(lines[s - 1 : e]).rstrip(),
                        chunk_type=_ChunkType.CLASS,
                        start_line=s,
                        end_line=e,
                        metadata={"name": node.name},
                    )
                )
                covered.update(range(s, e + 1))

    # Module-level leftovers (imports, constants, etc.)
    mod: list[str] = []
    mod_start: int | None = None
    for i, line in enumerate(lines, 1):
        if i not in covered and line.strip() and not line.strip().startswith("#"):
            if mod_start is None:
                mod_start = i
            mod.append(line)
    if mod and mod_start is not None:
        txt = "".join(mod).rstrip()
        if txt:
            chunks.append(
                _CodeChunk(
                    content=txt,
                    chunk_type=_ChunkType.MODULE,
                    start_line=mod_start,
                    end_line=mod_start + len(mod) - 1,
                )
            )

    return chunks if chunks else _chunk_window(content, config)


def _chunk_markdown(content: str, _config: _ChunkingConfig) -> list[_CodeChunk]:
    pat = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    lines = content.split("\n")
    matches = list(pat.finditer(content))
    if not matches:
        return _chunk_window(content, _config)

    positions: list[tuple[int, str]] = []
    for m in matches:
        ln = content[: m.start()].count("\n") + 1
        positions.append((ln, m.group(0)))

    chunks: list[_CodeChunk] = []
    for i, (ln, hdr) in enumerate(positions):
        end = positions[i + 1][0] - 1 if i + 1 < len(positions) else len(lines)
        section = "\n".join(lines[ln - 1 : end]).strip()
        if section:
            chunks.append(
                _CodeChunk(
                    content=section,
                    chunk_type=_ChunkType.MARKDOWN_SECTION,
                    start_line=ln,
                    end_line=end,
                    metadata={"header": hdr.lstrip("#").strip()},
                )
            )

    if positions and positions[0][0] > 1:
        pre = "\n".join(lines[: positions[0][0] - 1]).strip()
        if pre:
            chunks.insert(
                0,
                _CodeChunk(
                    content=pre,
                    chunk_type=_ChunkType.MARKDOWN_SECTION,
                    start_line=1,
                    end_line=positions[0][0] - 1,
                    metadata={"header": "preamble"},
                ),
            )
    return chunks


def _chunk_yaml(content: str, _config: _ChunkingConfig) -> list[_CodeChunk]:
    try:
        import yaml

        data = yaml.safe_load(content)
    except Exception:
        return _chunk_window(content, _config)

    if not isinstance(data, dict):
        return _chunk_window(content, _config)

    lines = content.split("\n")
    keys: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"^(\S+)\s*:", line)
        if m:
            keys.append((i, m.group(1)))

    chunks: list[_CodeChunk] = []
    for i, (ln, key) in enumerate(keys):
        end = keys[i + 1][0] - 1 if i + 1 < len(keys) else len(lines)
        section = "\n".join(lines[ln - 1 : end]).strip()
        if section:
            chunks.append(
                _CodeChunk(
                    content=section,
                    chunk_type=_ChunkType.YAML_KEY,
                    start_line=ln,
                    end_line=end,
                    metadata={"key": key},
                )
            )
    return chunks if chunks else _chunk_window(content, _config)


def _chunk_json(content: str, _config: _ChunkingConfig) -> list[_CodeChunk]:
    try:
        data = json.loads(content)
    except Exception:
        return _chunk_window(content, _config)

    if isinstance(data, dict):
        chunks: list[_CodeChunk] = []
        for key, value in data.items():
            chunks.append(
                _CodeChunk(
                    content=json.dumps({key: value}, indent=2),
                    chunk_type=_ChunkType.JSON_KEY,
                    start_line=1,
                    end_line=1,
                    metadata={"key": key},
                )
            )
        return chunks if chunks else _chunk_window(content, _config)
    return _chunk_window(content, _config)


def _chunk_window(content: str, config: _ChunkingConfig) -> list[_CodeChunk]:
    stride = max(1, config.chars_per_chunk - config.overlap_chars)
    chunks: list[_CodeChunk] = []
    start = 0
    total = len(content)
    while start < total:
        end = min(start + config.chars_per_chunk, total)
        txt = content[start:end]
        sl = content[:start].count("\n") + 1
        el = content[:end].count("\n") + 1
        if txt.strip():
            chunks.append(
                _CodeChunk(
                    content=txt.strip(),
                    chunk_type=_ChunkType.WINDOW,
                    start_line=sl,
                    end_line=el,
                )
            )
        if end >= total:
            break
        start += stride
    return chunks


# ---------------------------------------------------------------------------
# File dispatch + redaction
# ---------------------------------------------------------------------------

_CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("github_token", re.compile(r"ghp_[a-zA-Z0-9]{36,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "password",
        re.compile(r"password\s*[=:]\s*[^\s#]{3,}", re.IGNORECASE),
    ),
    (
        "secret",
        re.compile(r"secret\s*[=:]\s*[^\s#]{3,}", re.IGNORECASE),
    ),
    (
        "token",
        re.compile(r"token\s*[=:]\s*[^\s#]{3,}", re.IGNORECASE),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
]


def _redact(chunk: _CodeChunk) -> _CodeChunk:
    text = chunk.content
    spans: list[tuple[int, int]] = []
    for _name, pat in _CREDENTIAL_PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    if not spans:
        return chunk

    spans.sort()
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    parts: list[str] = []
    cursor = 0
    for s, e in merged:
        parts.append(text[cursor:s])
        parts.append("[REDACTED]")
        cursor = e
    parts.append(text[cursor:])

    meta = dict(chunk.metadata)
    meta["_redacted"] = "true"
    return _CodeChunk(
        content="".join(parts),
        chunk_type=chunk.chunk_type,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        source_path=chunk.source_path,
        metadata=meta,
    )


def chunk_file(file_path: Path, config: _ChunkingConfig | None = None) -> list[_CodeChunk]:
    """Extract semantic chunks from *file_path*, redacting credentials."""
    config = config or _ChunkingConfig()
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not raw.strip():
        return []

    ext = file_path.suffix.lower()
    if ext == ".py":
        chunks = _chunk_python(raw, config)
    elif ext == ".md":
        chunks = _chunk_markdown(raw, config)
    elif ext in (".yaml", ".yml"):
        chunks = _chunk_yaml(raw, config)
    elif ext == ".json":
        chunks = _chunk_json(raw, config)
    else:
        chunks = _chunk_window(raw, config)

    out: list[_CodeChunk] = []
    for c in chunks:
        out.append(
            _CodeChunk(
                content=c.content,
                chunk_type=c.chunk_type,
                start_line=c.start_line,
                end_line=c.end_line,
                source_path=str(file_path),
                metadata=c.metadata,
            )
        )
    return [_redact(c) for c in out]


# ---------------------------------------------------------------------------
# Chroma store
# ---------------------------------------------------------------------------


class CodeMemoryStore:
    """Chroma-backed semantic store for code chunks."""

    def __init__(
        self,
        collection_name: str = "code_memory",
        persist_dir: str = "./chroma_db",
    ) -> None:
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[_CodeChunk], session_tag: str = "") -> list[str]:
        """Store chunks. Returns inserted IDs."""
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for chunk in chunks:
            boost = " ".join(
                v for k, v in chunk.metadata.items() if k in ("name", "class", "header", "key")
            )
            emb_text = f"{boost}\n{boost}\n{chunk.content}" if boost else chunk.content

            cid = _hash_text(emb_text + chunk.source_path)
            ids.append(cid)
            documents.append(emb_text)
            meta = {
                "chunk_type": chunk.chunk_type,
                "source_path": chunk.source_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "session_tag": session_tag,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                **chunk.metadata,
            }
            metadatas.append(meta)

        self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return ids

    def query(
        self,
        question: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Semantic search with optional metadata filter."""
        results = self.collection.query(
            query_texts=[question],
            n_results=n_results,
            where=where,
        )
        out: list[dict] = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            out.append(
                {
                    "content": doc,
                    "distance": results["distances"][0][i],
                    **meta,
                }
            )
        return out


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


def ingest_codebase(
    root: Path,
    store: CodeMemoryStore,
    *,
    globs: list[str] | None = None,
    exclude: list[str] | None = None,
    session_tag: str = "",
    skip_existing: bool = True,
) -> dict:
    """Ingest a codebase into Chroma. Returns manifest summary."""
    globs = globs or ["*.py", "*.md"]
    exclude = exclude or ["*/test*", "*/__pycache__/*", "*/node_modules/*"]

    manifest_path = root / ".code_memory_manifest.json"
    prev: dict = {}
    if skip_existing and manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text())
        except Exception:
            pass

    stored = 0
    skipped = 0
    entries: dict = {}

    for pattern in globs:
        for path in root.rglob(pattern):
            if any(path.match(p) for p in exclude):
                continue
            rel = str(path.relative_to(root))
            h = _hash_file(path)
            if skip_existing and prev.get("files", {}).get(rel, {}).get("hash") == h:
                skipped += 1
                continue

            chunks = chunk_file(path)
            if chunks:
                store.add_chunks(chunks, session_tag=session_tag)
                stored += len(chunks)
            entries[rel] = {"hash": h, "chunks": len(chunks)}

    manifest = {
        "version": "1.0",
        "root": str(root),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {"stored": stored, "skipped": skipped, "manifest": manifest_path}


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python code_aware_memory.py <codebase_path> [session_tag]")
        sys.exit(1)

    target = Path(sys.argv[1]).expanduser().resolve()
    if not target.is_dir():
        print(f"Error: {target} is not a directory.")
        sys.exit(1)

    tag = sys.argv[2] if len(sys.argv) > 2 else "manual"

    store = CodeMemoryStore(persist_dir=str(target / ".chroma_db"))

    print(f"Indexing {target} ...")
    result = ingest_codebase(target, store, session_tag=tag)
    print(f"Stored {result['stored']} chunks, skipped {result['skipped']} unchanged files.")

    print("\n--- Demo Query: 'authentication logic' ---")
    for hit in store.query("authentication logic", n_results=3):
        print(f"\n[{hit['chunk_type']}] {hit['source_path']}:{hit['start_line']}-{hit['end_line']}")
        print(hit["content"][:300] + "...")
