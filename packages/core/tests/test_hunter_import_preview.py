"""Migration previews retain evidence and fail closed without live dependencies."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from animus.hunter_os import import_sources
from animus.hunter_os.import_preview import build_preview, main
from animus.hunter_os.import_sources import PreviewError

AS_OF = date(2026, 9, 22)
REPO = Path(__file__).resolve().parents[3]
SEEDS = REPO / "packages/core/animus/hunter_os/seed_sources"


@pytest.fixture
def bundle(tmp_path):
    destination = tmp_path / "sources"
    shutil.copytree(SEEDS, destination)
    return destination


def replace_source(bundle, relative, text):
    """Simulate an intentionally revised snapshot, retaining manifest integrity."""
    target = bundle / relative
    target.write_bytes(text.encode("utf-8"))
    manifest_path = bundle / "provenance.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next((f for f in manifest["files"] if f["path"] == relative), None)
    if entry is None:
        entry = {**manifest["files"][0], "path": relative}
        manifest["files"].append(entry)
    entry["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


def record(plan, name="rathian"):
    return next(r for r in plan.records if r.source_path == f"records/{name}.yaml")


def test_packaged_snapshot_matches_n8n_snapshot():
    original = REPO / "integrations/hunter_review/sources"
    for source in SEEDS.rglob("*"):
        if source.is_file():
            assert source.read_bytes() == (original / source.relative_to(SEEDS)).read_bytes()
    assert {p.relative_to(SEEDS) for p in SEEDS.rglob("*") if p.is_file()} == {
        p.relative_to(original) for p in original.rglob("*") if p.is_file()
    }


def test_complete_preview_is_repeatable_and_preserves_exact_sources(bundle):
    plan = build_preview(bundle, as_of=AS_OF)
    assert plan.to_json() == build_preview(bundle, as_of=AS_OF).to_json()
    assert plan.to_json() == build_preview(as_of=AS_OF).to_json()
    assert plan.registry_comparison == "not_performed"
    assert plan.counts == {
        "created": None,
        "updated": None,
        "unchanged": None,
        "source_files": 7,
        "records": 4,
        "converted_records": 4,
        "forum_sections": 101,
        "held": 105,
        "items_with_conversion_conflicts": 0,
        "approved": 0,
        "writes": 0,
    }
    decoded = json.loads(plan.to_json())
    assert decoded["manifest_raw_text"].encode() == (bundle / "provenance.json").read_bytes()
    for source in decoded["source_files"]:
        raw = source["raw_text"].encode("utf-8")
        assert raw == (bundle / source["provenance"]["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["provenance"]["sha256"]
    assert all(not r.unmapped_fields for r in plan.records)
    assert all(
        r.source_claims == {"status": "verified", "verified_date": "2026-09-21"}
        for r in plan.records
    )
    for r in plan.records:
        assert r.payload["status"] == "review"
        assert r.payload["verified_date"] is None
        assert r.payload["review_reasons"]
        assert {f["code"] for f in r.audit} >= {
            "review.required",
            "verification.missing",
            "source.locator",
        }
        assert all(s["content_sha256"] is None for s in r.payload["sources"])


def test_conversion_preserves_specialist_details_and_relationships():
    plan = build_preview(as_of=AS_OF)
    rathian = record(plan).payload
    assert rathian["targets"] == {"hunting_horn": ["Head"], "sever": ["Tail"]}
    assert rathian["weakness_secondary"] == ["Thunder"]
    assert rathian["capture_rule"] is None
    horn = record(plan, "hunting_horn").payload
    assert horn["weapon_type"] == "hunting_horn"
    assert horn["controls"]["note_1"] == {"xbox": "Y", "ps5": "Triangle", "pc": "LMB"}
    assert horn["exact_weapon_required"] is True
    guide = record(plan, "combat_healer_hh_lbg").payload
    assert guide["topic"] == "combat-healer"
    assert guide["relationships"] == [{"relation": "related", "record_id": horn["id"]}]
    omega = record(plan, "omega_planetes")
    assert omega.payload["phases"] == []
    assert omega.payload["timeline_complete"] is False
    assert all(not m["source_ids"] for m in omega.payload["mechanics"])
    assert {f["code"] for f in omega.audit} >= {"source.feature", "encounter.timeline"}


def test_forum_ranges_reconstruct_documents_and_keep_distinct_variants(bundle):
    plan = build_preview(bundle, as_of=AS_OF)
    for path in sorted({s.source_path for s in plan.forum}):
        sections = [s for s in plan.forum if s.source_path == path]
        assert "".join(s.raw_text for s in sections).encode() == (bundle / path).read_bytes()
        assert sections[0].kind == "preamble"
        for index, section in enumerate(sections):
            assert section.sha256 == hashlib.sha256(section.raw_text.encode()).hexdigest()
            assert section.start_line == (sections[index - 1].end_line + 1 if index else 1)
            assert section.disposition == "held"
    headings = {s.heading for s in plan.forum}
    assert {"OMEGA PLANETES", "OMEGA SAVAGE", "ARKVELD", "GUARDIAN ARKVELD"} <= headings


def test_forum_fences_crlf_and_duplicate_titles_are_lossless(bundle):
    text = "# Preamble\r\n```md\r\n## Not a section\r\n```\r\n## Same\r\nA\r\n## Same\r\nB"
    replace_source(bundle, "forum/weapons.md", text)
    plan = build_preview(bundle, as_of=AS_OF)
    sections = [s for s in plan.forum if s.source_path == "forum/weapons.md"]
    assert len(sections) == 3
    assert "".join(s.raw_text for s in sections) == text
    assert all("forum.ambiguous_heading" in s.issues for s in sections[1:])
    assert plan.counts["items_with_conversion_conflicts"] == 2


def test_duplicate_id_is_never_overwritten_and_relationship_is_held(bundle):
    replace_source(
        bundle, "records/duplicate.yaml", (bundle / "records/hunting_horn.yaml").read_text()
    )
    plan = build_preview(bundle, as_of=AS_OF)
    assert plan.counts["records"] == 5
    duplicates = [r for r in plan.records if r.canonical_id == "mhw-weapon-type-hunting-horn"]
    assert len(duplicates) == 2
    assert all("record.duplicate_identity" in r.issues for r in duplicates)
    assert "relationship.target_missing_or_ambiguous" in record(plan, "combat_healer_hh_lbg").issues


def test_missing_target_is_held(bundle):
    target = bundle / "records/hunting_horn.yaml"
    replace_source(
        bundle,
        "records/hunting_horn.yaml",
        target.read_text().replace("id: hunting_horn", "id: unknown_horn"),
    )
    plan = build_preview(bundle, as_of=AS_OF)
    assert record(plan, "hunting_horn").payload is None
    assert "relationship.target_missing_or_ambiguous" in record(plan, "combat_healer_hh_lbg").issues


@pytest.mark.parametrize(
    "suffix,pointer",
    [
        ("future_field: keep me\n", "/future_field"),
        ("weakness: {primary: Dragon, unknown: keep me}\n", "/weakness/unknown"),
        (
            "sources: [{document: manual, section: section, unexpected: keep me}]\n",
            "/sources/0/unexpected",
        ),
    ],
)
def test_unmapped_fields_are_visible_and_retained(bundle, suffix, pointer):
    import yaml

    target = bundle / "records/rathian.yaml"
    raw = yaml.safe_load(target.read_text())
    raw.update(yaml.safe_load(suffix))
    text = yaml.safe_dump(raw)
    replace_source(bundle, "records/rathian.yaml", text)
    plan = build_preview(bundle, as_of=AS_OF)
    assert pointer in record(plan).unmapped_fields
    assert "record.unmapped_fields" in record(plan).issues
    assert any(s["raw_text"] == text for s in plan.source_files)


@pytest.mark.parametrize(
    "text",
    [
        "id: rathian\nid: overwrite\n",
        "x: &x [*x]\n",
        "[a, b]\n",
        "{1: value}",
        "x: !!python/object/apply:os.system [echo forbidden]",
        "x: .nan",
        "x: " + "[" * 31 + "0" + "]" * 31,
        "x: !!binary c2VjcmV0",
        'status: "\\uD800"',
        'unknown: "\\uD800"',
    ],
)
def test_invalid_yaml_is_held_without_losing_raw_source(bundle, text):
    replace_source(bundle, "records/rathian.yaml", text)
    plan = build_preview(bundle, as_of=AS_OF)
    assert record(plan).payload is None
    assert record(plan).issues == ["record.invalid_yaml"]
    assert any(s["raw_text"] == text for s in plan.source_files)


@pytest.mark.parametrize(
    "before,after",
    [
        ("timeline_complete: false", 'timeline_complete: "false"'),
        ("name: Omega Planetes", "name: 123"),
    ],
)
def test_schema_rejects_scalar_coercion(bundle, before, after):
    target = bundle / "records/omega_planetes.yaml"
    replace_source(bundle, "records/omega_planetes.yaml", target.read_text().replace(before, after))
    item = record(build_preview(bundle, as_of=AS_OF), "omega_planetes")
    assert item.payload is None
    assert "record.invalid_payload" in item.issues


@pytest.mark.parametrize(
    "change", ["hash", "missing", "extra", "symlink", "directory_link", "hardlink", "oversized"]
)
def test_bad_snapshot_is_rejected_before_returning_a_plan(bundle, tmp_path, change):
    target = bundle / "records/rathian.yaml"
    if change == "hash":
        target.write_text(target.read_text() + "# changed")
    elif change == "missing":
        target.unlink()
    elif change == "extra":
        (bundle / "forum/extra.md").write_text("extra")
    elif change in {"symlink", "hardlink"}:
        outside = tmp_path / "outside.yaml"
        target.rename(outside)
        if change == "symlink":
            target.symlink_to(outside)
        else:
            target.hardlink_to(outside)
    elif change == "directory_link":
        (bundle / "forum").rename(tmp_path / "outside")
        (bundle / "forum").symlink_to(tmp_path / "outside", target_is_directory=True)
    else:
        target.write_bytes(b"x" * (import_sources.MAX_FILE_BYTES + 1))
    with pytest.raises(PreviewError):
        build_preview(bundle, as_of=AS_OF)


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "../outside.yaml"),
        ("path", "/tmp/outside.yaml"),
        ("source_commit", "bad"),
        ("sha256", "BAD"),
        ("path", "records/nested/file.yaml"),
    ],
)
def test_invalid_manifest_is_rejected(bundle, field, value):
    path = bundle / "provenance.json"
    manifest = json.loads(path.read_text())
    manifest["files"][0][field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(PreviewError):
        build_preview(bundle, as_of=AS_OF)


def test_changed_source_during_scan_fails(bundle, monkeypatch):
    original = import_sources._read
    reads = 0

    def changing(path):
        nonlocal reads
        data = original(path)
        reads += 1
        if reads == 8:
            source = bundle / "records/rathian.yaml"
            source.write_text(source.read_text() + "# concurrent change")
        return data

    monkeypatch.setattr(import_sources, "_read", changing)
    with pytest.raises(PreviewError, match="changed"):
        build_preview(bundle, as_of=AS_OF)


@pytest.mark.parametrize("value", [None, "2026-09-22", datetime(2026, 9, 22)])
def test_explicit_date_is_required(value):
    with pytest.raises(ValueError):
        build_preview(as_of=value)


def test_cli_writes_complete_json_and_refuses_overwrite(tmp_path, capsys):
    output = tmp_path / "preview.json"
    args = ["--as-of", "2026-09-22", "--output", str(output)]
    result = main(args)
    assert result == 0
    assert json.loads(output.read_text())["counts"]["held"] == 105
    assert json.loads(capsys.readouterr().out)["writes"] == 0
    original = output.read_bytes()
    result = main(args)
    assert result == 1
    assert output.read_bytes() == original
    assert set(tmp_path.iterdir()) == {output}
    assert "Preview failed" in capsys.readouterr().err


def test_cli_invalid_bundle_does_not_create_artifact(bundle, tmp_path, capsys):
    (bundle / "records/rathian.yaml").write_text("broken")
    output = tmp_path / "preview.json"
    result = main(["--source-root", str(bundle), "--as-of", "2026-09-22", "--output", str(output)])
    assert result == 1
    assert not output.exists()
    assert "broken" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "sources",
    [
        "sources: [ignored, {document: field manual, section: Rathian}]",
        "sources: [{document: first, section: A}, ignored, {document: second, section: B}]",
    ],
)
def test_provenance_mappings_follow_destination_index_after_invalid_source(bundle, sources):
    import yaml

    target = bundle / "records/rathian.yaml"
    raw = yaml.safe_load(target.read_text())
    raw.update(yaml.safe_load(sources))
    replace_source(bundle, "records/rathian.yaml", yaml.safe_dump(raw))
    item = record(build_preview(bundle, as_of=AS_OF))
    for source_pointer, destination_pointer in item.mappings.items():
        if source_pointer.startswith("/sources/"):
            source_index, key = source_pointer.split("/")[2:]
            destination_index = destination_pointer.split("/")[2]
            assert (
                raw["sources"][int(source_index)][key]
                == item.payload["sources"][int(destination_index)][key]
            )
    assert "record.unmapped_fields" in item.issues


def test_manifest_duplicate_keys_rejected(bundle):
    path = bundle / "provenance.json"
    path.write_text(
        path.read_text().replace('"repository":', '"repository": "other", "repository":')
    )
    with pytest.raises(PreviewError, match="unique"):
        build_preview(bundle, as_of=AS_OF)


def test_output_cannot_be_inside_source_bundle(bundle):
    output = bundle / "preview.json"
    result = main(["--source-root", str(bundle), "--as-of", "2026-09-22", "--output", str(output)])
    assert result == 1
    assert not output.exists()
    assert build_preview(bundle, as_of=AS_OF).counts["held"] == 105


def test_new_variant_requires_explicit_identity_mapping(bundle):
    path = bundle / "records/rathian.yaml"
    replace_source(
        bundle,
        "records/rathian.yaml",
        path.read_text().replace("variant: normal", "variant: guardian"),
    )
    item = record(build_preview(bundle, as_of=AS_OF))
    assert item.payload is None
    assert item.canonical_id is None
    assert item.issues == ["record.identity_mapping_required"]


def test_patch_sensitive_claim_retains_caveat(bundle):
    path = bundle / "records/rathian.yaml"
    replace_source(
        bundle,
        "records/rathian.yaml",
        path.read_text().replace("status: verified", "status: patch-sensitive"),
    )
    item = record(build_preview(bundle, as_of=AS_OF))
    assert item.payload["patch_sensitive"] is True
    assert {f["code"] for f in item.audit} >= {"patch.caveat", "patch.policy"}
