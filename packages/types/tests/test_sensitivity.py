"""Tests for the shared Sensitivity enum."""

from __future__ import annotations

import pytest

from animus_types import Sensitivity


class TestSensitivityEnum:
    def test_four_members(self):
        assert len(list(Sensitivity)) == 4

    def test_values(self):
        assert Sensitivity.PUBLIC.value == "public"
        assert Sensitivity.PERSONAL.value == "personal"
        assert Sensitivity.CONFIDENTIAL.value == "confidential"
        assert Sensitivity.SECRET.value == "secret"

    @pytest.mark.parametrize(
        "v,expected",
        [
            ("public", Sensitivity.PUBLIC),
            ("personal", Sensitivity.PERSONAL),
            ("confidential", Sensitivity.CONFIDENTIAL),
            ("secret", Sensitivity.SECRET),
        ],
    )
    def test_construct_from_value(self, v, expected):
        assert Sensitivity(v) is expected

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Sensitivity("medium")

    def test_zero_deps(self):
        """Sanity check: importing the package doesn't pull in heavy deps."""
        import importlib
        import sys

        # Reload to confirm a fresh import
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("animus_types"):
                del sys.modules[mod_name]

        importlib.import_module("animus_types")
        # animus_types must not pull in any non-stdlib THIRD-PARTY deps. Its own
        # submodules are fine: __init__ re-exports sensitivity + egress, and
        # egress imports secrets (the credential scanner) — three first-party,
        # zero-dependency submodules. Assert no external packages crept in.
        submods = {m for m in sys.modules if m.startswith("animus_types") and "." in m}
        expected = {
            "animus_types.action",
            "animus_types.assessment",
            "animus_types.claim",
            "animus_types.common",
            "animus_types.decision",
            "animus_types.egress",
            "animus_types.entity",
            "animus_types.event",
            "animus_types.exceptions",
            "animus_types.forecast",
            "animus_types.hypothesis",
            "animus_types.knowledge_edge",
            "animus_types.lesson",
            "animus_types.observation",
            "animus_types.outcome",
            "animus_types.pattern",
            "animus_types.sensitivity",
            "animus_types.secrets",
            "animus_types.signal",
            "animus_types.source",
        }
        assert submods == expected, (
            f"animus_types submodule mismatch: got {submods}, expected {expected}"
        )
