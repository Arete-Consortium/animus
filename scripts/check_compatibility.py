#!/usr/bin/env python3
"""Validate that all Animus package versions satisfy the COMPATIBILITY_MATRIX.

Reads every pyproject.toml in packages/*/ and checks that declared
inter-package dependency ranges match the compatibility promise.

Exit codes:
    0 — all checks pass
    1 — version mismatch or invalid dependency range
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).parent.parent.resolve()
PACKAGES_DIR = REPO_ROOT / "packages"

# Map PyPI name → local directory name
PACKAGE_DIRS: dict[str, str] = {
    "animus-core": "core",
    "animus-forge": "forge",
    "animus-kernel": "kernel",
    "animus-bootstrap": "bootstrap",
    "animus-contracts": "contracts",
    "animus-types": "types",
    "animus-quorum": "quorum",
}

# Compatibility promise: consumer → [(required_package, min_version, max_version)]
COMPAT_PROMISE: dict[str, list[tuple[str, str, str]]] = {
    "animus-core": [
        ("animus-types", "0.1.0", "1.0.0"),
    ],
    "animus-forge": [
        ("animus-types", "0.1.0", "1.0.0"),
        ("animus-quorum", "1.1.0", "2.0.0"),
    ],
    "animus-bootstrap": [
        # Bootstrap depends on core and types at runtime but they are
        # currently vendored/implicit; no explicit pyproject.toml entries.
        # When explicit deps are added, uncomment these checks.
        # ("animus-core", "2.3.0", "3.0.0"),
        # ("animus-types", "0.1.0", "1.0.0"),
    ],
}


def _parse_version(version: str) -> tuple[int, int, int]:
    """Parse a semver string into a tuple."""
    parts = version.split(".")
    return tuple(int(p) for p in parts[:3])


def _version_in_range(version: str, min_version: str, max_version: str) -> bool:
    """Check if version satisfies min <= version < max."""
    v = _parse_version(version)
    min_v = _parse_version(min_version)
    max_v = _parse_version(max_version)
    return min_v <= v < max_v


def _extract_dep_version(dep_string: str, package_name: str) -> str | None:
    """Extract the pinned version from a dependency string like 'animus-types>=0.1.0,<1'."""
    # Normalize package name (replace underscores/hyphens)
    normalized = package_name.replace("-", "_")
    # Look for the package name at the start of the string
    if not dep_string.replace("-", "_").startswith(normalized):
        return None
    # Extract version specifiers
    match = re.search(r"([<>]=?|=)\s*([0-9]+\.[0-9]+\.[0-9]+)", dep_string)
    if match:
        return match.group(2)
    # Try without patch version
    match = re.search(r"([<>]=?|=)\s*([0-9]+\.[0-9]+)", dep_string)
    if match:
        return match.group(2) + ".0"
    return None


def _load_package_metadata(package_dir: Path) -> dict:
    """Load pyproject.toml and return project metadata."""
    pyproject_path = package_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return {}
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def _get_installed_versions() -> dict[str, str]:
    """Read current versions from all package pyproject.toml files."""
    versions: dict[str, str] = {}
    for pypi_name, dir_name in PACKAGE_DIRS.items():
        meta = _load_package_metadata(PACKAGES_DIR / dir_name)
        version = meta.get("project", {}).get("version")
        if version:
            versions[pypi_name] = version
    return versions


def _check_promise(versions: dict[str, str]) -> list[str]:
    """Validate that each consumer's deps satisfy the compatibility promise."""
    errors: list[str] = []

    for consumer, requirements in COMPAT_PROMISE.items():
        consumer_version = versions.get(consumer)
        if not consumer_version:
            errors.append(f"{consumer}: not found in packages/")
            continue

        # Load consumer's actual dependencies
        dir_name = PACKAGE_DIRS[consumer]
        meta = _load_package_metadata(PACKAGES_DIR / dir_name)
        deps = meta.get("project", {}).get("dependencies", [])

        for req_pkg, req_min, req_max in requirements:
            # Find the dependency declaration
            found = False
            for dep in deps:
                dep_norm = dep.replace("-", "_")
                req_norm = req_pkg.replace("-", "_")
                if dep_norm.startswith(req_norm):
                    found = True
                    dep_version = _extract_dep_version(dep, req_pkg)
                    if dep_version is None:
                        errors.append(f"{consumer}: cannot parse version from '{dep}'")
                        continue
                    if not _version_in_range(dep_version, req_min, req_max):
                        errors.append(
                            f"{consumer}: {req_pkg} version {dep_version} outside "
                            f"promised range [{req_min}, {req_max})"
                        )
                    break
            if not found:
                errors.append(f"{consumer}: missing dependency on {req_pkg}")

    return errors


def _check_version_alignment(versions: dict[str, str]) -> list[str]:
    """Warn when packages that should be close in version are wildly divergent."""
    errors: list[str] = []
    # Core and Forge are expected to be within 1 major version
    core_v = versions.get("animus-core", "0.0.0")
    forge_v = versions.get("animus-forge", "0.0.0")
    if abs(_parse_version(core_v)[0] - _parse_version(forge_v)[0]) > 1:
        errors.append(
            f"Version gap: animus-core {core_v} vs animus-forge {forge_v} "
            "(expected within 1 major version)"
        )
    return errors


def main() -> int:
    versions = _get_installed_versions()
    print(f"Packages found: {len(versions)}")
    for name, version in sorted(versions.items()):
        print(f"  {name:20s} {version}")
    print()

    promise_errors = _check_promise(versions)
    alignment_errors = _check_version_alignment(versions)
    all_errors = promise_errors + alignment_errors

    if all_errors:
        print("FAIL — compatibility violations found:")
        for err in all_errors:
            print(f"  ✗ {err}")
        return 1

    print("PASS — all compatibility checks satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
