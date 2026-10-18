# Animus Personal Roadmap — Optimizing for One User

> **Status:** Operating doctrine for evolving animus as a personal exocortex.
> **Owner:** ARETE (sole user, by design).
> **Authored:** 2026-05-15 after a session that re-grounded animus as "best possible tool for one person" rather than "framework chasing public adoption."

---

## North star

Animus's success metric is **"did it make ARETE more effective today"** — not "did anyone install it," not "did stars accumulate," not "did a recruiter notice the test count." Every choice below optimizes for personal-tool quality. When a tradeoff exists between making animus better for one user versus opening it to more users, the single-user branch wins by default.

## Operating principles

- **Resist productization features.** Multi-tenant, SSO, admin UI, RBAC, billing — none of these serve the operator. Don't build them.
- **Reduce friction over add features.** A workflow that runs reliably beats two workflows that mostly run.
- **Cost-efficiency matters.** The operator pays the bill in full. Every avoidable token is a small win that compounds.
- **Durability matters disproportionately.** There's only one user. Lose the user (machine dies, account corrupts, data lost), the tool dies. Plan for resilience.
- **Personal tools should age well.** Still useful in five years. Not requiring constant maintenance. Plain-text exit paths.
- **Composability with the rest of the portfolio.** Animus should consume the portfolio's other infrastructure (drift-monitor, memboot patterns, anchormd discipline) and benefit when those mature.

---

## Track 1 — Durability + rebuild speed

**Why:** If the current machine dies, animus is unusable until restored. Restoration time is the single point of catastrophic failure for a personal-tool with this much accumulated state. The Bootstrap one-command install was designed for this; it needs to actually work end-to-end on a fresh box.

**Current state:** Bootstrap exists. Real-world rebuild has never been tested cold.

**Concrete steps:**
1. Quarterly dry-run on a clean Ubuntu VM (no prior animus state): `bash <(curl -fsSL bootstrap-url)`. Time it. Should be under 15 minutes to operational.
2. Identify what restores cleanly and what requires manual setup (API keys,
   OAuth tokens, MCP server registrations, supported memory state, Ollama model
   pulls, and any separately managed retrieval index).
3. Document the manual-setup tail in `docs/REBUILD.md` with explicit env vars + token-rotation procedure.
4. Memory restore: confirm the supported local/durable store rebuilds from the
   verified source records. Preserve any legacy Chroma snapshot only as an
   isolated migration input under the retirement plan.
5. Identity restore: `CORE_VALUES.md` + LEARNED.md + persona configs all in version control (private repo). Verify they're actually committed, not just sitting in the working tree.

**Effort:** First dry-run ~3 hours. Documentation ~1 hour. Recurring quarterly ritual ~30 min.

**Execution gate:** Schedule the first dry-run before any work machine becomes the daily driver. If FDE role lands, this becomes urgent — work machine cannot host animus.

---

## Track 2 — Cost-efficiency audit

**Why:** Animus runs 24/7 with proactive checks, message gateway adapters, and self-improvement loops. Token spend can drift up without anyone noticing. The Effective-Tokens metric in PR #41 was specifically designed to make this visible.

**Current state:** ET metric shipped in `BudgetManager`. HybridBackend routes Anthropic vs Ollama based on `_classify_query` heuristics (45 agentic verbs + URL/path regex). Real-traffic data exists in budget logs but hasn't been analyzed.

**Concrete steps:**
1. Pull 30 days of budget logs. Compute: total spend, top 10 workflows by cost, top 5 agents by token consumption.
2. For each top-cost workflow: is it routing correctly (Anthropic for hard reasoning, Ollama for scaffolding)? Use ET to compare actual vs optimal routing.
3. Tune `_classify_query` heuristics against real traffic. Add domain-specific verbs / phrases that should bias Ollama.
4. Identify recurring queries (same prompt shape, repeated) — candidates for caching or template-substitution.
5. Set a monthly budget ceiling. If exceeded, animus should self-throttle to Ollama-only for non-critical workflows.

**Effort:** Analysis ~2 hours. Tuning + tests ~3 hours. Ongoing ~30 min/month.

**Execution gate:** Monthly. Surface cost trend in proactive engine.

---

## Track 3 — Tool surface audit

**Why:** Animus has 37 tools registered. After a year of use, some are real workhorses (web_fetch, memory_query, file edits), some haven't been called in months (rotting registrations). A bloated tool surface hurts both routing (more context burned on tool selection) and cognitive load when reading the registry.

**Current state:** 37 tools. Usage logs exist in `audit_log`. Never been audited as a set.

**Concrete steps:**
1. Query audit log: per-tool call count over the last 90 days.
2. Three buckets: **active** (10+ calls/month), **occasional** (1-10), **rotting** (0).
3. For each rotting tool: decide deprecate-and-remove, deprecate-and-keep-disabled, or "this is a planned-but-unused feature."
4. For each active tool: are the parameter schemas sharp? Wrong-shape calls waste tokens on error recovery.
5. Re-audit quarterly; rotting buildup is a slow drift.

**Effort:** First audit ~2 hours. Pruning ~1 hour. Recurring quarterly ~30 min.

**Execution gate:** First audit before any major feature work in 2026 H2. Keeps the surface honest.

---

## Track 4 — Persona tuning

**Why:** The Phase 4 PersonaEngine + channel-aware routing + VoiceConfig (6 presets) was built to make animus feel right across 8 message channels (Telegram, Discord, Slack, Matrix, WhatsApp, Signal, Email, WebChat). After months of real use, cadence drift is likely — direct enough on Signal, formal enough on Email, terse enough in WebChat. Worth a calibration pass against actual conversation samples.

**Current state:** 6 VoiceConfig presets + time-shift modulation + KnowledgeDomainRouter (9 domains) + ContextAdapter (time/channel/mood). Calibration was done at build-time; never re-tuned against user-felt friction.

**Concrete steps:**
1. Per channel, pull 20 recent animus responses. Read them. Note any that feel off (too formal, too casual, wrong cadence for the channel).
2. Adjust VoiceConfig per channel based on real friction, not theoretical fit.
3. Add an explicit "feedback" command per channel — "voice off on this one" — so future drift is caught fast.
4. Persona-vs-domain interplay: if you're talking technical-Linux on Discord vs personal-life on Signal, the persona should shift. Verify it does.
5. Document the persona-tuning approach in `docs/PERSONAS.md` so future-you can recalibrate without re-deriving.

**Effort:** First read-through ~1.5 hours. Adjustments + tests ~2 hours.

**Execution gate:** After any significant change in channel mix (e.g., adding a new message gateway).

---

## Track 5 — Self-knowledge (LEARNED.md and the reflection loop)

**Why:** The reflection loop reads feedback (`animus-bootstrap feedback add up/down`) and updates `LEARNED.md`. After a year, what does LEARNED.md actually say? Is it tracking the right patterns? Are there meta-patterns animus could surface that would be valuable but isn't yet?

**Current state:** LEARNED.md is auto-maintained by the reflection trigger. Content quality and signal density unknown — never audited.

**Concrete steps:**
1. Read LEARNED.md end-to-end. Score each entry: signal / noise / outdated.
2. Identify entry classes that are useful (working preferences, anti-patterns, calibration notes) vs ones that aren't (transient session details, ephemeral debug info).
3. Adjust the reflection prompt to bias toward useful entry classes.
4. Add a quarterly compaction pass: archive old entries, surface durable patterns at the top.
5. Consider derived insights: "ARETE's decision style," "energy curve by time-of-day," "tool preferences by domain." These are higher-order patterns animus could compute from LEARNED + audit log + memory.

**Effort:** Audit ~1 hour. Prompt tuning + tests ~2 hours. Recurring quarterly ~45 min.

**Execution gate:** Q3 2026. Useful for understanding own patterns; informs every other track.

---

## Track 6 — Succession + plain-text exit path

**Why:** Personal tools that lock data behind their own infrastructure age badly. If something happens (you stop using it, hardware fails irretrievably, family needs to extract data), there should be a graceful export. This is durability for the *data*, separate from durability for the *tool*.

**Current state:** Supported Core memory is local JSON or configured durable SQL,
with raw markdown source files where applicable. Preserved legacy Chroma data is
an isolated migration input, not a current runtime store. Identity is in
`CORE_VALUES.md`, the audit log is JSONL, and tasks are in SQLite. All are
extractable but not unified.

**Concrete steps:**
1. Write `animus export --all <output-dir>` command that produces a portable archive:
   - All memory files as markdown
   - LEARNED.md, CORE_VALUES.md, persona configs
   - Audit log as JSONL with timestamps
   - Task history as markdown
   - README explaining what each file is and how to read without animus
2. Test the export: can a stranger open the archive and understand what's there?
3. Quarterly: run the export, verify file integrity, archive to encrypted backup.
4. Document the export schema so it's stable across animus versions — future-you (or family) opens an export from 5 years ago and it still parses.

**Effort:** Export command + tests ~4-6 hours. Documentation ~1 hour. Recurring quarterly ~15 min.

**Execution gate:** Within Q3 2026. Before any major schema change.

---

## Track 7 — Adversarial robustness

**Why:** Animus has access to a lot — file I/O, web fetch, message gateways across 8 channels, MCP tool surface, OAuth tokens to integrations. If a prompt-injection from a webpage (via `web_fetch`) or a malicious MCP server got animus to misbehave, the damage radius is substantial. Approval gates exist on destructive actions; they're a partial defense.

**Current state:** Approval gates exist per memory. Audit log captures all tool calls. No formal red-team has been done.

**Concrete steps:**
1. Threat model the proactive-engine: what can a malicious input cause autonomously, without operator approval?
2. Audit the tool registry: which tools could exfiltrate (web POST, email send, file write to non-animus paths, MCP calls to attacker-controlled servers)?
3. Add allowlists for outbound network destinations on tools that can call out.
4. Add rate-limiting on tools that can have damage scale with frequency (email send, file write).
5. Run a structured red-team session: craft 10 prompt-injection scenarios via web_fetch + 10 via message-gateway adapters. Document which ones succeed.
6. Treat findings like memboot's security audit — file as `SECURITY_FINDINGS.md` with fix/no-fix decisions per finding.

**Effort:** Threat model ~3 hours. Red-team session ~4 hours. Findings remediation: variable.

**Execution gate:** Before any further expansion of the tool surface or message-gateway channels.

---

## Track 8 — Finish the in-flight active work

**Why:** Two architectural threads are mid-flight and worth finishing on their own merits — they're improvements to the personal tool, not productization detours.

**Current state:**
- **Active-inference IntentResolver** — replacement for the Async-CA approach. Week of 2026-05-04 commit. In flight.
- **Quorum v2 5-week extension plan** — Week 1 EventLog bitemporal shipped (PR #36). Weeks 2-5 queued: LivenessWatchdog, active-inference IntentResolver (the one behavior change), coupling MI dashboard, hard re-eval gate.

**Concrete steps:**
1. Finish Quorum v2 Week 1 follow-ups (SCORE_UPDATED + INTENT_RESOLVED mutation sites — deferred to Week 3-4 in original plan).
2. Execute Week 2: LivenessWatchdog. Bounded scope: detects agents that stop emitting expected signals.
3. Execute Week 3-4: active-inference IntentResolver. The load-bearing piece. Replaces current Async-CA. Surprise-weighted Bayesian inference.
4. Execute Week 5: coupling MI dashboard. Hard re-eval gate — does the new resolver actually behave better?
5. Decide post-week-5: ship as Quorum v0.2 spec update + reference implementation update. Public versioning.

**Effort:** Multi-week. Original plan scoped 5 weeks. Quorum v0.2 spec update post-completion.

**Execution gate:** Don't start Week 2 until Week 1 follow-ups land. Don't open Week 5 dashboard work until resolver is observable in real workflows.

---

## Track 9 — Work-personal boundary

**Why:** If FDE role lands, animus running on the same machine as work creates ambiguity — whose context, whose memory, what happens at offboarding. Cleanest move is to set the boundary *before* the role lands, not after.

**Current state:** Animus lives on personal hardware. No work integration. No formal policy.

**Concrete steps:**
1. Write `docs/WORK_BOUNDARY.md` policy:
   - Animus stays on personal hardware exclusively
   - Work has its own context store (work laptop, separate accounts)
   - Cross-pollination is manual and intentional (e.g., explicit "remember this for ARETE personal" tag)
   - No animus credentials on work hardware
   - No work credentials in animus secrets store
   - If a role requires AI tooling, evaluate work-provided tools or build a minimal work-specific assistant — never bridge personal animus into work
2. Audit: any current animus integration that could leak into work context? (Calendar, Todoist, etc. — ensure separation)
3. Tag system: animus tags memories/tasks with `personal` vs `work-adjacent`. Default: personal.
4. If FDE role lands: at offboarding-readiness moment, work content (if any) gets purged, animus stays untouched.

**Effort:** Policy doc ~1 hour. Audit ~1 hour. Tag system ~3 hours if it doesn't exist already.

**Execution gate:** Before any FDE role onboarding. Critical for legal/IP-ownership clarity.

---

## Track 10 — Resist productization, deliberately

**Why:** The Silicon Valley reflex is "must monetize." For animus, monetizing would degrade the personal tool. This track is a standing reminder + a checklist of features-NOT-to-build.

**Standing reminders:**
- Don't add SSO. (You're the only user.)
- Don't add RBAC. (You're the only role.)
- Don't add admin UI separate from operator UI. (Same person.)
- Don't add multi-tenant data isolation. (Single tenant.)
- Don't add API rate-limiting for external callers. (No external callers.)
- Don't add a billing system. (No customers.)
- Don't add a public landing page. (Animus is not a product.)
- Don't write external user documentation. (One user; the operator IS the documentation.)
- Don't add a community Discord or support channel for animus itself. (Quorum has its own community surface as a protocol.)
- Don't pursue stars, downloads, or social-media metrics for animus. (These optimize for the wrong outcome.)

**Concrete steps:**
1. Quarterly: re-read this section before any architectural decision. Productization creep is gradual.
2. If a feature feels org-shaped, ask: "would I want this even if I were the only user forever?"
3. If the answer is no, don't build it.

**Effort:** 0 (a standing rule, enforced by re-reading).

**Execution gate:** Every architectural decision.

---

## Quarterly rituals

To prevent drift on the above:

- **Q-start:** review this roadmap. Adjust priorities. Note completed tracks.
- **Q-mid:** run Track 1 dry-run + Track 2 cost audit + Track 3 tool audit.
- **Q-end:** run Track 5 LEARNED.md audit + Track 6 export.
- **Annual:** run Track 7 adversarial red-team.

---

## Cross-portfolio interactions

Animus benefits when other portfolio pieces mature:

- **drift-monitor** → wire into animus Forge BudgetManager (per `notes/topics/drift-monitor-adoption-plan.md` Target 2). Animus becomes a paying user of its own infrastructure.
- **memboot** → animus's memory layer could optionally use memboot patterns (bitemporal-lite, source attribution). Not a replacement; an interop.
- **anchormd** → run on animus's own internal CLAUDE.md regularly. Animus polishes its own context.
- **arete-evals** → run periodically against animus's workflows. Catches regression in animus's outputs.
- **TIAID** → if TIAID engagements happen, animus is the backend tool. Each engagement informs improvements to animus.

---

## What this roadmap is NOT

- Not a public-product plan
- Not a "make animus famous" plan
- Not a "monetize animus" plan
- Not a feature wishlist

It's a personal-tool care-and-feeding plan. Most entries are reductive (audit, prune, tune) rather than additive (build new feature). That's intentional. A mature personal tool grows by accretion of value through use, not by adding surface area.

---

## Changelog

- **2026-05-15:** v1.0 — initial roadmap. Authored after re-grounding animus as "best possible tool for one user" rather than "framework chasing public adoption."
