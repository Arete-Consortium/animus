"""Kernel memory CRUD must coexist with Hunter objects without decoding or altering them."""

from __future__ import annotations

from dataclasses import replace

import pytest
from animus_kernel.memory.stores.durable import DurableMemoryStore
from animus_kernel.memory.types import Memory, MemoryType

from .test_registry_compatibility import counts, record
from .test_registry_compatibility import database_url as database_url  # noqa: F401
from .test_registry_compatibility import stores as stores  # noqa: F401


@pytest.mark.parametrize(
    "configuration",
    [{}, {"owner_id": "configured-owner", "workspace_id": "configured-workspace"}],
)
def test_kernel_memory_and_hunter_records_remain_isolated(stores, configuration):  # noqa: F811
    admin, hunter = stores
    kernel = DurableMemoryStore(admin.database_url, **configuration)
    try:
        hunter_record = record()
        hunter.store(hunter_record)
        memory = Memory.create("synthetic owned memory", MemoryType.SEMANTIC)
        memory.tags = ["owned"]
        kernel.store(memory)

        assert [item.id for item in kernel.search("synthetic", limit=1)] == [memory.id]
        assert [item.id for item in kernel.list_all()] == [memory.id]
        assert kernel.get_all_tags() == {"owned": 1}
        assert kernel.retrieve(hunter_record.object_id) is None

        before = counts(admin)
        collision = replace(memory, id=hunter_record.object_id)
        updated = kernel.update(collision)
        deleted = kernel.delete(hunter_record.object_id)
        assert updated is False
        assert deleted is False
        with pytest.raises(PermissionError, match="another registry scope"):
            kernel.store(collision)
        assert counts(admin) == before
        retained = hunter.retrieve(hunter_record.object_id)
        assert retained.payload == hunter_record.payload
        assert retained.version == 1

        memory.content = "synthetic updated memory"
        updated = kernel.update(memory)
        assert updated is True
        assert kernel.retrieve(memory.id).content == memory.content
        deleted = kernel.delete(memory.id)
        assert deleted is True
        assert kernel.retrieve(memory.id) is None
        assert hunter.retrieve(hunter_record.object_id) is not None
    finally:
        kernel._engine.dispose()
