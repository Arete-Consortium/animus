"""Durable source comparison and conservative review packets for n8n."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from animus.hunter_os.audit import audit_record
from animus.hunter_os.models import parse_record

MAX_FILE = 256 * 1024
MAX_TOTAL = 4 * 1024 * 1024
MAX_FILES = 250
MAX_RECORDS = 500


class SourceUnavailableError(ValueError):
    """A source cannot be inspected safely; keep the last successful baseline."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(path: Path) -> bytes:
    """Reject indirect files and racing writes; never report their contents on error."""
    try:
        for part in (path, *path.parents):
            if part.is_symlink():
                raise SourceUnavailableError("Source symlinks are not supported")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > MAX_FILE
            ):
                raise SourceUnavailableError("Source must be a bounded, unlinked regular file")
            data = stream.read(MAX_FILE + 1)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(data) > MAX_FILE:
            raise SourceUnavailableError("Source changed during inspection")
        return data
    except (OSError, UnicodeError) as exc:
        raise SourceUnavailableError("A configured source is unavailable") from exc


def finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "block", "code": code, "message": message}


def inspect_record(raw: bytes, relative: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"record:{relative}",
        "source_path": relative,
        "name": Path(relative).stem,
        "kind": "candidate_record",
        "sha256": digest(raw),
        "schema_valid": False,
        "claimed_status": None,
        "findings": [],
    }
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError("mapping required")
        # Source labels are claims, never approval signals.
        if isinstance(data.get("name"), str):
            item["name"] = data["name"][:200]
        if isinstance(data.get("status"), str):
            item["claimed_status"] = data["status"][:80]
        try:
            record = parse_record(data)
            item["schema_valid"] = True
            report = audit_record(record)
            item["findings"] = [
                {"severity": f.severity, "code": f.code, "message": f.message}
                for f in report.findings
            ]
        except ValueError:
            item["findings"].append(
                finding(
                    "schema.migration_required",
                    "Candidate does not match the current Hunter OS schema; "
                    "preserve and map its fields.",
                )
            )
            if not str(data.get("id", "")).startswith("mhw-"):
                item["findings"].append(
                    finding("identity.legacy", "Map the legacy ID to a canonical mhw- ID.")
                )
            sources = data.get("sources")
            if (
                not isinstance(sources, list)
                or not sources
                or any(
                    not isinstance(s, dict) or not s.get("id") or not s.get("content_sha256")
                    for s in sources
                )
            ):
                item["findings"].append(
                    finding(
                        "source.provenance_required",
                        "Resolve source IDs and source-content hashes before approval.",
                    )
                )
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        item["findings"] = [
            finding(
                "source.malformed", "Candidate YAML cannot be validated; inspect the source file."
            )
        ]
    item["findings"].append(
        finding(
            "approval.required",
            "Operator review is required; this source inspection grants no approval.",
        )
    )
    item["status"] = "HELD"
    return item


def inspect_markdown(raw: bytes, relative: str) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise SourceUnavailableError("Source text encoding is invalid") from exc
    parts = re.split(r"(?m)^## ", text)
    items = []
    seen: set[str] = set()
    for index, part in enumerate(parts):
        if not part.strip():
            continue
        title = "Start Here" if index == 0 else part.splitlines()[0].strip()
        key = "__intro__" if index == 0 else re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
        if not key or key in seen:
            raise SourceUnavailableError("Forum source contains ambiguous section identities")
        seen.add(key)
        items.append(
            {
                "id": f"section:{relative}:{key}",
                "source_path": relative,
                "section": title[:200],
                "name": title[:200],
                "kind": "forum_section",
                "sha256": digest(part.encode()),
                "schema_valid": False,
                "claimed_status": None,
                "status": "HELD",
                "findings": [
                    finding(
                        "text.conversion_required",
                        "Convert this source section into evidenced typed records "
                        "before publication.",
                    )
                ],
            }
        )
    return items


def scan(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    total = 0

    def directory_error(error: OSError) -> None:
        raise SourceUnavailableError("Source directory cannot be inspected") from error

    for folder, suffixes in (("records", {".yaml", ".yml", ".json"}), ("forum", {".md"})):
        directory = root / folder
        if not directory.is_dir() or directory.is_symlink():
            raise SourceUnavailableError("Configured source directory is unavailable")
        for current, dirs, names in os.walk(directory, followlinks=False, onerror=directory_error):
            if any((Path(current) / d).is_symlink() for d in dirs):
                raise SourceUnavailableError("Source symlinks are not supported")
            for name in sorted(names):
                path = Path(current) / name
                if path.suffix not in suffixes:
                    continue
                relative = path.relative_to(root).as_posix()
                raw = read_source(path)
                total += len(raw)
                hashes[relative] = digest(raw)
                if total > MAX_TOTAL or len(hashes) > MAX_FILES:
                    raise SourceUnavailableError("Source inventory exceeds review bounds")
                records.extend(
                    inspect_markdown(raw, relative)
                    if folder == "forum"
                    else [inspect_record(raw, relative)]
                )
                if len(records) > MAX_RECORDS:
                    raise SourceUnavailableError("Source record count exceeds review bounds")
    if not records:
        raise SourceUnavailableError("Source inventory is empty; baseline was not changed")
    for relative, expected in hashes.items():
        if digest(read_source(root / relative)) != expected:
            raise SourceUnavailableError("Source changed during inspection")
    try:
        provenance = json.loads(read_source(root / "provenance.json"))
    except (ValueError, UnicodeError) as exc:
        raise SourceUnavailableError("Source provenance is malformed") from exc
    if not isinstance(provenance, dict) or not isinstance(provenance.get("files"), list):
        raise SourceUnavailableError("Source provenance is malformed")
    return sorted(records, key=lambda item: item["id"]), {
        "origin": "staged_local_sources",
        "files": hashes,
        "seed_provenance": provenance,
        "digest": digest(json.dumps(hashes, sort_keys=True).encode()),
        "live_chatgpt_sync": False,
        "canonical_database_modified": False,
    }


class ReviewStore:
    def __init__(self, source_root: Path, state_root: Path):
        self.source_root = source_root
        self.state_root = state_root
        state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = state_root / "reviews.sqlite3"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS reviews (sequence INTEGER PRIMARY KEY, "
                "request_id TEXT UNIQUE NOT NULL, packet TEXT NOT NULL)"
            )

    def latest(self) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT packet FROM reviews ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def review(self, request_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9:_-]{1,100}", request_id):
            raise ValueError("Invalid review request ID")
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT packet FROM reviews WHERE request_id = ?", (request_id,)
            ).fetchone()
            if existing:
                packet = json.loads(existing[0])
                self.write_report(packet)
                conn.commit()
                return self.export_latest(packet)
            previous = conn.execute(
                "SELECT packet FROM reviews ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            baseline = json.loads(previous[0]) if previous else None
            records, provenance = scan(self.source_root)
            old = {item["id"]: item for item in baseline["records"]} if baseline else {}
            for item in records:
                prior = old.pop(item["id"], None)
                item["change"] = (
                    "added"
                    if prior is None
                    else ("unchanged" if prior["sha256"] == item["sha256"] else "changed")
                )
                item["previous_sha256"] = prior["sha256"] if prior else None
            removed = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "source_path": item["source_path"],
                    "sha256": item["sha256"],
                    "change": "removed",
                    "status": "HELD",
                }
                for item in old.values()
            ]
            summary = {
                change: sum(r["change"] == change for r in records)
                for change in ("added", "changed", "unchanged")
            }
            summary.update(
                total=len(records),
                removed=len(removed),
                held=len(records),
                schema_valid=sum(r["schema_valid"] for r in records),
                candidate_records=sum(r["kind"] == "candidate_record" for r in records),
                forum_sections=sum(r["kind"] == "forum_section" for r in records),
            )
            packet = {
                "schema_version": "1",
                "mode": "review_only",
                "status": "REVIEW_REQUIRED",
                "run_id": str(uuid.uuid4()),
                "request_id": request_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "baseline_run_id": baseline["run_id"] if baseline else None,
                "baseline_kind": "previous_observation_not_approval",
                "publication_allowed": False,
                "summary": summary,
                "provenance": provenance,
                "records": records,
                "removed": removed,
                "next_action": (
                    "Review held source records, map legacy fields, and verify evidence "
                    "before import or publishing."
                ),
            }
            # Do not acknowledge or advance the baseline without the run report.
            self.write_report(packet)
            conn.execute(
                "INSERT INTO reviews(request_id, packet) VALUES (?, ?)",
                (request_id, json.dumps(packet)),
            )
        return self.export_latest(packet)

    def export_latest(self, packet: dict[str, Any]) -> dict[str, Any]:
        """Refresh the convenience export from committed state, serialized with writers.

        The per-run report is required before commit. A failure of this derived
        convenience file must not turn a committed review into an HTTP failure.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT packet FROM reviews ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if row:
                    current = json.loads(row[0])
                    report = self.state_root / f"{current['run_id']}.md"
                    atomic_write(self.state_root / "latest.md", report.read_text())
        except (OSError, sqlite3.Error):
            return {
                **packet,
                "report_export_warning": (
                    "Review saved; latest.md export unavailable. Read the per-run report "
                    "or retry the same request to regenerate the export."
                ),
            }
        return packet

    def write_report(self, packet: dict[str, Any]) -> None:
        lines = [
            "# Hunter OS source review",
            "",
            f"Run: {packet['run_id']}",
            f"Observed: {packet['created_at']}",
            "",
            "**REVIEW REQUIRED — publication is not authorized.**",
            "",
            "Changes compare against the previous observation, not an approved baseline.",
            "",
            json.dumps(packet["summary"], sort_keys=True),
            "",
        ]
        for item in packet["records"]:
            lines += [
                f"## {item['name']} ({item['change']})",
                f"Source: `{item['source_path']}`",
                "",
            ]
            lines += [f"- {f['code']}: {f['message']}" for f in item["findings"]]
            lines += [""]
        if packet["removed"]:
            lines += ["## Removed sources", ""] + [
                f"- {r['source_path']}: {r['name']}" for r in packet["removed"]
            ]
        destination = self.state_root / f"{packet['run_id']}.md"
        atomic_write(destination, "\n".join(lines) + "\n")


def atomic_write(destination: Path, text: str) -> None:
    """Leave the previous report intact if writing its replacement fails."""
    fd, name = tempfile.mkstemp(prefix=".report-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
