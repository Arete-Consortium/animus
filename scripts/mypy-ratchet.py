#!/usr/bin/env python3
"""Run mypy and enforce the existing per-package error-count allowances.

The ratchet is the single type gate; each invocation saves complete diagnostics.
Infrastructure failures and unknown packages fail closed. ``--init`` may only
lower existing allowances, never increase them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = Path(__file__).with_name(".mypy-baseline.json")
# Keep the options used to measure the recorded baseline in one place.
MYPY_OPTIONS = [
    "--ignore-missing-imports",
    "--no-error-summary",
    "--no-pretty",
    "--no-color-output",
]


def count_errors(directory: str, report: Path | None = None) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", directory, *MYPY_OPTIONS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    diagnostics = result.stdout + result.stderr
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(diagnostics)
    print(diagnostics, end="")
    count = sum(": error:" in line for line in diagnostics.splitlines())
    if result.returncode not in (0, 1) or (result.returncode == 1 and count == 0):
        raise RuntimeError(f"mypy failed to check {directory} (exit {result.returncode})")
    return count


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: mypy-ratchet.py core kernel forge bootstrap | --init")
        return 1
    if not BASELINE_FILE.exists():
        print(f"Ratchet baseline file not found: {BASELINE_FILE}")
        return 1
    baseline = json.loads(BASELINE_FILE.read_text())
    initialize = argv == ["--init"]
    packages = list(baseline) if initialize else argv
    failed = False
    for pkg in packages:
        if pkg not in baseline:
            print(f"[FAIL] No baseline for package '{pkg}'")
            failed = True
            continue
        cfg = baseline[pkg]
        allowed = int(cfg["allowed"])
        try:
            actual = count_errors(cfg["directory"], ROOT / "packages" / pkg / "mypy-report.txt")
        except (OSError, RuntimeError) as exc:
            print(f"[FAIL] {pkg}: {exc}")
            failed = True
            continue
        if actual > allowed:
            print(f"[FAIL] {pkg}: {actual} errors (allowed {allowed}, +{actual - allowed})")
            failed = True
        else:
            print(f"[PASS] {pkg}: {actual} errors (allowed {allowed})")
            if initialize:
                cfg["allowed"] = actual
    if initialize and not failed:
        BASELINE_FILE.write_text(json.dumps(baseline, indent=2) + "\n")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
