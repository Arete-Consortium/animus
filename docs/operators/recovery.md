# Animus Recovery Guide

Steps for the predictable disaster cases. Not a substitute for the
broader [`../reference/threat-model.md`](../reference/threat-model.md) which describes what each
gate defends against and how.

## At-rest-encrypted supported memory: rollback to unencrypted

Performed by `scripts/setup-gocryptfs-vault.sh`, which now handles only the
supported local/json memory directory and refuses other effective backends.
Older script versions may also have created historical
`chroma.unencrypted-backup.YYYYMMDD-HHMMSS/` directories. Chroma backups are
legacy migration inputs: preserve them offline and follow the
[Chroma retirement plan](chroma-retirement-plan.md). Do not restore a Chroma
directory into the live Core path or restart Core against it.

For a supported local-memory rollback, first verify that the effective Core
backend is `local` or `json` and that the selected backup contains the expected
`memories.json`. Then restore only the supported memory directory:

```bash
# 1. Stop the daemon
systemctl --user stop animus.service

# 2. Remove the supported-memory symlink
rm -f ~/.animus/memory

# 3. Restore the supported-memory original (select one exact backup path)
mv ~/.animus/memory.unencrypted-backup.* ~/.animus/memory

# 4. Unmount the vault (best-effort)
fusermount -u ~/.animus/_secure 2>/dev/null

# 5. Revert the systemd unit
cp ~/.config/systemd/user/animus.service.bak.* ~/.config/systemd/user/animus.service
systemctl --user daemon-reload

# 6. Restart only after confirming the effective backend is local/json
systemctl --user start animus.service
```

The vault dir at `~/.animus/_vault/` can stay (it's just data the daemon
no longer touches) or be removed to free disk — `rm -rf ~/.animus/_vault`.
Keep every legacy Chroma backup until migration parity and rollback acceptance
are complete and a separate retention decision is authorized.

## TPM unseal failed (after motherboard change, BIOS reset, etc.)

The TPM-sealed credential is bound to **this machine's TPM**. A new
TPM or BIOS-reset PCR state will break the unseal. Symptoms: daemon
fails to start, journal shows `systemd-creds` errors about unseal.

```bash
# Confirm the diagnosis
systemd-creds decrypt --name=animus-vault ~/.config/credstore.encrypted/animus-vault
# → expected: prints a passphrase
# → broken:   "Failed to decrypt ... TPM2 error"

# Recovery path: rebuild the credential, re-encrypt the vault contents
# with a fresh passphrase. Source data IS still encrypted under the OLD
# passphrase; without TPM unseal you cannot recover memories.
#
# Mitigation: if you anticipate hardware changes, run setup with
# --with-key=host+tpm2 instead of --with-key=tpm2. Then a host-only
# decrypt remains possible if the TPM goes away, at the cost of disk-
# seizure resilience.
```

If you don't have a fresh passphrase and the TPM is gone: restore from
Restic.

## Restic restore (full memory dir from snapshot)

The repositories at `~/backups-local/` include:
- `animus-state` — `~/.animus/` (excluding hot caches), hourly
- `animus-memory` — `~/.claude/projects/.../memory/` (Claude memory), hourly
- `animus-chroma` — preserved legacy `~/.animus/chroma/`, captured while
  quiesced; restore only into an isolated migration/retrieval-verification area

```bash
# Source the env (sets RESTIC_PASSWORD_FILE + repo paths)
set -a; source ~/.config/restic/animus.env; set +a

# List snapshots in chroma repo
export RESTIC_REPOSITORY="$RESTIC_REPO_CHROMA"
restic snapshots

# Restore a specific snapshot to a recovery dir (NOT directly over live)
mkdir -p /tmp/animus-restore
restic restore <snapshot-id> --target /tmp/animus-restore

# Verify that the isolated restore is complete. Do not copy it over a live path.
find /tmp/animus-restore/home/arete/.animus/chroma -maxdepth 2 -type f -print
```

Stop here for a legacy Chroma snapshot. Inventory it and perform backup,
migration rehearsal, retrieval parity, and rollback checks in the isolated
environment described by the retirement plan. A production configuration change
and service restart require separate cutover authorization.

Use `RESTIC_REPO_STATE` / `RESTIC_REPO_MEMORY` for supported state and memory
recovery as needed, with their own content verification before replacing live
paths.

## Daemon won't start after a security feature change

Triggered when a new hardening change (integrity baseline, redaction
pattern, MCP gate, …) breaks the daemon's boot path. The integrity
checker is the most common culprit: if you edited a security-critical
file and didn't regenerate the baseline, it refuses to boot.

```bash
# Check journal for the error
journalctl --user -u animus.service -n 50 --no-pager

# Common case: integrity drift
# Symptom: "IntegrityMismatchError: sha256 differs for ..."
# Fix: regenerate the baseline
ANIMUS_INTEGRITY_OVERRIDE=1 python -c "
from animus.integrity.checker import regenerate_baseline
regenerate_baseline()
"
# Then restart
systemctl --user start animus.service
```

If the integrity check itself is broken (rare), comment out
`from animus.integrity.checker import verify_or_raise` in the boot
path temporarily, restart, fix the underlying file, regenerate.

## Red-team finds a HIGH bypass mid-flight

`animus-redteam.timer` exits non-zero on new HIGH findings. The systemd
default behavior is just "the timer logs and moves on" — no auto-page.
Active monitoring options:

```bash
# Read the latest dashboard
tail -50 ~/.animus/audit/standing-redteam-dashboard.md

# Read every recent HIGH finding from the JSONL ledger
jq -c 'select(.severity == "high" and .is_novel == true)' \
   ~/.animus/audit/standing-redteam-ledger.jsonl | tail -20

# Manually run the find→fix→regression loop
python -m animus.redteam.driver --n-per-category 5 --output-dir /tmp/redteam-investigate
# Inspect findings, patch packages/core/animus/memory/redaction.py
# Add regression test in packages/core/tests/test_redaction.py
# Re-run until 30/30 OK
```

## Backup repos drift / can't decrypt

If the Restic password file is lost or the repos are corrupted, the
backups are unrecoverable — there's no key escrow. To prevent this:

```bash
# Verify the password file exists + has the expected entropy
test -f ~/.config/restic/password && \
  wc -c ~/.config/restic/password
# Expected: 45 bytes (per ls -la output)

# Confirm each repo is healthy (subset check, not the full --read-data)
set -a; source ~/.config/restic/animus.env; set +a
for repo_var in RESTIC_REPO_STATE RESTIC_REPO_MEMORY RESTIC_REPO_CHROMA; do
    export RESTIC_REPOSITORY="${!repo_var}"
    echo "=== $repo_var ==="
    restic check --read-data-subset=5% 2>&1 | tail -5
done
```

When you migrate to B2 (memory's open item), re-test the integrity from
B2 before retiring the local repos.

## When to suspect something deeper

Three signs the rollback procedures above won't help:

1. **Repeated TPM unseal failures across reboots** — TPM chip drift or
   firmware corruption. Replace passphrase + run setup again.
2. **Multiple novel HIGH findings in a single sweep, all in the same
   category** — the gate has regressed wholesale, not just one shape.
   Check git log of the relevant module.
3. **Integrity check drift across security files we didn't touch** —
   possible filesystem corruption or an unauthorized modification.
   Compare files against `git show HEAD:<path>` and the most recent
   Restic state snapshot.
