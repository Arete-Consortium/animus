"""Offline, deterministic migration preview. No store, provider or publisher is used.

The converter deliberately recognizes only the four staged legacy identities.
Everything else is retained as source text and held for an explicit mapping.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import yaml

from animus.hunter_os.audit import EligibilityPolicy, audit_record
from animus.hunter_os.import_sources import PreviewError, SourceBundle, digest, load_bundle
from animus.hunter_os.models import HunterDataError, parse_record, record_payload

IDENTITIES = {
    "rathian": ("monster", "mhw-monster-rathian"),
    "hunting_horn": ("weapon_type", "mhw-weapon-type-hunting-horn"),
    "combat_healer_hh_lbg": ("guide", "mhw-guide-combat-healer-hh-lbg"),
    "omega_planetes": ("special_encounter", "mhw-special-encounter-omega-planetes"),
}
COPY_COMMON = {
    "name",
    "record_type",
    "game",
    "tags",
    "notes",
    "variant",
    "patch_version",
    "patch_sensitive",
}
COPY_FIELDS = {
    "monster": {"targets", "control_prep", "status_prep", "fight_plan", "capture_rule"},
    "weapon_type": {"controls", "rules", "core_loop", "failure_modes"},
    "guide": {"sections"},
    "special_encounter": {"targets", "capture_rule", "timeline_complete"},
}
REVIEW_REASON = "Legacy source requires evidence review and explicit operator approval."
MAX_ITEMS = 500
NAVIGATION_HEADINGS = {
    ("forum/weapons.md", "INPUT LEGEND"),
    ("forum/weapons.md", "HH — ROLE INDEX"),
    ("forum/weapons.md", "HH — DATA QUALITY NOTE"),
    ("forum/monsters.md", "ENDGAME VARIANT RULE"),
    ("forum/hunter_guide.md", "START HERE — HUNTER OS QUICK REFERENCE"),
    ("forum/hunter_guide.md", "FARMING VERSION RULE"),
    ("forum/hunter_guide.md", "VARIANT RULE"),
}


class _Loader(yaml.SafeLoader):
    """Retain date strings and refuse duplicate keys instead of overwriting facts."""

    yaml_implicit_resolvers = {
        key: [(tag, pattern) for tag, pattern in rules if tag != "tag:yaml.org,2002:timestamp"]
        for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise PreviewError("YAML keys must be unique strings.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _parse_yaml(text: str) -> dict[str, Any]:
    try:
        # Disallow aliases and limit nesting before construction/recursive field walking.
        depth = 0
        for index, event in enumerate(yaml.parse(text)):
            if isinstance(event, yaml.AliasEvent) or index > 25000:
                raise PreviewError("YAML aliases or excessive complexity are not supported.")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
            if depth > 30:
                raise PreviewError("YAML nesting exceeds the limit.")
        value = yaml.load(text, Loader=_Loader)
        if not isinstance(value, dict):
            raise PreviewError("YAML record must be a mapping.")
        # Reject non-JSON values and escaped surrogate code points before reporting.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (yaml.YAMLError, TypeError, ValueError, RecursionError):
        raise PreviewError("Invalid or unsupported YAML record.") from None


def _pointer(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _leaves(value: Any, path: str = "") -> set[str]:
    if isinstance(value, dict) and value:
        return set().union(*(_leaves(v, f"{path}/{_pointer(k)}") for k, v in value.items()))
    if isinstance(value, list) and value:
        return set().union(*(_leaves(v, f"{path}/{i}") for i, v in enumerate(value)))
    return {path}


@dataclass
class RecordPreview:
    source_path: str
    canonical_id: str | None = None
    disposition: str = "held"
    payload: dict[str, Any] | None = None
    source_claims: dict[str, Any] = field(default_factory=dict)
    mappings: dict[str, str] = field(default_factory=dict)
    unmapped_fields: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    audit: list[dict[str, str]] = field(default_factory=list)


def _convert(path: str, text: str, as_of: date) -> RecordPreview:
    item = RecordPreview(source_path=path)
    try:
        raw = _parse_yaml(text)
    except PreviewError:
        item.issues.append("record.invalid_yaml")
        return item
    for key in ("status", "verified_date"):
        if key in raw:
            item.source_claims[key] = raw[key]
            item.mappings[f"/{key}"] = f"source_claims/{key}"
    legacy_id = raw.get("id")
    identity = IDENTITIES.get(legacy_id) if isinstance(legacy_id, str) else None
    if (
        identity is None
        or raw.get("record_type") != identity[0]
        or raw.get("variant", "normal") != "normal"
    ):
        item.issues.append("record.identity_mapping_required")
        item.unmapped_fields = sorted(_leaves(raw) - set(item.mappings))
        return item
    family, item.canonical_id = identity
    candidate: dict[str, Any] = {
        "id": item.canonical_id,
        "status": "review",
        "verified_date": None,
        "review_reasons": [REVIEW_REASON],
    }
    item.mappings["/id"] = "payload/id (explicit legacy identity map)"
    for key in sorted(COPY_COMMON | COPY_FIELDS[family]):
        if key in raw:
            candidate[key] = raw[key]
            item.mappings[f"/{key}"] = f"payload/{key}"
    if raw.get("status") == "patch-sensitive":
        candidate["patch_sensitive"] = True
    sources = raw.get("sources")
    if isinstance(sources, list):
        candidate["sources"] = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                continue
            destination_index = len(candidate["sources"])
            ref = {"id": f"legacy-source-{index + 1}"}
            for key in ("document", "section"):
                if key in source:
                    ref[key] = source[key]
                    item.mappings[f"/sources/{index}/{key}"] = (
                        f"payload/sources/{destination_index}/{key}"
                    )
            # The staged YAML hash does not prove the contents of the cited manual.
            candidate["sources"].append(ref)
        if not sources:
            item.mappings["/sources"] = "payload/sources"
    weakness = raw.get("weakness")
    if isinstance(weakness, dict) and family in {"monster", "special_encounter"}:
        for key in ("primary", "secondary") if family == "monster" else ("primary",):
            if key in weakness:
                candidate[f"weakness_{key}"] = weakness[key]
                item.mappings[f"/weakness/{key}"] = f"payload/weakness_{key}"
    if family == "weapon_type":
        candidate["weapon_type"] = "hunting_horn"  # Explicit identity mapping, not inference.
    if family == "guide":
        candidate["topic"] = "combat-healer"
    if family == "special_encounter":
        mechanics = raw.get("mechanics")
        if isinstance(mechanics, list) and all(isinstance(m, str) for m in mechanics):
            candidate["mechanics"] = [{"text": m, "source_ids": []} for m in mechanics]
            item.mappings["/mechanics"] = "payload/mechanics (feature evidence remains unknown)"
        if raw.get("phase_notes") == []:
            candidate["phases"] = []
            item.mappings["/phase_notes"] = "payload/phases (empty legacy timeline)"
    related = raw.get("related_records")
    if isinstance(related, list):
        candidate["relationships"] = []
        for index, target in enumerate(related):
            if isinstance(target, str) and target in IDENTITIES:
                candidate["relationships"].append(
                    {"relation": "related", "record_id": IDENTITIES[target][1]}
                )
                item.mappings[f"/related_records/{index}"] = "payload/relationships (identity map)"
            else:
                item.issues.append("relationship.unmapped_target")
        if not related:
            item.mappings["/related_records"] = "payload/relationships"
    item.unmapped_fields = sorted(
        pointer
        for pointer in _leaves(raw)
        if not any(pointer == p or pointer.startswith(p + "/") for p in item.mappings)
    )
    if item.unmapped_fields:
        item.issues.append("record.unmapped_fields")
    try:
        record = parse_record(candidate)
        item.payload = record_payload(record)
        item.audit = [
            asdict(f) for f in audit_record(record, EligibilityPolicy(as_of=as_of)).findings
        ]
    except HunterDataError:
        item.issues.append("record.invalid_payload")
    return item


@dataclass
class ForumPreview:
    source_path: str
    section_index: int
    heading: str | None
    kind: str
    start_line: int
    end_line: int
    raw_text: str
    sha256: str
    disposition: str = "held"
    issues: list[str] = field(default_factory=lambda: ["forum.structured_mapping_required"])


def _sections(path: str, text: str) -> list[ForumPreview]:
    # Split only actual H2 headings outside fenced blocks, preserving every byte.
    lines = text.splitlines(keepends=True)
    starts = [0]
    headings: dict[int, str] = {}
    fence: str | None = None
    for index, line in enumerate(lines):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif (
                token[0] == fence[0]
                and len(token) >= len(fence)
                and not line[match.end() :].strip()
            ):
                fence = None
        elif fence is None and line.startswith("## "):
            if index:
                starts.append(index)
            headings[index] = line[3:].strip()
    if len(starts) > MAX_ITEMS:
        raise PreviewError("Forum section count exceeds the limit.")
    result = []
    counts = Counter(headings.values())
    for index, (start, stop) in enumerate(zip(starts, [*starts[1:], len(lines)], strict=True)):
        raw = "".join(lines[start:stop])
        heading = headings.get(start)
        item = ForumPreview(
            source_path=path,
            section_index=index,
            heading=heading,
            kind=(
                "preamble"
                if heading is None
                else "navigation"
                if (path, heading) in NAVIGATION_HEADINGS
                else "unmapped_section"
            ),
            start_line=start + 1,
            end_line=stop,
            raw_text=raw,
            sha256=digest(raw.encode("utf-8")),
        )
        if heading is not None and (not heading or counts[heading] > 1):
            item.issues.append("forum.ambiguous_heading")
        result.append(item)
    return result


@dataclass(frozen=True)
class ImportPreview:
    schema_version: str
    mode: str
    as_of: str
    manifest_sha256: str
    source_manifest: dict[str, Any]
    manifest_raw_text: str
    source_files: list[dict[str, Any]]
    records: list[RecordPreview]
    forum: list[ForumPreview]
    registry_comparison: str
    counts: dict[str, int | None]

    def to_json(self) -> str:
        """Stable serialization; no timestamps, random IDs, absolute paths or writes."""
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_preview(source_root: Path | None = None, *, as_of: date) -> ImportPreview:
    """Plan from a checked snapshot (packaged seeds by default); never apply it."""
    EligibilityPolicy(as_of=as_of)  # Reject datetimes/strings before loading inputs.
    if as_of is None:
        raise ValueError("An explicit audit date is required.")
    if source_root is None:
        with as_file(files("animus.hunter_os").joinpath("seed_sources")) as root:
            bundle = load_bundle(root)
    else:
        bundle = load_bundle(source_root)
    return _plan(bundle, as_of)


def _plan(bundle: SourceBundle, as_of: date) -> ImportPreview:
    records = []
    forum = []
    for source in bundle.files:
        if source.declaration.path.startswith("records/"):
            records.append(_convert(source.declaration.path, source.text, as_of))
        else:
            forum.extend(_sections(source.declaration.path, source.text))
        if len(records) + len(forum) > MAX_ITEMS:
            raise PreviewError("Preview item count exceeds the limit.")
    identities = Counter(r.canonical_id for r in records if r.canonical_id)
    usable = {r.canonical_id for r in records if r.payload and not r.issues}
    for record in records:
        if record.canonical_id and identities[record.canonical_id] > 1:
            record.issues.append("record.duplicate_identity")
        for relationship in (record.payload or {}).get("relationships", []):
            target = relationship["record_id"]
            if identities[target] != 1 or target not in usable:
                record.issues.append("relationship.target_missing_or_ambiguous")
        record.issues = sorted(set(record.issues))
    conflict_count = sum(bool(r.issues) for r in records) + sum(
        "forum.ambiguous_heading" in s.issues for s in forum
    )
    return ImportPreview(
        schema_version="1.0.0",
        mode="preview_only",
        as_of=as_of.isoformat(),
        manifest_sha256=digest(bundle.manifest_text.encode("utf-8")),
        source_manifest=asdict(bundle.manifest),
        manifest_raw_text=bundle.manifest_text,
        source_files=[
            {"provenance": asdict(s.declaration), "raw_text": s.text} for s in bundle.files
        ],
        records=records,
        forum=forum,
        registry_comparison="not_performed",
        counts={
            "created": None,
            "updated": None,
            "unchanged": None,
            "source_files": len(bundle.files),
            "records": len(records),
            "converted_records": sum(r.payload is not None for r in records),
            "forum_sections": len(forum),
            "held": len(records) + len(forum),
            "items_with_conversion_conflicts": conflict_count,
            "approved": 0,
            "writes": 0,
        },
    )


def main(argv: list[str] | None = None) -> int:
    """Write one complete preview artifact; exit 0 for held plans, 1 for input/output errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, help="Defaults to the packaged staged snapshot."
    )
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--output", required=True, type=Path, help="New JSON file (never overwrite)."
    )
    args = parser.parse_args(argv)
    temporary: Path | None = None
    try:
        protected_root = args.source_root or Path(
            str(files("animus.hunter_os").joinpath("seed_sources"))
        )
        if args.output.resolve().is_relative_to(protected_root.resolve()):
            raise PreviewError("Output must be outside the source bundle.")
        preview = build_preview(args.source_root, as_of=args.as_of)
        # Fully write the temporary file before publishing it with an exclusive link.
        # Existing files/symlinks and original sources are never overwritten.
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(preview.to_json().encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, args.output)
        sys.stdout.write(json.dumps(preview.counts, sort_keys=True) + "\n")
        return 0
    except (PreviewError, OSError):
        sys.stderr.write(
            "Preview failed: invalid source bundle or unavailable/new output path required.\n"
        )
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
