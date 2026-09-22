"""Security and grounded-chat tests for Hunter OS."""

from pathlib import Path

from animus.hunter_os import HunterOSRepository
from animus.hunter_os.chat import HUNTER_CHAT_SYSTEM, HunterOSChatService
from animus.hunter_os.security import HunterOSChatPolicy


def _repo() -> HunterOSRepository:
    data = Path(__file__).resolve().parents[2] / "animus" / "hunter_os" / "data"
    return HunterOSRepository(data)


def test_policy_denies_everything_when_unconfigured() -> None:
    policy = HunterOSChatPolicy()
    assert not policy.permits_chat(guild_id=1, channel_id=2, is_mention=True)


def test_policy_is_channel_and_guild_allowlisted() -> None:
    policy = HunterOSChatPolicy(
        allowed_channel_ids=frozenset({20}),
        allowed_guild_ids=frozenset({10}),
    )
    assert policy.permits_chat(guild_id=10, channel_id=20, is_mention=True)
    assert not policy.permits_chat(guild_id=11, channel_id=20, is_mention=True)
    assert not policy.permits_chat(guild_id=10, channel_id=21, is_mention=True)
    assert not policy.permits_chat(guild_id=10, channel_id=20, is_mention=False)


def test_policy_admin_is_explicit_allowlist() -> None:
    policy = HunterOSChatPolicy(admin_user_ids=frozenset({99}))
    assert policy.permits_admin(99)
    assert not policy.permits_admin(100)


def test_env_policy_defaults_to_mentions_and_denies_dms() -> None:
    policy = HunterOSChatPolicy.from_env(
        {
            "HUNTER_OS_CHAT_CHANNEL_IDS": "20,21",
            "HUNTER_OS_GUILD_IDS": "10",
            "HUNTER_OS_ADMIN_USER_IDS": "99",
        }
    )
    assert policy.require_mention
    assert not policy.allow_dms
    assert policy.permits_chat(guild_id=10, channel_id=20, is_mention=True)
    assert not policy.permits_chat(guild_id=None, channel_id=20, is_mention=True)


def test_natural_search_finds_controls_and_guide_content() -> None:
    repo = _repo()
    assert repo.search("How does Encore work?")[0].id == "hunting_horn"
    assert repo.search("Wide-Range")[0].id == "combat_healer_hh_lbg"


def test_chat_context_uses_only_hunter_os_records() -> None:
    service = HunterOSChatService(_repo())
    context = service.context_for("What should we bring for Rathian?")
    assert context.found
    assert context.records[0].id == "rathian"
    assert "Privacy boundary: canonical Hunter OS records only" in context.text
    assert "general Animus memory" in context.text


def test_prompt_explicitly_forbids_general_memory_fallback() -> None:
    service = HunterOSChatService(_repo())
    user_prompt, system_prompt = service.prompt_for("How does Encore work?")
    assert "RECORD hunting_horn" in user_prompt
    assert system_prompt == HUNTER_CHAT_SYSTEM
    assert "Do not use or request general Animus memory" in system_prompt


def test_unknown_question_returns_no_verified_context() -> None:
    service = HunterOSChatService(_repo())
    context = service.context_for("Where can I find an undocumented mystery material?")
    assert not context.found
    assert "no verified matching record" in context.text
