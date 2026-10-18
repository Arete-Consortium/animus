#!/usr/bin/env bash
# setup-gocryptfs-vault.sh — one-shot migration to at-rest-encrypted
# supported local/json memory storage for Animus.
#
# Scope (per ARETE design 2026-05-27):
#   - encrypts ``~/.animus/memory/`` only
#   - refuses legacy Chroma configurations and leaves migration data untouched
#   - passphrase: TPM-sealed via systemd-creds
#   - migration: offline (daemon stopped for ~5-10 min)
#   - rollback: Restic snapshots already in ``~/backups-local/``
#
# Prerequisites BEFORE running this script:
#   1. ``sudo usermod -aG tss arete`` — grants TPM access for systemd-creds.
#   2. **Restart the user session** to give the systemd --user manager
#      its new tss group. Without this, the daemon's ``LoadCredential
#      Encrypted=`` can't reach /dev/tpmrm0 and the post-mount daemon
#      restart fails. ``sg tss -c '...'`` works for the script's
#      one-shot operations but does NOT cover the persistent unit.
#      Terminate + reconnect: ``sudo loginctl terminate-user arete``
#      (kills any running session — close out other work first).
#   3. ``~/backups-local/`` already has fresh snapshots from
#      ``animus-backup-hourly``. Re-run the pre-flight backup job
#      if the most recent is >1 hour old.
#
# The script is idempotent on the additive steps (vault init, credential
# encryption) — re-running them is safe. The destructive moment is the
# rename of ``~/.animus/memory/`` to
# ``.unencrypted-backup/``, which the script asks for explicit
# confirmation before doing.
#
# Cleanup of ``.unencrypted-backup/`` directories is NOT automated.
# Per the destructive-disk-ops protocol, that step is a separate
# manual command after a successful verification window.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANIMUS_DIR="${HOME}/.animus"
VAULT_DIR="${ANIMUS_DIR}/_vault"          # encrypted ciphertext on disk
SECURE_DIR="${ANIMUS_DIR}/_secure"        # mounted cleartext view
MEMORY_DIR="${ANIMUS_DIR}/memory"
VAULT_MEMORY_DIR="${SECURE_DIR}/memory"
CRED_DIR="${HOME}/.config/credstore.encrypted"
CRED_FILE="${CRED_DIR}/animus-vault"
SYSTEMD_UNIT="${HOME}/.config/systemd/user/animus.service"
LOG_PREFIX="[setup-gocryptfs-vault]"
PW_TMP=""
MEMORY_ALREADY_LINKED=0

log() { echo "${LOG_PREFIX} $*"; }
abort() { echo "${LOG_PREFIX} ABORT: $*" >&2; exit 1; }
cleanup_sensitive_temp() {
    if [[ -n "${PW_TMP}" && -f "${PW_TMP}" ]]; then
        shred -u "${PW_TMP}" 2>/dev/null || rm -f "${PW_TMP}"
    fi
    PW_TMP=""
}

verify_expected_vault_mount() {
    local mount_info mount_target mount_source mount_type
    mount_info=$(findmnt --noheadings --raw --mountpoint "${SECURE_DIR}" \
        --output TARGET,SOURCE,FSTYPE) \
        || abort "${SECURE_DIR} is not a verifiable mountpoint"
    read -r mount_target mount_source mount_type <<< "${mount_info}"
    [[ "${mount_target}" == "${SECURE_DIR}" ]] \
        || abort "unexpected mount target for ${SECURE_DIR}: ${mount_target}"
    [[ "${mount_source}" == "${VAULT_DIR}" ]] \
        || abort "unexpected mount source for ${SECURE_DIR}: ${mount_source}"
    [[ "${mount_type}" == "fuse.gocryptfs" ]] \
        || abort "unexpected filesystem type for ${SECURE_DIR}: ${mount_type}"
}

reject_mount_targets_at_or_below() {
    local protected_root=$1
    local mount_targets mount_target
    mount_targets=$(findmnt --noheadings --raw --output TARGET) \
        || abort "could not inspect mount boundaries below ${protected_root}"
    while IFS= read -r mount_target; do
        [[ -n "${mount_target}" ]] || continue
        case "${mount_target}" in
            "${protected_root}"|"${protected_root}"/*)
                abort "unexpected mount boundary at ${mount_target} below ${protected_root}"
                ;;
        esac
    done <<< "${mount_targets}"
}

trap cleanup_sensitive_temp EXIT

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

log "==> Phase 0: pre-flight"

# Tools
command -v gocryptfs >/dev/null || abort "gocryptfs not installed (apt install gocryptfs)"
command -v systemd-creds >/dev/null || abort "systemd-creds missing — install systemd >= 250"
command -v rsync >/dev/null || abort "rsync missing"
command -v readlink >/dev/null || abort "readlink missing"
command -v mountpoint >/dev/null || abort "mountpoint missing"
command -v findmnt >/dev/null || abort "findmnt missing"

# Refuse path aliases before creating credentials, stopping services, mounting,
# or copying data. The one allowed symlink is the exact idempotent link this
# script creates for the supported memory directory.
[[ ! -L "${ANIMUS_DIR}" ]] || abort "${ANIMUS_DIR} must not be a symlink"
[[ ! -L "${VAULT_DIR}" ]] || abort "${VAULT_DIR} must not be a symlink"
[[ ! -L "${SECURE_DIR}" ]] || abort "${SECURE_DIR} must not be a symlink"
[[ ! -L "${VAULT_MEMORY_DIR}" ]] || abort "${VAULT_MEMORY_DIR} must not be a symlink"
[[ ! -L "${CRED_DIR}" ]] || abort "${CRED_DIR} must not be a symlink"
[[ ! -L "${CRED_FILE}" ]] || abort "${CRED_FILE} must not be a symlink"
[[ ! -L "${SYSTEMD_UNIT}" ]] || abort "${SYSTEMD_UNIT} must not be a symlink"
[[ -f "${SYSTEMD_UNIT}" ]] || abort "${SYSTEMD_UNIT} not found; no data or service state changed"
reject_mount_targets_at_or_below "${VAULT_DIR}"
reject_mount_targets_at_or_below "${VAULT_MEMORY_DIR}"
[[ ! -d "${VAULT_DIR}" ]] || ! mountpoint -q "${VAULT_DIR}" \
    || abort "${VAULT_DIR} must not be a mountpoint"
if [[ -d "${SECURE_DIR}" ]] && mountpoint -q "${SECURE_DIR}"; then
    verify_expected_vault_mount
fi

if [[ -L "${MEMORY_DIR}" ]]; then
    MEMORY_ALREADY_LINKED=1
    MEMORY_LINK_TARGET=$(readlink -- "${MEMORY_DIR}")
    [[ "${MEMORY_LINK_TARGET}" == "${VAULT_MEMORY_DIR}" ]] \
        || abort "${MEMORY_DIR} points to unexpected target '${MEMORY_LINK_TARGET}'"
fi

# TPM access via tss group
if ! id -nG | tr ' ' '\n' | grep -qx tss; then
    abort "user '$USER' not in 'tss' group — run 'sudo usermod -aG tss arete' then re-login or use 'sg tss -c \"bash $0\"'"
fi

# TPM device readable
if [[ ! -r /dev/tpmrm0 ]]; then
    abort "/dev/tpmrm0 not readable (try a fresh shell after the usermod)"
fi

# Confirm the systemd --user manager also has tss access — without it,
# ``LoadCredentialEncrypted=`` in the patched unit fails post-mount and
# the daemon restart loops. The user-systemd's groups come from the
# login session that started it; if usermod happened after login, the
# session must be restarted before this script can complete cleanly.
USER_SYSTEMD_PID=$(systemctl --user show --property=ExecMainPID --value || true)
if [[ -n "${USER_SYSTEMD_PID:-}" && -r "/proc/${USER_SYSTEMD_PID}/status" ]]; then
    if ! grep -E '^Groups:' "/proc/${USER_SYSTEMD_PID}/status" | tr ' ' '\n' | grep -qx 105; then
        abort "systemd --user (pid ${USER_SYSTEMD_PID}) lacks tss group — restart your session ('sudo loginctl terminate-user $USER' or full logout/login). The script's manual mount works, but the unit's persistent auto-mount will loop-fail until the user-systemd inherits the group."
    fi
fi

# Supported source directory exists. Legacy Chroma data is deliberately outside
# this script; preserve and inspect it only through the retirement runbook.
[[ -d "${MEMORY_DIR}" ]] || abort "${MEMORY_DIR} not found"

# Refuse to touch data or stop the daemon unless the effective Core selector is
# the supported local/json backend. Durable SQL does not use this directory.
EFFECTIVE_BACKEND=$(python3 -c 'from animus.config import AnimusConfig; print(AnimusConfig.load().memory.backend)') \
    || abort "could not read the effective Core memory backend"
case "${EFFECTIVE_BACKEND}" in
    local|json) ;;
    *) abort "effective Core memory backend is '${EFFECTIVE_BACKEND}', expected local/json; no data or service state changed" ;;
esac

# Restic snapshot recency
SNAPSHOT_AGE=$(stat -c %Y "${HOME}/backups-local/animus-state/locks" 2>/dev/null || echo 0)
NOW=$(date +%s)
if (( NOW - SNAPSHOT_AGE > 3600 )); then
    log "WARNING: most recent state snapshot is older than 1 hour. Consider re-running animus-backup-hourly first."
    read -r -p "Continue anyway? (yes/N): " confirm
    [[ "$confirm" == "yes" ]] || abort "user declined stale-snapshot warning"
fi

log "pre-flight OK"

# ---------------------------------------------------------------------------
# Phase 1: encrypt passphrase via systemd-creds (TPM-sealed)
# ---------------------------------------------------------------------------

log "==> Phase 1: generate + TPM-seal passphrase"

mkdir -p "${CRED_DIR}"
chmod 700 "${CRED_DIR}"

if [[ -f "${CRED_FILE}" ]]; then
    log "credential ${CRED_FILE} already exists — reusing (delete it manually if you want to regenerate)"
else
    # 48 bytes of randomness → ~64-char base64 → > 256 bits of entropy
    openssl rand -base64 48 | tr -d '\n' | \
        systemd-creds encrypt --name=animus-vault --with-key=tpm2 - "${CRED_FILE}"
    chmod 600 "${CRED_FILE}"
    log "credential sealed to TPM → ${CRED_FILE}"
fi

# Verify we can decrypt (full round-trip)
PASSPHRASE_BYTES=$(systemd-creds decrypt --name=animus-vault "${CRED_FILE}" - | wc -c)
(( PASSPHRASE_BYTES > 32 )) || abort "decrypt returned ${PASSPHRASE_BYTES} bytes — TPM unseal looks broken"
log "TPM unseal verified (${PASSPHRASE_BYTES} bytes)"

# ---------------------------------------------------------------------------
# Phase 2: initialize the gocryptfs vault (idempotent — skips if exists)
# ---------------------------------------------------------------------------

log "==> Phase 2: initialize gocryptfs vault"

if [[ -f "${VAULT_DIR}/gocryptfs.conf" ]]; then
    log "vault already initialized at ${VAULT_DIR} — reusing"
else
    mkdir -p "${VAULT_DIR}"
    chmod 700 "${VAULT_DIR}"
    # ``gocryptfs -extpass "cat"`` reads from stdin which is fragile in
    # a pipeline. Use ``-passfile`` with a tmpfs file that exists only
    # for the init.
    PW_TMP=$(mktemp -p /dev/shm gocryptfs-pw.XXXXXX 2>/dev/null \
             || mktemp /tmp/gocryptfs-pw.XXXXXX)
    chmod 600 "${PW_TMP}"
    systemd-creds decrypt --name=animus-vault "${CRED_FILE}" - > "${PW_TMP}"
    gocryptfs -init -plaintextnames -q -passfile "${PW_TMP}" "${VAULT_DIR}"
    cleanup_sensitive_temp
    log "vault initialized at ${VAULT_DIR}"
fi

# ---------------------------------------------------------------------------
# Phase 3: stop the daemon (offline migration window starts here)
# ---------------------------------------------------------------------------

log "==> Phase 3: stop animus.service"

DAEMON_WAS_RUNNING=0
DAEMON_STOPPED=0
SERVICE_RESTORED=0
# Fail safely: after the offline window starts, an error leaves the daemon
# stopped for inspection instead of restarting it against an unverified path.
leave_daemon_stopped_on_error() {
    local exit_code=$?
    cleanup_sensitive_temp
    if (( exit_code != 0 && SERVICE_RESTORED )); then
        log "stopping animus.service after post-restart verification failure"
        if systemctl --user stop animus.service; then
            DAEMON_STOPPED=1
        else
            log "WARN: failed to stop animus.service"
        fi
        SERVICE_RESTORED=0
    fi
    if (( exit_code != 0 && DAEMON_STOPPED )); then
        log "daemon remains stopped after failure (exit=${exit_code}); inspect and roll back before restarting"
    fi
    exit "${exit_code}"
}
trap leave_daemon_stopped_on_error EXIT

if systemctl --user is-active --quiet animus.service; then
    DAEMON_WAS_RUNNING=1
    systemctl --user stop animus.service || abort "failed to stop animus.service; no memory data changed"
    systemctl --user is-active --quiet animus.service \
        && abort "animus.service is still active; no memory data changed"
    DAEMON_STOPPED=1
    log "stopped animus.service"
else
    DAEMON_STOPPED=1
    log "animus.service already inactive"
fi

# ---------------------------------------------------------------------------
# Phase 4: mount + rsync data into vault
# ---------------------------------------------------------------------------

log "==> Phase 4: mount vault + copy data"

systemctl --user is-active --quiet animus.service \
    && abort "animus.service became active during the offline migration window"

mkdir -p "${SECURE_DIR}"
chmod 700 "${SECURE_DIR}"

# Mount the vault. Same -passfile pattern as Phase 2 — tmpfs file, scrub
# after use.
if mountpoint -q "${SECURE_DIR}"; then
    log "vault already mounted at ${SECURE_DIR}"
else
    PW_TMP=$(mktemp -p /dev/shm gocryptfs-pw.XXXXXX 2>/dev/null \
             || mktemp /tmp/gocryptfs-pw.XXXXXX)
    chmod 600 "${PW_TMP}"
    systemd-creds decrypt --name=animus-vault "${CRED_FILE}" - > "${PW_TMP}"
    gocryptfs -q -fsname "${VAULT_DIR}" -passfile "${PW_TMP}" \
        "${VAULT_DIR}" "${SECURE_DIR}"
    cleanup_sensitive_temp
    log "vault mounted at ${SECURE_DIR}"
fi

verify_expected_vault_mount
reject_mount_targets_at_or_below "${VAULT_MEMORY_DIR}"

# Copy data INTO the encrypted view on the first run. On an idempotent rerun the
# exact memory symlink already resolves to this destination, so copying would be
# a source/destination alias and is deliberately skipped. Recheck after mount:
# the vault may contain a different ``memory`` entry than the unmounted path.
[[ ! -L "${VAULT_MEMORY_DIR}" ]] \
    || abort "${VAULT_MEMORY_DIR} must not be a symlink"
mkdir -p "${VAULT_MEMORY_DIR}"
if (( MEMORY_ALREADY_LINKED )); then
    log "memory already points to the verified vault path — skipping copy"
else
    log "rsyncing memory → vault"
    rsync -a --delete "${MEMORY_DIR}/" "${VAULT_MEMORY_DIR}/"

    # Verify file counts and byte content match.
    MEMORY_SRC=$(find "${MEMORY_DIR}" -type f | wc -l)
    MEMORY_DST=$(find "${VAULT_MEMORY_DIR}" -type f | wc -l)
    log "file-count check: memory ${MEMORY_SRC}→${MEMORY_DST}"
    (( MEMORY_SRC == MEMORY_DST )) \
        || abort "memory file-count mismatch (${MEMORY_SRC} vs ${MEMORY_DST})"
    RSYNC_VERIFY=$(rsync -a --delete --dry-run --checksum --itemize-changes \
        "${MEMORY_DIR}/" "${VAULT_MEMORY_DIR}/")
    [[ -z "${RSYNC_VERIFY}" ]] \
        || abort "memory content verification failed; rsync reported pending changes"
    log "copy verified"
fi

# ---------------------------------------------------------------------------
# Phase 5: swap directory names (THIS IS THE REVERSIBLE-DESTRUCTIVE STEP)
# ---------------------------------------------------------------------------

log "==> Phase 5: swap directories"

systemctl --user is-active --quiet animus.service \
    && abort "animus.service became active before the directory swap"

BACKUP_SUFFIX=".unencrypted-backup.$(date +%Y%m%d-%H%M%S)"

if [[ -L "${MEMORY_DIR}" ]]; then
    log "memory already a symlink — skipping swap"
else
    BACKUP_DIR="${MEMORY_DIR}${BACKUP_SUFFIX}"
    [[ ! -e "${BACKUP_DIR}" && ! -L "${BACKUP_DIR}" ]] \
        || abort "backup target already exists: ${BACKUP_DIR}"
    read -r -p "Type 'encrypt-local-memory' to replace ${MEMORY_DIR} with the verified vault link: " confirm
    [[ "${confirm}" == "encrypt-local-memory" ]] || abort "operator declined memory directory swap"
    mv "${MEMORY_DIR}" "${BACKUP_DIR}"
    ln -s "${VAULT_MEMORY_DIR}" "${MEMORY_DIR}"
    log "memory → ${BACKUP_DIR} (backup); verified symlink installed"
fi

# ---------------------------------------------------------------------------
# Phase 6: update animus.service with mount lifecycle
# ---------------------------------------------------------------------------

log "==> Phase 6: patch animus.service for mount lifecycle"

if grep -q "animus-vault" "${SYSTEMD_UNIT}"; then
    log "unit already patched (found 'animus-vault' reference)"
else
    UNIT_BACKUP="${SYSTEMD_UNIT}.bak.$(date +%Y%m%d-%H%M%S)"
    cp "${SYSTEMD_UNIT}" "${UNIT_BACKUP}"
    log "unit backup → ${UNIT_BACKUP}"

    # Insert credential + mount/unmount lines into [Service] block.
    # Strategy: find '[Service]' line, append directives right after.
    python3 - "$SYSTEMD_UNIT" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()

INSERT = [
    "# --- gocryptfs vault lifecycle (added by setup-gocryptfs-vault.sh) ---\n",
    "LoadCredentialEncrypted=animus-vault:%h/.config/credstore.encrypted/animus-vault\n",
    "ExecStartPre=/bin/sh -c 'mountpoint -q %h/.animus/_secure || /usr/bin/gocryptfs -q -fsname %h/.animus/_vault -passfile ${CREDENTIALS_DIRECTORY}/animus-vault %h/.animus/_vault %h/.animus/_secure'\n",
    "ExecStopPost=-/bin/fusermount -u %h/.animus/_secure\n",
    "# --- end gocryptfs vault ---\n",
]

out = []
inserted = False
for line in lines:
    out.append(line)
    if not inserted and line.strip() == "[Service]":
        out.append("\n")
        out.extend(INSERT)
        inserted = True

if not inserted:
    print("ERROR: no [Service] section found", file=sys.stderr)
    sys.exit(1)

with open(path, "w") as f:
    f.writelines(out)
PYEOF

    systemctl --user daemon-reload
    log "unit patched + daemon-reload run"
fi

# ---------------------------------------------------------------------------
# Phase 7: restart daemon, verify health
# ---------------------------------------------------------------------------

log "==> Phase 7: restore prior service state + verify"

# Recheck the effective selector immediately before restart. A concurrent config
# change must fail closed and leave the daemon stopped.
EFFECTIVE_BACKEND=$(python3 -c 'from animus.config import AnimusConfig; print(AnimusConfig.load().memory.backend)') \
    || abort "could not re-read the effective Core memory backend"
case "${EFFECTIVE_BACKEND}" in
    local|json) ;;
    *) abort "effective Core memory backend changed to '${EFFECTIVE_BACKEND}'; daemon remains stopped" ;;
esac

if (( DAEMON_WAS_RUNNING )); then
    # Unmount the manual mount so the unit's ExecStartPre performs the managed
    # mount before the previously running service is restored.
    if mountpoint -q "${SECURE_DIR}"; then
        fusermount -u "${SECURE_DIR}" || abort "manual unmount failed; daemon remains stopped"
    fi
    systemctl --user start animus.service
    SERVICE_RESTORED=1
    DAEMON_STOPPED=0
    sleep 3
    if systemctl --user is-active --quiet animus.service; then
        log "animus.service restored to active state"
    else
        log "ERROR: animus.service did not start cleanly — see journalctl --user -u animus.service"
        exit 2
    fi
else
    log "animus.service was inactive before migration; leaving it inactive"
fi

# Verify the vault remains mounted (via the unit for a restored service, or via
# the manual setup mount when the service remains inactive).
if mountpoint -q "${SECURE_DIR}"; then
    verify_expected_vault_mount
    log "vault mounted"
else
    log "ERROR: vault NOT mounted after service-state restoration"
    exit 3
fi

# Quick sanity: daemon can see its supported local data path
if [[ -f "${MEMORY_DIR}/memories.json" ]]; then
    log "memories.json reachable via symlink ✓"
else
    log "ERROR: memories.json not reachable — daemon cannot see local memory"
    exit 4
fi

# Successful completion may clear the fail-safe trap.
DAEMON_WAS_RUNNING=0
DAEMON_STOPPED=0
SERVICE_RESTORED=0
trap - EXIT

log ""
log "============================================================"
log "DONE. At-rest encryption active for supported local memory."
log ""
log "Verify with:"
log "  systemctl --user status animus.service"
log "  journalctl --user -u animus.service --since '5 min ago'"
log "  python -m animus.cli recall 'test query'  # exercise the memory layer"
log ""
log "After a verification window (suggested 24h), remove the"
log "unencrypted backups (DESTRUCTIVE — SSD TRIM will physically"
log "erase the bits in minutes):"
log ""
log "  ls -la ${ANIMUS_DIR}/memory${BACKUP_SUFFIX}"
log "  rm -rf ${ANIMUS_DIR}/memory.unencrypted-backup.*"
log "============================================================"
