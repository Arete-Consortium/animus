"""File-backed canonical repository for Hunter OS records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    RecordStatus,
    SourceRef,
    SpecialEncounterRecord,
    WeaponTypeRecord,
    tupleize,
)


class HunterOSDataError(ValueError):
    """Raised when a Hunter OS data file cannot be converted safely."""


class HunterOSRepository:
    """Load and query structured Hunter OS YAML records."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parent / "data"
        )

    def _files(self) -> list[Path]:
        if not self.data_dir.exists():
            return []
        return sorted(self.data_dir.rglob("*.yaml"))

    def all(self) -> tuple[HunterRecord, ...]:
        return tuple(self._load_file(path) for path in self._files())

    def get(self, record_id: str) -> HunterRecord:
        wanted = record_id.casefold()
        for record in self.all():
            if record.id.casefold() == wanted:
                return record
        raise KeyError(record_id)

    def search(self, query: str, limit: int = 20) -> tuple[HunterRecord, ...]:
        needle = query.casefold().strip()
        if not needle:
            return ()

        scored: list[tuple[int, HunterRecord]] = []
        for record in self.all():
            haystacks = [
                record.id.casefold(),
                record.name.casefold(),
                " ".join(record.tags).casefold(),
                record.record_type.casefold(),
            ]
            score = sum(1 for text in haystacks if needle in text)
            if score:
                scored.append((score, record))

        scored.sort(key=lambda pair: (-pair[0], pair[1].name.casefold()))
        return tuple(record for _, record in scored[:limit])

    def _load_file(self, path: Path) -> HunterRecord:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise HunterOSDataError(f"{path}: expected mapping")

        try:
            record_type = str(raw["record_type"])
            common = self._common(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise HunterOSDataError(f"{path}: invalid metadata: {exc}") from exc

        if record_type == "monster":
            return MonsterRecord(
                **common,
                weakness_primary=str(raw.get("weakness", {}).get("primary", "")),
                weakness_secondary=tupleize(raw.get("weakness", {}).get("secondary")),
                targets=self._tuple_mapping(raw.get("targets", {})),
                control_prep=tupleize(raw.get("control_prep")),
                status_prep=tupleize(raw.get("status_prep")),
                fight_plan=tupleize(raw.get("fight_plan")),
                capture_rule=str(raw.get("capture_rule", "")),
                variant=str(raw.get("variant", "normal")),
            )

        if record_type == "weapon_type":
            controls = raw.get("controls", {})
            if not isinstance(controls, dict):
                raise HunterOSDataError(f"{path}: controls must be a mapping")
            return WeaponTypeRecord(
                **common,
                controls={
                    str(action): {str(k): str(v) for k, v in bindings.items()}
                    for action, bindings in controls.items()
                },
                rules=tupleize(raw.get("rules")),
                core_loop=tupleize(raw.get("core_loop")),
                failure_modes=tupleize(raw.get("failure_modes")),
            )

        if record_type == "guide":
            return GuideRecord(
                **common,
                sections=self._tuple_mapping(raw.get("sections", {})),
                related_records=tupleize(raw.get("related_records")),
            )

        if record_type == "special_encounter":
            return SpecialEncounterRecord(
                **common,
                weakness_primary=str(raw.get("weakness", {}).get("primary", "")),
                targets=self._tuple_mapping(raw.get("targets", {})),
                mechanics=tupleize(raw.get("mechanics")),
                capture_rule=str(raw.get("capture_rule", "")),
                phase_notes=tupleize(raw.get("phase_notes")),
                timeline_complete=bool(raw.get("timeline_complete", False)),
            )

        raise HunterOSDataError(f"{path}: unsupported record_type={record_type!r}")

    @staticmethod
    def _common(raw: dict[str, Any]) -> dict[str, Any]:
        source_items = raw.get("sources", [])
        if not isinstance(source_items, list):
            raise HunterOSDataError("sources must be a list")

        sources = []
        for item in source_items:
            if not isinstance(item, dict) or not item.get("document"):
                raise HunterOSDataError("every source needs a document")
            sources.append(
                SourceRef(
                    document=str(item["document"]),
                    section=str(item.get("section", "")),
                    note=str(item.get("note", "")),
                )
            )

        return {
            "id": str(raw["id"]),
            "name": str(raw["name"]),
            "record_type": str(raw["record_type"]),
            "game": str(raw.get("game", "monster_hunter_wilds")),
            "status": RecordStatus(str(raw.get("status", "review"))),
            "verified_date": str(raw.get("verified_date", "")),
            "sources": tuple(sources),
            "tags": tupleize(raw.get("tags")),
            "notes": tupleize(raw.get("notes")),
        }

    @staticmethod
    def _tuple_mapping(value: Any) -> dict[str, tuple[str, ...]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise HunterOSDataError("expected mapping")
        return {str(key): tupleize(items) for key, items in value.items()}
