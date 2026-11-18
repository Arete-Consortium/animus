#!/usr/bin/env python3
"""Import explicitly approved files into Animus bootstrap SQLite memory.

Dry-run is the default. Use --apply only after reviewing the printed plan.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from animus_bootstrap.intelligence.memory_import import import_candidates_sync, load_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--source", action="append", required=True, type=Path)
    parser.add_argument("--type", required=True, choices=("episodic", "semantic", "procedural"))
    parser.add_argument("--apply", action="store_true", help="write after reviewing the plan")
    args = parser.parse_args()
    candidates = [load_candidate(path, args.type) for path in args.source]
    results = import_candidates_sync(args.db, candidates, apply=args.apply)
    print(json.dumps([result.__dict__ for result in results], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
