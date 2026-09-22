"""Discord text-format tests for Hunter OS."""

from pathlib import Path

import pytest

from animus.hunter_os import HunterOSRepository
from animus.hunter_os.discord_format import DISCORD_MESSAGE_LIMIT, format_record_message


def _repo() -> HunterOSRepository:
    data = Path(__file__).resolve().parents[2] / "animus" / "hunter_os" / "data"
    return HunterOSRepository(data)


@pytest.mark.parametrize(
    "record_id",
    ["rathian", "hunting_horn", "combat_healer_hh_lbg", "omega_planetes"],
)
def test_vertical_slice_discord_text_is_searchable_and_bounded(record_id: str) -> None:
    record = _repo().get(record_id)
    message = format_record_message(record)

    assert record.name.upper() in message
    assert record.id in message
    assert "Wilds only" in message
    assert len(message) <= DISCORD_MESSAGE_LIMIT


def test_rathian_text_includes_field_answer() -> None:
    message = format_record_message(_repo().get("rathian"))
    assert "Dragon" in message
    assert "Hunting Horn: Head" in message
    assert "Poison preparation" in message
