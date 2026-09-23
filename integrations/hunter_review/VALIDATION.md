# Local validation — September 22, 2026 (Pacific)

Workflow: [Hunter OS - Source Review](http://localhost:5678/workflow/g6ENdjfxPwgg6nbQ), personal n8n project.

| Check | Observed result |
| --- | --- |
| n8n SDK validation | Valid, 8 nodes; workflow update returned no validation warnings |
| Execution 54 | Failed visibly when the review service could not start; no successful review was recorded |
| Execution 55 | Real HTTP execution succeeded; 105 added items routed to Review Changed Sources |
| Execution 56 | Real HTTP execution succeeded; 105 unchanged items routed to Review Unchanged Holds |
| Source inventory | 4 legacy YAML candidates + 101 whole forum sections across 3 Markdown files |
| Approval state | All 105 items held; 0 schema-valid items; publication_allowed remained false |
| Automated tests | 11 passing tests, including real local HTTP requests |
| Ruff | Check and format passed |
| Runtime | Review container healthy; n8n readiness HTTP 200 |

The n8n executions used empty pin-data maps, so the HTTP, validation, branch, and reporting nodes executed against the installed service. No live ChatGPT sync, approved canonical import, game-fact verification, or Discord publication is claimed.

First review ID: `7394a438-cb6f-4e1a-9507-a20f66c28833`.

Docker create stalled with this macOS source-folder bind mount. The same image and network created successfully without it and with Docker-managed volumes. Installation now uses those volumes. A subsequent startup permission error on the dedicated credential was corrected by explicitly assigning the service UID and private file permissions during installation.

Review history survives service replacement. Source/config mounts are read only at runtime; the state volume is writable. Existing n8n workflows and restart policies were retained. Docker Desktop must remain available for this local workflow to run.
