# Local validation — September 22, 2026 (Pacific)

Workflow: [Hunter OS - Source Review](http://localhost:5678/workflow/g6ENdjfxPwgg6nbQ), personal n8n project.

| Check | Observed result |
| --- | --- |
| n8n SDK validation | Valid, 8 nodes; workflow update returned no validation warnings |
| Execution 54 | Failed visibly when the review service could not start; no successful review was recorded |
| Execution 55 | Real HTTP execution succeeded; 105 added items routed to Review Changed Sources |
| Execution 56 | Real HTTP execution succeeded; 105 unchanged items routed to Review Unchanged Holds |
| Execution 57 | Real HTTP execution succeeded after service replacement; all 105 items unchanged |
| Execution 58 | Real HTTP execution succeeded after the recovery fixes and staged replacement |
| Source inventory | 4 legacy YAML candidates + 101 whole forum sections across 3 Markdown files |
| Approval state | All 105 items held; 0 schema-valid items; publication_allowed remained false |
| Automated tests | 23 passing tests, including real local HTTP requests and simulated installer failures |
| Ruff | Check and format passed |
| Runtime | Review container healthy; n8n readiness HTTP 200 |

The n8n executions used empty pin-data maps, so the HTTP, validation, branch, and reporting nodes executed against the installed service. No live ChatGPT sync, approved canonical import, game-fact verification, or Discord publication is claimed.

First review ID: `7394a438-cb6f-4e1a-9507-a20f66c28833`.

Docker create stalled with this macOS source-folder bind mount. The same image and network created successfully without it and with Docker-managed volumes. Installation now uses those volumes. A subsequent startup permission error on the dedicated credential was corrected by explicitly assigning the service UID and private file permissions during installation.

Review history survives service replacement. Source/config mounts are read only at runtime; the state volume is writable. Existing n8n workflows and restart policies were retained. Docker Desktop must remain available for this local workflow to run.

## Review follow-up

Three reproduced defects are corrected:

- Directory traversal errors stop inspection and retain the baseline instead of reporting inaccessible records as removed.
- Per-run reports are written atomically before baseline commit. A failed report write returns an error without consuming its change; retry preserves the delta. Replayed requests regenerate their report. The derived latest export is serialized against committed history and reports a recoverable warning on export-only failure.
- Replacement uses fresh source/config volumes, validates them as the runtime UID, and creates the replacement before stopping the working service. Startup/readiness failures restore the previous container; old source/config volumes remain intact. Six injected failure stages and successful handover are covered without touching the live service during those tests. A real successful replacement and n8n execution 58 confirm the installed path.

Parent stack gates remain separate: #133's hosted Forge tests passed (10,736 tests), but coverage was 94.19% against the unchanged 95% minimum; its legacy Core[chroma] dependency audit also failed. This integration does not waive either gate.
