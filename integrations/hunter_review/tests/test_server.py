"""Exercise the actual HTTP boundary with a temporary source inventory."""

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from integrations.hunter_review.review import ReviewStore
from integrations.hunter_review.server import make_server


@pytest.fixture
def service(tmp_path):
    source = tmp_path / "sources"
    shutil.copytree(Path(__file__).parents[1] / "sources", source)
    store = ReviewStore(source, tmp_path / "state")
    token = "test-only-credential-" + "x" * 32
    server = make_server(store, token, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield store, f"http://127.0.0.1:{server.server_port}", token
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def request(service, path, body=None, *, auth=True, origin=None):
    _, base, token = service
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def test_auth_and_operator_only_configuration(service):
    store, _, _ = service
    assert request(service, "/healthz", auth=False)[0] == 200
    assert request(service, "/v1/reviews", {"request_id": "unauth"}, auth=False)[0] == 401
    assert request(service, "/v1/reviews/latest", auth=False)[0] == 401
    assert (
        request(service, "/v1/reviews", {"request_id": "browser"}, origin="https://example.com")[0]
        == 403
    )
    assert request(service, "/v1/reviews", {"request_id": "override", "sources": "/tmp"})[0] == 400
    assert request(service, "/v1/publish", {"request_id": "publish"})[0] == 404
    assert request(service, "/v1/reviews", {"request_id": "x" * 2048})[0] == 413
    assert store.latest() is None


def test_http_review_replay_and_source_failure(service):
    store, _, _ = service
    status, initial = request(service, "/v1/reviews", {"request_id": "first"})
    assert status == 200 and initial["publication_allowed"] is False
    assert request(service, "/v1/reviews", {"request_id": "first"}) == (200, initial)
    (store.source_root / "provenance.json").write_text("malformed")
    assert request(service, "/v1/reviews", {"request_id": "bad-source"})[0] == 503
    assert request(service, "/v1/reviews/latest") == (200, initial)
