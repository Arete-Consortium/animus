"""SEC-08 regression: sensitive memory content must not reach log output.

These tests prove that raw memory content and search queries do not appear
verbatim in Animus log output at any enabled log level.

Scope:
- MemoryLayer.remember() INFO preview
- DurableMemoryStore.search() DEBUG query
- LocalMemoryStore.search() DEBUG query
- ChromaMemoryStore.search() DEBUG query

Adversarial secret shapes cover credential patterns, PII, and proprietary
phrases to avoid overfitting to a single redaction pattern.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from animus.memory import MemoryLayer
from animus.memory.stores.chroma import ChromaMemoryStore
from animus.memory.stores.durable import DurableMemoryStore
from animus.memory.stores.local import LocalMemoryStore
from animus.memory.types import Memory

# Adversarial secret shapes — representative of the patterns the canonical
# redactor handles, plus one without a credential prefix to ensure truncation
# alone is insufficient.  All values are synthetic test fixtures.
_ADVERSARIAL_SECRETS = [
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123",  # Anthropic key prefix
    "ghp_abcdefghij1234567890ABCDEFGH",  # GitHub token
    "Bearer abcdefghijklmnopqrstuvwxyz1234",  # Bearer token
    "credential_value=test1234567890ABCDEF",  # Credential label pattern
    "ssn_value=123-45-6789 on file",  # PII / SSN
    "ProprietaryProjectX-SECRET-SAUCE-2026",  # Proprietary without credential prefix
]


class TestRememberLogging:
    """MemoryLayer.remember() must not emit raw content in INFO logs."""

    @pytest.mark.parametrize("secret", _ADVERSARIAL_SECRETS)
    def test_remember_info_preview_excludes_raw_secret(self, tmp_path, caplog, secret):
        caplog.set_level(logging.INFO, logger="animus.memory")

        layer = MemoryLayer(tmp_path, backend="local")
        # Place the secret at the start so a naive [:50] preview would capture it.
        content = f"{secret} and some additional harmless prose here"
        layer.remember(content=content)

        # The raw secret must not appear anywhere in captured INFO logs.
        info_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.INFO)
        assert secret not in info_logs, (
            f"raw secret found in INFO logs: {secret!r}\nlogs:\n{info_logs}"
        )

    def test_remember_info_preview_preserves_operational_metadata(self, tmp_path, caplog):
        caplog.set_level(logging.INFO, logger="animus.memory")

        layer = MemoryLayer(tmp_path, backend="local")
        layer.remember(content="harmless fact about Python")

        info_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.INFO)
        # Useful observability: the operation itself should still be visible.
        assert "Remembered" in info_logs or "remembered" in info_logs.lower(), (
            "operational logging was unexpectedly suppressed"
        )


class TestLocalStoreSearchLogging:
    """LocalMemoryStore.search() must not emit raw query in DEBUG logs."""

    @pytest.mark.parametrize("secret", _ADVERSARIAL_SECRETS)
    def test_local_search_debug_excludes_raw_query(self, tmp_path, caplog, secret):
        caplog.set_level(logging.DEBUG, logger="animus.memory")

        store = LocalMemoryStore(tmp_path)
        store.store(Memory.create(content="irrelevant"))
        store.search(secret)

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert secret not in debug_logs, (
            f"raw query found in DEBUG logs: {secret!r}\nlogs:\n{debug_logs}"
        )

    def test_local_search_debug_preserves_operational_metadata(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG, logger="animus.memory")

        store = LocalMemoryStore(tmp_path)
        store.store(Memory.create(content="something"))
        store.search("something")

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        # The search event itself should remain observable.
        assert "found" in debug_logs.lower(), (
            "operational search logging was unexpectedly suppressed"
        )


class TestDurableStoreSearchLogging:
    """DurableMemoryStore.search() must not emit raw query in DEBUG logs."""

    @pytest.mark.parametrize("secret", _ADVERSARIAL_SECRETS)
    def test_durable_search_debug_excludes_raw_query(self, tmp_path, caplog, secret):
        caplog.set_level(logging.DEBUG, logger="animus.memory.durable")

        store = DurableMemoryStore(database_url="sqlite:///:memory:")
        store.create_tables()
        store.store(Memory.create(content="irrelevant"))
        store.search(secret)

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert secret not in debug_logs, (
            f"raw query found in DEBUG logs: {secret!r}\nlogs:\n{debug_logs}"
        )

    def test_durable_search_debug_preserves_operational_metadata(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG, logger="animus.memory.durable")

        store = DurableMemoryStore(database_url="sqlite:///:memory:")
        store.create_tables()
        store.store(Memory.create(content="something"))
        store.search("something")

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert "found" in debug_logs.lower(), (
            "operational search logging was unexpectedly suppressed"
        )


class TestChromaStoreSearchLogging:
    """ChromaMemoryStore.search() must not emit raw query prefix in DEBUG logs.

    Truncation to 30 chars is NOT sufficient redaction — a sensitive prefix
    can still leak. This test uses a secret longer than 30 chars to prove that
    even a truncated preview can expose secrets.
    """

    @pytest.fixture(scope="class")
    def mock_chroma_module(self):
        """Minimal mock chromadb module sufficient for store instantiation."""
        mod = MagicMock()

        class _MockCollection:
            def query(self, **kwargs):
                # Return empty results so the loop exits cleanly.
                return {
                    "ids": [[]],
                    "documents": [[]],
                    "metadatas": [[]],
                    "distances": [[]],
                }

            def add(self, **kwargs):
                pass

            def upsert(self, **kwargs):
                pass

            def delete(self, **kwargs):
                pass

            def count(self):
                return 0

        class _MockClient:
            def __init__(self, path, **kwargs):
                pass

            def get_or_create_collection(self, name, **kwargs):
                return _MockCollection()

            def heartbeat(self):
                return True

        mod.PersistentClient = _MockClient
        mod.HttpClient.side_effect = Exception("no chromadb server")
        mod.Settings = MagicMock()
        return mod

    @pytest.mark.parametrize("secret", _ADVERSARIAL_SECRETS)
    def test_chroma_search_debug_excludes_raw_query_prefix(
        self, tmp_path, caplog, secret, mock_chroma_module
    ):
        caplog.set_level(logging.DEBUG, logger="animus.memory")

        with patch.dict("sys.modules", {"chromadb": mock_chroma_module}):
            store = ChromaMemoryStore(tmp_path)
            store.store(Memory.create(content="irrelevant"))
            store.search(secret)

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        # The FULL secret must not appear. Also, if the secret is >30 chars,
        # its first 30 chars must not appear (the truncation leak).
        assert secret not in debug_logs, (
            f"raw query found in DEBUG logs: {secret!r}\nlogs:\n{debug_logs}"
        )
        if len(secret) > 30:
            prefix = secret[:30]
            assert prefix not in debug_logs, (
                f"truncated prefix leaked in DEBUG logs: {prefix!r}\nlogs:\n{debug_logs}"
            )

    def test_chroma_search_debug_preserves_operational_metadata(
        self, tmp_path, caplog, mock_chroma_module
    ):
        caplog.set_level(logging.DEBUG, logger="animus.memory")

        with patch.dict("sys.modules", {"chromadb": mock_chroma_module}):
            store = ChromaMemoryStore(tmp_path)
            store.store(Memory.create(content="something"))
            store.search("something")

        debug_logs = "\n".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert "found" in debug_logs.lower(), (
            "operational search logging was unexpectedly suppressed"
        )
