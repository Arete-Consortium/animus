# Hunter OS Discord Integration — Project Plan & Audit

**Status:** Planning / implementation branch created  
**Branch:** `feat/hunter-os-discord-v1`  
**Scope:** Monster Hunter Wilds only  
**Primary interface:** Existing Animus Discord application  
**Discord information architecture:** three forums — Weapons, Monsters, Hunter Guide

## 1. Objective

Turn the existing Hunter OS PDFs/cards into a canonical, versioned Monster Hunter Wilds knowledge system that Animus can retrieve, render, audit, and publish to Discord.

The core rule is:

> Canonical structured data supplies facts. Animus supplies retrieval, rendering, publishing, and grounded reasoning. PDFs and Discord cards are generated outputs, not competing sources of truth.

The system must optimize for:
- fast lookup during hunts;
- excellent iPhone/iPad readability;
- exact-weapon handling for Hunting Horn melodies and bowgun ammo;
- explicit patch-sensitive and variant-sensitive status;
- minimal Discord hierarchy;
- deterministic, crisp card rendering;
- no silent reconciliation of conflicting source material.

## 2. Current State Audit

### 2.1 Discord structure

Keep the user's existing three Forum Channels:

1. **Weapons**
2. **Monsters**
3. **Hunter Guide**

Do not add a large channel tree. Forum posts are the records; tags and search provide secondary navigation.

Recommended optional non-forum channel:
- `hunter-os-log` — publication/audit/update notices only.

### 2.2 Existing Animus Discord runtime

Primary repo implementation inspected:
- `tools/animus_discord_bot.py`
- service: `tools/animus-discord.service`

The standalone bot currently provides:
- `/harvest`
- `/watchlist`
- `/watchlist-add`
- `/watchlist-scan`
- `/recall`
- `/remember`
- `/ask`
- `/brief`
- conversational replies to mentions / designated chat channel

The repository also contains a separate kernel Discord implementation:
- `packages/kernel/src/animus_kernel/channels/discord_bot.py`
- provides the `/build` command group.

### 2.3 Important runtime drift finding

The live Discord screenshots show commands including:
- `/animus_status`
- `/ping`
- `/build`

Those commands are not all registered by the current `tools/animus_discord_bot.py` on `main`.

This creates a **deployment/source-of-truth risk**:
- the live bot may be running local code ahead of GitHub;
- multiple Discord bot implementations may be sharing one application/token;
- or stale command registrations may exist.

This must be resolved before Hunter OS command deployment because `tree.sync()` in the standalone bot synchronizes global commands at startup and can conflict with other registrars.

**Gate H0:** identify exactly which process/code path owns the live Discord application and command tree.

### 2.4 Discord permission audit

Current permissions shown in Discord are enough for a read-only V1 and likely initial publishing:
- View Channels
- Send Messages
- Send Messages in Threads
- Create Public Threads
- Embed Links
- Attach Files
- Read Message History
- Use Application Commands

Not currently granted:
- Manage Threads
- Manage Messages
- Manage Channels
- Manage Webhooks
- Administrator

Do **not** grant Administrator.

For V1, use current permissions. If updating forum post names/tags/archival state requires `Manage Threads`, request only that permission after a narrow integration test proves it is necessary.

### 2.5 Animus memory/privacy audit

The existing conversational bot:
- searches general Animus memory;
- may include project/personal memory in context;
- responds in a public/server Discord context;
- logs incoming message content prefixes.

Hunter OS should **not** rely on the general memory store for canonical game facts.

Reasons:
1. correctness — memory retrieval can surface stale/duplicate facts;
2. privacy — Hunter OS is intended to be shareable with friends;
3. determinism — game records should be exact and versioned;
4. auditability — every published fact needs an identifiable canonical record.

Hunter OS therefore gets a separate structured repository/data layer.

### 2.6 Dependency/test audit

Findings:
- `tools/animus_discord_bot.py` imports `discord.py`, but Core's `pyproject.toml` does not declare a Discord extra.
- Bootstrap declares `discord = ["discord.py>=2.3"]`.
- Release evidence includes `discord.py==2.7.1`, but the standalone service depends on the Core venv.
- No dedicated tests were found for `tools/animus_discord_bot.py`.

Implications:
- bot install is currently somewhat environment-dependent;
- Hunter OS logic should not be added directly as untested code inside the tool script.

Plan:
- place Hunter OS domain logic under `packages/core/animus/hunter_os/`;
- keep Discord registration thin;
- add Core tests;
- decide whether to add a Core `discord` optional dependency or migrate the runtime onto the existing Bootstrap Discord extra.

## 3. Hunter OS Source Audit

### 3.1 Canonical candidate sources

Treat the audited/final Hunter OS documents as current source material for migration:

- `00_Hunter_OS_v1_Quick_Reference`
- `01_Hunter_OS_v1_Weapon_Field_Manual`
- `02_Hunter_OS_v1_Monster_Field_Manual`
- `03_Hunter_OS_v1_Support_and_Builds`
- `04_Hunter_OS_v1_Farming_and_Resources`
- `05_Hunter_OS_v1_Hunter_Database`
- `07_Hunter_OS_v1_HH_LBG_Specialist_Reference`
- `09_Hunter_OS_v1_Endgame_and_Progression`
- `10_Hunter_OS_v1_Artian_Forge_Guide`
- `11_Hunter_OS_Hunting_Horn_Songbook_and_Melody_Atlas`

The separately generated Combat Healer HH+LBG manual is a **derived output**, not a canonical source.

### 3.2 Duplicate files

Known byte-identical duplicates in the uploaded set:
- two copies of `01_Hunter_OS_v1_Weapon_Field_Manual`;
- two copies of `MHW_Wilds_Elite_Weapon_Combo_Field_Manual_v2`.

Migration must deduplicate by content hash, not filename.

### 3.3 Legacy/reference documents

These are valuable but should not outrank later audited Hunter OS records:
- `MHW_Wilds_Elite_Weapon_Combo_Field_Manual_v2`
- `02_Monster_Field_Manual_FIXED_LINKS`
- `03_Hunt_Support_Manual_FIXED_LINKS`

They contain useful presentation, navigation, mastery, and combo material, but they represent earlier document generations.

### 3.4 Semantic conflict risk: "target" is not one field

Legacy monster cards often use a generic `TARGET` field. The audited Hunter OS manual frequently uses explicit role/weapon targeting such as `HH: head`, tail sever priorities, state-specific hitzones, or special mechanic targets.

Therefore the canonical schema must **not** collapse all target information into one string.

Required structure:
- generic target(s)
- blunt / Hunting Horn target(s)
- sever target(s)
- shot target(s) when known
- wound/focus target(s)
- state/phase-specific target(s)

This prevents false contradictions and preserves useful differences between weapon classes.

### 3.5 Special encounter mismatch

The audited Hunter OS rules state that encounters such as:
- Omega Planetes
- Savage Omega
- Gogmazios

should use phase/mechanic timelines rather than ordinary simple monster cards.

The current image deck uses the same general card shell for these special encounters.

That is visually usable as a quick summary, but it is not sufficient as the canonical representation.

Plan:
- keep a quick summary cover card;
- add a dedicated `SpecialEncounterRecord` and timeline/mechanics card family.

### 3.6 Hunting Horn rule

Hunting Horn data must remain exact-horn / exact-song-set specific.

Do not:
- infer melodies from another horn tree;
- treat a song package as universal;
- silently inherit title-update melody wording;
- infer Artian melody packages without forge-preview-specific evidence.

Schema must support:
- exact weapon/upgrade;
- note recipes;
- effect;
- Echo Bubble;
- Special Performance;
- verification state;
- patch sensitivity;
- source/date.

### 3.7 Light Bowgun rule

LBG ammunition is exact-weapon specific.

Do not:
- infer ammo from Hunter Rank;
- infer ammo from another LBG;
- build support doctrine around Recover/Demon/Armor ammo unless the exact gun supports it.

Schema must support:
- damage ammo levels;
- elemental ammo;
- status ammo;
- support ammo;
- rapid-fire compatibility;
- recoil;
- reload;
- magazine/handling;
- verification state.

### 3.8 Versioning rule

Every canonical record needs:
- game = Monster Hunter Wilds;
- data snapshot / verified date;
- status: verified / patch-sensitive / weapon-specific / review;
- source provenance;
- variant identity where applicable.

Event quests and reward schedules must remain explicitly patch-sensitive.

## 4. Card Deck Audit

Current monster card deck:
- 35 PNG cards;
- 1080 × 1620;
- consistent 2:3 portrait layout;
- strong contrast;
- large headings;
- readable card sections;
- excellent starting visual language.

Strengths:
- Discord-friendly portrait format;
- clear hierarchy;
- visible verification/date state;
- consistent color-coded borders/status;
- substantially more usable on mobile than full PDF pages.

Changes for generated V1:
1. retain 2:3 portrait family;
2. render at 1440 × 2160 when practical for higher-density screens, while keeping export size reasonable;
3. keep text programmatic/deterministic;
4. enforce minimum body font size;
5. avoid shrinking text to solve overflow — split into multiple cards;
6. support card families instead of one universal template;
7. reserve image/illustration area for optional art, but never place essential facts only in the artwork;
8. special encounters receive timeline/mechanics cards;
9. weapon controls use consistent button tokens/glyphs;
10. Discord companion text remains searchable and accessible.

## 5. Target Architecture

```text
Discord
  |
  +-- Weapons forum
  +-- Monsters forum
  +-- Hunter Guide forum
  |
Animus Discord interface
  |
  +-- /hunter ...
  +-- optional grounded routing from conversational chat
  |
Hunter OS service/domain
  |
  +-- Repository / search
  +-- Schema validation
  +-- Audit engine
  +-- Card renderer
  +-- Discord formatter
  +-- Publisher
  |
Canonical structured records
  |
  +-- monsters/
  +-- weapons/
  +-- guides/
  +-- builds/
  +-- resources/
  +-- encounters/
```

Proposed package:

```text
packages/core/animus/hunter_os/
├── __init__.py
├── models.py
├── repository.py
├── search.py
├── audit.py
├── discord_format.py
├── renderer.py
├── publisher.py
├── provenance.py
├── exceptions.py
├── data/
│   ├── monsters/
│   ├── weapons/
│   ├── guides/
│   ├── builds/
│   ├── resources/
│   └── encounters/
└── templates/
```

Tests:

```text
packages/core/tests/hunter_os/
├── test_models.py
├── test_repository.py
├── test_search.py
├── test_audit.py
├── test_discord_format.py
├── test_renderer.py
└── test_publisher.py
```

## 6. Core Data Models

### 6.1 Shared metadata

All records:
- `id`
- `name`
- `game`
- `record_type`
- `status`
- `verified_date`
- `patch_version` when known
- `sources[]`
- `tags[]`
- `notes[]`

### 6.2 MonsterRecord

Fields:
- weakness by state/part where needed;
- target groups;
- controls/traps;
- status/blight prep;
- fight plan;
- break/sever notes;
- capture rules;
- variant relationship;
- patch sensitivity.

### 6.3 SpecialEncounterRecord

Fields:
- encounter identity;
- role/mechanic requirements;
- phase list;
- transition triggers;
- wipe checks;
- positioning;
- recovery windows;
- capture rules;
- reward loop.

### 6.4 WeaponTypeRecord

Fields:
- control legend;
- universal actions;
- core loop;
- resource/gauge mechanics;
- focus/wound interaction;
- mastery notes;
- common failure modes.

### 6.5 ExactWeaponRecord

Fields:
- exact weapon/upgrade;
- tree;
- element/status;
- weapon-specific features;
- verification.

Subtypes:
- HuntingHornRecord
- LightBowgunRecord
- HeavyBowgunRecord where needed.

### 6.6 GuideRecord / BuildRecord

Examples:
- Combat Healer;
- Palico support;
- pre-hunt checklist;
- farming;
- Artian forging;
- progression.

Build records should distinguish:
- core invariant skills;
- optional/encounter swaps;
- exact gear snapshot;
- user/personal build notes.

## 7. Discord UX

### 7.1 Initial command namespace

One top-level group:

`/hunter`

Subcommands for V1:
- `/hunter monster <name>`
- `/hunter weapon <name>`
- `/hunter guide <name>`
- `/hunter search <query>`
- `/hunter audit <record>`
- `/hunter card <record>`

Publishing added only after read/audit/card paths are stable:
- `/hunter publish <record>`

Use autocomplete from the canonical repository.

### 7.2 Forum mapping

**Weapons**
- one forum post per weapon type;
- exact weapon/build cards can be replies within the post;
- Hunting Horn and bowgun specialist material remains grouped under the weapon post.

**Monsters**
- one forum post per monster/variant record;
- first message = searchable text summary + quick card;
- advanced/timeline/material cards follow as replies.

**Hunter Guide**
- Quick Reference / Start Here;
- Combat Healer;
- Palico;
- Farming;
- Artian;
- Progression;
- item/status systems.

### 7.3 Searchable companion text

Every image card publication must include concise Discord text:
- canonical title;
- key answer line;
- tags;
- verification date/status;
- record ID/version.

Do not rely on image-only information.

## 8. Animus Reasoning Integration

V1 should **not** modify the generic `/ask` command.

Reason:
- current `/ask` is a memory search response, not the conversational LLM path;
- changing it combines two projects and increases regression risk.

After V1:
1. add Hunter OS intent detection to conversational messages;
2. retrieve canonical Hunter records first;
3. provide only those records as the game-fact context;
4. let the cognitive model reason over them;
5. prohibit unsupported factual completion.

Rule:

> If Hunter OS has no verified value for a requested exact fact, Animus says the record does not currently verify it rather than inventing it.

## 9. Publishing Model

### 9.1 Record -> output flow

```text
load record
 -> schema validate
 -> provenance validate
 -> semantic audit
 -> render card
 -> visual QA
 -> build Discord text
 -> locate forum/post
 -> publish or update
 -> record publication metadata
```

### 9.2 Publication metadata

Track:
- guild ID
- forum/channel ID
- thread/post ID
- first message ID
- last published record hash
- last card hash
- published timestamp

Store outside canonical facts, e.g.:
`~/.animus/hunter_os/publications.json`

This allows idempotent update behavior.

## 10. Audit Engine

Audit categories:

### Scope
- Wilds only;
- valid record type;
- valid variant.

### Provenance
- source exists;
- verified date present;
- status present;
- no untraceable inherited fact.

### Monster
- weakness;
- target semantics;
- prep/control;
- fight plan;
- capture/variant handling.

### HH
- exact horn;
- exact melodies;
- Echo Bubble;
- Special Performance;
- verification state.

### LBG
- exact LBG;
- ammo table;
- handling;
- rapid-fire compatibility;
- support ammo proof.

### Card
- render dimensions;
- minimum font;
- no overflow;
- contrast;
- status/date visible;
- title within bounds.

### Publication
- correct forum;
- correct tags;
- record ID in metadata;
- no duplicate forum post.

Audit statuses:
- PASS
- WARN
- BLOCK

Only PASS is auto-publishable.

## 11. Security and Privacy

1. Hunter OS data is public/game-domain data and must remain separate from personal Animus memory.
2. `/hunter` must not query general memory unless explicitly requested by an admin-only personal-build feature.
3. Do not place API tokens, Discord IDs, or secrets in canonical YAML.
4. Log command metadata, not full user message bodies by default.
5. Publisher actions should be guild/channel allowlisted.
6. Publishing mutations should be restricted to configured admin users/roles.
7. Do not grant Administrator.
8. Keep current systemd hardening; write generated assets under `~/.animus/hunter_os/` or an explicit cache path.
9. No uncontrolled web research in publish path. Research/reverification should be an explicit separate workflow.

## 12. Testing Strategy

### Unit
- schema validation;
- record loading;
- exact-weapon rules;
- variant rules;
- search;
- audit severity;
- Discord formatter length constraints;
- deterministic card rendering.

### Golden tests
Keep reference snapshots for:
- Rathian monster card;
- Hunting Horn quick controls;
- Combat Healer guide card;
- Omega special encounter timeline.

### Integration
Mock Discord objects to test:
- forum lookup;
- thread creation;
- message attachment;
- update/idempotency;
- permission failure behavior.

### Manual device QA
Required devices:
- iPhone;
- iPad;
- desktop Discord.

Acceptance:
- preview legible enough to identify card;
- tapped image text crisp at normal zoom;
- no horizontal scrolling;
- no clipped lines;
- key answer visible in under 10 seconds.

## 13. Delivery Phases

### Phase 0 — Runtime ownership audit
**Goal:** establish live Discord source of truth.

Tasks:
- identify service/process using the Animus Discord token;
- compare deployed `animus_discord_bot.py` to GitHub main;
- determine source of `/animus_status`, `/ping`, and `/build`;
- ensure only one component owns global command synchronization.

Exit criterion:
- one documented command-registration owner.

### Phase 1 — Canonical Hunter OS foundation
**Goal:** deterministic read-only domain.

Tasks:
- implement models;
- repository loader;
- provenance;
- audit engine;
- migrate three vertical-slice records:
  - Rathian;
  - Hunting Horn universal controls;
  - Combat Healer HH+LBG guide.

Exit criterion:
- unit tests pass and three records audit PASS.

### Phase 2 — Card renderer
**Goal:** mobile-first deterministic cards.

Tasks:
- create 2:3 renderer;
- text-fit/overflow checks;
- controller tokens;
- verification/status badges;
- three golden cards.

Exit criterion:
- cards pass automated QA and user device review.

### Phase 3 — Discord read interface
**Goal:** `/hunter` usable in live server.

Tasks:
- add slash group;
- autocomplete;
- monster/weapon/guide/search/audit/card;
- guild/channel allowlist;
- no publishing yet.

Exit criterion:
- live read-only Hunter OS works without impacting existing commands.

### Phase 4 — Full data migration
**Goal:** migrate current Hunter OS corpus.

Tasks:
- all 35 monsters;
- all 14 weapon types;
- HH songbook;
- LBG specialist records as exact guns become verified;
- farming/resources;
- Artian;
- progression/endgame;
- support/Palico.

Exit criterion:
- no unresolved BLOCK records in publishable set.

### Phase 5 — Forum publisher
**Goal:** Animus maintains the three Forum Channels.

Tasks:
- map forums by configured ID;
- create/update posts;
- upload cards;
- tags;
- idempotency;
- publication registry;
- changelog.

Exit criterion:
- re-running publish creates no duplicates and updates only changed records.

### Phase 6 — Grounded conversational routing
**Goal:** natural-language Hunter OS through Animus.

Tasks:
- domain intent detection;
- canonical retrieval;
- context builder;
- unsupported-fact refusal behavior;
- optional exact build context.

Exit criterion:
- Monster Hunter answers cite/use canonical record data and do not silently use stale memory.

### Phase 7 — Patch maintenance
**Goal:** sustainable updates.

Tasks:
- patch/change watch workflow;
- mark affected records REVIEW/PATCH-SENSITIVE;
- re-audit;
- regenerate;
- republish changed cards only.

## 14. Initial Vertical Slice

Build these first:

### A. Rathian
Tests monster schema, targets, prep, card rendering, Discord forum presentation.

### B. Hunting Horn
Tests platform controls, song-system rules, exact-weapon separation, controller tokens.

### C. Combat Healer HH + LBG
Tests guide/build composition and cross-record linking.

### D. Omega Planetes
Added to renderer/audit tests before full migration to prove special encounters are not forced into ordinary monster schema.

## 15. Key Risks

### R1. Live bot/source drift — HIGH
Mitigation: Phase 0 gate before command deployment.

### R2. Multiple Discord registrars overwrite commands — HIGH
Mitigation: single global command-sync owner.

### R3. Legacy/current document fact collisions — HIGH
Mitigation: structured provenance + explicit semantic fields + BLOCK on true conflicts.

### R4. Personal memory leaks into shared Hunter OS — HIGH
Mitigation: isolated Hunter repository, no general-memory fallback.

### R5. Card readability regression — MEDIUM
Mitigation: minimum typography, split-card rule, golden snapshots, device QA.

### R6. Patch-sensitive game data ages silently — MEDIUM
Mitigation: verification dates and review states.

### R7. Bot permissions too broad — MEDIUM
Mitigation: least privilege; no Administrator.

### R8. Exact HH/LBG data inferred incorrectly — HIGH
Mitigation: schema and audit rules make exact weapon identity mandatory.

## 16. Definition of Done — V1

V1 is complete when:
- live Discord command ownership is documented;
- Hunter OS package exists in Core;
- canonical records load deterministically;
- Rathian, Hunting Horn, Combat Healer, and Omega test records are modeled;
- audit engine returns PASS/WARN/BLOCK;
- mobile card renderer produces deterministic PNGs;
- `/hunter monster`, `weapon`, `guide`, `search`, `audit`, and `card` work;
- no generic Animus memory is needed for Hunter OS factual answers;
- existing Animus commands still work;
- tests/lint pass;
- user has validated representative cards on iPhone/iPad.

## 17. Immediate Next Actions

1. Complete Phase 0 runtime ownership audit.
2. Create Core Hunter OS package skeleton.
3. Implement metadata + MonsterRecord + GuideRecord + WeaponTypeRecord + SpecialEncounterRecord.
4. Implement repository/audit.
5. Add the four vertical-slice records.
6. Add tests.
7. Only then wire `/hunter` into the Discord command tree.
