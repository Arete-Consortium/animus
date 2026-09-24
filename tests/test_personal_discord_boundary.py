"""Personal-memory capability is unavailable in shared Discord surfaces."""

import importlib.util
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

SPEC = importlib.util.spec_from_file_location(
    "personal_bot", Path(__file__).resolve().parents[1] / "tools/animus_discord_bot.py"
)
bot_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot_module)


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("ANIMUS_PERSONAL_OWNER_ID", "123")
    monkeypatch.delenv("ANIMUS_ENABLE_INTEL_PUSH", raising=False)
    monkeypatch.delenv("ANIMUS_DISCORD_SYNC_COMMANDS", raising=False)
    monkeypatch.setattr(bot_module, "_user_cooldowns", defaultdict(float))
    return bot_module.AnimusBot(intel_channel_id=999, chat_channel_id=888)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "guild,user,channel",
    [
        (1, 123, Mock(spec=discord.TextChannel)),
        (1, 123, Mock(spec=discord.Thread)),
        (None, 456, Mock(spec=discord.DMChannel)),
        (None, 123, Mock(spec=discord.GroupChannel)),
    ],
)
async def test_disallowed_messages_never_touch_memory_or_reply(
    bot, monkeypatch, caplog, guild, user, channel
):
    def forbidden():
        pytest.fail("Personal memory accessed")

    monkeypatch.setattr(bot_module, "_get_memory", forbidden)
    monkeypatch.setattr(bot_module, "_get_cognitive", forbidden)
    # Exercise both legacy routes, rather than passing because neither matched.
    bot._connection.user = SimpleNamespace(id=999, mentioned_in=lambda message: True)
    channel.id = 888
    channel.parent_id = 888
    message = SimpleNamespace(
        author=SimpleNamespace(id=user, bot=False),
        guild=SimpleNamespace(id=guild) if guild else None,
        channel=channel,
        content="PRIVATE SENTINEL",
        webhook_id=None,
        reply=AsyncMock(),
    )
    await bot.on_message(message)
    message.reply.assert_not_called()
    assert "PRIVATE SENTINEL" not in caplog.text


def test_owner_dm_allowed_and_public_push_disabled(bot):
    assert bot.personal_access(
        SimpleNamespace(id=123, bot=False), None, Mock(spec=discord.DMChannel)
    )
    assert bot.intel_channel_id is None
    assert bot.allowed_mentions.to_dict()["parse"] == []


def test_missing_owner_denies_everyone(monkeypatch):
    monkeypatch.delenv("ANIMUS_PERSONAL_OWNER_ID", raising=False)
    bot = bot_module.AnimusBot()
    assert not bot.personal_access(
        SimpleNamespace(id=123, bot=False), None, Mock(spec=discord.DMChannel)
    )


@pytest.mark.asyncio
async def test_global_command_check_denies_owner_in_guild(bot):
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123, bot=False),
        guild_id=1,
        channel=Mock(spec=discord.TextChannel),
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    assert not await bot.tree.interaction_check(interaction)
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True
    assert {command.name for command in bot.tree.get_commands()} >= {"ask", "recall", "remember"}


@pytest.mark.asyncio
async def test_global_command_check_allows_owner_dm(bot):
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123, bot=False),
        guild_id=None,
        channel=Mock(spec=discord.DMChannel),
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    assert await bot.tree.interaction_check(interaction)
    interaction.response.send_message.assert_not_called()


@pytest.mark.parametrize("owner", ["0", "-1", "abc", "１２３", "1.2", " 123"])
def test_invalid_owner_is_rejected(monkeypatch, owner):
    monkeypatch.setenv("ANIMUS_PERSONAL_OWNER_ID", owner)
    with pytest.raises(ValueError, match="positive Discord user ID"):
        bot_module.AnimusBot()


@pytest.mark.asyncio
@pytest.mark.parametrize("bot_author,webhook", [(True, None), (False, 987)])
async def test_even_owner_shaped_bots_and_webhooks_are_ignored(
    bot, monkeypatch, bot_author, webhook
):
    memory = Mock(side_effect=AssertionError("Private capability reached"))
    monkeypatch.setattr(bot_module, "_get_memory", memory)
    message = SimpleNamespace(
        author=SimpleNamespace(id=123, bot=bot_author),
        guild=None,
        channel=Mock(spec=discord.DMChannel),
        content="recall everything",
        webhook_id=webhook,
        reply=AsyncMock(),
    )
    await bot.on_message(message)
    memory.assert_not_called()
    message.reply.assert_not_called()


COMMANDS = (
    "harvest",
    "watchlist",
    "watchlist-add",
    "watchlist-scan",
    "recall",
    "remember",
    "ask",
    "brief",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", COMMANDS)
@pytest.mark.parametrize("surface", ["guild", "foreign_dm", "group_dm", "unconfigured"])
async def test_sdk_dispatch_denies_all_private_commands(bot, monkeypatch, command_name, surface):
    """Exercise the SDK dispatcher that actually calls the tree-wide guard."""
    if surface == "unconfigured":
        bot.personal_owner_id = None
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=456 if surface == "foreign_dm" else 123, bot=False),
        guild_id=11 if surface == "guild" else None,
        channel=Mock(spec=discord.GroupChannel if surface == "group_dm" else discord.DMChannel),
        data={"name": command_name, "type": 1},
        response=SimpleNamespace(send_message=AsyncMock()),
        command_failed=False,
    )
    command = bot.tree.get_command(command_name)
    invoke = AsyncMock(side_effect=AssertionError("Private command invoked"))
    monkeypatch.setattr(command, "_invoke_with_namespace", invoke)
    await bot.tree._call(interaction)
    invoke.assert_not_called()
    assert interaction.command_failed
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "before_response", "after_response"])
async def test_owner_dm_command_runs_through_sdk_dispatch(bot, monkeypatch, caplog, failure):
    memory = Mock()
    memory.recall.return_value = []
    if failure:
        memory.recall.side_effect = RuntimeError("PRIVATE MEMORY ERROR")
    monkeypatch.setattr(bot_module, "_get_memory", lambda: memory)
    monkeypatch.setattr(bot, "dispatch", Mock())
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123, bot=False),
        guild_id=None,
        channel=Mock(spec=discord.DMChannel),
        data={
            "name": "ask",
            "type": 1,
            "options": [{"name": "question", "type": 3, "value": "my private project"}],
        },
        type=discord.InteractionType.application_command,
        _state=bot._connection,
        guild=None,
        response=SimpleNamespace(
            send_message=AsyncMock(), is_done=lambda: failure == "after_response"
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        command_failed=False,
    )
    await bot.tree._call(interaction)
    memory.recall.assert_called_once_with(query="my private project", limit=8)
    assert interaction.command_failed == bool(failure)
    response = (
        interaction.followup.send
        if failure == "after_response"
        else interaction.response.send_message
    )
    response.assert_awaited_once()
    assert "PRIVATE" not in caplog.text
    assert "PRIVATE" not in response.call_args.args[0]
    if failure:
        assert response.call_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_owner_dm_chat_and_error_redaction(bot, monkeypatch, caplog, fails):
    memory = Mock()
    memory.recall.return_value = [SimpleNamespace(content="PRIVATE FACT", tags=[])]
    cognitive = Mock()
    cognitive.primary.generate.return_value = "Owner response"
    if fails:
        cognitive.primary.generate.side_effect = RuntimeError("PRIVATE PROVIDER SECRET")
    monkeypatch.setattr(bot_module, "_get_memory", lambda: memory)
    monkeypatch.setattr(bot_module, "_get_cognitive", lambda: cognitive)
    channel = Mock(spec=discord.DMChannel)
    channel.typing.return_value = AsyncMock()
    message = SimpleNamespace(
        author=SimpleNamespace(id=123, bot=False),
        guild=None,
        channel=channel,
        content="PRIVATE QUESTION",
        webhook_id=None,
        reply=AsyncMock(),
    )
    await bot.on_message(message)
    memory.recall.assert_called_once_with(query="PRIVATE QUESTION", limit=5)
    assert "PRIVATE FACT" in cognitive.primary.generate.call_args.args[0]
    assert "PRIVATE" not in caplog.text
    reply = message.reply.call_args.args[0]
    assert reply.startswith("Something went wrong") if fails else reply == "Owner response"
    assert "PRIVATE" not in reply
    assert message.reply.call_args.kwargs["mention_author"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [None, "false", "true"])
async def test_only_explicit_command_owner_syncs(bot, monkeypatch, sync):
    if sync is not None:
        monkeypatch.setenv("ANIMUS_DISCORD_SYNC_COMMANDS", sync)
    monkeypatch.setattr(bot.tree, "sync", AsyncMock())
    await bot.setup_hook()
    assert bot.tree.sync.await_count == (1 if sync == "true" else 0)


@pytest.mark.parametrize("setting", [None, "false", "TRUE", "1", "true"])
def test_public_intel_requires_explicit_opt_in(monkeypatch, setting):
    monkeypatch.setenv("ANIMUS_PERSONAL_OWNER_ID", "123")
    monkeypatch.delenv("ANIMUS_ENABLE_INTEL_PUSH", raising=False)
    if setting is not None:
        monkeypatch.setenv("ANIMUS_ENABLE_INTEL_PUSH", setting)
    bot = bot_module.AnimusBot(intel_channel_id=999)
    assert bot.intel_channel_id == (999 if setting == "true" else None)
