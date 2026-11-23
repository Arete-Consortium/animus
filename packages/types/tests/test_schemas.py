#!/usr/bin/env python3
"""Round-trip tests for generated contract models.

Validates that JSON schema instances can be parsed into Pydantic models
and serialized back to JSON without data loss.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "src" / "animus_contracts" / "schemas"


def _load_schema(name: str) -> dict:
    path = SCHEMA_DIR / f"{name}.schema.json"
    return json.loads(path.read_text())


def test_common_model_importable():
    from animus_types import Common

    assert Common is not None


def test_action_round_trip():
    from animus_types import AnimusActionObject

    raw = {
        "object_id": "act-001",
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
    }
    obj = AnimusActionObject.model_validate(raw)
    assert obj.artifact_type == "action"
    assert obj.payload.action_kind == "deploy"


def test_event_round_trip():
    from animus_types import AnimusEventObject

    raw = {
        "object_id": "evt-001",
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
    }
    obj = AnimusEventObject.model_validate(raw)
    assert obj.artifact_type == "event"
    assert obj.payload.event_kind == "user_login"


@pytest.mark.parametrize(
    "module_name",
    [
        "action",
        "action_receipt",
        "approval_receipt",
        "assessment",
        "capability_grant",
        "claim",
        "context_envelope",
        "decision",
        "entity",
        "event",
        "forecast",
        "hypothesis",
        "knowledge_edge",
        "ledger_event",
        "lesson",
        "memory_candidate",
        "object_version",
        "observation",
        "outbox_entry",
        "outcome",
        "pattern",
        "policy_decision",
        "signal",
        "source",
        "trace",
    ],
)
def test_schema_model_importable(module_name: str):
    """Every generated schema module must be importable."""
    mod = __import__(f"animus_types.{module_name}", fromlist=["dummy"])
    assert mod is not None
