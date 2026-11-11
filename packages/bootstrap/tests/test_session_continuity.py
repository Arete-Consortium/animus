"""Session-continuity API behavior with and without Animus Kernel."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.config.schema import AnimusConfig
from animus_bootstrap.dashboard.app import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    original = app.state.config
    app.state.config = AnimusConfig()
    try:
        yield TestClient(app)
    finally:
        app.state.config = original


def test_checkpoint_reports_unavailable_without_kernel(client: TestClient) -> None:
    with patch(
        "animus_bootstrap.dashboard.routers.session._checkpoint_facade",
        return_value=None,
    ):
        response = client.get("/api/session/checkpoint")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "messages": [],
        "summary": "",
        "turns": 0,
    }
