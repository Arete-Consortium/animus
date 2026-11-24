"""Verify the packaged entry point through Forgehand's normal selection path."""

import json

from principal_engineering_harness.extensions import (
    CapabilityRegistry,
    ContextBudget,
    ContextProject,
    ContextRequest,
    ContextTask,
    PluginConfiguration,
)
from principal_engineering_harness.extensions.selection import collect_selected_context


def test_scoped_snapshot_obeys_forgehand_context_budget():
    edge = {
        "edge_id": "edge-observed-incident",
        "edge_version": 2,
        "subject_id": "release-build",
        "predicate": "DEPENDS_ON",
        "object_id": "schema-validation",
    }
    configuration = PluginConfiguration.model_validate(
        {
            "schema_version": "1.0",
            "plugins": {
                "animus.knowledge-context": {
                    "enabled": True,
                    "required": True,
                    "configuration": {
                        "project": "animus",
                        "edges": [edge, {**edge, "edge_id": "edge-second"}],
                    },
                },
            },
        }
    )
    registry = CapabilityRegistry.discover(configuration=configuration)
    project = ContextProject(
        name="animus", canonical_branch="main", classification="internal", maturity="pilot"
    )
    task = ContextTask(
        task_id="release-incident",
        title="Investigate a historical release failure",
        objective="Identify the relevant dependency before planning diagnostics.",
    )
    request = ContextRequest(
        task=task,
        profile_identifier="debugging",
        project=project,
        budget=ContextBudget(max_items=1),
    )

    def collect(current_request):
        state = collect_selected_context(registry, ["animus_knowledge_edges"], current_request)
        return state.context.bundles[0]

    try:
        bundle = collect(request)
        assert bundle.item_count == 1
        assert bundle.truncated
        assert json.loads(bundle.items[0].content) == edge
        foreign = project.model_copy(update={"name": "another-project"})
        assert collect(request.model_copy(update={"project": foreign})).item_count == 0
        tight_budget = ContextBudget(max_items=2, max_item_bytes=1)
        limited = collect(request.model_copy(update={"budget": tight_budget}))
        assert limited.item_count == 0 and limited.truncated
    finally:
        registry.shutdown()
