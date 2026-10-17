#!/usr/bin/env python3
"""Coverage ratchet — fail the build if coverage drops below baseline.

Usage::

    python scripts/coverage-ratchet.py <package> [<package> ...]

Each package needs a ``.coverage-baseline.json`` file in the repo root with a
mapping ``{package: {allowed: N, directory: "path/to/tests"}}``.

The script runs pytest with coverage, extracts the percentage, and compares
against the stored baseline.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASELINE_FILE = Path(__file__).resolve().parent.parent / ".coverage-baseline.json"


def run_coverage(package_dir: str, source: str) -> float:
    # Ensure the package under test is importable
    src_dir = str(Path(source).parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    json_path = "/tmp/coverage-ratchet.json"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        package_dir,
        "-q",
        "--tb=short",
        f"--cov={source}",
        f"--cov-report=json:{json_path}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # Parse JSON report
    try:
        data = json.loads(Path(json_path).read_text())
        totals = data.get("totals", {})
        covered = totals.get("covered_lines", 0)
        total = totals.get("num_statements", 0)
        if total:
            return round((covered / total) * 100, 1)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    # Fallback: try the terminal total line
    for line in reversed(result.stdout.splitlines()):
        m = re.search(r"TOTAL\s+[\d\s]+(\d+)%", line)
        if m:
            return float(m.group(1))
    print(f"Could not extract coverage percentage for {package_dir}")
    print("stdout tail:", result.stdout[-500:])
    print("stderr tail:", result.stderr[-500:])
    return 0.0


def report_coverage(path: Path) -> float:
    """Read the report from the preceding successful test step."""
    data = json.loads(path.read_text())
    totals = data["totals"]
    covered = totals["covered_lines"]
    total = totals["num_statements"]
    if (
        not isinstance(total, int)
        or not isinstance(covered, int)
        or not 0 <= covered <= total
        or total == 0
    ):
        raise ValueError("Invalid coverage totals")
    return round(covered / total * 100, 1)


def main(argv: list[str]) -> int:
    report = None
    if argv and argv[0] == "--report":
        if len(argv) != 3:
            print("Usage: coverage-ratchet.py --report REPORT.json PACKAGE")
            return 1
        report = Path(argv[1])
        argv = argv[2:]
    if not BASELINE_FILE.exists():
        print(f"Baseline file not found: {BASELINE_FILE}")
        print("Create it with: python scripts/coverage-ratchet.py --init")
        return 1

    with BASELINE_FILE.open() as fh:
        baseline: dict[str, dict[str, str | int | float]] = json.load(fh)

    if not argv or argv[0] == "--init":
        for pkg, cfg in baseline.items():
            cfg["allowed"] = run_coverage(str(cfg["directory"]), str(cfg.get("source", ".")))
        with BASELINE_FILE.open("w") as fh:
            json.dump(baseline, fh, indent=2)
        print("Re-baselined coverage percentages.")
        return 0

    failed = False
    for pkg in argv:
        cfg = baseline.get(pkg)
        if cfg is None:
            print(f"[SKIP] No baseline for package '{pkg}'")
            continue
        allowed = float(cfg["allowed"])
        directory = str(cfg["directory"])
        source = str(cfg.get("source", "."))
        try:
            actual = (
                report_coverage(report) if report is not None else run_coverage(directory, source)
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"[FAIL] {pkg}: invalid or missing coverage report: {exc}")
            failed = True
            continue
        delta = actual - allowed
        if actual < allowed:
            print(f"[FAIL] {pkg}: {actual:.1f}% coverage (allowed {allowed:.1f}%, {delta:+.1f}%)")
            failed = True
        else:
            status = f"{delta:+.1f}%" if delta > 0 else "at limit"
            print(f"[PASS] {pkg}: {actual:.1f}% coverage (allowed {allowed:.1f}%, {status})")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
