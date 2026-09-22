"""Card rendering tests for Hunter OS."""

from pathlib import Path

import pytest

from animus.hunter_os import HunterOSRepository
from animus.hunter_os.renderer import CARD_HEIGHT, CARD_WIDTH, HunterCardRenderer

PIL = pytest.importorskip("PIL.Image")


def _repo() -> HunterOSRepository:
    data = Path(__file__).resolve().parents[2] / "animus" / "hunter_os" / "data"
    return HunterOSRepository(data)


@pytest.mark.parametrize(
    "record_id",
    ["rathian", "hunting_horn", "combat_healer_hh_lbg", "omega_planetes"],
)
def test_vertical_slice_cards_render(tmp_path: Path, record_id: str) -> None:
    record = _repo().get(record_id)
    output = tmp_path / f"{record_id}.png"

    HunterCardRenderer().render(record, output)

    assert output.exists()
    with PIL.open(output) as image:
        assert image.size == (CARD_WIDTH, CARD_HEIGHT)
        assert image.format == "PNG"
