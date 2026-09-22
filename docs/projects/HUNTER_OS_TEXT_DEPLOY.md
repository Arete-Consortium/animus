# Hunter OS — Text-Only Forum Deployment

This branch is intentionally based on the preserved live Discord host branch and contains only the text-first Hunter OS publishing path.

It does **not**:
- change or restart the running Animus Discord service;
- add image/Pillow dependencies;
- modify general Animus memory;
- create new Forum threads;
- require Manage Threads or Administrator.

## What it publishes

Existing Hunter OS Forum threads:
- Weapons
- Monsters
- Hunter Guide

Content is sourced from the audited Hunter OS documents and formatted as searchable Discord text.

## Safe deployment method

Use a separate git worktree so the running service checkout is untouched.

```bash
cd ~/projects/animus
git fetch origin

git worktree add ~/projects/animus-hunter-text origin/deploy/hunter-os-text-v1
cd ~/projects/animus-hunter-text
```

## Dry run

The publisher reads the Discord bot token from:
`~/.config/animus/discord.env`

Pass the three existing thread IDs explicitly:

```bash
/home/arete/projects/animus/packages/core/.venv/bin/python tools/hunter_os_publish_text.py \
  --weapons-thread <WEAPONS_THREAD_ID> \
  --monsters-thread <MONSTERS_THREAD_ID> \
  --guide-thread <HUNTER_GUIDE_THREAD_ID> \
  --dry-run
```

Dry run performs no Discord writes.

## Publish

Remove `--dry-run`:

```bash
/home/arete/projects/animus/packages/core/.venv/bin/python tools/hunter_os_publish_text.py \
  --weapons-thread <WEAPONS_THREAD_ID> \
  --monsters-thread <MONSTERS_THREAD_ID> \
  --guide-thread <HUNTER_GUIDE_THREAD_ID>
```

## Idempotency

Publisher state is stored at:

`~/.animus/hunter_os/forum_publications.json`

Each managed block records:
- Discord message ID;
- content SHA-256;
- title.

Re-running the publisher:
- skips unchanged blocks;
- edits changed bot-owned messages;
- creates only missing messages;
- never deletes stale messages automatically.

## Rollback

Because the running Animus service checkout is untouched, rollback is simply:
- stop using the temporary worktree;
- manually remove any bot-published Discord messages if desired.

No service restart is required for the text-only publish.
