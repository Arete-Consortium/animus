"""Explicit operator commands: plan a review import, then apply the inspected plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import date
from importlib.resources import files
from pathlib import Path

from animus.durability.postgres_store import DurableObjectStore
from animus.durability.scope import ObjectScope
from animus.hunter_os.importer import MAX_PLAN_BYTES, HunterOSImporter, ImportPlan


def _write_new(path: Path, text: str) -> None:
    temporary = None
    try:
        data = text.encode("utf-8")
        if len(data) > MAX_PLAN_BYTES:
            raise ValueError("Plan exceeds the size limit.")
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Use ANIMUS_DATABASE_URL; never accept or print a URL on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="Deployment-selected Hunter owner.")
    parser.add_argument("--source-root", type=Path, help="Defaults to packaged seed sources.")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="Read-only comparison; write a new review plan.")
    planning.add_argument("--as-of", type=date.fromisoformat, required=True)
    planning.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser(
        "apply-review", help="Import inspected candidates, without approval."
    )
    apply.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    store = None
    applying = args.command == "apply-review"
    try:
        store = DurableObjectStore(scope=ObjectScope.hunter(args.owner))
        importer = HunterOSImporter(store)
        if applying:
            if not args.plan.is_file() or args.plan.stat().st_size > MAX_PLAN_BYTES:
                raise ValueError("Invalid plan file.")
            with args.plan.open("rb") as stream:
                data = stream.read(MAX_PLAN_BYTES + 1)
            if len(data) > MAX_PLAN_BYTES:
                raise ValueError("Plan exceeds the size limit.")
            plan = ImportPlan.from_json(data.decode("utf-8"))
            result = importer.apply(plan, source_root=args.source_root)
            sys.stdout.write(result.to_json())
        else:
            source_root = args.source_root or Path(
                str(files("animus.hunter_os").joinpath("seed_sources"))
            )
            if args.output.resolve().is_relative_to(source_root.resolve()):
                raise ValueError("Plan output must be outside the source bundle.")
            plan = importer.plan(source_root=args.source_root, as_of=args.as_of)
            _write_new(args.output, plan.to_json())
            sys.stdout.write(
                json.dumps(
                    {
                        "actions": dict(Counter(i.action for i in plan.items)),
                        "issues": list(plan.issues),
                    }
                )
                + "\n"
            )
        return 0
    except Exception:
        # Driver exceptions can contain credentials and SQL payloads. A lost commit
        # acknowledgment may require an idempotent replay, not a claim of rollback.
        message = (
            "Import did not report success; inspect or replay the same plan."
            if applying
            else "Import plan unavailable; check source, destination and output."
        )
        sys.stderr.write(message + "\n")
        return 1
    finally:
        if store is not None:
            store._engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
