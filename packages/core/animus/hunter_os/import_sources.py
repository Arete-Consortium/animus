"""Bounded, provenance-checked staging inputs for the offline Hunter preview."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_FILES = 250


class PreviewError(ValueError):
    """Sanitized input/output failure; no partial plan is returned."""


@dataclass(frozen=True)
class SourceDeclaration:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    path: str
    source_commit: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    source_path: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


@dataclass(frozen=True)
class Manifest:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    repository: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    origin: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    files: Annotated[tuple[SourceDeclaration, ...], Field(min_length=1, max_length=MAX_FILES)]


@dataclass(frozen=True)
class SourceFile:
    declaration: SourceDeclaration
    text: str


@dataclass(frozen=True)
class SourceBundle:
    manifest: Manifest
    manifest_text: str
    files: tuple[SourceFile, ...]


def digest(data: bytes) -> str:
    """SHA-256 identifies staged bytes, not the truth of their game claims."""
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> bytes:
    # Refuse links (including directory links), devices and unexpectedly large inputs.
    # This is an offline operator utility, not a sandbox against hostile local writers.
    try:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise PreviewError("Source links are not allowed.")
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PreviewError("Sources must be regular files with one link.")
            if before.st_size > MAX_FILE_BYTES:
                raise PreviewError("Source exceeds the file size limit.")
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(data) > MAX_FILE_BYTES:
            raise PreviewError("Source exceeds the file size limit.")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise PreviewError("Source changed while reading.")
        return data
    except OSError:
        raise PreviewError("Source cannot be read.") from None


def _inventory(root: Path) -> set[str]:
    found: set[str] = set()

    def walk_error(_: OSError) -> None:
        raise PreviewError("Source directory cannot be read.")

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        relative = Path(directory).relative_to(root)
        if relative != Path(".") and (relative.parts[0] not in {"records", "forum"} or dirs):
            raise PreviewError("Unexpected source directory.")
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise PreviewError("Source directory links are not allowed.")
        if relative == Path(".") and set(dirs) - {"records", "forum"}:
            raise PreviewError("Unexpected source directory.")
        for name in names:
            found.add((relative / name).as_posix())
            if len(found) > MAX_FILES + 1:
                raise PreviewError("Source file count exceeds the limit.")
    return found


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PreviewError("Manifest keys must be unique.")
        result[key] = value
    return result


def load_bundle(root: Path) -> SourceBundle:
    """Validate the complete snapshot before parsing any record or forum content."""
    root = root.absolute()
    raw_manifest = _read(root / "provenance.json")
    try:
        json.loads(raw_manifest, object_pairs_hook=_unique_keys)
        manifest = TypeAdapter(Manifest).validate_json(raw_manifest, strict=True)
    except (ValidationError, json.JSONDecodeError, UnicodeDecodeError):
        raise PreviewError("Invalid source manifest.") from None
    paths = [entry.path for entry in manifest.files]
    if len(paths) != len(set(paths)) or any(
        not re.fullmatch(r"(?:records/[a-z0-9_-]+\.ya?ml|forum/[a-z0-9_-]+\.md)", p) for p in paths
    ):
        raise PreviewError("Source paths must be unique, supported, relative file names.")
    expected = {*paths, "provenance.json"}
    if _inventory(root) != expected:
        raise PreviewError("Source inventory does not match the manifest.")
    raw_files = {"provenance.json": raw_manifest}
    result = []
    total = len(raw_manifest)
    for entry in sorted(manifest.files, key=lambda entry: entry.path):
        data = _read(root / entry.path)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise PreviewError("Source bundle exceeds the total size limit.")
        if digest(data) != entry.sha256:
            raise PreviewError("Source hash does not match the manifest.")
        raw_files[entry.path] = data
        try:
            result.append(SourceFile(entry, data.decode("utf-8")))
        except UnicodeDecodeError:
            raise PreviewError("Source must be UTF-8.") from None
    if _inventory(root) != expected or any(
        _read(root / name) != data for name, data in raw_files.items()
    ):
        raise PreviewError("Source bundle changed while reading.")
    return SourceBundle(manifest, raw_manifest.decode("utf-8"), tuple(result))
