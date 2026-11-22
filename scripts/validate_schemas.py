#!/usr/bin/env python3
"""validate_schemas.py — CI gate for Animus JSON Schema contracts.

Checks:
  1. Every *.schema.json is valid Draft 2020-12 JSON Schema.
  2. Every schema declares a unique $id.
  3. Every $ref resolves to a known schema (no dangling refs).
  4. Every schema has a $schema declaration.
  5. Schema filenames match their $id basename.
  6. (NEW) Every schema has a corresponding generated Pydantic model
     in packages/types/ that is importable and structurally valid
     (JSON Schema → Pydantic gate).

Usage::

    python scripts/validate_schemas.py [contracts_dir] [--no-fail-fast]

Exit codes:
    0 — All checks passed.
    1 — One or more checks failed (exits on first failure by default).
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DEFAULT_CONTRACTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "contracts"
    / "src"
    / "animus_contracts"
    / "schemas"
)
REPO_ROOT = Path(__file__).resolve().parent.parent
TYPES_DIR = REPO_ROOT / "packages" / "types" / "src" / "animus_types"

_ERRORS: list[str] = []
_FAIL_FAST: bool = True


def _fail(msg: str) -> None:
    """Record an error and optionally exit immediately."""
    _ERRORS.append(msg)
    print(f"  [FAIL] {msg}", file=sys.stderr)
    if _FAIL_FAST:
        sys.exit(1)


def find_schemas(contracts_dir: Path) -> list[Path]:
    """Return all *.schema.json files in the contracts directory."""
    return sorted(contracts_dir.glob("*.schema.json"))


def load_schemas(schema_paths: list[Path]) -> dict[Path, dict]:
    """Load schemas, reporting line-accurate JSON errors."""
    loaded: dict[Path, dict] = {}
    for path in schema_paths:
        text = path.read_text(encoding="utf-8")
        try:
            loaded[path] = json.loads(text)
        except json.JSONDecodeError as e:
            # Line-accurate error: lineno, colno from JSONDecodeError
            _fail(f"{path.name}: Invalid JSON at line {e.lineno}, column {e.colno} — {e.msg}")
    return loaded


def check_schema_declaration(schemas: dict[Path, dict]) -> list[str]:
    """Ensure every schema has a $schema declaration."""
    errors: list[str] = []
    for path, data in schemas.items():
        if "$schema" not in data:
            errors.append(f"{path.name}: Missing $schema declaration")
    return errors


def check_unique_ids(schemas: dict[Path, dict]) -> list[str]:
    """Ensure every schema declares a unique $id."""
    errors: list[str] = []
    seen: dict[str, Path] = {}
    for path, data in schemas.items():
        sid = data.get("$id")
        if not sid:
            errors.append(f"{path.name}: Missing $id")
            continue
        if sid in seen:
            errors.append(f"{path.name}: Duplicate $id '{sid}' (also in {seen[sid].name})")
        else:
            seen[sid] = path
    return errors


def check_filename_matches_id(schemas: dict[Path, dict]) -> list[str]:
    """Ensure filename basename matches the $id basename."""
    errors: list[str] = []
    for path, data in schemas.items():
        sid = data.get("$id")
        if not sid:
            continue
        expected_name = sid.split("/")[-1]
        if path.name != expected_name:
            errors.append(f"{path.name}: Filename mismatch — $id expects '{expected_name}'")
    return errors


def check_valid_draft202012(schemas: dict[Path, dict]) -> list[str]:
    """Ensure every schema validates as Draft 2020-12."""
    errors: list[str] = []
    for path, data in schemas.items():
        try:
            Draft202012Validator.check_schema(data)
        except Exception as e:
            errors.append(f"{path.name}: Invalid Draft 2020-12 — {e}")
    return errors


def _collect_refs(data: dict | list, refs: set[str]) -> None:
    """Recursively collect all $ref values from a schema."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "$ref" and isinstance(value, str):
                refs.add(value)
            else:
                _collect_refs(value, refs)
    elif isinstance(data, list):
        for item in data:
            _collect_refs(item, refs)


def check_dangling_refs(schemas: dict[Path, dict]) -> list[str]:
    """Ensure every $ref resolves to a known schema $id or local fragment."""
    errors: list[str] = []
    ids = {data.get("$id") for data in schemas.values() if data.get("$id")}

    for path, data in schemas.items():
        refs: set[str] = set()
        _collect_refs(data, refs)
        base_id = data.get("$id", "")

        for ref in refs:
            # Local fragment refs — always valid within the same schema
            if ref.startswith("#"):
                continue

            # Resolve relative refs against base $id
            if base_id and "/" in base_id:
                base = base_id.rsplit("/", 1)[0] + "/"
                resolved = ref if "://" in ref else base + ref
            else:
                resolved = ref

            if resolved not in ids:
                errors.append(f"{path.name}: Dangling $ref '{ref}' (resolved: '{resolved}')")

    return errors


# ---------------------------------------------------------------------------
# JSON Schema → Pydantic gate
# ---------------------------------------------------------------------------

# Pre-built minimal valid payloads for representative schemas.
# These are hand-crafted to satisfy field-level constraints (patterns,
# minLength, datetime formats, enums, etc.).
_MINIMAL_PAYLOADS: dict[str, dict[str, Any]] = {
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
            "idempotency_key": "idemp-1234",
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
            "actor_refs": ["user-1"],
            "object_refs": ["session-1"],
            "event_data": {"ip": "127.0.0.1"},
        },
    },
}


def _schema_name_to_class_name(name: str) -> str | None:
    """Map schema basename (e.g. 'action') to expected Pydantic class name."""
    special = {
        "action": "AnimusActionObject",
        "action_receipt": "AnimusActionReceipt",
        "approval_receipt": "AnimusApprovalReceipt",
        "assessment": "DissentItem",
        "capability_grant": "Budget",
        "claim": "AnimusClaimObject",
        "context_envelope": "Contradiction",
        "decision": "AnimusDecisionObject",
        "entity": "AnimusEntityObject",
        "event": "AnimusEventObject",
        "forecast": "AnimusForecastObject",
        "hypothesis": "AnimusHypothesisObject",
        "knowledge_edge": "AnimusKnowledgeEdge",
        "ledger_event": "LedgerEvent",
        "lesson": "AnimusLessonObject",
        "memory_candidate": "AnimusMemoryCandidate",
        "object_version": "ObjectVersion",
        "observation": "AnimusObservationObject",
        "outbox_entry": "OutboxEntry",
        "outcome": "AnimusOutcomeObject",
        "pattern": "AnimusPatternObject",
        "policy_decision": "Obligation",
        "signal": "AnimusSignalObject",
        "source": "AnimusSourceObject",
        "trace": "AnimusTraceBundle",
    }
    return special.get(name)


def check_pydantic_models(schemas: dict[Path, dict]) -> list[str]:
    """Validate that each schema has a corresponding importable Pydantic model.

    For representative schemas with known minimal payloads, also validates
    that the model can instantiate the payload (round-trip gate).
    """
    errors: list[str] = []
    sys.path.insert(0, str(TYPES_DIR.parent))

    for path, data in schemas.items():
        # Skip common.schema.json (it's a base, not a standalone object)
        if path.name == "common.schema.json":
            continue

        module_name = path.stem.replace(".schema", "").replace("_schema", "")
        class_name = _schema_name_to_class_name(module_name)
        if not class_name:
            errors.append(f"{path.name}: No Pydantic class mapping found")
            continue

        # Try importing the module
        try:
            mod = __import__(f"animus_types.{module_name}", fromlist=[class_name])
            model_cls = getattr(mod, class_name, None)
            if model_cls is None:
                errors.append(
                    f"{path.name}: Class '{class_name}' not found in animus_types.{module_name}"
                )
                continue
        except ImportError as exc:
            errors.append(f"{path.name}: Cannot import animus_types.{module_name} ({exc})")
            continue

        # Verify the class is a Pydantic model (has model_validate)
        if not (inspect.isclass(model_cls) and hasattr(model_cls, "model_validate")):
            errors.append(
                f"{path.name}: {class_name} is not a Pydantic BaseModel (missing model_validate)"
            )
            continue

        # If we have a minimal payload for this schema, validate it
        if module_name in _MINIMAL_PAYLOADS:
            payload = _MINIMAL_PAYLOADS[module_name]
            try:
                model_cls.model_validate(payload)
            except Exception as exc:
                errors.append(
                    f"{path.name}: Pydantic validation failed for minimal payload — {exc}"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Animus JSON Schema validation gate")
    parser.add_argument(
        "contracts_dir",
        nargs="?",
        default=DEFAULT_CONTRACTS_DIR,
        help="Directory containing *.schema.json files",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Collect all errors instead of exiting on first failure",
    )
    args = parser.parse_args()

    global _FAIL_FAST
    _FAIL_FAST = not args.no_fail_fast

    contracts_dir = Path(args.contracts_dir)

    print(f"Schema Validation — {contracts_dir}")
    print("=" * 50)

    schema_paths = find_schemas(contracts_dir)
    print(f"Schemas found: {len(schema_paths)}")

    schemas = load_schemas(schema_paths)
    if len(schemas) != len(schema_paths):
        print(f"  [FAIL] {len(schema_paths) - len(schemas)} file(s) could not be loaded.")
        if _FAIL_FAST:
            return 1

    all_errors: list[str] = []

    print("\n1. Checking $schema declarations...")
    errors = check_schema_declaration(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print("\n2. Checking unique $id declarations...")
    errors = check_unique_ids(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print("\n3. Checking filename ↔ $id alignment...")
    errors = check_filename_matches_id(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print("\n4. Checking Draft 2020-12 validity...")
    errors = check_valid_draft202012(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print("\n5. Checking for dangling $refs...")
    errors = check_dangling_refs(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print("\n6. Checking JSON Schema → Pydantic compilation...")
    errors = check_pydantic_models(schemas)
    all_errors.extend(errors)
    for e in errors:
        _fail(e)
    print(f"  {'PASS' if not errors else f'{len(errors)} FAIL'}")

    print(f"\n{'=' * 50}")
    if all_errors:
        print(f"RESULT: FAIL — {len(all_errors)} issue(s) found.")
        return 1
    print(f"RESULT: PASS — {len(schemas)} schema(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
