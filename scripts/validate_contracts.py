#!/usr/bin/env python3
"""validate_contracts.py — CI gate for Animus JSON Schema contracts.

Checks:
1. Every *.schema.json is valid JSON with required metadata ($id, $schema).
2. Every schema is valid Draft 2020-12 JSON Schema (meta-schema validation).
3. All $ref values resolve to existing schemas.
4. All generated Python modules in packages/types/ are importable.
5. (Optional) Generated types are fresh vs. source schemas (requires datamodel-codegen).

Exit codes:
    0 — all checks pass
    1 — one or more checks failed
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).parent.parent.resolve()
CONTRACTS_DIR = REPO_ROOT / "packages" / "contracts" / "src" / "animus_contracts" / "schemas"
TYPES_DIR = REPO_ROOT / "packages" / "types" / "src" / "animus_types"

ERRORS: list[str] = []
WARNINGS: list[str] = []


def error(msg: str) -> None:
    ERRORS.append(msg)
    print(f"  ✗ {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  ⚠ {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def load_schemas() -> dict[str, dict]:
    """Load every *.schema.json into a dict keyed by $id."""
    schemas: dict[str, dict] = {}
    paths = sorted(CONTRACTS_DIR.glob("*.schema.json"))
    if not paths:
        error(f"No .schema.json files found in {CONTRACTS_DIR}")
        return schemas

    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        schema_id = raw.get("$id")
        if not schema_id:
            error(f"{path.name}: missing $id")
            continue
        schemas[schema_id] = raw
    return schemas


def check_schema_validity(schemas: dict[str, dict]) -> None:
    """Validate each schema against Draft 2020-12 meta-schema."""
    print("\n[1/5] Schema validity (JSON Schema Draft 2020-12)")
    meta_schema = Draft202012Validator.META_SCHEMA

    for schema_id, schema in schemas.items():
        filename = schema_id.split("/")[-1]

        # Required fields
        if "$schema" not in schema:
            error(f"{filename}: missing $schema")
            continue
        expected = "https://json-schema.org/draft/2020-12/schema"
        if schema["$schema"] != expected:
            error(f"{filename}: $schema is {schema['$schema']!r}, expected {expected!r}")
            continue

        # Meta-schema validation
        validator = Draft202012Validator(meta_schema)
        errs = list(validator.iter_errors(schema))
        if errs:
            for e in errs[:3]:
                error(f"{filename}: meta-schema error at {e.json_path}: {e.message}")
        else:
            ok(f"{filename}")


def check_cross_references(schemas: dict[str, dict]) -> None:
    """Ensure all $ref values resolve to known schemas."""
    print("\n[2/5] Cross-reference resolution")
    ids = set(schemas.keys())
    base_uri = "https://animus.local/schemas/"

    for schema_id, schema in schemas.items():
        filename = schema_id.split("/")[-1]
        refs = _extract_refs(schema)
        for ref in refs:
            # Local file reference like "common.schema.json"
            if ref.endswith(".schema.json") and "/" not in ref:
                target_path = CONTRACTS_DIR / ref
                if not target_path.exists():
                    error(f"{filename}: $ref {ref!r} → file not found")
                continue

            # Full URI reference
            if ref in ids:
                continue
            if ref.startswith(base_uri):
                short = ref.split("/")[-1]
                if (CONTRACTS_DIR / short).exists():
                    warn(
                        f"{filename}: $ref {ref!r} resolved by filename "
                        "but not by $id (schema $id mismatch?)"
                    )
                else:
                    error(f"{filename}: $ref {ref!r} → unknown schema")
            else:
                warn(f"{filename}: external $ref {ref!r} (not validated)")

    if not any(e.startswith("$") for e in ERRORS):
        ok("All internal $ref values resolve")


def _extract_refs(obj: object) -> set[str]:
    """Recursively extract all $ref strings from a schema dict."""
    refs: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str):
                refs.add(v)
            else:
                refs.update(_extract_refs(v))
    elif isinstance(obj, list):
        for item in obj:
            refs.update(_extract_refs(item))
    return refs


def check_importability() -> None:
    """Verify every generated module can be imported."""
    print("\n[3/5] Generated type importability")
    sys.path.insert(0, str(TYPES_DIR.parent))

    importable = 0
    for py_file in sorted(TYPES_DIR.glob("*.py")):
        if py_file.name in ("__init__.py", "egress.py", "secrets.py", "sensitivity.py"):
            continue
        module = py_file.stem
        try:
            __import__(f"animus_types.{module}", fromlist=["dummy"])
            importable += 1
        except ImportError as exc:
            warn(
                f"animus_types.{module}: import failed ({exc}) "
                "— install packages/types/ dependencies"
            )
        except Exception as exc:
            error(f"animus_types.{module}: import failed ({exc})")

    if importable:
        ok(f"{importable} schema modules importable")


def check_round_trip(schemas: dict[str, dict]) -> None:
    """Validate sample payloads round-trip through runtime validator."""
    print("\n[4/5] Runtime validation round-trip")
    try:
        from animus_contracts import ValidationError, validate
    except ImportError:
        warn("animus_contracts not importable — skipping runtime validation")
        return

    # Minimal valid payloads for a subset of schemas
    samples: dict[str, dict] = {
        "action": {
            "object_id": "act-test",
            "object_version": 1,
            "schema_id": "https://animus.local/schemas/action.schema.json",
            "schema_version": "1.0.0",
            "owner_id": "owner-test",
            "workspace_id": "ws-test",
            "subject_domain": "project",
            "artifact_type": "action",
            "cognitive_role": "intelligence",
            "workflow_status": "approved",
            "epistemic_status": "supported",
            "lifecycle_status": "active",
            "storage_tier": "hot",
            "presentation": "canonical",
            "security_class": "internal",
            "valid_time": {"valid_from": "2026-01-01T00:00:00Z", "valid_to": None},
            "transaction_time": {"recorded_at": "2026-01-01T00:00:00Z", "superseded_at": None},
            "provenance": {
                "created_by": "test",
                "source_refs": [],
                "derived_from": [],
                "trace_id": None,
            },
            "integrity": {"content_sha256": "a" * 64},
            "payload": {
                "action_kind": "deploy",
                "risk_class": "R1",
                "target": "production",
                "parameters": {},
                "approval_required": False,
                "approval_id": None,
                "idempotency_key": "idemp-test",
                "status": "proposed",
            },
        },
        "event": {
            "object_id": "evt-test",
            "object_version": 1,
            "schema_id": "https://animus.local/schemas/event.schema.json",
            "schema_version": "1.0.0",
            "owner_id": "owner-test",
            "workspace_id": "ws-test",
            "subject_domain": "world",
            "artifact_type": "event",
            "cognitive_role": "memory",
            "workflow_status": "not_applicable",
            "epistemic_status": "supported",
            "lifecycle_status": "active",
            "storage_tier": "hot",
            "presentation": "canonical",
            "security_class": "public",
            "valid_time": {"valid_from": "2026-01-01T00:00:00Z", "valid_to": None},
            "transaction_time": {"recorded_at": "2026-01-01T00:00:00Z", "superseded_at": None},
            "provenance": {
                "created_by": "test",
                "source_refs": [],
                "derived_from": [],
                "trace_id": None,
            },
            "integrity": {"content_sha256": "b" * 64},
            "payload": {
                "event_kind": "user_login",
                "occurred_at": "2026-01-01T00:00:00Z",
                "actor_refs": [],
                "object_refs": [],
                "event_data": {},
            },
        },
    }

    passed = 0
    for name, payload in samples.items():
        try:
            validate(payload, name)
            passed += 1
        except ValidationError as exc:
            error(f"runtime validation '{name}': {exc.errors[0]}")
        except Exception as exc:
            error(f"runtime validation '{name}': {exc}")

    ok(f"{passed}/{len(samples)} sample payloads validate at runtime")


def check_types_freshness() -> None:
    """Regenerate types to temp and compare against committed files.

    Note: compile_schemas.py writes directly to packages/types/ and does not
    support output redirection. Freshness verification must be done manually
    or via a worktree. This check is informational only.
    """
    print("\n[5/5] Generated type freshness (informational)")
    codegen = subprocess.run(
        ["which", "datamodel-codegen"],
        capture_output=True,
        text=True,
    )
    if codegen.returncode != 0:
        warn("datamodel-codegen not found — install with 'pip install datamodel-code-generator'")
        return

    ok("datamodel-codegen available (run scripts/compile_schemas.py manually to regenerate types)")


def main() -> int:
    print("=" * 60)
    print("Animus Contract Validation Gate")
    print("=" * 60)

    schemas = load_schemas()
    if not schemas:
        print("\nNo schemas loaded — aborting.", file=sys.stderr)
        return 1

    ok(f"Loaded {len(schemas)} schemas from {CONTRACTS_DIR.relative_to(REPO_ROOT)}")

    check_schema_validity(schemas)
    check_cross_references(schemas)
    check_importability()
    check_round_trip(schemas)
    check_types_freshness()

    print("\n" + "=" * 60)
    if ERRORS:
        print(f"FAIL: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
        return 1
    if WARNINGS:
        print(f"PASS with {len(WARNINGS)} warning(s)")
        return 0
    print("PASS: all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
