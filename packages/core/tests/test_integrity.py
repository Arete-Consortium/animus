"""Tests for the integrity checker (10/10 polish — tampering detection)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from animus.integrity.checker import (
    _TRACKED_RELATIVE_PATHS,
    _TRACKED_REPO_PATHS,
    IntegrityMismatchError,
    IntegrityNotInitializedError,
    IntegritySignatureError,
    baseline_path,
    compute_current,
    public_key_path,
    regenerate_baseline,
    signature_path,
    signing_key_path,
    tracked_files,
    tracked_module_hashes,
    verify_or_raise,
)


@pytest.fixture
def fake_tree(tmp_path: Path):
    """Build a synthetic mini-tree mirroring the layout of the tracked files."""
    # Layout: tmp_path/animus_pkg/{memory,network,audit}/*.py + mcp_server.py
    pkg_root = tmp_path / "animus_pkg"
    for rel in _TRACKED_RELATIVE_PATHS:
        p = pkg_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# original content of {rel}\n")
    # E9 — create a fake repo root with .git and systemd unit files
    # The repo root must be an ancestor of pkg_root so _repo_root() finds it
    repo_root = tmp_path
    (repo_root / ".git").mkdir(parents=True)
    for repo_rel in _TRACKED_REPO_PATHS:
        p = repo_root / repo_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# systemd unit {repo_rel}\n")
    data_dir = tmp_path / "data"
    return pkg_root, data_dir, repo_root


class TestComputeCurrent:
    def test_hashes_every_tracked_file(self, fake_tree):
        pkg_root, _, repo_root = fake_tree
        hashes = compute_current(pkg_root)
        expected = set(_TRACKED_RELATIVE_PATHS) | set(tracked_module_hashes())
        # When _repo_root() finds a repo, repo paths are also included
        expected |= {f"repo:{p}" for p in _TRACKED_REPO_PATHS}
        assert set(hashes.keys()) == expected
        for h in hashes.values():
            assert len(h) == 64  # sha256 hex
            assert all(c in "0123456789abcdef" for c in h)

    def test_raises_if_tracked_file_missing(self, fake_tree):
        pkg_root, _, _ = fake_tree
        (pkg_root / _TRACKED_RELATIVE_PATHS[0]).unlink()
        with pytest.raises(FileNotFoundError):
            compute_current(pkg_root)


class TestRegenerateBaseline:
    def test_writes_manifest(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        manifest = regenerate_baseline(data_dir, root=pkg_root, note="initial")
        path = baseline_path(data_dir)
        assert path.exists()
        on_disk = json.loads(path.read_text())
        # tracked_files is a tuple in-memory; JSON round-trip yields a list.
        # Compare the meaningful contents independently.
        assert on_disk["hashes"] == manifest["hashes"]
        assert on_disk["note"] == manifest["note"] == "initial"
        assert on_disk["schema_version"] == 1
        assert list(on_disk["tracked_files"]) == list(manifest["tracked_files"])
        assert "generated_at" in manifest
        expected = set(_TRACKED_RELATIVE_PATHS) | set(tracked_module_hashes())
        expected |= {f"repo:{p}" for p in _TRACKED_REPO_PATHS}
        assert set(manifest["hashes"].keys()) == expected

    def test_round_trip_idempotent_on_unchanged_tree(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        m1 = regenerate_baseline(data_dir, root=pkg_root)
        m2 = regenerate_baseline(data_dir, root=pkg_root)
        # Hashes identical; generated_at + note may differ
        assert m1["hashes"] == m2["hashes"]


class TestVerifyOrRaise:
    def test_passes_on_clean_baseline(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        verify_or_raise(data_dir, root=pkg_root)  # no raise

    def test_raises_on_drift(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        # Tamper with one file
        target = pkg_root / _TRACKED_RELATIVE_PATHS[0]
        target.write_text(target.read_text() + "\n# malicious patch\n")
        with pytest.raises(IntegrityMismatchError) as exc:
            verify_or_raise(data_dir, root=pkg_root)
        assert _TRACKED_RELATIVE_PATHS[0] in str(exc.value)
        assert "drifted from baseline" in str(exc.value)

    def test_raises_on_missing_tracked_file(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        (pkg_root / _TRACKED_RELATIVE_PATHS[1]).unlink()
        # Should fail at compute_current with FileNotFoundError, not
        # IntegrityMismatchError — the failure mode for a tracked file
        # vanishing is "the gate is gone entirely", a louder error.
        with pytest.raises(FileNotFoundError):
            verify_or_raise(data_dir, root=pkg_root)

    def test_raises_when_baseline_missing(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        # No baseline written
        with pytest.raises(IntegrityNotInitializedError):
            verify_or_raise(data_dir, root=pkg_root)

    def test_override_env_alone_does_not_bypass(self, fake_tree, monkeypatch):
        # C1-8: the env var by itself must NOT bypass — it needs the operator
        # sentinel too. An attacker who can set an env var can't skip the gate.
        pkg_root, data_dir, _ = fake_tree
        monkeypatch.setenv("ANIMUS_INTEGRITY_OVERRIDE", "1")
        with pytest.raises(IntegrityMismatchError, match="sentinel"):
            verify_or_raise(data_dir, root=pkg_root)

    def test_override_env_plus_sentinel_bypasses(self, fake_tree, monkeypatch, caplog):
        # C1-8: env var + the deliberately-created sentinel file bypasses, and
        # the bypass is audit-logged at ERROR (never a silent skip).
        pkg_root, data_dir, _ = fake_tree
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / ".integrity-override").write_text("update window 2026-06-04\n")
        monkeypatch.setenv("ANIMUS_INTEGRITY_OVERRIDE", "1")
        with caplog.at_level("ERROR"):
            verify_or_raise(data_dir, root=pkg_root)  # no raise
        assert any("INTEGRITY CHECK BYPASSED" in r.message for r in caplog.records)

    def test_extra_files_in_actual_flagged_as_drift(self, fake_tree, monkeypatch):
        """If the tracked-files set is extended without regenerating the
        baseline, the new file shows as drift."""
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)

        # Simulate a new tracked file added in code but not in baseline
        import animus.integrity.checker as checker

        orig_tracked = checker._TRACKED_RELATIVE_PATHS
        extended = orig_tracked + ("new/file.py",)
        monkeypatch.setattr(checker, "_TRACKED_RELATIVE_PATHS", extended)
        (pkg_root / "new").mkdir()
        (pkg_root / "new" / "file.py").write_text("# new tracked file\n")

        with pytest.raises(IntegrityMismatchError) as exc:
            verify_or_raise(data_dir, root=pkg_root)
        assert "new/file.py" in str(exc.value)


class TestTrackedFiles:
    def test_returns_paths_under_root(self, fake_tree, monkeypatch):
        pkg_root, _, repo_root = fake_tree
        # Patch _animus_pkg_root so _repo_root() discovers the fake repo
        import animus.integrity.checker as checker

        monkeypatch.setattr(checker, "_animus_pkg_root", lambda: pkg_root)
        files = tracked_files(pkg_root)
        # Relative tracked files resolve under the given root; cross-package
        # module files resolve to their real installed locations.
        n_modules = len(tracked_module_hashes())
        assert len(files) == len(_TRACKED_RELATIVE_PATHS) + len(_TRACKED_REPO_PATHS) + n_modules
        under_root = [p for p in files if pkg_root in p.parents]
        assert len(under_root) == len(_TRACKED_RELATIVE_PATHS)
        # E9 — repo paths should also be present when repo root is discoverable
        # Exclude package files (which are also under tmp_path) by checking
        # that the path is NOT under pkg_root.
        repo_paths = [p for p in files if repo_root in p.parents and pkg_root not in p.parents]
        assert len(repo_paths) == len(_TRACKED_REPO_PATHS)


class TestRealAnimusPackage:
    """Smoke check against the actually-installed animus package — every
    tracked relative path must point to a real file in the live package."""

    def test_all_tracked_files_exist_in_live_package(self):
        # No root override — uses _animus_pkg_root() default
        hashes = compute_current()  # raises if any file is missing
        expected = set(_TRACKED_RELATIVE_PATHS) | set(tracked_module_hashes())
        # E9 — repo paths are included when the package lives inside a git repo
        import animus.integrity.checker as checker

        repo_root = checker._repo_root()
        if repo_root is not None:
            expected |= {f"repo:{p}" for p in _TRACKED_REPO_PATHS}
        assert set(hashes.keys()) == expected


class TestCrossPackageTracking:
    """A6: the baseline must hash the checker itself and the REAL (cross-
    package) egress/DLP logic, not just core's re-export shim."""

    def test_self_hash_and_real_egress_modules_tracked(self):
        keys = set(compute_current().keys())
        assert "integrity/checker.py" in keys  # self-hash
        assert "learning/guardrails.py" in keys
        assert "module:animus_types.egress" in keys  # real egress logic
        assert "module:animus_types.secrets" in keys  # credential patterns

    def test_forge_enforcement_modules_tracked_when_installed(self):
        """C5 — when forge is importable, the modules that actually gate every
        cloud call (egress engine, content-aware DLP helper, sensitivity router)
        must be in the baseline. Skip cleanly if forge isn't installed."""
        import importlib.util

        if importlib.util.find_spec("animus_forge") is None:
            pytest.skip("animus_forge not installed in this interpreter")

        keys = set(tracked_module_hashes().keys())
        assert "module:animus_forge.network.egress" in keys
        assert "module:animus_forge.providers.base" in keys
        assert "module:animus_forge.providers.router" in keys
        # C1-5 — each concrete cloud provider carries its OWN _check_request_egress;
        # all must be hashed so tampering one provider's gate is detected at boot.
        for prov in (
            "anthropic_provider",
            "openai_provider",
            "azure_openai_provider",
            "bedrock_provider",
            "vertex_provider",
            "llamacpp_provider",
        ):
            assert f"module:animus_forge.providers.{prov}" in keys

    def test_module_drift_trips_verify(self, fake_tree, monkeypatch):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)

        import animus.integrity.checker as checker

        real = checker.tracked_module_hashes

        def tampered():
            h = dict(real())
            first = next(iter(h))
            h[first] = "0" * 64  # simulate a tampered cross-package module
            return h

        monkeypatch.setattr(checker, "tracked_module_hashes", tampered)
        with pytest.raises(IntegrityMismatchError):
            verify_or_raise(data_dir, root=pkg_root)


class TestSignedBaseline:
    """C1-8 — the baseline is ed25519-signed; verify checks the signature
    before trusting the manifest."""

    def test_regenerate_writes_keypair_and_signature(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        assert signing_key_path(data_dir).is_file()
        assert public_key_path(data_dir).is_file()
        assert signature_path(data_dir).is_file()
        # Private key is 0600.
        assert (signing_key_path(data_dir).stat().st_mode & 0o777) == 0o600

    def test_signed_baseline_verifies(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        verify_or_raise(data_dir, root=pkg_root)  # no raise

    def test_tampered_manifest_fails_signature(self, fake_tree):
        # Edit the manifest after signing → signature no longer matches.
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        path = baseline_path(data_dir)
        manifest = json.loads(path.read_text())
        manifest["note"] = "attacker rewrote this"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        with pytest.raises(IntegritySignatureError, match="INVALID"):
            verify_or_raise(data_dir, root=pkg_root)

    def test_missing_signature_when_pubkey_present_fails(self, fake_tree):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        signature_path(data_dir).unlink()  # delete the sig, keep the pubkey
        with pytest.raises(IntegritySignatureError, match="no signature"):
            verify_or_raise(data_dir, root=pkg_root)

    def test_forged_baseline_without_key_is_rejected(self, fake_tree):
        # Attacker regenerates a self-consistent manifest but lacks the signing
        # key → re-signs with a DIFFERENT key whose pubkey doesn't match... the
        # realistic attack is editing the manifest without re-signing, covered
        # above. Here: swap in a different keypair's pubkey → sig mismatch.
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        attacker_pub = Ed25519PrivateKey.generate().public_key()
        public_key_path(data_dir).write_bytes(
            attacker_pub.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        with pytest.raises(IntegritySignatureError):
            verify_or_raise(data_dir, root=pkg_root)


class TestE9SystemdUnitIntegrity:
    """E9 — systemd unit files that define sandbox boundaries must be tracked
    and tampering detected at boot time."""

    def test_systemd_files_in_tracked_set(self):
        assert "redteam/systemd/animus-redteam.service" in _TRACKED_RELATIVE_PATHS
        assert "redteam/systemd/animus-redteam.timer" in _TRACKED_RELATIVE_PATHS

    def test_systemd_drift_trips_verify(self, fake_tree, monkeypatch):
        pkg_root, data_dir, _ = fake_tree
        regenerate_baseline(data_dir, root=pkg_root)

        # Tamper with the service file — e.g., attacker widens the sandbox
        service = pkg_root / "redteam/systemd/animus-redteam.service"
        service.write_text(service.read_text() + "\n# attacker-added override\n")

        with pytest.raises(IntegrityMismatchError) as exc:
            verify_or_raise(data_dir, root=pkg_root)
        assert "animus-redteam.service" in str(exc.value)

    def test_systemd_unit_exists_in_live_package(self):
        import animus

        pkg_root = Path(animus.__file__).parent
        assert (pkg_root / "redteam/systemd/animus-redteam.service").is_file()
        assert (pkg_root / "redteam/systemd/animus-redteam.timer").is_file()

    def test_repo_systemd_files_in_tracked_set(self):
        assert "systemd/animus-autonomous.service" in _TRACKED_REPO_PATHS
        assert "packages/bootstrap/contrib/systemd/animus.service" in _TRACKED_REPO_PATHS

    def test_repo_systemd_drift_trips_verify(self, fake_tree, monkeypatch):
        pkg_root, data_dir, repo_root = fake_tree
        # Patch _animus_pkg_root so _repo_root() walks from the fake tree
        import animus.integrity.checker as checker

        monkeypatch.setattr(checker, "_animus_pkg_root", lambda: pkg_root)
        regenerate_baseline(data_dir, root=pkg_root)

        # Tamper with a repo-level service file
        service = repo_root / "systemd/animus-autonomous.service"
        service.write_text(service.read_text() + "\n# attacker-added override\n")

        with pytest.raises(IntegrityMismatchError) as exc:
            verify_or_raise(data_dir, root=pkg_root)
        assert "systemd/animus-autonomous.service" in str(exc.value)


def test_repo_root_accepts_worktree_git_file(tmp_path, monkeypatch):
    """Worktree installs must retain repo service files in integrity checks."""
    import animus.integrity.checker as checker

    pkg = tmp_path / "packages" / "core" / "animus"
    pkg.mkdir(parents=True)
    (tmp_path / ".git").write_text("gitdir: /unused/worktrees/repair\n")
    monkeypatch.setattr(checker, "_animus_pkg_root", lambda: pkg)
    assert checker._repo_root() == tmp_path
