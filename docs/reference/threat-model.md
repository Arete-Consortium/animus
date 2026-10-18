# Animus Threat Model

Status: living document. Last updated 2026-05-26 alongside the 10/10
polish pass (post-Stage 3.D + sibling adopters + systemd narrowing).

> **Legacy deployment scope:** Chroma paths and controls below describe the
> preserved pre-retirement deployment that remains at risk until its data is
> inventoried and migrated. Chroma is not a supported Core runtime backend. See
> the [retirement plan](../operators/chroma-retirement-plan.md); this threat
> evidence does not authorize a configuration or data cutover.

This document captures what the [hardening
pass](https://github.com/your-org/animus/blob/main/packages/core/animus/scripts/verify_hardening.py) defends
against, the adversaries it considers, the assumptions it relies on,
and what it explicitly does not address. The hardening was built
reactively against specific surfaces; this document is the formal
write-up that surfaces unknown unknowns.

## What Animus stores (the data at risk)

A four-tier classification of memory content, applied at write time
(Stage 2.A schema) and enforced at read time (Stage 2.B `allowed_tiers`
gate, Stage 2.C MCP scope pin):

| Tier | Examples | Volume in live store (2026-05-26 backfill) |
|------|----------|---------------------------------------------|
| `PUBLIC` | Public docs, podcast transcripts, public-repo harvest | 11 |
| `PERSONAL` | Own notes, decisions, task outcomes, harvest | 1408 |
| `CONFIDENTIAL` | TIAID client material, Toyota litigation context, NAVEX application | 4 |
| `SECRET` | Credentials, financial, MUST NOT cross boundaries | 0 in live store; gate present |

Storage location at the 2026-05-26 snapshot: `~/.animus/chroma/` (legacy
ChromaDB), `~/.animus/audit/`
(append-only JSONL), `~/.local/share/animus/` (SQLite for automations +
feedback), `~/.config/animus/` (config + identity proposals).

## Adversary model

We consider three classes of adversary explicitly:

### A1. Network-only attacker (passive + active on the wire)

- **Capabilities**: observes outbound HTTP, may MITM if no TLS,
  cannot execute code on the box, cannot read files locally.
- **What stops them**:
  - All MCP transport is stdio — there's no listening network socket
    for memory tools.
  - Local services bind 127.0.0.1 only (Stage 1 Track F).
  - Outbound LLM traffic is TLS to known providers; ANIMUS_OFFLINE=1
    + tier-aware dispatch (Stage 3.D) refuse cloud egress for
    CONFIDENTIAL/SECRET requests.
- **Residual risk**: TLS termination at cloud LLM providers means the
  *provider* sees PUBLIC-tier requests. Acceptable trade per the
  spec ("public-tier → cloud" was explicitly approved 2026-05-25).

### A2. Local interactive user (someone with shell access on this box)

- **Capabilities**: can run commands as `arete`, can read any file the
  user can read, can call MCP tools through Claude Code.
- **What stops them**:
  - The MCP tools surface only PUBLIC-tier memories (Stage 2.C scope).
  - DLP scrubber (Stage 3.A) catches legacy secrets at egress.
  - Audit log (Stage 3.B) records every tool call.
- **Residual risk**: The adversary IS the user account — they can
  read the underlying ChromaDB directly. Tier enforcement is a
  *defense against accidental disclosure through automation*, not a
  defense against a malicious shell user. **This is by design.**
  Multi-user separation is out of scope (see below).

### A3. Compromised dependency / code injection

- **Capabilities**: arbitrary code execution inside the
  `animus.service` or `animus-forge.service` process. Could come from
  a malicious pip dep, a subverted Forge auto-commit, or a
  prompt-injection that escalates into tool abuse.
- **What stops them**:
  - systemd hardening (`ProtectSystem=strict`, `ReadOnlyPaths=$HOME`,
    `ReadWritePaths=` carve-out) limits filesystem writes to specific
    dirs.
  - Forge sandbox (Stage 4): gitleaks pre-commit blocks secret
    inclusion in autonomous commits; allow-list restricts which
    source files Forge can edit; default-branch fix prevents the
    whip-saw vector.
  - Egress gates (Stage 3.C + sibling adopters): cloud LLM calls
    refuse construction under `ANIMUS_OFFLINE=1` or for sensitive
    tiers.
  - Tampering detection (10/10 polish): SHA-256 baseline of
    critical-path files; daemon refuses to boot on drift.
- **Residual risk**:
  - In-memory subversion (RAM-only payload) bypasses on-disk
    tampering detection.
  - Network egress is enforced in code (helper) but not at the
    kernel layer **until the 10/10 polish adds
    `IPAddressDeny=`/`IPAddressAllow=`** — at which point a code
    bypass cannot leave the box without also defeating systemd's
    network filter.

## Data flow

```
            ┌──────────────────────────────────────────────────────┐
            │ User (Claude Code session) [trusted: A1 boundary]    │
            └──────────────────────┬───────────────────────────────┘
                                   │ MCP stdio
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│ animus.service — animus_bootstrap.daemon                         │
│                                                                  │
│  MCP tools (animus_recall, _brief, _search_tags)                 │
│      │   allowed_tiers={PUBLIC}    (Stage 2.C)                   │
│      ▼                                                            │
│  MemoryLayer.recall(...)                                         │
│      │                                                            │
│      ▼                                                            │
│  ChromaMemoryStore (per-tier where clause via metadata)          │
│      │   tier-filtered results                                    │
│      ▼                                                            │
│  redact(text)  (Stage 3.A — second-line DLP)                     │
│      │                                                            │
│      ▼                                                            │
│  wrap_untrusted(...)  (Stage 5 — PI envelope)                    │
│      │                                                            │
│      ▼                                                            │
│  audit_log.record(...)  (Stage 3.B — metadata-only)              │
│      │                                                            │
│      ▼                                                            │
│  Response back through MCP stdio → User                          │
└──────────────────────────────────────────────────────────────────┘

            ┌──────────────────────────────────────────────────────┐
            │ animus-forge.service — uvicorn animus_forge.api      │
            │                                                      │
            │  CompletionRequest(prompt, sensitivity)              │
            │      │                                                │
            │      ▼                                                │
            │  TierRouter._select_provider(request)                 │
            │      ├─ CONFIDENTIAL/SECRET → force local (Ollama)    │
            │      └─ PUBLIC/PERSONAL → HYBRID / cloud-allowed      │
            │      │                                                │
            │      ▼                                                │
            │  Provider._check_request_egress(request)              │
            │      ├─ ANIMUS_OFFLINE=1 → EgressDeniedError          │
            │      ├─ sensitivity ≥ CONFIDENTIAL → EgressDeniedError│
            │      └─ otherwise → cloud client invoked              │
            └──────────────────────────────────────────────────────┘
```

## Defenses in place (the 7-track summary)

| Stage | What it defends | Where to verify |
|-------|-----------------|-----------------|
| 1 (Track A) | Secrets at memory ingest | `tests/test_redaction.py` |
| 1 (Track F) | Service network bind + ChromaDB telemetry | `chroma.py`, `chromadb_backend.py`, 5 unit `127.0.0.1` flips |
| 1 (Track E partial) | Forge `auto_approve` + `create_issue` env-gated | `orchestrator.py`, `executor_integrations.py` |
| 2 | Sensitivity tier schema + recall gate + MCP scope + backfill | `tests/test_sensitivity.py`, `verify_hardening` scenarios |
| 3.A | DLP scrub at MCP egress | `mcp_server._scrub_egress` |
| 3.B | Append-only audit log | `animus.audit.egress_log` |
| 3.C | `ANIMUS_OFFLINE=1` + tier-aware egress helper | `animus.network.egress` |
| 3.D | Tier-aware LLM dispatch end-to-end | `animus_forge.providers.router` |
| 4 | Forge sandbox (gitleaks + allow-list + whip-saw) | `pr_manager.py`, `self_improve_safety.yaml` |
| 5 | Prompt-injection defense `<untrusted_data>` envelope | `mcp_server._wrap_untrusted`, `forge.security.pi_wrap` |
| 6 | Adversarial verification suite | `python -m animus.scripts.verify_hardening` |
| Sibling adopters | Bootstrap gateway gate + Forge cloud gates + Forge RAG PI-wrap + tier dispatch end-to-end | PRs #56-#59 |
| systemd narrowing (Stage 1 deferral) | `ReadOnlyPaths=$HOME` + minimal carve-out | unit files; backups at `*.bak.20260526-*` |

## Explicit assumptions

The hardening relies on these holding. If any breaks, the corresponding
defense weakens.

1. **The Linux user account `arete` is not compromised.** Local
   privilege isolation between users is not enforced by Animus.
2. **The Python venv at `/home/arete/projects/animus/.venv` is not
   tampered with.** Anyone with write access can modify dependencies.
3. **Systemd unit files have not been edited by an adversary.** They
   live in `~/.config/systemd/user/` and a write there bypasses
   `ReadOnlyPaths` (because the read-only mount applies to the daemon
   process, not its config).
4. **The Ollama process is trustworthy.** Local-only routing for
   sensitive tiers assumes Ollama itself doesn't exfiltrate. Ollama
   binds 127.0.0.1 by default and has no known telemetry.
5. **Claude Code (the MCP client) honors the `<untrusted_data>`
   envelope.** Stage 5's defense is structural at the protocol level
   but ultimately depends on the consuming model's behavior. Tested
   against Claude Sonnet; unverified against Qwen / Llama.
6. **Time on the host is correct.** Audit log retention, daily
   rotation, and the 30-day cleanup window all assume system time
   isn't adversarially manipulated.

## Out of scope (explicit non-goals)

These threats are real but not addressed by this hardening pass.

### Disk-level encryption at rest

**Status as of 2026-05-26: NOT IN PLACE.** The root partition
(`/dev/nvme0n1p6`) is plain ext4 — no LUKS. Laptop theft = full
plaintext exposure of `~/.animus/` (1423 memories) and
`~/.local/share/animus/`.

**Why it's out of scope of the code hardening**: this is a
filesystem-layer concern, not an application-layer one. SQLCipher
integration with ChromaDB requires forking ChromaDB; the cleaner fix
is `gocryptfs` overlay or full-disk migration to LUKS.

**Recommended follow-up**: separate scoped session — install
`gocryptfs`, generate passphrase (1Password / keyring), mount
encrypted overlay at `~/.animus/`, migrate existing 22MB of memories,
update systemd unit to depend on the mount. ~2-4 hours of work with
daemon downtime. Document decisions: passphrase storage, daemon-start
unlock strategy (kernel keyring vs systemd `LoadCredentialEncrypted=`).

### Multi-user / multi-tenant access

The system is single-user by design. No identity tracking on tier
queries — `allowed_tiers={PUBLIC}` means "whoever is asking via MCP
gets the public tier" with no further authorization. If multi-user
ever becomes a goal, every tier check needs a `caller_identity`
parameter and per-tier ACLs.

### Memory dump from a privileged compromise

If an attacker achieves root on the running system, they can `gdb`
attach to the daemon, dump RAM, and extract decrypted ChromaDB
contents. No mitigation in code; defense-in-depth would require
sealed enclave / TPM-backed memory protection.

### Quorum / IntentGraph tier policies

The hardening enforces tier rules in memory recall and LLM dispatch.
The Quorum coordination protocol (intent graph, triumvirate voting)
is orthogonal — intents are not currently tier-classified. Out of
scope for this pass.

### Supply-chain attacks on Python dependencies

Stage 4 closes Forge's autonomous-commit path. It does NOT prevent a
malicious package landing via legitimate dependabot or manual `pip
install` from doing anything once executed. Mitigations would be
package pinning + hash verification + sandbox per-process; not in
scope.

### Side channels (timing, power, electromagnetic)

Out of scope. Not a realistic adversary for personal use.

## Verification

### Deterministic gate suite

Run the curated adversarial scenarios anytime:

```bash
python -m animus.scripts.verify_hardening
# Expected: 24 scenarios pass; report at <data_dir>/audit/hardening-report-YYYY-MM-DD.json
```

The pytest equivalent runs in CI:

```bash
cd packages/core && pytest tests/test_hardening_verification.py
```

### Red-team driver (probabilistic, LLM-generated attacks)

The deterministic suite proves the gates we designed for. The red-team
driver proves the gates against attacks **we didn't design for** — it
uses an uncensored local model (default ``qwen2.5:14b``; preferred
``hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q6_K_P``
when reachable) to generate adversarial inputs against every category
of gate, applies them against isolated test fixtures, and emits a
JSONL report of findings.

```bash
python -m animus.redteam.driver               # 3 probes per category
python -m animus.redteam.driver --quick       # 1 probe per category (CI gate)
python -m animus.redteam.driver --category pi # single-category run
```

Report at ``<data_dir>/audit/redteam-YYYY-MM-DD.jsonl``. Exit code is
non-zero when any finding meets the ``--fail-on`` severity (default
``high``).

### Project policy: red-team-on-every-change

**Any new security-relevant feature must be run through the red-team
driver before merge.** The driver becomes part of the
review-and-verify loop, alongside ``pytest`` and ``ruff``. A real
incident the driver caught during its own first run:

- 2026-05-26 iteration 1 — Qwen generated
  ``BearerTokenForXYZ-Project_2023!@#``. The original ``bearer_token``
  regex required whitespace between "bearer" and the content; CamelCase
  concatenation defeated it. Fix: ``credential_label_camelcase`` pattern.
- 2026-05-26 iteration 2 — Qwen escalated to leetspeak
  ``Bearert0k3nF0rS3cRetUsag3!123``. The CamelCase fix required literal
  ``Token`` chars; ``t0k3n`` defeated it. Fix: ``bearer_loose_concat``
  pattern requiring 8+ token-shaped chars after the literal word
  ``bearer``.

Each iteration produced a regression test in
``tests/test_redaction.py`` so the bypass cannot return. This is the
intended cadence: find → fix → regression-test → confirm.

## Revision history

- **2026-05-26** — Initial threat model, formalized after the 7-track
  hardening pass + Stage 3.D + systemd narrowing landed. Authored
  alongside the 10/10 polish pass (tampering detection + network
  egress + this document).
