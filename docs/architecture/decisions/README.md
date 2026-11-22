# Architecture Decisions

> Append-only log of high-leverage decisions affecting Animus architecture, scope, and tooling.

---

## What is an ADR?

An **Architecture Decision Record (ADR)** documents a significant decision: the context, the options considered, the choice made, and the tradeoffs accepted. ADRs are append-only — once logged, they are not edited, only superseded by a new ADR.

An **Arete Decision Log (ADL)** entry is a higher-level commitment scoped to a project milestone. ADLs live here alongside ADRs.

---

## Index

| ID | Title | Date | Status | Class |
|---|---|---|---|---|
| [ADR-001](ADR-001.md) | Adopt v2.1 Mind-class Architecture | 2026-06-18 | Accepted | ARCH |
| [ADL-20260618-001](ADL-20260618-001.md) | Commit to v2.1 as canonical executable baseline | 2026-06-18 | Committed | ARCH |
| [ADR-002](ADR-002.md) | Store typed knowledge edges in Core durable storage | 2026-11-21 | Accepted for pilot | ARCH |

---

## Classes

- **ARCH** — Structural or cross-cutting architecture changes
- **UX** — Interface, interaction, or workflow decisions
- **SCOPE** — Project scope inclusions and exclusions
- **TOOLING** — Build, CI, deployment, or development tool choices
- **PHIL** — Philosophical or principle-level decisions

---

## How to Propose a New ADR

1. Copy `_templates/adr.md` to `ADR-NNN.md` (next sequential number)
2. Fill in all sections
3. Submit a PR with the `docs:` prefix
4. Discuss and revise; once accepted, merge

---

## Template

See [_templates/adr.md](../../_templates/adr.md).
