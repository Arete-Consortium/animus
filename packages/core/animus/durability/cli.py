"""CLI for durability export / rebuild (roadmap A8).

Run::

    python -m animus.durability.cli export --all [-o animus-export.zip]
    python -m animus.durability.cli verify <archive.zip>
    python -m animus.durability.cli rebuild <archive.zip> --target <dir> [--overwrite]
    python -m animus.durability.cli preflight

``export --all`` captures the whole data dir + a redacted config snapshot.
``rebuild`` verifies the manifest checksums before restoring (cold-rebuild).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from animus.durability.export import (
    DurabilityError,
    ManifestMismatchError,
    export_all,
    rebuild,
    verify_archive,
)


def _load_config():
    from animus.config import AnimusConfig

    return AnimusConfig.load()


def cmd_export(out: str | None, all_flag: bool) -> int:
    if not all_flag:
        print("export currently supports only --all", file=sys.stderr)
        return 2
    config = _load_config()
    out_path = Path(out) if out else Path.cwd() / "animus-export.zip"
    try:
        snapshot = config.model_dump() if hasattr(config, "model_dump") else None
    except Exception:
        snapshot = None
    written = export_all(config.data_dir, out_path, config_snapshot=snapshot)
    print(f"Exported all state to {written}")
    return 0


def cmd_verify(archive: str) -> int:
    try:
        manifest = verify_archive(Path(archive))
    except (DurabilityError, ManifestMismatchError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Archive OK — {manifest['file_count']} files, schema v{manifest['schema_version']}")
    return 0


def cmd_rebuild(archive: str, target: str, overwrite: bool) -> int:
    try:
        manifest = rebuild(Path(archive), Path(target), overwrite=overwrite)
    except (DurabilityError, ManifestMismatchError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Restored {manifest['file_count']} files into {target}")
    return 0


def cmd_preflight() -> int:
    """Inspect configured SQL schema without writes or connection-detail output."""
    from animus.durability.postgres_store import DurableObjectStore
    from animus.durability.schema import SchemaCompatibilityError

    store = None
    try:
        store = DurableObjectStore()
        store.preflight()
    except SchemaCompatibilityError as exc:
        # This exception contains only metadata checks, never row data or URLs.
        print(f"Incompatible registry: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Registry preflight unavailable; check configuration and connectivity.", file=sys.stderr
        )
        return 2
    finally:
        if store is not None:
            store._engine.dispose()
    print("Registry schema compatible. No data was changed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Animus durability export/rebuild.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="Export all state to a portable archive.")
    ex.add_argument("--all", action="store_true", help="Export the entire data dir.")
    ex.add_argument("-o", "--out", default=None, help="Output archive path.")

    ve = sub.add_parser("verify", help="Verify an archive's manifest checksums.")
    ve.add_argument("archive")

    rb = sub.add_parser("rebuild", help="Restore state from an archive (cold rebuild).")
    rb.add_argument("archive")
    rb.add_argument("--target", required=True, help="Destination data dir.")
    rb.add_argument("--overwrite", action="store_true", help="Restore over a non-empty dir.")

    sub.add_parser("preflight", help="Read-only SQL schema compatibility check.")

    args = parser.parse_args(argv)
    if args.cmd == "export":
        return cmd_export(args.out, args.all)
    if args.cmd == "verify":
        return cmd_verify(args.archive)
    if args.cmd == "rebuild":
        return cmd_rebuild(args.archive, args.target, args.overwrite)
    if args.cmd == "preflight":
        return cmd_preflight()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
