"""
Retrieval evaluation harness for the Animus memory layer.

Pure-functional measurement of how well a `MemoryStore` implementation
returns the right memories for a query. No test-framework coupling —
can be called from unit tests, from a CLI, or from CI as a metric gate.

Metrics computed:

- **Precision@k:** fraction of top-k retrieved IDs that are relevant.
- **Recall@k:** fraction of relevant IDs that appear in the top-k.
- **MRR (Mean Reciprocal Rank):** 1/rank of first relevant hit, averaged
  across queries. Rewards systems that rank the right answer high.

The fixture format (see `fixtures/memory_eval_corpus.json`) is:

    {
      "memories": [ {Memory.to_dict()...}, ... ],
      "queries":  [
        {
          "id":          "q-01",
          "query":       "arete project portfolio",
          "expected_ids": ["mem-001", "mem-007"],
          "notes":       "semantic match on 'arete'",
          "memory_type": null,    # optional filter
          "tags":        null,    # optional filter
          "k":           5        # optional override
        },
        ...
      ]
    }

Call `evaluate(store, fixture)` to get a `EvaluationResult` with per-query
breakdowns and aggregate scores.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from animus.memory.types import Memory, MemoryType


@dataclass
class LabeledQuery:
    """One evaluation query with ground-truth expected hits."""

    id: str
    query: str
    expected_ids: list[str]
    notes: str = ""
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    k: int = 5


@dataclass
class Fixture:
    """A corpus + labeled queries bundle."""

    memories: list[Memory]
    queries: list[LabeledQuery]


@dataclass
class QueryResult:
    """Metrics for one query."""

    query_id: str
    query: str
    retrieved_ids: list[str]
    expected_ids: list[str]
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float


@dataclass
class EvaluationResult:
    """Aggregate metrics + per-query detail."""

    store_name: str
    corpus_size: int
    query_count: int
    precision_at_k: float  # mean across queries
    recall_at_k: float  # mean across queries
    mrr: float  # mean reciprocal rank
    k: int
    per_query: list[QueryResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def summary_line(self) -> str:
        return (
            f"{self.store_name:20s}  corpus={self.corpus_size:4d}  "
            f"q={self.query_count:3d}  "
            f"P@{self.k}={self.precision_at_k:.3f}  "
            f"R@{self.k}={self.recall_at_k:.3f}  "
            f"MRR={self.mrr:.3f}"
        )


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def precision_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """Fraction of the top-k retrieved that are in the expected set."""
    if k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for mid in top_k if mid in expected_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """Fraction of expected IDs that appear in top-k retrieved."""
    if not expected_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = sum(1 for mid in expected_ids if mid in top_k)
    return hits / len(expected_ids)


def reciprocal_rank(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """1 / rank of the first expected ID in retrieved. 0 if none present."""
    expected_set = set(expected_ids)
    for rank, mid in enumerate(retrieved_ids, start=1):
        if mid in expected_set:
            return 1.0 / rank
    return 0.0


# --------------------------------------------------------------------------- #
# Fixture loading
# --------------------------------------------------------------------------- #


def load_fixture(path: Path) -> Fixture:
    """Load corpus + labeled queries from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    memories = [Memory.from_dict(m) for m in data["memories"]]
    queries = []
    for q in data["queries"]:
        mt_raw = q.get("memory_type")
        queries.append(
            LabeledQuery(
                id=q["id"],
                query=q["query"],
                expected_ids=list(q["expected_ids"]),
                notes=q.get("notes", ""),
                memory_type=MemoryType(mt_raw) if mt_raw else None,
                tags=q.get("tags"),
                k=int(q.get("k", 5)),
            )
        )
    return Fixture(memories=memories, queries=queries)


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def evaluate(
    store,
    fixture: Fixture,
    store_name: str | None = None,
    fetch_limit_multiplier: int = 2,
) -> EvaluationResult:
    """Load fixture into store, run every query, compute metrics.

    NOTE: mutates store by inserting fixture memories. Use a fresh store
    instance (for example, a temp directory for ``LocalMemoryStore``). The
    legacy Chroma adapter may be evaluated only in an isolated migration
    environment with an independently reviewed dependency.

    Args:
        store: Any MemoryStore implementation.
        fixture: Loaded fixture.
        store_name: Label for the result row. Defaults to store's class name.
        fetch_limit_multiplier: Request k*multiplier hits to leave room for
            post-filtering; most stores do this internally already.

    Returns:
        EvaluationResult with aggregate + per-query metrics.
    """
    for memory in fixture.memories:
        store.store(memory)

    per_query: list[QueryResult] = []
    max_k = 0

    for q in fixture.queries:
        max_k = max(max_k, q.k)
        retrieved = store.search(
            q.query,
            memory_type=q.memory_type,
            tags=q.tags,
            limit=q.k * fetch_limit_multiplier,
        )
        retrieved_ids = [m.id for m in retrieved]
        per_query.append(
            QueryResult(
                query_id=q.id,
                query=q.query,
                retrieved_ids=retrieved_ids[:20],  # cap detail output
                expected_ids=list(q.expected_ids),
                precision_at_k=precision_at_k(retrieved_ids, q.expected_ids, q.k),
                recall_at_k=recall_at_k(retrieved_ids, q.expected_ids, q.k),
                reciprocal_rank=reciprocal_rank(retrieved_ids, q.expected_ids),
            )
        )

    n = len(per_query)
    mean_p = sum(r.precision_at_k for r in per_query) / n if n else 0.0
    mean_r = sum(r.recall_at_k for r in per_query) / n if n else 0.0
    mrr = sum(r.reciprocal_rank for r in per_query) / n if n else 0.0

    return EvaluationResult(
        store_name=store_name or store.__class__.__name__,
        corpus_size=len(fixture.memories),
        query_count=n,
        precision_at_k=round(mean_p, 4),
        recall_at_k=round(mean_r, 4),
        mrr=round(mrr, 4),
        k=max_k,
        per_query=per_query,
    )
