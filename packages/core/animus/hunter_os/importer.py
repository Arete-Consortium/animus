"""Operator-only reviewed staging into SQL; this API cannot approve Hunter facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from animus.durability.batch import BatchChange, BatchResult, apply_batch, record_fingerprint
from animus.durability.postgres_store import ConcurrencyError, DurableObjectStore, ObjectRecord
from animus.durability.schema import SchemaCompatibilityError
from animus.durability.scope import ObjectScope
from animus.hunter_os.import_preview import ImportPreview, build_preview
from animus.hunter_os.import_sources import _unique_keys
from animus.hunter_os.models import HunterDataError, parse_record

IMPORT_ACTOR = "hunter-os-importer-v1"
MAX_PLAN_BYTES = 32 * 1024 * 1024
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class HunterImportError(ValueError):
    """Sanitized review-plan rejection; no writes were applied."""


class _Strict:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


@dataclass(frozen=True, kw_only=True)
class PlannedItem(_Strict):
    object_id: str
    action: Literal["create", "update", "unchanged", "conflict"]
    expected_version: Annotated[int, Field(ge=0)]
    expected_fingerprint: Digest | None


@dataclass(frozen=True, kw_only=True)
class ImportPlan(_Strict):
    """Serializable review artifact; its payload is re-derived from sources at apply."""

    format_version: Literal["hunter-review-import-v1"]
    destination: Digest
    owner_id: str
    as_of: date
    preview_json: str
    items: tuple[PlannedItem, ...]
    issues: tuple[str, ...]

    def to_json(self) -> str:
        return TypeAdapter(ImportPlan).dump_json(self, indent=2).decode("utf-8") + "\n"

    @classmethod
    def from_json(cls, text: str) -> ImportPlan:
        if len(text.encode("utf-8")) > MAX_PLAN_BYTES:
            raise HunterImportError("Import plan exceeds the size limit.")
        try:
            json.loads(text, object_pairs_hook=_unique_keys)
            return TypeAdapter(cls).validate_json(text, strict=True)
        except (ValidationError, ValueError):
            raise HunterImportError("Invalid import plan.") from None


@dataclass(frozen=True, kw_only=True)
class ImportResult:
    records: tuple[BatchResult, ...]
    held: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _owned(record: ObjectRecord) -> bool:
    if (
        record.created_by != IMPORT_ACTOR
        or record.workflow_status != "candidate"
        or record.epistemic_status != "unverified"
        or not record.trace_id
        or not record.trace_id.startswith("hunter-import:")
        or record.valid_from is not None
        or record.valid_to is not None
    ):
        return False
    try:
        payload = parse_record(record.payload)
        return (
            payload.id == record.object_id
            and payload.record_type == record.artifact_type
            and payload.schema_version == record.schema_version
            and payload.status == "review"
            and bool(payload.review_reasons)
        )
    except HunterDataError:
        return False


def _candidates(
    preview: ImportPreview, owner: str
) -> dict[str, tuple[ObjectRecord, dict[str, Any]]]:
    sources = {s["provenance"]["path"]: s for s in preview.source_files}
    result = {}
    for item in preview.records:
        if item.payload is None or item.issues:
            continue
        payload = parse_record(item.payload)
        # Evidence belongs to the ledger, not the strict game-fact payload. This
        # per-record stamp excludes the audit date and unrelated forum edits.
        evidence = {
            "converter": IMPORT_ACTOR,
            "repository": preview.source_manifest["repository"],
            "origin": preview.source_manifest["origin"],
            "source": sources[item.source_path],
            "source_claims": item.source_claims,
            "mappings": item.mappings,
        }
        envelope = ObjectRecord(
            object_id=payload.id,
            schema_id="hunter_os",
            schema_version=payload.schema_version,
            owner_id=owner,
            workspace_id="hunter-os",
            subject_domain="monster_hunter_wilds",
            artifact_type=payload.record_type,
            cognitive_role="knowledge",
            workflow_status="candidate",
            epistemic_status="unverified",
            security_class="public",
            payload=item.payload,
            tags=list(payload.tags),
            created_by=IMPORT_ACTOR,
            trace_id="hunter-import:" + _hash(evidence),
        )
        result[payload.id] = (envelope, {"hunter_import": evidence})
    return result


class HunterOSImporter:
    """Construct only in an operator context with server-selected database and owner.

    All writes remain candidate/unverified/review. Chat keeps its read-only
    repository, which excludes these candidates. No approval override is exposed.
    """

    def __init__(self, store: DurableObjectStore):
        if store.scope is None or store.scope != ObjectScope.hunter(store.scope.owner_id):
            raise ValueError("Importer requires an exact operator-selected Hunter scope.")
        destination_url = store._engine.url
        if destination_url.get_backend_name() == "sqlite":
            database = destination_url.database
            if not database or not Path(database).is_absolute() or destination_url.query.get("uri"):
                raise ValueError("SQLite importers require an absolute, non-URI database path.")
            destination_url = destination_url.set(database=str(Path(database).resolve()))
        self._store = store
        self._owner = store.scope.owner_id
        # Bind plans to the configured destination without serializing credentials.
        self._destination = _hash(
            {
                "database": destination_url.render_as_string(hide_password=False),
                "owner": self._owner,
            }
        )
        try:
            store.preflight()
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterImportError("Hunter registry is unavailable or incompatible.") from None

    def plan(self, *, source_root: Path | None = None, as_of: date) -> ImportPlan:
        """Compare the checked source preview to scoped current SQL records; no writes."""
        preview = build_preview(source_root, as_of=as_of)
        candidates = _candidates(preview, self._owner)
        issues = []
        if preview.counts["items_with_conversion_conflicts"] or not candidates:
            issues.append("source.conversion_conflicts")
        items = []
        try:
            for record_id, (candidate, _) in sorted(candidates.items()):
                current = self._store.retrieve(record_id)
                version = current.version if current else 0
                fingerprint = record_fingerprint(current) if current else None
                action: Literal["create", "update", "unchanged", "conflict"]
                if current and not _owned(current):
                    action = "conflict"
                    issues.append("registry.protected_record")
                elif fingerprint == record_fingerprint(candidate):
                    action = "unchanged"
                else:
                    action = "update" if current else "create"
                items.append(
                    PlannedItem(
                        object_id=record_id,
                        action=action,
                        expected_version=version,
                        expected_fingerprint=fingerprint,
                    )
                )
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterImportError("Hunter import planning failed.") from None
        return ImportPlan(
            format_version="hunter-review-import-v1",
            destination=self._destination,
            owner_id=self._owner,
            as_of=as_of,
            preview_json=preview.to_json(),
            items=tuple(items),
            issues=tuple(sorted(set(issues))),
        )

    def apply(self, plan: ImportPlan, *, source_root: Path | None = None) -> ImportResult:
        """Apply the reviewed batch atomically, or reject changed input/baseline.

        A repeated apply of identical content is a no-op, even after an uncertain
        response. Plan JSON is not authority to edit payloads: sources are reloaded
        and converted, while current protected records are checked again.
        """
        plan = ImportPlan.from_json(plan.to_json())
        if plan.destination != self._destination or plan.owner_id != self._owner:
            raise HunterImportError("Import plan belongs to a different destination.")
        fresh = self.plan(source_root=source_root, as_of=plan.as_of)
        if plan.preview_json != fresh.preview_json:
            raise HunterImportError("Import sources or converter changed; create a new plan.")
        if plan.issues or fresh.issues or any(i.action == "conflict" for i in plan.items):
            raise HunterImportError("Import has unresolved conflicts; no writes applied.")
        if [i.object_id for i in plan.items] != [i.object_id for i in fresh.items]:
            raise HunterImportError("Import plan record inventory does not match its sources.")
        # Reconstruct only the independently regenerated preview, never client payloads.
        preview = build_preview(source_root, as_of=plan.as_of)
        if preview.to_json() != fresh.preview_json:
            raise HunterImportError("Sources changed during apply; create a new plan.")
        candidates = _candidates(preview, self._owner)
        changes = tuple(
            BatchChange(
                record=candidates[i.object_id][0],
                expected_version=i.expected_version,
                expected_fingerprint=i.expected_fingerprint,
                evidence=candidates[i.object_id][1],
            )
            for i in plan.items
        )
        try:
            results = apply_batch(self._store, changes, current_allowed=_owned)
        except PermissionError:
            raise HunterImportError("Current record is protected; no writes applied.") from None
        except ConcurrencyError:
            raise HunterImportError(
                "Import baseline changed or identity is unavailable; replan."
            ) from None
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterImportError(
                "Import transaction failed or completion is uncertain; inspect or replay the plan."
            ) from None
        return ImportResult(records=results, held=int(preview.counts["held"] or 0))
