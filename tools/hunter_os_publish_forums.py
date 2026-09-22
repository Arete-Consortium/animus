#!/usr/bin/env python3
"""Publish Hunter OS text as organized Discord Forum posts.

Target layout:
  Monster Hunter Wilds (Discord category, created manually)
    ├─ Weapons (Forum Channel)
    │    ├─ Great Sword
    │    ├─ Long Sword
    │    ├─ Hunting Horn
    │    └─ ...
    ├─ Monsters (Forum Channel)
    │    ├─ Rathian
    │    ├─ Rey Dau
    │    └─ ...
    └─ Hunter Guide (Forum Channel)
         ├─ Start Here
         ├─ Combat Healer
         ├─ Farming
         ├─ Artian Forge
         └─ ...

Discord Forum posts are threads. Threads do not nest, so hierarchy is created at
the Category -> Forum Channel -> Forum Post level.

This script uses Discord REST only. It does not start another gateway session
and does not access Animus memory.
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
from typing import Any

_CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "packages", "core")
if os.path.isdir(_CORE_DIR) and os.path.realpath(_CORE_DIR) not in sys.path:
    sys.path.insert(0, os.path.realpath(_CORE_DIR))

from animus.hunter_os.forum_text import ForumBlock, load_forum_blocks

API_BASE = "https://discord.com/api/v10"
REGISTRY_PATH = Path("~/.animus/hunter_os/forum_posts.json").expanduser()
ENV_PATH = Path("~/.config/animus/discord.env").expanduser()

FORUM_ENV = {
    "weapons": "HUNTER_OS_WEAPONS_FORUM_ID",
    "monsters": "HUNTER_OS_MONSTERS_FORUM_ID",
    "hunter_guide": "HUNTER_OS_GUIDE_FORUM_ID",
}


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


def _setting(name: str, file_env: dict[str, str]) -> str:
    return os.environ.get(name) or file_env.get(name, "")


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_registry(registry: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(REGISTRY_PATH)


class DiscordRest:
    """Minimal Discord REST client with rate-limit handling."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Discord bot token is required.")
        self._token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        attempts: int = 6,
    ) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bot {self._token}",
            "User-Agent": "Animus-HunterOS-ForumPublisher/1.0",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(attempts):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                body = exc.read()
                if exc.code == 429 and attempt < attempts - 1:
                    try:
                        retry = float(json.loads(body or b"{}").get("retry_after", 1.0))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        retry = 1.0
                    time.sleep(max(retry, 0.25))
                    continue
                detail = body.decode("utf-8", errors="replace")[:700]
                raise RuntimeError(
                    f"Discord API {method} {path} failed: HTTP {exc.code}: {detail}"
                ) from exc

        raise RuntimeError(f"Discord API {method} {path} exhausted retries.")

    def create_forum_post(self, forum_id: str, block: ForumBlock) -> tuple[str, str]:
        payload = {
            "name": block.title[:100],
            "auto_archive_duration": 10080,
            "message": {
                "content": block.content,
                "allowed_mentions": {"parse": []},
            },
        }
        result = self.request("POST", f"/channels/{forum_id}/threads", payload)
        thread_id = str(result["id"])
        message = result.get("message") or {}
        message_id = str(message.get("id") or "")
        if not message_id:
            raise RuntimeError("Discord did not return the forum starter message ID.")
        return thread_id, message_id

    def edit_starter(self, thread_id: str, message_id: str, content: str) -> None:
        self.request(
            "PATCH",
            f"/channels/{thread_id}/messages/{message_id}",
            {
                "content": content,
                "allowed_mentions": {"parse": []},
            },
        )


def _publish_forum(
    client: DiscordRest,
    *,
    name: str,
    forum_id: str,
    registry: dict[str, Any],
    dry_run: bool,
) -> tuple[int, int, int]:
    blocks = load_forum_blocks(name)
    forum_registry = registry.setdefault(name, {})

    created = updated = unchanged = 0

    for block in blocks:
        prior = forum_registry.get(block.key, {})
        prior_sha = prior.get("sha256")
        thread_id = prior.get("thread_id")
        message_id = prior.get("message_id")

        if prior_sha == block.sha256 and thread_id and message_id:
            unchanged += 1
            continue

        if dry_run:
            if thread_id and message_id:
                updated += 1
            else:
                created += 1
            continue

        if thread_id and message_id:
            try:
                client.edit_starter(str(thread_id), str(message_id), block.content)
                updated += 1
            except RuntimeError as exc:
                if "HTTP 404" not in str(exc):
                    raise
                thread_id, message_id = client.create_forum_post(forum_id, block)
                created += 1
        else:
            thread_id, message_id = client.create_forum_post(forum_id, block)
            created += 1

        forum_registry[block.key] = {
            "thread_id": str(thread_id),
            "message_id": str(message_id),
            "sha256": block.sha256,
            "title": block.title,
        }
        _save_registry(registry)
        time.sleep(0.2)

    current_keys = {block.key for block in blocks}
    stale = sorted(set(forum_registry).difference(current_keys))
    if stale:
        print(f"{name}: {len(stale)} stale managed post(s) retained for manual review.")

    return created, updated, unchanged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish Hunter OS text as individual Discord Forum posts."
    )
    parser.add_argument(
        "--only",
        choices=tuple(FORUM_ENV),
        action="append",
        help="Publish only one content family; may be repeated.",
    )
    parser.add_argument("--weapons-forum", help="Weapons Forum Channel ID.")
    parser.add_argument("--monsters-forum", help="Monsters Forum Channel ID.")
    parser.add_argument("--guide-forum", help="Hunter Guide Forum Channel ID.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without Discord writes.")
    args = parser.parse_args()

    file_env = _load_env_file(ENV_PATH)
    token = _setting("ANIMUS_DISCORD_TOKEN", file_env) or _setting("DISCORD_BOT_TOKEN", file_env)
    if not token and not args.dry_run:
        print("Missing ANIMUS_DISCORD_TOKEN / DISCORD_BOT_TOKEN.", file=sys.stderr)
        return 2

    selected = args.only or list(FORUM_ENV)
    cli_forums = {
        "weapons": args.weapons_forum,
        "monsters": args.monsters_forum,
        "hunter_guide": args.guide_forum,
    }

    forums: dict[str, str] = {}
    for name in selected:
        forum_id = cli_forums[name] or _setting(FORUM_ENV[name], file_env)
        if not forum_id and not args.dry_run:
            print(
                f"Missing {FORUM_ENV[name]} or corresponding --*-forum argument.",
                file=sys.stderr,
            )
            return 2
        forums[name] = forum_id or "<dry-run>"

    registry = _load_registry()
    client = DiscordRest(token or "dry-run-token")

    total_created = total_updated = total_unchanged = 0
    for name in selected:
        created, updated, unchanged = _publish_forum(
            client,
            name=name,
            forum_id=forums[name],
            registry=registry,
            dry_run=args.dry_run,
        )
        total_created += created
        total_updated += updated
        total_unchanged += unchanged
        print(f"{name}: create={created} update={updated} unchanged={unchanged}")

    print(
        f"TOTAL: create={total_created} update={total_updated} unchanged={total_unchanged}"
        + (" [DRY RUN]" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
