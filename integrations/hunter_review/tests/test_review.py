"""Review boundaries: real domain validation, durable diffs, source immutability."""

import hashlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from integrations.hunter_review import review as review_module
from integrations.hunter_review.review import ReviewStore, SourceUnavailableError


@pytest.fixture
def store(tmp_path):
    source = tmp_path / "sources"
    shutil.copytree(Path(__file__).parents[1] / "sources", source)
    return ReviewStore(source, tmp_path / "state")


def test_real_staging_inventory_is_held_and_durable(store):
    before = {p: p.read_bytes() for p in store.source_root.rglob("*") if p.is_file()}
    provenance = json.loads((store.source_root / "provenance.json").read_text())
    for source in provenance["files"]:
        assert (
            hashlib.sha256((store.source_root / source["path"]).read_bytes()).hexdigest()
            == source["sha256"]
        )
    first = store.review("first")
    assert first["summary"]["candidate_records"] == 4
    assert first["summary"]["forum_sections"] > 50
    assert first["summary"]["added"] == first["summary"]["total"]
    assert first["summary"]["held"] == first["summary"]["total"]
    assert first["summary"]["schema_valid"] == 0
    assert not first["publication_allowed"]
    assert first == store.review("first")
    second = ReviewStore(store.source_root, store.state_root).review("second")
    assert second["summary"]["unchanged"] == first["summary"]["total"]
    assert second["summary"]["added"] == 0
    assert second["status"] == "REVIEW_REQUIRED"
    assert second["baseline_run_id"] == first["run_id"]
    assert all(p.read_bytes() == data for p, data in before.items())
    assert (store.state_root / "latest.md").exists()


def test_added_changed_removed_and_replayed_requests(store):
    store.review("first")
    path = store.source_root / "records/rathian.yaml"
    path.write_text(path.read_text() + "\nnotes: [review change]\n")
    (store.source_root / "records/combat_healer_hh_lbg.yaml").unlink()
    (store.source_root / "records/new.yaml").write_text("name: New candidate\n")
    packet = store.review("second")
    assert {k: packet["summary"][k] for k in ("added", "changed", "removed")} == {
        "added": 1,
        "changed": 1,
        "removed": 1,
    }
    assert packet == store.review("second")
    assert packet["publication_allowed"] is False


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "oversized", "missing_folder"])
def test_unsafe_or_unavailable_source_preserves_baseline(store, unsafe, tmp_path):
    initial = store.review("initial")
    path = store.source_root / "records/rathian.yaml"
    if unsafe == "symlink":
        path.unlink()
        path.symlink_to(tmp_path / "outside.yaml")
    elif unsafe == "hardlink":
        (tmp_path / "linked.yaml").hardlink_to(path)
    elif unsafe == "oversized":
        path.write_bytes(b"x" * (256 * 1024 + 1))
    else:
        shutil.rmtree(store.source_root / "records")
    with pytest.raises(SourceUnavailableError):
        store.review("bad")
    assert store.latest() == initial


def test_malformed_candidate_is_held_not_approved(store):
    (store.source_root / "records/rathian.yaml").write_text("[malformed: ")
    packet = store.review("malformed")
    item = next(r for r in packet["records"] if r["source_path"].endswith("rathian.yaml"))
    assert item["findings"][0]["code"] == "source.malformed"
    assert item["status"] == "HELD"


def test_current_schema_audit_is_used_without_granting_approval(store):
    source = {
        "id": "mhw-guide-test",
        "name": "Fixture",
        "record_type": "guide",
        "status": "review",
        "verified_date": None,
        "topic": "fixture",
        "sections": {},
    }
    (store.source_root / "records/new.json").write_text(json.dumps(source))
    packet = store.review("typed")
    item = next(r for r in packet["records"] if r["source_path"].endswith("new.json"))
    assert item["schema_valid"]
    assert "verification.missing" in {f["code"] for f in item["findings"]}
    assert "approval.required" in {f["code"] for f in item["findings"]}


def test_concurrent_duplicate_request_has_one_durable_run(store):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.review, ["same", "same"]))
    assert results[0] == results[1]
    assert store.review("next")["baseline_run_id"] == results[0]["run_id"]


def test_unreadable_directory_keeps_baseline(store, monkeypatch):
    initial = store.review("initial")
    original = os.scandir

    def unreadable(path):
        if Path(path) == store.source_root / "records":
            raise PermissionError("directory unavailable")
        return original(path)

    monkeypatch.setattr(os, "scandir", unreadable)
    with pytest.raises(SourceUnavailableError):
        store.review("unreadable")
    assert store.latest() == initial


def test_report_failure_keeps_baseline_and_retry_keeps_delta(store, monkeypatch):
    initial = store.review("initial")
    target = store.source_root / "records/rathian.yaml"
    target.write_text(target.read_text() + "\nnotes: [changed]\n")
    original = store.write_report

    def fail(_packet):
        raise OSError("report storage unavailable")

    monkeypatch.setattr(store, "write_report", fail)
    with pytest.raises(OSError):
        store.review("retry")
    assert store.latest() == initial
    monkeypatch.setattr(store, "write_report", original)
    recovered = store.review("retry")
    assert recovered["summary"]["changed"] == 1
    assert (store.state_root / f"{recovered['run_id']}.md").exists()


def test_replay_repairs_report_without_reverting_latest(store):
    first = store.review("first")
    second = store.review("second")
    report = store.state_root / f"{first['run_id']}.md"
    report.unlink()
    assert store.review("first") == first
    assert report.exists()
    assert second["run_id"] in (store.state_root / "latest.md").read_text()


def test_latest_export_failure_returns_committed_packet_and_retry_repairs(store, monkeypatch):
    original = review_module.atomic_write

    def failed_export(path, text):
        if path.name == "latest.md":
            raise OSError("export unavailable")
        original(path, text)

    monkeypatch.setattr(review_module, "atomic_write", failed_export)
    packet = store.review("first")
    assert packet["report_export_warning"]
    assert store.latest()["run_id"] == packet["run_id"]
    assert (store.state_root / f"{packet['run_id']}.md").exists()
    monkeypatch.setattr(review_module, "atomic_write", original)
    replay = store.review("first")
    assert "report_export_warning" not in replay
    assert replay["run_id"] in (store.state_root / "latest.md").read_text()
