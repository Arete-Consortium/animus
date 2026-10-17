"""Regression gates for retiring Chroma from the supported Core runtime."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import tomllib

from animus.config import AnimusConfig, MemoryConfig
from animus.memory import MemoryLayer


def test_new_config_defaults_to_local_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIMUS_MEMORY_BACKEND", raising=False)

    assert MemoryConfig().backend == "local"


def test_memory_layer_defaults_to_local_store(tmp_path: Path) -> None:
    layer = MemoryLayer(tmp_path)

    assert layer.backend_type == "local"
    assert type(layer.store).__name__ == "LocalMemoryStore"


def test_legacy_chroma_config_fails_closed_without_opening_fallback(tmp_path: Path) -> None:
    with (
        patch("animus.memory.LocalMemoryStore") as local_store,
        pytest.raises(RuntimeError, match="Chroma memory backend is retired"),
    ):
        MemoryLayer(tmp_path, backend="chroma")

    local_store.assert_not_called()


@pytest.mark.parametrize("backend", ["chromadb", "locla", "", "auto"])
def test_unknown_backend_fails_closed_without_opening_local_store(
    tmp_path: Path, backend: str
) -> None:
    with (
        patch("animus.memory.LocalMemoryStore") as local_store,
        pytest.raises(ValueError, match="Unsupported memory backend"),
    ):
        MemoryLayer(tmp_path, backend=backend)

    local_store.assert_not_called()


def test_existing_config_without_backend_preserves_legacy_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANIMUS_MEMORY_BACKEND", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_level: INFO\n", encoding="utf-8")

    config = AnimusConfig.load(config_path)

    assert config.memory.backend == "chroma"
    with pytest.raises(RuntimeError, match="Chroma memory backend is retired"):
        MemoryLayer(tmp_path, backend=config.memory.backend)


def test_memory_environment_override_wins_after_file_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("memory:\n  backend: chroma\n", encoding="utf-8")
    monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "local")

    config = AnimusConfig.load(config_path)

    assert config.memory.backend == "local"


def test_invalid_memory_environment_override_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("memory:\n  backend: chroma\n", encoding="utf-8")
    monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "locla")

    config = AnimusConfig.load(config_path)

    assert config.memory.backend == "locla"
    with (
        patch("animus.memory.LocalMemoryStore") as local_store,
        pytest.raises(ValueError, match="Unsupported memory backend"),
    ):
        MemoryLayer(tmp_path, backend=config.memory.backend)

    local_store.assert_not_called()


def test_invalid_memory_backend_from_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANIMUS_MEMORY_BACKEND", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("memory:\n  backend: chromadb\n", encoding="utf-8")

    config = AnimusConfig.load(config_path)

    assert config.memory.backend == "chromadb"
    with (
        patch("animus.memory.LocalMemoryStore") as local_store,
        pytest.raises(ValueError, match="Unsupported memory backend"),
    ):
        MemoryLayer(tmp_path, backend=config.memory.backend)

    local_store.assert_not_called()


def test_ensure_dirs_does_not_create_legacy_chroma_directory(tmp_path: Path) -> None:
    config = AnimusConfig(data_dir=tmp_path)

    config.ensure_dirs()

    assert tmp_path.is_dir()
    assert not config.chroma_dir.exists()


def test_core_metadata_does_not_publish_chroma_extra() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]

    assert "chroma" not in extras
    assert all("chroma" not in dependency.lower() for dependency in extras["all"])
