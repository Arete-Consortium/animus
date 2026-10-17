#!/usr/bin/env python3
"""
Run the Animus memory retrieval evaluation harness.

Evaluates any available MemoryStore implementation against the labeled
fixture at packages/core/tests/fixtures/memory_eval_corpus.json. Prints
aggregate precision@k / recall@k / MRR plus per-query breakdown.

Usage:
    python tools/memory_eval.py                    # Supported local backend
    python tools/memory_eval.py --backend local    # Just Local
    python tools/memory_eval.py --backend chroma   # Legacy isolated migration check
    python tools/memory_eval.py --json             # Machine-readable output
    python tools/memory_eval.py --show-queries     # Per-query detail
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "packages", "core")
if os.path.isdir(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, os.path.realpath(_CORE_DIR))

from animus.memory import LocalMemoryStore  # noqa: E402
from animus.memory.evaluation import evaluate, load_fixture  # noqa: E402

DEFAULT_FIXTURE = (
    Path(__file__).parent.parent
    / "packages"
    / "core"
    / "tests"
    / "fixtures"
    / "memory_eval_corpus.json"
)


def _build_chroma_store(tmp_path: Path):
    """Return a ChromaMemoryStore instance or None if ChromaDB is unavailable."""
    try:
        from animus.memory import ChromaMemoryStore

        return ChromaMemoryStore(tmp_path)
    except ImportError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Animus memory retrieval eval harness")
    ap.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to fixture JSON (default: bundled fixture)",
    )
    ap.add_argument(
        "--backend",
        choices=["local", "chroma", "both"],
        default="local",
        help="Store to evaluate (default: supported local backend; Chroma is migration-only)",
    )
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ap.add_argument("--show-queries", action="store_true", help="Include per-query breakdown")
    args = ap.parse_args(argv)

    if not args.fixture.exists():
        print(f"Fixture not found: {args.fixture}", file=sys.stderr)
        return 1

    fixture = load_fixture(args.fixture)
    results = []

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        if args.backend in ("local", "both"):
            local_store = LocalMemoryStore(td_path / "local")
            results.append(evaluate(local_store, fixture, store_name="LocalMemoryStore"))

        if args.backend in ("chroma", "both"):
            chroma = _build_chroma_store(td_path / "chroma")
            if chroma is None:
                if args.backend == "chroma":
                    print("ChromaMemoryStore unavailable (chromadb not installed)", file=sys.stderr)
                    return 1
            else:
                results.append(evaluate(chroma, fixture, store_name="ChromaMemoryStore"))

    if args.json:
        payload = {
            "fixture": str(args.fixture),
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"\nAnimus memory eval  —  fixture: {args.fixture.name}")
    print(f"  {'store':20s}  {'corpus':>7s}  {'q':>3s}  {'P@k':>6s}  {'R@k':>6s}  {'MRR':>6s}")
    print(f"  {'-' * 20}  {'-' * 7}  {'-' * 3}  {'-' * 6}  {'-' * 6}  {'-' * 6}")
    for r in results:
        print(
            f"  {r.store_name:20s}  {r.corpus_size:>7d}  {r.query_count:>3d}  "
            f"{r.precision_at_k:>6.3f}  {r.recall_at_k:>6.3f}  {r.mrr:>6.3f}"
        )

    if args.show_queries:
        for r in results:
            print(f"\n  --- {r.store_name} per-query ---")
            for q in r.per_query:
                hit_marker = "✓" if q.reciprocal_rank > 0 else "✗"
                print(
                    f"    {hit_marker} {q.query_id}  P@k={q.precision_at_k:.2f}  "
                    f"R@k={q.recall_at_k:.2f}  RR={q.reciprocal_rank:.2f}  "
                    f"  {q.query!r}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
