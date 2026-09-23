"""Read-only domain adapters. Only explicitly scoped SQL stores are accepted."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Generic, TypeVar, cast

from sqlalchemy.exc import SQLAlchemyError

from animus.durability.postgres_store import DurableObjectStore, ObjectRecord
from animus.durability.schema import SchemaCompatibilityError
from animus.durability.scope import ObjectScope
from animus.hunter_os.audit import AuditFinding, AuditReport, EligibilityPolicy, audit_record
from animus.hunter_os.models import (
    ExactWeaponRecord,
    HunterDataError,
    HunterRecord,
    MonsterRecord,
    Record,
    WeaponTypeRecord,
    parse_record,
    record_payload,
)

T = TypeVar("T", bound=HunterRecord)


class HunterUnavailableError(RuntimeError):
    """No fallback is allowed; caller should return a neutral unavailable response."""


@dataclass(frozen=True, kw_only=True)
class HunterEntry(Generic[T]):
    """Facts and caveats travel together; callers must retain the audit report."""

    record: T
    version: int
    audit: AuditReport
    recorded_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None


def _limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 50:
        raise ValueError("limit must be an integer between 1 and 50.")
    return value


def _record_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"mhw-[a-z0-9][a-z0-9_-]{0,123}", value):
        raise ValueError("A canonical Hunter record ID is required.")


class _Reader:
    def __init__(
        self,
        store: DurableObjectStore,
        *,
        policy: EligibilityPolicy | None = None,
        max_candidates: int = 1000,
    ) -> None:
        scope = store.scope
        if scope is None or scope != ObjectScope.hunter(scope.owner_id):
            raise ValueError("Hunter repository requires an exact, operator-selected Hunter scope.")
        if type(max_candidates) is not int or not 1 <= max_candidates <= 10000:
            raise ValueError("max_candidates must be between 1 and 10000.")
        self._store = store
        self._policy = policy or EligibilityPolicy()
        self._max_candidates = max_candidates
        try:
            store.preflight()
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterUnavailableError(
                "Hunter registry is unavailable or incompatible."
            ) from None

    def _decode(self, row: ObjectRecord) -> HunterEntry[Record]:
        record = parse_record(row.payload)
        if (
            record.id != row.object_id
            or record.record_type != row.artifact_type
            or record.schema_version != row.schema_version
        ):
            raise HunterDataError("Hunter payload does not match its registry envelope.")
        report = audit_record(record, self._policy)
        if row.workflow_status != "approved" or row.epistemic_status != "supported":
            report = replace(
                report,
                findings=report.findings
                + (
                    AuditFinding(
                        severity="block",
                        code="envelope.review",
                        message="Registry approval and support are required.",
                    ),
                ),
            )
        return HunterEntry(
            record=record,
            version=row.version,
            audit=report,
            recorded_at=row.recorded_at,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )

    def _load(self, record_id: str) -> HunterEntry[Record] | None:
        _record_id(record_id)
        try:
            row = self._store.retrieve(record_id)
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterUnavailableError("Hunter registry read failed.") from None
        return self._decode(row) if row is not None else None

    def _scan(self, artifact_type: str | None = None) -> tuple[HunterEntry[Record], ...]:
        try:
            rows = self._store.list_current(artifact_type, limit=self._max_candidates + 1)
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterUnavailableError("Hunter registry query failed.") from None
        if len(rows) > self._max_candidates:
            raise HunterUnavailableError("Hunter query exceeds the configured candidate limit.")
        return tuple(self._decode(row) for row in rows)


class HunterOSRepository(_Reader):
    """Eligible read surface for future chat. No writes, global memory or fallback."""

    def get(self, record_id: str) -> HunterEntry[Record] | None:
        """Return an eligible current record, with warnings and provenance intact."""
        entry = self._load(record_id)
        return entry if entry is not None and entry.audit.eligible else None

    def _typed(self, record_id: str, kind: type[T]) -> HunterEntry[T] | None:
        entry = self.get(record_id)
        if entry is not None and isinstance(entry.record, kind):
            return cast(HunterEntry[T], entry)
        return None

    def monster(
        self, record_id: str, *, variant: str = "normal"
    ) -> HunterEntry[MonsterRecord] | None:
        """Require exact variant identity; do not substitute another encounter."""
        entry = self._typed(record_id, MonsterRecord)
        return entry if entry is not None and entry.record.variant == variant else None

    def weapon_type(self, record_id: str) -> HunterEntry[WeaponTypeRecord] | None:
        return self._typed(record_id, WeaponTypeRecord)

    def exact_weapon(self, record_id: str) -> HunterEntry[ExactWeaponRecord] | None:
        return self._typed(record_id, ExactWeaponRecord)

    def search(self, query: str, *, limit: int = 6) -> tuple[HunterEntry[Record], ...]:
        """Bounded deterministic search over this small domain, never general memory."""
        _limit(limit)
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("query must be text of at most 200 characters.")
        terms = set(re.findall(r"[^\W_]+", query.casefold()))
        if not terms:
            return ()
        ranked = []
        for entry in self._scan():
            if not entry.audit.eligible:
                continue
            payload = record_payload(entry.record)
            # Source titles and bookkeeping must not make unrelated facts rank.
            for key in ("sources", "review_reasons", "verified_date", "schema_version", "game"):
                payload.pop(key, None)
            text = json.dumps(payload, ensure_ascii=False).casefold()
            words = set(re.findall(r"[^\W_]+", text))
            score = len(terms & words)
            if score:
                if query.strip().casefold() == entry.record.name.casefold():
                    score += 100
                ranked.append((score, entry))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].record.name.casefold(), pair[1].record.id))
        return tuple(entry for _, entry in ranked[:limit])

    def horns_with_effects(
        self, effect_ids: Sequence[str], *, limit: int = 6
    ) -> tuple[HunterEntry[ExactWeaponRecord], ...]:
        """Match all effects from evidenced melodies on the exact horn only."""
        _limit(limit)
        if (
            isinstance(effect_ids, str)
            or not effect_ids
            or len(effect_ids) > 20
            or any(
                not isinstance(effect, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", effect)
                for effect in effect_ids
            )
        ):
            raise ValueError("Supply between 1 and 20 canonical effect IDs.")
        wanted = set(effect_ids)
        matches = []
        for entry in self._scan("exact_weapon"):
            record = entry.record
            if (
                entry.audit.eligible
                and isinstance(record, ExactWeaponRecord)
                and record.weapon_type == "hunting_horn"
                and record.horn is not None
            ):
                effects = {
                    effect for melody in record.horn.melodies for effect in melody.effect_ids
                }
                if wanted.issubset(effects):
                    matches.append(cast(HunterEntry[ExactWeaponRecord], entry))
        return tuple(matches[:limit])

    def bowguns_with_ammo(
        self, ammo: str, *, level: int | None = None, limit: int = 6
    ) -> tuple[HunterEntry[ExactWeaponRecord], ...]:
        """Confirmed support only; absence/unknown and other levels never match."""
        _limit(limit)
        if not isinstance(ammo, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", ammo):
            raise ValueError("A canonical ammo ID is required.")
        if level is not None and (type(level) is not int or level < 1):
            raise ValueError("level must be a positive integer when supplied.")
        matches = []
        for entry in self._scan("exact_weapon"):
            record = entry.record
            if (
                entry.audit.eligible
                and isinstance(record, ExactWeaponRecord)
                and record.weapon_type in ("light_bowgun", "heavy_bowgun")
            ):
                if any(
                    a.ammo == ammo
                    and a.support == "supported"
                    and (level is None or a.level == level)
                    for a in record.ammo_table
                ):
                    matches.append(cast(HunterEntry[ExactWeaponRecord], entry))
        return tuple(matches[:limit])


class HunterOSReviewRepository(_Reader):
    """Operator-only inspection; same privacy scope, including held domain records."""

    def inspect(self, record_id: str) -> HunterEntry[Record] | None:
        return self._load(record_id)

    def history(self, record_id: str, *, limit: int = 20) -> tuple[HunterEntry[Record], ...]:
        """Latest versions first; current scope still governs access to old versions."""
        _limit(limit)
        current = self._load(record_id)
        if current is None:
            return ()
        entries = []
        try:
            for version in range(current.version, max(0, current.version - limit), -1):
                row = self._store.retrieve_version(record_id, version)
                if row is not None:
                    entries.append(self._decode(row))
        except (SQLAlchemyError, SchemaCompatibilityError):
            raise HunterUnavailableError("Hunter registry history unavailable.") from None
        return tuple(entries)
