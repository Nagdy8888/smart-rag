---
title: Phase 1 foundation — packet evidence
owner: engineering-lead
status: in_progress
last-reviewed: 2026-08-12
audience: engineering, reviewers
---

# Phase 1 foundation evidence

Canonical packet evidence for Phase 1. Each packet appends its handoff. Do not check a packet from file presence alone.

## Packet 1 — targets, budgets, and human sign-off

### Requirement (quoted)

> Obtain and record sign-off for quality, capacity, distinct normal/graph-maintenance budgets, RTO/RPO, availability/workload-isolation triggers, v1 media limitations, and dated Hybrid Pilot decision criteria.

### Concrete acceptance checks

- Every numeric target in global-contract lines 63–81 represented once with units and provenance; no contradictory duplicate.
- Capacity covers 10,000 Hybrid versions, 1,000,000 chunks, 25 users, five simultaneous runs, and 2,000-document/200,000-chunk graph envelope.
- Normal and maintenance budgets, media limitation, UTC/Hijri policy, RTO/RPO, and every multi-host trigger separately visible.
- Hybrid Pilot checkpoints contain actual dates, approver field, objective criteria, and production-label prohibition.
- User has explicitly approved defaults or approved recorded replacements; otherwise Packet 1 and Phase 1 remain blocked.
- Only allowed documentation paths changed; evidence lists pending versus approved fields.

### Inspected paths (before edit)

| Path | Result |
| --- | --- |
| `docs/` | Only `docs/reviews/2026-08-12-hybrid-graph-rag-plan-review.md` existed |
| `docs/QUALITY_TARGETS.md` | Absent (created) |
| `docs/adr/` | Absent (created) |
| `docs/development/` | Absent (created) |
| `docs/architecture/` | Absent (created) |
| `.cursor/plans/hybrid-graph-rag/00-global-contracts.md` | Read; provisional targets source |
| `.cursor/plans/hybrid-graph-rag/01-phase-foundation.md` | Read; Packet 1 contract |
| Plan review record | Historical amendment context; not treated as client approval |

### Files changed (allowed outputs only)

| File | Action |
| --- | --- |
| `docs/QUALITY_TARGETS.md` | Created then accepted — all provisional targets with IDs |
| `docs/adr/ADR-hybrid-pilot-release-cut.md` | Created then accepted — dated checkpoints |
| `docs/development/RISK_REGISTER.md` | Created — Phase 1 risks and assumption log |
| `docs/architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md` | Created then accepted |
| `docs/development/phase-01-foundation-evidence.md` | Created/updated — this file |
| `.cursor/plans/hybrid-graph-rag/01-phase-foundation.md` | Packet 1 checkbox marked `[x]` after sign-off evidence |

### Commands and exit codes

Documentation-only packet. No install, test, or Compose commands required.

| Command | Exit code | Notes |
| --- | --- | --- |
| Directory create for `docs/adr`, `docs/development`, `docs/architecture` | 0 | Host filesystem |

### Negative / failure checks

- No application code, lockfiles, containers, migrations, CI, or dependency selection introduced (Packet 1 forbidden outputs).
- No fabricated legal approver name; recorded as `user (Cursor chat; no legal name provided)`.
- Normal OpenAI ceilings kept separate from graph reserve formula; formula remains unevaluable until measured rebuild.
- No replacements requested.

### Sign-off record

| Field | Value |
| --- | --- |
| Exact user decision text | `approved` |
| Interpretation | Approve all provisional defaults with no replacements |
| Date | 2026-08-12 |
| Approver | user (Cursor chat; no legal name provided) |

### Pending versus approved fields

| Field | Status |
| --- | --- |
| All QT-* numeric targets | `accepted` 2026-08-12 |
| QT-COST-001/002 normal ceilings | `accepted` |
| QT-COST-003 graph reserve formula | `accepted` as formula (dollar amount still unevaluable until measured rebuild) |
| QT-MEDIA-* v1 media limitation | `accepted` |
| QT-TZ-* UTC / non-authoritative Hijri | `accepted` |
| QT-AVL-* RTO/RPO | `accepted` |
| Availability/isolation triggers document | `accepted` |
| ADR-hybrid-pilot framework + dates | `accepted`; continue-vs-pilot *votes* still due 2026-08-22 and 2026-11-07 |
| Risk register assumptions (BM25 resources, rebuild cost, hardware, governance) | Still unmeasured / unsigned (expected) |

### Unresolved assumptions (non-blocking for Packet 1)

1. Graph maintenance reserve monthly dollar amount cannot be computed until a measured full-rebuild cost exists.
2. BM25 full-envelope resource numbers remain assumptions until Phase 4/9 measurement.
3. Planned link targets not yet authored (Packet 5+): `docs/adr/ADR-embedding-model-dimension.md`, `docs/adr/ADR-vision-captioning.md`.
4. Local hardware sufficiency unverified until Packet 3/6.

### Handoff

- Packet 1 acceptance checks met. Sign-off blocker cleared.
- Next packet: **Packet 2** — uv/pnpm workspace and dependency directions (requires scaffold skill + primary docs verification).
- One-packet-per-run: Packet 2 not started in this run.

### Packet 1 checkbox

**Checked** — evidence and explicit user approval recorded.

## Packet 2 — reproducible uv/pnpm workspace and dependency boundaries

### Requirement (quoted)

> Create the exact uv/pnpm workspace and dependency directions; add one lockfile per ecosystem and one LangGraph project file.

### Concrete acceptance checks

- Exactly one `uv.lock`, one `pnpm-lock.yaml`, and one `langgraph.json`.
- uv/pnpm members, distribution/import pairs, wheel targets, and direct dependencies match Section 3.
- Core has no app import; frontend has no Python workspace imports; positive + intentional-negative boundary tests pass.
- Each Python distribution installs/imports from the locked root workspace.
- Frontend production build succeeds with strict TypeScript; no mock auth/retrieval claim.
- LangGraph config loads both graph IDs via pinned `langgraph-cli.validate_config_file`; no business-execution claim.
- No out-of-scope auth/RLS/retrieval/ingestion/graph/managed infra behavior.

### Inspected paths (before edit)

| Path | Result |
| --- | --- |
| Root apps/packages/lockfiles | Absent (greenfield) |
| Host uv / Node / pnpm | uv 0.11.23, Node 20.20.2, pnpm 9.15.0, Python 3.11.15 |
| Primary docs | uv workspaces; LangGraph CLI config schema; Next.js create-next-app / TS |

### Verified versions (see also TOOL_VERSIONS.md)

| Item | Version / source |
| --- | --- |
| langgraph | 1.2.11 (PyPI) |
| langgraph-cli | 0.4.31 (PyPI) |
| fastapi | 0.141.1 |
| uvicorn | 0.52.1 |
| hatchling | 1.32.0 |
| pydantic | 2.13.4 |
| next | 16.3.0 |
| react / react-dom | 19.2.8 |
| typescript | 5.9.3 |

### Files changed (allowed outputs)

- Root `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.gitignore`, `.python-version`
- `docs/development/TOOL_VERSIONS.md`
- Python members: `apps/agents`, `apps/backend`, `apps/worker`, `packages/core` with Hatchling `src/` layouts
- `apps/agents/langgraph.json`
- `apps/frontend` (`smart-rag-frontend`) App Router scaffold
- `tests/unit`, `tests/contract` including negative boundary fixture test

### Commands and exit codes

| Command | Exit code |
| --- | --- |
| `uv lock --python 3.11` | 0 |
| `uv sync --all-packages --group dev --python 3.11` | 0 |
| `pnpm create next-app@16.3.0 apps/frontend ...` | 0 |
| `pnpm --filter smart-rag-frontend build` | 0 |
| `uv run --python 3.11 pytest tests/unit tests/contract -v` | 0 (14 passed) |
| `langgraph_cli.config.validate_config_file(apps/agents/langgraph.json)` | success (query + ingestion) |
| Lockfile/project counts (`uv.lock` / `pnpm-lock.yaml` / `langgraph.json`) | 1 / 1 / 1 |

### Negative / failure checks

- Intentional core→`smart_rag_api` import fixture fails the boundary scanner (`test_boundary_scanner_fails_on_intentional_negative_fixture`).
- Graph invoke returns `status=unconfigured` with “not implemented” detail (no fake business success).
- Backend `/health/ready` returns `unconfigured`.
- Nested `apps/frontend/.git` from create-next-app removed.

### Unverified / deferred

- Docker images, Compose, ParadeDB digests, Valkey, crawl proxy (Packet 3).
- Ruff/Pyright/CI tiers (Packet 4/5).
- `langgraph dev` interactive Studio session not run (CLI `--help` crashes on this host; config validation API used instead).

### Handoff

- Packet 2 acceptance checks met.
- Next: **Packet 3** — local private-service topology and honest health.

### Packet 2 checkbox

**Checked** — lockfiles, boundaries, frontend build, and LangGraph config validation evidenced.
