"""SHA-256 baseline checker for critical hardening code.

Tracks a fixed set of files that implement the boundary gates. On
daemon startup, computes their hashes and compares to a signed-on-disk
baseline. Drift = refuse to boot.

The tracked file set is intentionally small and curated. Adding files
to the set requires regenerating the baseline. This is the right
posture: explicit, auditable, manually attested.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("integrity")


class IntegrityMismatchError(RuntimeError):
    """Raised when a tracked file's hash differs from the baseline."""


class IntegrityNotInitializedError(RuntimeError):
    """Raised when the baseline file is missing and override isn't set."""


class IntegritySignatureError(RuntimeError):
    """Raised when the baseline's detached signature is missing or invalid.

    C1-8: the baseline is signed with an ed25519 key at regenerate time and the
    signature is verified before the manifest is trusted. A present-but-invalid
    or missing-yet-expected signature means the baseline was tampered with (or
    forged by someone without the private key) — fail closed.
    """


# ---------------------------------------------------------------------------
# E9 — Repo-root tracked files (systemd units, deploy configs, etc.)
#
# These live outside the animus package tree but define runtime sandbox
# boundaries. Tampering them silently widens the attack surface.
# Resolved against the git repo root (found by walking up from the package).
# ---------------------------------------------------------------------------
_TRACKED_REPO_PATHS: tuple[str, ...] = (
    "systemd/animus-autonomous.service",
    "systemd/animus-autonomous-knowledge.service",
    "systemd/animus-autonomous-conversation.service",
    "systemd/animus-autonomous-all.service",
    "systemd/animus-autonomous-test.service",
    "deploy/systemd/user/animus-sync.service",
    "deploy/systemd/user/animus-sync-fail.service",
    "packages/bootstrap/contrib/systemd/animus.service",
    "packages/bootstrap/contrib/systemd/animus-forge.service",
    "packages/forge/scripts/animus-bounty-watcher.service",
)


def _repo_root() -> Path | None:
    """Walk up from the animus package root to find the git repo root.

    Returns None if no .git directory or worktree pointer is found (e.g., in a shallow
    deployment without version control).
    """
    pkg = _animus_pkg_root()
    for parent in (pkg, *pkg.parents):
        if (parent / ".git").is_dir() or (parent / ".git").is_file():
            return parent
    return None


# Critical-path files — relative to the animus package root.
# Each path is resolved against ``Path(animus.__file__).parent`` at runtime
# so tests can target a synthetic tree without hardcoded absolute paths.
_TRACKED_RELATIVE_PATHS: tuple[str, ...] = (
    "memory/redaction.py",
    "network/egress.py",
    "mcp_server.py",
    "audit/egress_log.py",
    # A6 — the checker must hash itself (tampering it would otherwise defeat
    # detection) and the immutable learning guardrails.
    "integrity/checker.py",
    "learning/guardrails.py",
    # E9 — redteam systemd unit files (inside the package tree)
    "redteam/systemd/animus-redteam.service",
    "redteam/systemd/animus-redteam.timer",
)

# A6 — cross-package critical-path modules. Core's ``network/egress.py`` is now
# a re-export shim; the REAL egress + DLP logic lives in ``animus_types``, so
# hashing the shim alone is useless. Resolved via importlib (they live outside
# the core package). REQUIRED ones must be present; OPTIONAL forge adopters are
# hashed only when forge is installed in the running interpreter.
_TRACKED_MODULES_REQUIRED: tuple[str, ...] = (
    "animus_types.egress",
    "animus_types.secrets",
)
_TRACKED_MODULES_OPTIONAL: tuple[str, ...] = (
    "animus_forge.providers.openrouter_provider",
    "animus_forge.security.pi_wrap",
    # C5 — the forge-side egress enforcement surface. A6 hashed the OpenRouter
    # provider but left the modules that actually gate every cloud call
    # untracked: the egress allow/deny engine, the content-aware DLP helper +
    # ``CompletionRequest.scannable_text`` (providers.base), and the
    # sensitivity-aware model router (providers.router / TierRouter). Tampering
    # any of these silently disables the boundary, so they must be in baseline.
    "animus_forge.network.egress",
    "animus_forge.providers.base",
    "animus_forge.providers.router",
    # C1-5 — the concrete cloud providers each carry their OWN
    # ``_check_request_egress`` + call sites; C5 tracked only base/router, so
    # tampering a single provider's gate (e.g. making it a no-op) still passed
    # boot detection. Track all five so any provider's egress logic is hashed.
    "animus_forge.providers.anthropic_provider",
    "animus_forge.providers.openai_provider",
    "animus_forge.providers.azure_openai_provider",
    "animus_forge.providers.bedrock_provider",
    "animus_forge.providers.vertex_provider",
    "animus_forge.providers.llamacpp_provider",
)


def _module_file(mod: str) -> Path | None:
    """Resolve an importable module to its source file, or None if absent."""
    import importlib.util

    try:
        spec = importlib.util.find_spec(mod)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin or spec.origin == "built-in":
        return None
    return Path(spec.origin)


def tracked_module_hashes() -> dict[str, str]:
    """Hash the cross-package tracked modules. Required-missing raises."""
    out: dict[str, str] = {}
    for mod in _TRACKED_MODULES_REQUIRED:
        path = _module_file(mod)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"Tracked module missing: {mod}")
        out[f"module:{mod}"] = _hash_file(path)
    for mod in _TRACKED_MODULES_OPTIONAL:
        path = _module_file(mod)
        if path is not None and path.is_file():
            out[f"module:{mod}"] = _hash_file(path)
    return out


def _animus_pkg_root() -> Path:
    """Return the on-disk root of the installed ``animus`` package."""
    import animus

    return Path(animus.__file__).parent


def tracked_files(root: Path | None = None) -> list[Path]:
    """Return the absolute paths of every tracked file (relative + repo + modules)."""
    base = root or _animus_pkg_root()
    paths = [base / rel for rel in _TRACKED_RELATIVE_PATHS]
    # E9 — repo-root paths (systemd units, deploy configs)
    repo = _repo_root()
    if repo is not None:
        for repo_rel in _TRACKED_REPO_PATHS:
            p = repo / repo_rel
            if p.is_file():
                paths.append(p)
    for mod in (*_TRACKED_MODULES_REQUIRED, *_TRACKED_MODULES_OPTIONAL):
        mod_path = _module_file(mod)
        if mod_path is not None:
            paths.append(mod_path)
    return paths


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_current(root: Path | None = None) -> dict[str, str]:
    """Compute the current SHA-256 of every tracked file.

    Missing files raise FileNotFoundError — they're load-bearing and
    must be present.
    """
    base = root or _animus_pkg_root()
    out: dict[str, str] = {}
    for rel in _TRACKED_RELATIVE_PATHS:
        path = base / rel
        if not path.is_file():
            raise FileNotFoundError(f"Tracked file missing: {path}")
        out[rel] = _hash_file(path)
    # E9 — repo-root tracked files (systemd units, deploy configs)
    repo = _repo_root()
    if repo is not None:
        for repo_rel in _TRACKED_REPO_PATHS:
            path = repo / repo_rel
            if not path.is_file():
                raise FileNotFoundError(f"Tracked repo file missing: {path}")
            out[f"repo:{repo_rel}"] = _hash_file(path)
    # Cross-package modules resolve via importlib (independent of ``root``).
    out.update(tracked_module_hashes())
    return out


def default_baseline_dir() -> Path:
    """Canonical location for the integrity baseline.

    Anchored to ``~/.config/animus/`` (NOT ``AnimusConfig.data_dir``)
    because the latter can shift with env overrides (``ANIMUS_DATA_DIR``
    in the daemon's EnvironmentFile). Config dir is stable across env
    changes and lives in the daemon's writable carve-out.
    """
    return Path.home() / ".config" / "animus"


def baseline_path(baseline_dir: Path) -> Path:
    """Return the manifest file path inside ``baseline_dir``.

    Tests pass a tmp_path here. The live CLI + daemon call
    ``default_baseline_dir()`` and pass that.
    """
    return Path(baseline_dir) / "integrity-baseline.json"


# ---------------------------------------------------------------------------
# C1-8 — ed25519 detached signature over the baseline manifest.
#
# The in-process hash self-check is defeatable by anyone who can also rewrite
# the manifest (regenerate a self-consistent baseline). Signing the manifest
# with an ed25519 private key the operator holds OFFLINE closes that: a tamper
# requires re-signing, which needs the private key. Verification uses only the
# public key, which can stay on the box.
#
# Key files live in the baseline dir:
#   integrity-signing.key  — PRIVATE (0600). Generated once; the operator is
#                            warned to back it up and move it OFF the box for
#                            full protection (on-box it still raises the bar
#                            vs. no signature, but an attacker with full box
#                            access could re-sign).
#   integrity-signing.pub  — PUBLIC. Used to verify; safe to keep on-box.
#   integrity-baseline.json.sig — detached signature over the manifest bytes.
# ---------------------------------------------------------------------------


def signing_key_path(baseline_dir: Path) -> Path:
    return Path(baseline_dir) / "integrity-signing.key"


def public_key_path(baseline_dir: Path) -> Path:
    return Path(baseline_dir) / "integrity-signing.pub"


def signature_path(baseline_dir: Path) -> Path:
    return Path(baseline_dir) / "integrity-baseline.json.sig"


def _load_ed25519():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as e:  # pragma: no cover - dep is declared in core
        raise IntegritySignatureError(
            "The `cryptography` package is required for signed integrity "
            "baselines (C1-8). Install animus-core with its dependencies."
        ) from e
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def _ensure_signing_key(baseline_dir: Path):
    """Return the ed25519 private key, generating + persisting it on first use.

    The private key is written 0600 and the operator is loudly warned to move
    it off the box. The public key is written alongside for verification.
    """
    serialization, Ed25519PrivateKey, _ = _load_ed25519()  # noqa: N806 — class, not a var
    priv_path = signing_key_path(baseline_dir)
    pub_path = public_key_path(baseline_dir)
    if priv_path.is_file():
        priv = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        priv_path.parent.mkdir(parents=True, exist_ok=True)
        priv_path.write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        priv_path.chmod(0o600)
        logger.warning(
            "Generated a new integrity signing key at %s. BACK IT UP OFFLINE "
            "and remove it from this box for full tamper-evidence — on-box, an "
            "attacker with file access could re-sign a tampered baseline.",
            priv_path,
        )
    # (Re)write the public key so it always matches the private key.
    pub = priv.public_key()
    pub_path.write_bytes(
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv


def _sign_manifest_bytes(baseline_dir: Path, manifest_bytes: bytes) -> None:
    """Sign the exact manifest bytes and write the detached signature."""
    priv = _ensure_signing_key(baseline_dir)
    sig = priv.sign(manifest_bytes)
    signature_path(baseline_dir).write_bytes(sig)


def _verify_manifest_signature(baseline_dir: Path, manifest_bytes: bytes) -> None:
    """Verify the detached signature over ``manifest_bytes``.

    Policy (fail-closed when a key is present):
      - public key + valid signature → OK.
      - public key present, signature missing/invalid → IntegritySignatureError.
      - no public key on disk → un-migrated baseline; warn and allow (the next
        ``regenerate`` creates the keypair and starts signing). This keeps
        pre-C1-8 installs bootable while making signing the default going forward.
    """
    serialization, _, _ = _load_ed25519()
    from cryptography.exceptions import InvalidSignature

    pub_path = public_key_path(baseline_dir)
    sig_path = signature_path(baseline_dir)
    if not pub_path.is_file():
        logger.warning(
            "Integrity baseline is UNSIGNED (no %s). Run "
            "`python -m animus.integrity.cli regenerate` to start signing it.",
            pub_path.name,
        )
        return
    if not sig_path.is_file():
        raise IntegritySignatureError(
            f"Integrity baseline has a public key but no signature ({sig_path}). "
            "The baseline may have been tampered with. Regenerate it from an "
            "attested-clean tree, or investigate."
        )
    pub = serialization.load_pem_public_key(pub_path.read_bytes())
    try:
        pub.verify(sig_path.read_bytes(), manifest_bytes)
    except InvalidSignature as e:
        raise IntegritySignatureError(
            "Integrity baseline signature is INVALID — the manifest does not "
            "match its signature. Tampering or key mismatch. Refusing to trust "
            "the baseline."
        ) from e


def regenerate_baseline(
    baseline_dir: Path,
    root: Path | None = None,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Write a fresh baseline manifest (and its ed25519 signature). Returns the
    manifest contents.

    Call this only after intentional, attested updates to a tracked
    file. The note field is for human auditability — e.g.
    "Stage 3.D landed; regenerated baseline".
    """
    current = compute_current(root)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        # Every tracked key (relative paths + ``module:*`` entries).
        "tracked_files": sorted(current.keys()),
        "hashes": current,
    }
    path = baseline_path(baseline_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    path.write_bytes(manifest_bytes)
    # C1-8: sign the exact bytes just written.
    _sign_manifest_bytes(baseline_dir, manifest_bytes)
    logger.info(
        "Regenerated + signed integrity baseline at %s (%d files tracked)",
        path,
        len(_TRACKED_RELATIVE_PATHS),
    )
    return manifest


def load_baseline(baseline_dir: Path) -> dict[str, Any]:
    """Load the manifest. Raises if missing."""
    path = baseline_path(baseline_dir)
    if not path.is_file():
        raise IntegrityNotInitializedError(
            f"No integrity baseline at {path}. Run "
            "`python -m animus.integrity.cli regenerate` after the next "
            "intentional update to tracked files, or set "
            "ANIMUS_INTEGRITY_OVERRIDE=1 to bypass (NOT recommended)."
        )
    return json.loads(path.read_text())


def verify_or_raise(baseline_dir: Path, root: Path | None = None) -> None:
    """Check tracked files against the on-disk baseline.

    Behavior:
      - Signature invalid/missing-when-expected → ``IntegritySignatureError``.
      - Hashes match → return silently.
      - Mismatch → raise ``IntegrityMismatchError`` listing drifted files.
      - Baseline missing → raise ``IntegrityNotInitializedError``.
      - Override → requires BOTH ``ANIMUS_INTEGRITY_OVERRIDE=1`` AND an
        operator-created sentinel file (C1-8 hardening); audit-logged.

    This is the daemon-startup hook. Refusing to boot on drift forces
    the operator to either confirm the legitimate update (by
    regenerating the baseline) or investigate the unexpected change.
    """
    # C1-8: the env var alone is too easy for an attacker to inject. Require a
    # deliberate, operator-created sentinel file alongside it, and audit-log the
    # bypass loudly so it can never be a silent skip.
    if os.environ.get("ANIMUS_INTEGRITY_OVERRIDE") == "1":
        sentinel = Path(baseline_dir) / ".integrity-override"
        if not sentinel.is_file():
            raise IntegrityMismatchError(
                "ANIMUS_INTEGRITY_OVERRIDE=1 is set but the confirmation "
                f"sentinel {sentinel} is absent. Create it deliberately to "
                "confirm a legitimate update window, then remove it after. "
                "(C1-8: the env var alone no longer bypasses the gate.)"
            )
        logger.error(
            "INTEGRITY CHECK BYPASSED — ANIMUS_INTEGRITY_OVERRIDE=1 + sentinel "
            "%s present. The tamper gate is OFF for this boot. Remove the "
            "sentinel once the update window closes.",
            sentinel,
        )
        return

    # C1-8: verify the ed25519 signature over the exact on-disk manifest bytes
    # BEFORE parsing/trusting it. A tampered baseline (or one forged without the
    # private key) fails here.
    path = baseline_path(baseline_dir)
    if not path.is_file():
        raise IntegrityNotInitializedError(
            f"No integrity baseline at {path}. Run "
            "`python -m animus.integrity.cli regenerate` after the next "
            "intentional update to tracked files."
        )
    manifest_bytes = path.read_bytes()
    _verify_manifest_signature(baseline_dir, manifest_bytes)

    manifest = json.loads(manifest_bytes)
    expected = manifest.get("hashes", {})
    actual = compute_current(root)

    mismatches: list[tuple[str, str, str]] = []
    for rel, expected_hash in expected.items():
        actual_hash = actual.get(rel)
        if actual_hash != expected_hash:
            mismatches.append((rel, expected_hash, actual_hash or "MISSING"))

    extra = set(actual) - set(expected)
    for rel in extra:
        mismatches.append((rel, "(not in baseline)", actual[rel]))

    if mismatches:
        lines = ["Integrity check failed — tracked file(s) drifted from baseline:"]
        for rel, exp, act in mismatches:
            lines.append(f"  {rel}: expected={exp[:16]}… actual={act[:16]}…")
        lines.append(
            "If this drift is legitimate (intentional update), regenerate "
            "the baseline via `python -m animus.integrity.cli regenerate`. "
            "Otherwise investigate before allowing the daemon to start."
        )
        raise IntegrityMismatchError("\n".join(lines))

    logger.debug(
        "Integrity check passed: %d tracked files match baseline (generated at %s)",
        len(expected),
        manifest.get("generated_at", "unknown"),
    )
