# Forgehand knowledge-edge context pilot

Install this package as a wheel alongside Forgehand 0.3.1. Forgehand discovers
the bundled manifest from the installed distribution metadata, so use a regular
install. Animus Core runs separately with a read-only registry credential that
can query the registry schema and knowledge edges.

From the Core environment, generate one private snapshot for the intended project:

```bash
umask 077
python -m animus.durability.cli export-edge-context \
  --project animus --entity repo-animus --owner owner-example \
  --workspace ws-example --limit 8 > edge-context.json
```

Use the repository directory name from the Forgehand task contract, with the
same capitalization. Core filters a single entity's immediate neighbors by
owner, workspace, project domain, and security class. It exports current
supported edges valid at export time and caps the query at 16 rows.
The snapshot contains edge identities, versions, endpoints, and predicates.

In the Forgehand environment, preview the context without starting a worker:

```bash
forgehand context inspect task.yaml --plugin-config edge-context.json \
  --context-provider animus_knowledge_edges
```

The provider returns advisory references for the configured project and
honors the request's item and UTF-8 byte budgets. It has no registry
credentials or service connection. Keep each snapshot with its intended
workspace and refresh it before a run. A copied snapshot retains the
visibility and approval state of its export time. Forgehand's project check
does not authenticate workspace membership or revoke previously exported data.

Run the packaged plugin regression after installing the wheel:

```bash
python -m pytest packages/forgehand-context/tests
```
