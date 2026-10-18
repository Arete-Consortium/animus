"""Coverage push round 12 — manager Fernet, config YAML branches, proactive, entities load."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# IntegrationManager — Fernet encryption paths (lines 257-258, 269-274, 296-304)
# ---------------------------------------------------------------------------


class TestManagerFernetSaveLoad:
    """Fernet encryption paths for credential save/load."""

    def _derive_key(self, secret: str) -> bytes:
        digest = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    def test_fernet_save_and_load_roundtrip(self, tmp_path):
        """Test Fernet paths by mocking cryptography at the import level."""
        from animus.integrations.manager import IntegrationManager

        mgr = IntegrationManager(data_dir=tmp_path)

        # Real-ish Fernet mock that does reversible encrypt/decrypt
        encrypted_store = {}

        class FakeFernet:
            def __init__(self, key):
                self.key = key

            @staticmethod
            def generate_key():
                return b"fake-fernet-key-32-bytes-padded!"

            def encrypt(self, data):
                token = base64.b64encode(data)
                encrypted_store["last"] = token
                return token

            def decrypt(self, token):
                return base64.b64decode(token)

        fake_crypto_fernet = MagicMock()
        fake_crypto_fernet.Fernet = FakeFernet

        with (
            patch.object(IntegrationManager, "_fernet_available", return_value=True),
            patch.dict(
                "sys.modules",
                {
                    "cryptography": MagicMock(),
                    "cryptography.fernet": fake_crypto_fernet,
                },
            ),
        ):
            mgr._save_credentials("test_svc", {"token": "secret123"})
            loaded = mgr._load_credentials("test_svc")

        assert loaded is not None
        assert loaded["token"] == "secret123"

    def test_fernet_load_decrypt_failure_falls_through(self, tmp_path):
        """Fernet available but decrypt fails → falls through to base64."""
        from animus.integrations.manager import IntegrationManager

        mgr = IntegrationManager(data_dir=tmp_path)

        # Save with base64 (no Fernet)
        with patch.object(IntegrationManager, "_fernet_available", return_value=False):
            mgr._save_credentials("svc", {"key": "val"})

        # Now load with Fernet "available" but decrypt fails
        class BadFernet:
            def __init__(self, key):
                pass

            @staticmethod
            def generate_key():
                return b"key"

            def decrypt(self, token):
                raise Exception("bad token")

        fake_mod = MagicMock()
        fake_mod.Fernet = BadFernet

        with (
            patch.object(IntegrationManager, "_fernet_available", return_value=True),
            patch.dict(
                "sys.modules",
                {
                    "cryptography": MagicMock(),
                    "cryptography.fernet": fake_mod,
                },
            ),
        ):
            loaded = mgr._load_credentials("svc")

        # Should fall through to base64 decode
        assert loaded is not None
        assert loaded["key"] == "val"


# ---------------------------------------------------------------------------
# AnimusConfig.load — full YAML config branches (lines 470-611)
# ---------------------------------------------------------------------------


class TestConfigLoadFullYaml:
    """Cover all the `if "key" in data:` branches in AnimusConfig.load."""

    @patch.dict("os.environ", {}, clear=False)
    def test_load_full_config_yaml(self, tmp_path):
        import os

        os.environ.pop("OPENAI_BASE_URL", None)

        from animus.config import AnimusConfig

        config_file = tmp_path / "config.yaml"
        config_data = {
            "data_dir": str(tmp_path / "data"),
            "log_level": "DEBUG",
            "log_to_file": True,
            "model": {
                "provider": "anthropic",
                "name": "claude-3",
                "ollama_url": "http://localhost:11434",
                "openai_base_url": "http://localhost:8080",
            },
            "memory": {
                "backend": "local",
                "collection_name": "test_coll",
            },
            "api": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 9090,
                "api_key": "test-key",
            },
            "voice": {
                "input_enabled": True,
                "output_enabled": True,
                "whisper_model": "small",
                "tts_engine": "espeak",
                "tts_rate": 180,
            },
            "integrations": {
                "google": {
                    "enabled": True,
                    "client_id": "gid",
                    "client_secret": "gsecret",
                },
                "todoist": {
                    "enabled": True,
                    "api_key": "todo-key",
                },
                "filesystem": {
                    "enabled": True,
                    "indexed_paths": ["/home/test"],
                    "exclude_patterns": ["*.pyc"],
                },
                "webhooks": {
                    "enabled": True,
                    "port": 8888,
                    "secret": "wh-secret",
                },
            },
            "learning": {
                "enabled": True,
                "auto_scan_enabled": True,
                "auto_scan_interval_hours": 6,
                "min_pattern_occurrences": 5,
                "min_pattern_confidence": 0.8,
                "lookback_days": 30,
            },
            "proactive": {
                "enabled": True,
                "background_enabled": True,
                "background_interval_seconds": 120,
            },
            "entities": {
                "enabled": True,
                "auto_extract": True,
                "auto_discover": True,
            },
            "autonomous": {
                "enabled": True,
                "observe_policy": "all",
                "notify_policy": "important",
                "act_policy": "approved",
                "execute_policy": "never",
            },
        }

        import yaml

        config_file.write_text(yaml.dump(config_data))

        config = AnimusConfig.load(config_path=config_file)

        assert config.log_level == "DEBUG"
        assert config.log_to_file is True
        assert config.model.provider == "anthropic"
        assert config.model.name == "claude-3"
        assert config.model.ollama_url == "http://localhost:11434"
        assert config.model.openai_base_url == "http://localhost:8080"
        assert config.memory.backend == "local"
        assert config.memory.collection_name == "test_coll"
        assert config.api.enabled is True
        assert config.api.host == "0.0.0.0"
        assert config.api.port == 9090
        assert config.api.api_key == "test-key"
        assert config.voice.input_enabled is True
        assert config.voice.output_enabled is True
        assert config.voice.whisper_model == "small"
        assert config.voice.tts_engine == "espeak"
        assert config.voice.tts_rate == 180
        assert config.integrations.google.enabled is True
        assert config.integrations.google.client_id == "gid"
        assert config.integrations.google.client_secret == "gsecret"
        assert config.integrations.todoist.enabled is True
        assert config.integrations.todoist.api_key == "todo-key"
        assert config.integrations.filesystem.enabled is True
        assert config.integrations.filesystem.indexed_paths == ["/home/test"]
        assert config.integrations.filesystem.exclude_patterns == ["*.pyc"]
        assert config.integrations.webhooks.enabled is True
        assert config.integrations.webhooks.port == 8888
        assert config.integrations.webhooks.secret == "wh-secret"
        assert config.learning.enabled is True
        assert config.learning.auto_scan_enabled is True
        assert config.learning.auto_scan_interval_hours == 6
        assert config.learning.min_pattern_occurrences == 5
        assert config.learning.min_pattern_confidence == 0.8
        assert config.learning.lookback_days == 30
        assert config.proactive.enabled is True
        assert config.proactive.background_enabled is True
        assert config.proactive.background_interval_seconds == 120
        assert config.entities.enabled is True
        assert config.entities.auto_extract is True
        assert config.entities.auto_discover is True
        assert config.autonomous.enabled is True
        assert config.autonomous.observe_policy == "all"
        assert config.autonomous.notify_policy == "important"
        assert config.autonomous.act_policy == "approved"
        assert config.autonomous.execute_policy == "never"


# ---------------------------------------------------------------------------
# Proactive — morning brief follow-ups section (lines 254-255)
# ---------------------------------------------------------------------------


class TestProactiveMorningBriefFollowUpSection:
    """Lines 254-255: follow-ups section in morning brief."""

    def test_morning_brief_follow_up_tags(self, tmp_path):
        from animus.proactive import ProactiveEngine

        mem = MagicMock()
        pe = ProactiveEngine(data_dir=tmp_path, memory=mem)
        pe.memory = mem
        pe.memory.store = MagicMock()

        m = MagicMock()
        m.content = "Follow up with vendor about delivery"
        m.tags = {"follow-up"}
        m.subtype = "note"
        m.created_at = datetime.now() - timedelta(hours=3)
        m.memory_type = MagicMock()
        m.memory_type.value = "episodic"
        m.id = "m1"
        pe.memory.store.list_all.return_value = [m]

        with patch.object(pe, "_save_nudges"):
            result = pe.generate_morning_brief()
        assert result is not None
        assert "follow" in result.content.lower() or "vendor" in result.content.lower()

    def test_morning_brief_follow_up_underscore_tag(self, tmp_path):
        """follow_up tag variant (with underscore)."""
        from animus.proactive import ProactiveEngine

        mem = MagicMock()
        pe = ProactiveEngine(data_dir=tmp_path, memory=mem)
        pe.memory = mem
        pe.memory.store = MagicMock()

        m = MagicMock()
        m.content = "Follow up on quarterly report"
        m.tags = {"follow_up"}
        m.subtype = "note"
        m.created_at = datetime.now() - timedelta(hours=1)
        m.memory_type = MagicMock()
        m.memory_type.value = "episodic"
        m.id = "m2"
        pe.memory.store.list_all.return_value = [m]

        with patch.object(pe, "_save_nudges"):
            result = pe.generate_morning_brief()
        assert result is not None


# ---------------------------------------------------------------------------
# Proactive — synthesis error fallback (lines 267-268)
# ---------------------------------------------------------------------------


class TestProactiveSynthesisError:
    """Lines 267-268: cognitive synthesis fails, uses raw content."""

    def test_synthesis_error_fallback(self, tmp_path):
        from animus.proactive import ProactiveEngine

        mem = MagicMock()
        cognitive = MagicMock()
        cognitive.think.side_effect = RuntimeError("LLM down")

        pe = ProactiveEngine(data_dir=tmp_path, memory=mem, cognitive=cognitive)
        pe.memory = mem
        pe.memory.store = MagicMock()

        m = MagicMock()
        m.content = "Important task for today"
        m.tags = set()
        m.subtype = "note"
        m.created_at = datetime.now() - timedelta(hours=2)
        m.memory_type = MagicMock()
        m.memory_type.value = "episodic"
        m.id = "m3"
        pe.memory.store.list_all.return_value = [m]

        with patch.object(pe, "_save_nudges"):
            result = pe.generate_morning_brief()
        assert result is not None
        # Should still have content despite synthesis failure
        assert len(result.content) > 0


# ---------------------------------------------------------------------------
# Proactive — scheduled check error (lines 558-559)
# ---------------------------------------------------------------------------


class TestProactiveScheduledCheckError:
    """Lines 558-559: scheduled check raises exception."""

    def test_check_error_caught(self, tmp_path):
        from animus.proactive import ProactiveEngine

        mem = MagicMock()
        pe = ProactiveEngine(data_dir=tmp_path, memory=mem)
        pe.memory = mem
        pe.memory.store = MagicMock()

        # Make scan_deadlines raise
        pe.scan_deadlines = MagicMock(side_effect=RuntimeError("db error"))
        pe.scan_follow_ups = MagicMock(return_value=[])

        # Force all checks to be due
        for check in pe._checks:
            check.last_run = datetime.now() - timedelta(days=1)

        results = pe.run_scheduled_checks()
        # Should not raise — error is caught
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# EntityMemory._load — relationships + interactions branches (lines 242, 244)
# ---------------------------------------------------------------------------


class TestEntityMemoryLoadRelationshipsInteractions:
    """Lines 242, 244: _load with relationships and interactions in JSON."""

    def test_load_with_relationships_and_interactions(self, tmp_path):
        from animus.entities import EntityMemory, RelationType

        now = datetime.now()
        data = {
            "entities": [
                {
                    "id": "e1",
                    "name": "Alice",
                    "entity_type": "person",
                    "aliases": [],
                    "attributes": {},
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "last_mentioned": None,
                    "mention_count": 0,
                    "memory_ids": [],
                    "notes": "",
                },
                {
                    "id": "e2",
                    "name": "Bob",
                    "entity_type": "person",
                    "aliases": [],
                    "attributes": {},
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "last_mentioned": None,
                    "mention_count": 0,
                    "memory_ids": [],
                    "notes": "",
                },
            ],
            "relationships": [
                {
                    "id": "r1",
                    "source_id": "e1",
                    "target_id": "e2",
                    "relation_type": "works_with",
                    "description": "colleagues",
                    "strength": 0.8,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "metadata": {},
                },
            ],
            "interactions": [
                {
                    "timestamp": now.isoformat(),
                    "entity_id": "e1",
                    "memory_id": "m1",
                    "summary": "Met at conference",
                },
            ],
        }

        entities_file = tmp_path / "entities.json"
        entities_file.write_text(json.dumps(data))

        em = EntityMemory(data_dir=tmp_path)
        assert len(em._entities) == 2
        assert len(em._relationships) == 1
        assert len(em._interactions) == 1
        assert em._relationships[0].relation_type == RelationType.WORKS_WITH
        assert em._interactions[0].summary == "Met at conference"


# ---------------------------------------------------------------------------
# Config env overrides (lines 257, 259)
# ---------------------------------------------------------------------------


class TestConfigEnvOverrides:
    """Lines 257, 259: ProactiveConfig env var overrides."""

    def test_proactive_env_overrides(self):
        from animus.config import ProactiveConfig

        with patch.dict(
            "os.environ",
            {
                "ANIMUS_PROACTIVE_ENABLED": "true",
                "ANIMUS_PROACTIVE_BACKGROUND": "1",
            },
        ):
            pc = ProactiveConfig()
        assert pc.enabled is True
        assert pc.background_enabled is True

    def test_proactive_env_override_false(self):
        from animus.config import ProactiveConfig

        with patch.dict(
            "os.environ",
            {
                "ANIMUS_PROACTIVE_ENABLED": "false",
                "ANIMUS_PROACTIVE_BACKGROUND": "no",
            },
        ):
            pc = ProactiveConfig()
        assert pc.enabled is False
        assert pc.background_enabled is False
