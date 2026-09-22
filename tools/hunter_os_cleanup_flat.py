#!/usr/bin/env python3
"""Remove the text-only flat Hunter OS dump created by the first publisher.

Deletes only messages recorded in ~/.animus/hunter_os/forum_publications.json.
It does not delete the three user-created Forum posts/threads themselves.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://discord.com/api/v10"
REGISTRY_PATH = Path("~/.animus/hunter_os/forum_publications.json").expanduser()
ENV_PATH = Path("~/.config/animus/discord.env").expanduser()


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _token() -> str:
    env = _load_env_file(ENV_PATH)
    return os.environ.get("ANIMUS_DISCORD_TOKEN") or env.get("ANIMUS_DISCORD_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN") or env.get("DISCORD_BOT_TOKEN", "")


def _request_delete(token: str, channel_id: str, message_id: str) -> None:
    req = urllib.request.Request(
        f"{API_BASE}/channels/{channel_id}/messages/{message_id}",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "Animus-HunterOS-Cleanup/1.0",
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            f"Delete failed for {channel_id}/{message_id}: HTTP {exc.code}: {detail}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete the first flat Hunter OS dump.")
    parser.add_argument("--weapons-thread", required=True)
    parser.add_argument("--monsters-thread", required=True)
    parser.add_argument("--guide-thread", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        print(f"No registry found at {REGISTRY_PATH}.")
        return 0

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    thread_ids = {
        "weapons": args.weapons_thread,
        "monsters": args.monsters_thread,
        "hunter_guide": args.guide_thread,
    }

    items: list[tuple[str, str, str]] = []
    for family, entries in registry.items():
        channel_id = thread_ids.get(family)
        if not channel_id or not isinstance(entries, dict):
            continue
        for key, meta in entries.items():
            message_id = str((meta or {}).get("message_id") or "")
            if message_id:
                items.append((family, channel_id, message_id))

    print(f"Managed messages found: {len(items)}")
    if args.dry_run:
        for family, channel_id, message_id in items[:10]:
            print(f"DRY-RUN delete {family}: {channel_id}/{message_id}")
        if len(items) > 10:
            print(f"... and {len(items) - 10} more")
        return 0

    token = _token()
    if not token:
        print("Missing Discord bot token.", file=sys.stderr)
        return 2

    deleted = 0
    for family, channel_id, message_id in items:
        _request_delete(token, channel_id, message_id)
        deleted += 1
        if deleted % 10 == 0:
            print(f"Deleted {deleted}/{len(items)}")
        time.sleep(0.15)

    backup = REGISTRY_PATH.with_suffix(".flat-backup.json")
    REGISTRY_PATH.replace(backup)
    print(f"Deleted {deleted} managed messages.")
    print(f"Registry moved to {backup}")
    print("The three old Forum posts themselves were not deleted; remove or archive them manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
