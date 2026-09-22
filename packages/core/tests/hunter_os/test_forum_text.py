"""Tests for text-first Hunter OS Forum content."""

from animus.hunter_os.forum_text import DISCORD_SAFE_LIMIT, build_index_blocks, load_forum_blocks


def test_all_three_forum_documents_load() -> None:
    for name in ("weapons", "monsters", "hunter_guide"):
        blocks = load_forum_blocks(name)
        assert blocks
        assert all(len(block.content) <= DISCORD_SAFE_LIMIT for block in blocks)


def test_monster_forum_contains_full_audited_roster() -> None:
    blocks = load_forum_blocks("monsters")
    text = "\n".join(block.content for block in blocks)
    for monster in (
        "CHATACABRA",
        "RATHIAN",
        "REY DAU",
        "OMEGA PLANETES",
        "OMEGA SAVAGE",
        "GOGMAZIOS",
    ):
        assert monster in text


def test_weapon_forum_contains_all_weapon_types_and_hh_songbook() -> None:
    blocks = load_forum_blocks("weapons")
    text = "\n".join(block.content for block in blocks)
    for weapon in (
        "GREAT SWORD",
        "LONG SWORD",
        "HUNTING HORN",
        "LIGHT BOWGUN",
        "HEAVY BOWGUN",
        "BOW",
    ):
        assert weapon in text
    assert "HH — BONE HORN LINE" in text
    assert "HH — ARTIAN OMILTIKA" in text


def test_hunter_guide_contains_core_systems() -> None:
    blocks = load_forum_blocks("hunter_guide")
    text = "\n".join(block.content for block in blocks)
    for section in (
        "COMBAT HEALER",
        "ARMOR SPHERE FARMING",
        "ZENNY FARMING",
        "PROGRESSION ROADMAP",
        "ARTIAN FORGE",
    ):
        assert section in text


def test_index_is_chunked_safely() -> None:
    blocks = load_forum_blocks("weapons")
    index = build_index_blocks("weapons", blocks)
    assert index
    assert all(len(block.content) <= DISCORD_SAFE_LIMIT for block in index)
