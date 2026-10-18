"""
Shared types + cache for Lugh external-source adapters.

A `Source` produces a stream of `SourceItem`s. The `SourceCache` is a thin
SQLite dedup store keyed by a stable fingerprint (SHA-256 of source_id +
item_id), mirroring the pattern in `animus.lugh.cache.TranscriptCache` and
`tools/animus_sync.py`. Repeat fetches do not re-insert known items.

Stdlib-only. Fail-open on I/O — callers never need a try/except.

Default cache location: ~/.animus/lugh_sources.sqlite
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path("~/.animus/lugh_sources.sqlite").expanduser()

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    fingerprint       TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    seen_at           TEXT NOT NULL,
    published_at      TEXT,
    relevance_score   REAL,
    item_json         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_seen ON items(seen_at);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at);
"""


@dataclass
class SourceItem:
    """One harvested item from an external source.

    Canonical cross-source shape so downstream consumers (relevance scorer,
    supported-memory writer, synthesis persona) don't need to branch on source
    type.
    """

    source_id: str  # registered source key, e.g. "arxiv:cs.LG" / "hn:front_page"
    item_id: str  # stable id assigned by the source (paper id, story id, guid)
    title: str
    url: str
    published: datetime | None
    summary: str = ""  # short blurb — abstract / show notes snippet / comment
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_text: str = ""  # fuller body when available (abstract, full show notes)
    metadata: dict = field(default_factory=dict)  # source-specific extras

    @property
    def fingerprint(self) -> str:
        """Stable SHA-256 of (source_id, item_id). Used for dedup."""
        h = hashlib.sha256()
        h.update(self.source_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.item_id.encode("utf-8"))
        return h.hexdigest()


class Source(Protocol):
    """Anything that can produce SourceItems.

    Implementations live in sibling modules (arxiv.py, hn.py, podcasts.py).
    Each instance corresponds to one configured feed/query; the registry
    creates N instances for N configured feeds of a given kind.
    """

    source_id: str

    def fetch(self, limit: int | None = None) -> Iterable[SourceItem]: ...


class SourceCache:
    """SQLite-backed dedup store for SourceItems."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CACHE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False per Animus CLAUDE.md cross-thread pattern
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def seen(self, fingerprint: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM items WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return row is not None

    def put(self, item: SourceItem, relevance_score: float | None = None) -> bool:
        """Insert item if not already seen. Returns True if newly inserted."""
        if self.seen(item.fingerprint):
            return False
        self._conn.execute(
            "INSERT INTO items (fingerprint, source_id, item_id, seen_at, "
            "published_at, relevance_score, item_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item.fingerprint,
                item.source_id,
                item.item_id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                item.published.isoformat() if item.published else None,
                relevance_score,
                _item_to_json(item),
            ),
        )
        self._conn.commit()
        return True

    def put_many(
        self,
        items: Iterable[SourceItem],
        scorer: Scorer | None = None,
    ) -> dict[str, int]:
        """Insert new items, optionally scoring them. Returns counts dict."""
        inserted = skipped = 0
        for item in items:
            score = scorer.score(item) if scorer else None
            if self.put(item, relevance_score=score):
                inserted += 1
            else:
                skipped += 1
        return {"inserted": inserted, "skipped": skipped}

    def count(self, source_id: str | None = None) -> int:
        if source_id is None:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM items WHERE source_id = ?", (source_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def recent(
        self,
        source_id: str | None = None,
        limit: int = 50,
        min_score: float | None = None,
    ) -> list[SourceItem]:
        """Most-recently-seen items, optionally filtered by source and score."""
        where = []
        params: list = []
        if source_id is not None:
            where.append("source_id = ?")
            params.append(source_id)
        if min_score is not None:
            where.append("relevance_score >= ?")
            params.append(min_score)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT item_json FROM items {clause} "
            "ORDER BY COALESCE(published_at, seen_at) DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_item_from_json(r["item_json"]) for r in rows]


class Scorer(Protocol):
    """Anything that can score a SourceItem for relevance. 0.0–1.0."""

    def score(self, item: SourceItem) -> float: ...


def _item_to_json(item: SourceItem) -> str:
    d = asdict(item)
    if isinstance(d.get("published"), datetime):
        d["published"] = d["published"].isoformat()
    return json.dumps(d, separators=(",", ":"))


def _item_from_json(blob: str) -> SourceItem:
    d = json.loads(blob)
    pub = d.get("published")
    if isinstance(pub, str):
        try:
            d["published"] = datetime.fromisoformat(pub)
        except ValueError:
            d["published"] = None
    return SourceItem(**d)
