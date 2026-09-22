"""Security boundary for shared Hunter OS Discord chat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _parse_ids(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()

    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError as exc:
            raise ValueError(f"Invalid Discord ID in Hunter OS configuration: {item!r}") from exc
    return frozenset(values)


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean in Hunter OS configuration: {raw!r}")


@dataclass(frozen=True)
class HunterOSChatPolicy:
    """Least-privilege routing policy for the shared Monster Hunter chat.

    Secure defaults:
    - no allowed channel means no Hunter OS chat routing;
    - mentions are required;
    - DMs are denied;
    - admin actions are denied unless an explicit user allowlist is configured.
    """

    allowed_channel_ids: frozenset[int] = frozenset()
    allowed_guild_ids: frozenset[int] = frozenset()
    admin_user_ids: frozenset[int] = frozenset()
    forum_parent_ids: frozenset[int] = frozenset()
    forum_thread_ids: frozenset[int] = frozenset()
    require_mention: bool = True
    allow_dms: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HunterOSChatPolicy:
        values = os.environ if env is None else env
        return cls(
            allowed_channel_ids=_parse_ids(values.get("HUNTER_OS_CHAT_CHANNEL_IDS")),
            allowed_guild_ids=_parse_ids(values.get("HUNTER_OS_GUILD_IDS")),
            admin_user_ids=_parse_ids(values.get("HUNTER_OS_ADMIN_USER_IDS")),
            forum_parent_ids=_parse_ids(values.get("HUNTER_OS_FORUM_CHANNEL_IDS")),
            forum_thread_ids=_parse_ids(values.get("HUNTER_OS_FORUM_THREAD_IDS")),
            require_mention=_parse_bool(
                values.get("HUNTER_OS_REQUIRE_MENTION"),
                default=True,
            ),
            allow_dms=_parse_bool(values.get("HUNTER_OS_ALLOW_DMS"), default=False),
        )

    @property
    def configured(self) -> bool:
        return bool(self.allowed_channel_ids)

    def permits_chat(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        is_mention: bool,
    ) -> bool:
        """Return True only for explicitly allowed shared-chat traffic."""

        if channel_id not in self.allowed_channel_ids:
            return False

        if guild_id is None:
            if not self.allow_dms:
                return False
        elif self.allowed_guild_ids and guild_id not in self.allowed_guild_ids:
            return False

        if self.require_mention and not is_mention:
            return False

        return True

    def is_display_surface(self, *, channel_id: int, parent_id: int | None = None) -> bool:
        """Return True for the display-only Hunter OS Forum or its information threads."""

        if channel_id in self.forum_parent_ids or channel_id in self.forum_thread_ids:
            return True
        return parent_id is not None and parent_id in self.forum_parent_ids

    def permits_admin(self, user_id: int) -> bool:
        """Future publishing/admin commands require an explicit user allowlist."""

        return user_id in self.admin_user_ids
