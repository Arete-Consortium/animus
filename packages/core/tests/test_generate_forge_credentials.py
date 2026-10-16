"""The credential helper must never echo a plaintext password."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_forge_credentials.py"
spec = importlib.util.spec_from_file_location("generate_forge_credentials", SCRIPT)
assert spec is not None and spec.loader is not None
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


@pytest.mark.parametrize("prompted", [False, True])
def test_password_is_not_echoed_and_hash_still_authenticates(capsys, prompted):
    password = "test-only-password-42"
    argv = [str(SCRIPT), "testuser"]
    if not prompted:
        argv.append(password)
    with (
        patch.object(credentials.sys, "argv", argv),
        patch.object(credentials.getpass, "getpass", side_effect=[password, password]),
    ):
        credentials.main()
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err
    assert "FORGE_API_USER='testuser'" in captured.out
    assignments = [
        line.strip()
        for line in captured.out.splitlines()
        if line.strip().startswith("API_CREDENTIALS=")
    ]
    assert len(assignments) == 1
    stored = assignments[0].split("=", 1)[1].strip("'")
    username, hashed = stored.split(":", 1)
    assert username == "testuser"
    assert bcrypt.checkpw(password.encode(), hashed.encode())


def test_mismatched_passwords_emit_no_credentials(capsys):
    with (
        patch.object(credentials.sys, "argv", [str(SCRIPT), "testuser"]),
        patch.object(credentials.getpass, "getpass", side_effect=["test-one", "test-two"]),
        pytest.raises(SystemExit) as error,
    ):
        credentials.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert "Passwords do not match." in captured.err
    assert "API_CREDENTIALS=" not in captured.out
    assert "test-one" not in captured.out + captured.err
    assert "test-two" not in captured.out + captured.err
