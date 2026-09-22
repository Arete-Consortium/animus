#!/usr/bin/env python3
"""Run and record the Golden Workflow benchmark (starter scaffold).

This script intentionally starts simple so teams can iterate quickly:
- verifies benchmark workflow file exists
- emits a benchmark metadata record
- defines the expected artifact path contract for CI integration
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

WORKFLOW_PATH = Path("packages/forge/workflows/benchmarks/golden_workflow.yaml")
ARTIFACT_DIR = Path("docs/metrics/artifacts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit golden workflow benchmark metadata")
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Optional output path. Defaults to "
            "docs/metrics/artifacts/golden_workflow_<timestamp>.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not WORKFLOW_PATH.exists():
        print(f"ERROR: missing workflow: {WORKFLOW_PATH}")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output if args.output else ARTIFACT_DIR / f"golden_workflow_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "benchmark": "golden_workflow",
        "version": 1,
        "timestamp_utc": ts,
        "workflow_path": str(WORKFLOW_PATH),
        "status": "scaffold_created",
        "next_step": "wire to forge runner + collect cost/quality/latency metrics",
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
