"""Permission-free Forgehand adapter for operator-provided Core snapshots."""

import hashlib
import json

from principal_engineering_harness.extensions import (
    CapabilityKind,
    ContextContribution,
    ContextItem,
    ContextItemKind,
    ContextMediaType,
    ContextProvider,
    ContextRequest,
    ContextSourceKind,
    ForgehandPlugin,
    PluginHealth,
    PluginInitialization,
)


class KnowledgeEdgeProvider(ContextProvider):
    name = "Animus Knowledge Edges"

    def __init__(self, project: str, edges: tuple[str, ...]):
        self._project = project
        self._edges = edges

    def collect(self, request: ContextRequest) -> ContextContribution:
        if request.project is None or request.project.name != self._project:
            return ContextContribution()
        items = []
        remaining = request.budget.max_provider_bytes
        truncated = False
        for content in self._edges:
            size = len(content.encode("utf-8"))
            if size > request.budget.max_item_bytes:
                truncated = True
                continue
            if len(items) >= request.budget.max_items or size > remaining:
                truncated = True
                break
            items.append(
                ContextItem(
                    id=f"edge-{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
                    kind=ContextItemKind.REFERENCE,
                    title="Approved knowledge edge",
                    content=content,
                    source=ContextSourceKind.CONFIGURATION,
                    media_type=ContextMediaType.JSON,
                )
            )
            remaining -= size
        return ContextContribution(items=tuple(items), truncated=truncated)


class KnowledgeContextPlugin(ForgehandPlugin):
    def __init__(self) -> None:
        self._provider: KnowledgeEdgeProvider | None = None

    def initialize(self, initialization: PluginInitialization) -> None:
        configuration = initialization.configuration
        edges = tuple(
            dict.fromkeys(
                json.dumps(edge, sort_keys=True, separators=(",", ":"))
                for edge in configuration["edges"]
            )
        )
        self._provider = KnowledgeEdgeProvider(configuration["project"], edges)

    def health(self) -> PluginHealth:
        return PluginHealth(ready=self._provider is not None, summary="Core edge snapshot")

    def get_capability(self, kind: CapabilityKind, identifier: str) -> object:
        if (
            kind is not CapabilityKind.CONTEXT_PROVIDER
            or identifier != "animus_knowledge_edges"
            or self._provider is None
        ):
            raise KeyError((kind, identifier))
        return self._provider
