# Archived recipe: Secure, Code-Aware Episodic Memory with Chroma

> **Unsupported migration/reference material.** Chroma is retired from the
> supported Animus Core runtime because no patched upstream release is
> available. This standalone recipe requires an independently reviewed Chroma
> installation and must not be used to configure a Core service. Existing
> Animus Chroma data should follow the
> [retirement plan](../operators/chroma-retirement-plan.md).

**Goal:** Build a persistent memory system for AI-assisted development that:
- Remembers your codebase at function/class granularity (not just files)
- Automatically redacts credentials before storage
- Supports episodic queries ("What did I change in auth last Tuesday?")
- Runs locally with zero external dependencies beyond Chroma

**Source:** Ported from the [memboot](https://github.com/your-org/memboot) experiment into [Animus](https://github.com/your-org/animus). This recipe distills the approach into a standalone, reusable pattern.

---

## Prerequisites

```bash
pip install chromadb
# Optional: YAML support
pip install pyyaml
```

The Animus Core package does not install Chroma or expose a Chroma optional
dependency. Installing Core alone is therefore insufficient for this archived
standalone example.

---

## The Problem with File-Level Memory

Most code-memory tools store *entire files* as vectors. This breaks down when:
- A file has 20 unrelated functions — retrieval surfaces noise
- You want to ask "Where is the `validate_token` function?" — file-level chunks dilute signal
- Credentials live in config files — naive ingestion leaks secrets into the vector DB

The fix: **AST-aware semantic chunking** + **Chroma hybrid search** + **ingest-time redaction**.

---

## Architecture

```
Codebase
   │
   ├── AST Chunker ──────┐
   │   (func/class/md)   │
   ├── Redaction Filter ─┤
   │   (credentials)     │
   └── Manifest Tracker ─┘
            │
            ▼
    Chroma Collection
    (dense + metadata)
            │
            ▼
    Query: "How does auth work?"
            │
            ▼
    Results ranked by:
    - Dense vector similarity
    - Metadata filters (chunk_type:function, source_path:*auth*)
```

---

## Full Example

Save this as `scripts/code_aware_memory.py` and run it against any Python repo.

```python
"""
Secure, Code-Aware Episodic Memory with Chroma

Usage:
    python code_aware_memory.py ~/projects/myapp
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import chromadb

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ChunkType:
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    MARKDOWN_SECTION = "markdown_section"
    YAML_KEY = "yaml_key"
    JSON_KEY = "json_key"
    WINDOW = "window"


@dataclass(frozen=True)
class CodeChunk:
    content: str
    chunk_type: str
    start_line: int
    end_line: int
    source_path: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ChunkingConfig:
    max_chunk_tokens: int = 512
    overlap_tokens: int = 50

    @property
    def chars_per_chunk(self) -> int:
        return self.max_chunk_tokens * 4

    @property
    def overlap_chars(self) -> int:
        return self.overlap_tokens * 4


# ---------------------------------------------------------------------------
# Chunkers
# ---------------------------------------------------------------------------


def chunk_file(file_path: Path, config: ChunkingConfig | None = None) -> list[CodeChunk]:
    config = config or ChunkingConfig()
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

    out: list[CodeChunk] = []
    for c in chunks:
        out.append(CodeChunk(
            content=c.content,
            chunk_type=c.chunk_type,
            start_line=c.start_line,
            end_line=c.end_line,
            source_path=str(file_path),
            metadata=c.metadata,
        ))
    return [_redact(c) for c in out]


def _chunk_python(content: str, config: ChunkingConfig) -> list[CodeChunk]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _chunk_window(content, config)

    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    covered: set[int] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s, e = node.lineno, node.end_lineno or node.lineno
            chunks.append(CodeChunk(
                content="".join(lines[s - 1 : e]).rstrip(),
                chunk_type=ChunkType.FUNCTION,
                start_line=s, end_line=e,
                metadata={"name": node.name},
            ))
            covered.update(range(s, e + 1))

        elif isinstance(node, ast.ClassDef):
            s, e = node.lineno, node.end_lineno or node.lineno
            methods = [n for n in ast.iter_child_nodes(node)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if methods and (e - s + 1) * 25 > config.chars_per_chunk:
                for m in methods:
                    ms, me = m.lineno, m.end_lineno or m.lineno
                    chunks.append(CodeChunk(
                        content="".join(lines[ms - 1 : me]).rstrip(),
                        chunk_type=ChunkType.METHOD,
                        start_line=ms, end_line=me,
                        metadata={"class": node.name, "name": m.name},
                    ))
                    covered.update(range(ms, me + 1))
                fm = min(m.lineno for m in methods)
                if fm > s + 1:
                    hdr = "".join(lines[s - 1 : fm - 1])
                    if hdr.strip():
                        chunks.append(CodeChunk(
                            content=hdr.rstrip(), chunk_type=ChunkType.CLASS,
                            start_line=s, end_line=fm - 1,
                            metadata={"name": node.name},
                        ))
                covered.update(range(s, e + 1))
            else:
                chunks.append(CodeChunk(
                    content="".join(lines[s - 1 : e]).rstrip(),
                    chunk_type=ChunkType.CLASS,
                    start_line=s, end_line=e,
                    metadata={"name": node.name},
                ))
                covered.update(range(s, e + 1))

    # Module leftovers
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
            chunks.append(CodeChunk(
                content=txt, chunk_type=ChunkType.MODULE,
                start_line=mod_start, end_line=mod_start + len(mod) - 1,
            ))

    return chunks if chunks else _chunk_window(content, config)


def _chunk_markdown(content: str, _config: ChunkingConfig) -> list[CodeChunk]:
    pat = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    lines = content.split("\n")
    matches = list(pat.finditer(content))
    if not matches:
        return _chunk_window(content, _config)

    positions: list[tuple[int, str]] = []
    for m in matches:
        ln = content[: m.start()].count("\n") + 1
        positions.append((ln, m.group(0)))

    chunks: list[CodeChunk] = []
    for i, (ln, hdr) in enumerate(positions):
        end = positions[i + 1][0] - 1 if i + 1 < len(positions) else len(lines)
        section = "\n".join(lines[ln - 1 : end]).strip()
        if section:
            chunks.append(CodeChunk(
                content=section, chunk_type=ChunkType.MARKDOWN_SECTION,
                start_line=ln, end_line=end,
                metadata={"header": hdr.lstrip("#").strip()},
            ))

    if positions and positions[0][0] > 1:
        pre = "\n".join(lines[: positions[0][0] - 1]).strip()
        if pre:
            chunks.insert(0, CodeChunk(
                content=pre, chunk_type=ChunkType.MARKDOWN_SECTION,
                start_line=1, end_line=positions[0][0] - 1,
                metadata={"header": "preamble"},
            ))
    return chunks


def _chunk_yaml(content: str, _config: ChunkingConfig) -> list[CodeChunk]:
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

    chunks: list[CodeChunk] = []
    for i, (ln, key) in enumerate(keys):
        end = keys[i + 1][0] - 1 if i + 1 < len(keys) else len(lines)
        section = "\n".join(lines[ln - 1 : end]).strip()
        if section:
            chunks.append(CodeChunk(
                content=section, chunk_type=ChunkType.YAML_KEY,
                start_line=ln, end_line=end,
                metadata={"key": key},
            ))
    return chunks if chunks else _chunk_window(content, _config)


def _chunk_json(content: str, _config: ChunkingConfig) -> list[CodeChunk]:
    try:
        data = json.loads(content)
    except Exception:
        return _chunk_window(content, _config)

    if isinstance(data, dict):
        chunks: list[CodeChunk] = []
        for key, value in data.items():
            chunks.append(CodeChunk(
                content=json.dumps({key: value}, indent=2),
                chunk_type=ChunkType.JSON_KEY,
                start_line=1, end_line=1,
                metadata={"key": key},
            ))
        return chunks if chunks else _chunk_window(content, _config)
    return _chunk_window(content, _config)


def _chunk_window(content: str, config: ChunkingConfig) -> list[CodeChunk]:
    stride = max(1, config.chars_per_chunk - config.overlap_chars)
    chunks: list[CodeChunk] = []
    start = 0
    total = len(content)
    while start < total:
        end = min(start + config.chars_per_chunk, total)
        txt = content[start:end]
        sl = content[:start].count("\n") + 1
        el = content[:end].count("\n") + 1
        if txt.strip():
            chunks.append(CodeChunk(
                content=txt.strip(), chunk_type=ChunkType.WINDOW,
                start_line=sl, end_line=el,
            ))
        if end >= total:
            break
        start += stride
    return chunks


# ---------------------------------------------------------------------------
# Security: Credential Redaction
# ---------------------------------------------------------------------------

_CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("github_token", re.compile(r"ghp_[a-zA-Z0-9]{36,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("password", re.compile(r"password\s*[=:]\s*[^\s#]{3,}", re.IGNORECASE)),
    ("secret", re.compile(r"secret\s*[=:]\s*[^\s#]{3,}", re.IGNORECASE)),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]


def _redact(chunk: CodeChunk) -> CodeChunk:
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
    return CodeChunk(
        content="".join(parts), chunk_type=chunk.chunk_type,
        start_line=chunk.start_line, end_line=chunk.end_line,
        source_path=chunk.source_path, metadata=meta,
    )


# ---------------------------------------------------------------------------
# Chroma Store
# ---------------------------------------------------------------------------


class CodeMemoryStore:
    """Chroma-backed semantic store for code chunks."""

    def __init__(self, collection_name: str = "code_memory", persist_dir: str = "./chroma_db") -> None:
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[CodeChunk], session_tag: str = "") -> list[str]:
        """Store chunks. Returns inserted IDs."""
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for chunk in chunks:
            # Boost identifiers in embedding text for better retrieval
            boost = " ".join(
                v for k, v in chunk.metadata.items()
                if k in ("name", "class", "header", "key")
            )
            emb_text = f"{boost}\n{boost}\n{chunk.content}" if boost else chunk.content

            cid = _hash(emb_text + chunk.source_path)
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
            out.append({
                "content": doc,
                "distance": results["distances"][0][i],
                **meta,
            })
        return out


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Ingestion Pipeline
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
    import sys

    if len(sys.argv) < 2:
        print("Usage: python code_aware_memory.py <codebase_path> [session_tag]")
        sys.exit(1)

    target = Path(sys.argv[1]).expanduser().resolve()
    tag = sys.argv[2] if len(sys.argv) > 2 else "manual"

    store = CodeMemoryStore(persist_dir=str(target / ".chroma_db"))

    print(f"Indexing {target} ...")
    result = ingest_codebase(target, store, session_tag=tag)
    print(f"Stored {result['stored']} chunks, skipped {result['skipped']} unchanged files.")

    # Demo query
    print("\n--- Demo Query: 'authentication logic' ---")
    for hit in store.query("authentication logic", n_results=3):
        print(f"\n[{hit['chunk_type']}] {hit['source_path']}:{hit['start_line']}-{hit['end_line']}")
        print(hit["content"][:300] + "...")
```

---

## How It Works

### 1. AST-Aware Chunking

For Python files, we parse the AST and extract:
- **Functions** as standalone chunks with `metadata={"name": "func_name"}`
- **Classes** as either whole units (if small) or split into **methods** + a **header** chunk (if large)
- **Module-level** constants/imports as a single chunk

This means a query for `"validate_token"` surfaces the exact function, not the 800-line file it lives in.

### 2. Credential Redaction

Before storage, every chunk is scanned for:
- `sk-...` API keys
- `ghp_...` GitHub tokens
- `AKIA...` AWS keys
- `password=...`, `secret=...` assignments
- PEM private key blocks

Matches are replaced with `[REDACTED]` and metadata is tagged `_redacted: true`. This prevents secrets from ever entering the vector index.

### 3. Identifier Boosting

Chunks are embedded with identifiers repeated:

```python
emb_text = f"{func_name}\n{func_name}\n{chunk_content}"
```

This tells Chroma's dense encoder to weight the function/class name heavily, improving retrieval precision for symbol lookups.

### 4. Episodic Metadata

Every chunk carries:
- `ingested_at`: ISO timestamp
- `session_tag`: user-provided label (e.g. `"feature/auth-refactor"`)
- `source_path`, `start_line`, `end_line`: exact provenance

This enables queries like:

```python
store.query(
    "What changed in auth?",
    where={"session_tag": "feature/auth-refactor"},
)
```

---

## Query Patterns

### "Where is the function that handles JWT validation?"

```python
hits = store.query("JWT validation", n_results=5)
```

Returns function-level chunks ranked by cosine similarity.

### "Show me all markdown sections about deployment"

```python
hits = store.query(
    "deployment",
    where={"chunk_type": "markdown_section"},
)
```

Uses Chroma metadata filtering to scope the search.

### "What did I index in the auth refactor session?"

```python
hits = store.query(
    "authentication",
    where={"session_tag": "auth-refactor"},
)
```

Treats `session_tag` as an episodic label.

---

## Extending

### Add file-watching reindex

Use [watchdog](https://pypi.org/project/watchdog/) to trigger `ingest_codebase` on `*.py` changes:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ReindexHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            ingest_codebase(Path(event.src_path).parent, store, skip_existing=True)
```

### Add a web UI

Chroma's built-in `collection.peek()` and `collection.count()` make it trivial to build a streamlit dashboard:

```python
import streamlit as st

st.title("Code Memory")
q = st.text_input("Query")
if q:
    for hit in store.query(q, n_results=10):
        st.markdown(f"**{hit['source_path']}:{hit['start_line']}**")
        st.code(hit["content"])
```

---

## Security Checklist

Before production use:

- [ ] Review `_CREDENTIAL_PATTERNS` for your organization's secret formats
- [ ] Run `grep -r "REDACTED" .chroma_db/` after ingestion — zero matches expected
- [ ] Set `chroma` collection ACLs if using a shared persistent client
- [ ] Encrypt `persist_dir` at rest (Chroma stores raw documents in SQLite)

---

## See Also

- **Animus** — The full system this recipe was extracted from: [github.com/your-org/animus](https://github.com/your-org/animus)
- **Chroma Docs** — [docs.trychroma.com](https://docs.trychroma.com)
- **memboot** — The original experiment (archived): [github.com/your-org/memboot](https://github.com/your-org/memboot)
