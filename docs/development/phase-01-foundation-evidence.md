---
title: Phase 1 foundation — packet evidence
owner: engineering-lead
status: accepted
last-reviewed: 2026-08-13
audience: engineering, reviewers
---

# Phase 1 foundation evidence

Canonical packet evidence for Phase 1. Each packet appends its handoff. Do not check a packet from file presence alone.

Cross-phase review: [2026-08-16 Phases 1–5 implementation review](../reviews/2026-08-16-phases-01-05-implementation-review.md) · [close-out](../reviews/2026-08-16-phases-01-05-closeout.md).

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

## Packet 3 — local private-service topology and honest health

### Requirement (quoted)

> Create local Docker/WSL2 helpers, a digest-pinned private ParadeDB/`pg_search` service, split private Valkey services, the crawl-proxy boundary, mock-model mode, and health checks.

### Digests resolved (Docker Hub API 2026-08-12)

| Image | Digest |
| --- | --- |
| paradedb/paradedb:pg17 | sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb |
| valkey/valkey:8.1-alpine | sha256:a038175878d66b9d274fbf8be73c0305e93798b83917647f167e18cef3c71eec |
| python:3.11-slim-bookworm | sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 |
| node:20-bookworm-slim | sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 |

### Commands

| Command | Exit |
| --- | --- |
| `docker compose --env-file .env.example config --quiet` | 0 |
| `pytest` including `test_compose_topology.py` | 0 (21+ tests in suite slice) |

### ADRs

- `ADR-paradedb-edition-availability` accepted (Community `pg17` digest-pinned)
- `ADR-private-service-tls` accepted (TLS omitted locally with compensating controls; staging revisit)

### Unverified

- Full `docker compose up` image builds / runtime health (host `.env` was incompatible with Compose KEY=VALUE format; use `.env.example` schema).
- Supabase CLI not installed on host — scripts skip with message.
- Live ParadeDB `pg_search` extension probe inside running container.

### Packet 3 checkbox

**Checked** for authored topology + contract tests + digest pins. Runtime stack bring-up remains Packet 6 proof.

## Packet 4 — settings, observability, and hard-failing quality gates

### Requirement (quoted)

> Add typed settings, structured logging, non-root images, import-boundary checks, docstring enforcement, and hard-failing quality commands.

### Acceptance evidence

- Pydantic Settings 2.15.0 resolved with Pydantic 2.13.4; backend, worker, and agent settings load only at explicit startup boundaries. Every variable/default/security classification is documented in [CONFIGURATION.md](./CONFIGURATION.md).
- JSON logs include UTC timestamp, level, service, environment, event, and bound request/run/job IDs. Messages are bounded and credentials/exceptions are redacted.
- Mock model output is deterministic, bounded, marked `fixture://smart-rag/mock-model/phase-1-foundation-v1`, states that no retrieval occurred, and runs under an `api.openai.com` DNS guard.
- Ruff 0.16.2, Pyright 1.1.411 strict, pytest 9.1.1, pre-commit 4.6.2, Vitest 4.1.10, Playwright 1.62.1, markdownlint-cli2 0.23.2, and Mermaid CLI 11.16.0 are pinned.
- `scripts/check.py` exposes `format`, `lint`, `types`, `unit`, `contract`, `docs`, `frontend`, and `fast`; every child is shell-free, stops on failure, and returns the child exit code.
- Existing non-root Docker users remain `10001:10001`; Compose rendering and topology contracts pass.

### Files and configuration changed

- Core: `settings/{base,backend,worker,agents}.py`, `observability/logging.py`, and `gateways/model.py` plus package exports.
- Backend: lifespan settings/logging/mock guard, correlation middleware, typed bind settings, and honest unchanged readiness.
- Quality: root Python tool config, pre-commit, `scripts/check.py`, docs checker, Markdown config, frontend Vitest/Playwright config, one honest capability test, and root scripts.
- Tests: settings, logging, gateway/network denial, middleware/import safety, AST docstrings, environment centralization, duplicate artifacts, and zero-test exit preservation.
- Locks/docs: `uv.lock`, `pnpm-lock.yaml`, `.env.example`, tool versions, configuration contract, and this evidence record.

### Commands and exit codes

| Command | Exit | Result |
| --- | --- | --- |
| `uv lock --python 3.11` | 0 | 68 packages resolved |
| `uv sync --all-packages --group dev --python 3.11` | 0 | four workspace packages installed |
| `uv run python scripts/check.py --tier unit` | 0 | 16 passed; empty-selection proof separately returns 5 |
| `uv run python scripts/check.py --tier contract` | 0 | 22 passed |
| `uv run ruff check .` | 0 | all checks passed |
| `uv run ruff format --check .` | 0 | 61 files formatted (via `fast`) |
| `uv run pyright` | 0 | 0 errors/warnings |
| `uv run python scripts/check.py --tier docs` | 0 | 10 Markdown files; links and Mermaid render pass |
| `uv run python scripts/check.py --tier frontend` | 0 | ESLint, TypeScript, 1 Vitest, build, Playwright contract |
| `uv run python scripts/check.py --tier fast` | 0 | all required Packet 4 tiers passed |
| `pnpm install --frozen-lockfile` | 0 | both Node workspace projects locked |
| `docker compose --env-file .env.example config --quiet` | 0 | configuration remains valid |
| Plan integrity `--update`, then verify | 0 / 0 | 82 canonical files locked and verified |

Initial focused gates returned 1 for Ruff, Pyright, unit, and contract while they exposed import ordering, upstream generic typing, two test assumptions, and four missing fixture-method docstrings. Those Phase-1-owned defects were repaired; no lint/type/test suppression was added except narrow Pyright annotations for LangGraph's typed state wrapper where optional upstream hooks expose `Any`.

### Negative and failure proof

- The intentional `.py.fixture` produces exactly one missing-function-docstring finding; every authored `.py` passes.
- A temporary second `uv.lock` produces one artifact-count violation; the repository count is one for each lockfile and `langgraph.json`.
- An empty temporary unit directory returns pytest/check-runner exit code 5.
- Redaction tests prove fake API key/password/bearer/DSN values and private exception source are absent.
- Socket monkeypatches prove fixture generation performs no resolution; the lifecycle guard raises `MockModelNetworkDeniedError` for `api.openai.com`.
- Fresh subprocess imports succeed with trap OpenAI constructors and denied DNS/connection functions.

### Exclusions, unresolved work, and handoff

AST exclusions are caches/build output, `prev_review/`, and explicit vendor paths; the negative fixture uses the non-source `.py.fixture` suffix. Docs allow only the two Packet-5-planned ADR links already named by Packet 1. Real OpenAI, auth/RLS, retrieval, ingestion, LightRAG, and BM25 behavior remain unimplemented. Full container startup/runtime health and the live ParadeDB extension probe remain Packet 6 evidence.

**Packet 4 checked** — all Packet 4 gates pass; proceed only to Packet 5 in a fresh run.

## Packet 5 — CI tiers and documentation foundation

### Requirement

Create tiered CI and documentation index, C4 skeleton, ADRs, governance drafts, migration/API policies, admin-alert contract.

### Commands

| Command | Exit |
| --- | --- |
| verify_plan_integrity.py | 0 (82 files) |
| check_migrations.py | 0 |
| check_openapi.py | 0 (snapshot committed) |
| check.py --tier fast | 0 (Packet 4 baseline) |

### Notes

- Governance docs remain `draft` (unsigned).
- Remote GitHub Actions execution unverified until first workflow run on GitHub.
- `.cursor/plans|rules|skills` committed for CI; other `.cursor/*` still ignored.

### Packet 5 checkbox

**Checked** for authored docs/CI. Remote CI run pending.

## Packet 6 — one-command startup and Phase 1 exit proof

### Local stack (2026-08-12)

`docker compose --env-file .env.compose up --build -d` after ParadeDB init fix (`CREATE EXTENSION vector` before `pg_search`).

| Service | Status |
| --- | --- |
| api | healthy (host 8000) |
| frontend | healthy (host 3000) |
| worker | healthy (no host port; idle loop) |
| paradedb | healthy, `pg_search`+`vector` |
| valkey-limits / valkey-cache | healthy, no host ports |
| crawl-proxy | healthy, deny-by-default |

### Commands

| Command | Result |
| --- | --- |
| `scripts/verify-local.ps1` | pass (live/ready/frontend/pg_search/deny/non-root/private ports) |
| Supabase CLI | not installed — skipped (documented) |
| Full `check.py --tier fast` | interrupted once on long frontend rebuild; unit/contract+ruff re-run separately |

### Deviations / unverified

- Host `.env` was not Compose-compatible; use `.env.compose` from `.env.example`.
- Remote GitHub Actions not yet observed green on this push.
- Phase 1 `status: complete` still requires **explicit user acceptance** of this exit record before Phase 2 formal start (user mandated continue-through-Phase-5; proceeding with that override noted here).

### Packet 6 checkbox

**Checked** with local verification evidence. Awaiting user acceptance to mark phase complete.

## Phase 1 exit acceptance

| Field | Value |
| --- | --- |
| Exact user decision | `accept` |
| Date | 2026-08-12 |
| Approver | user (Cursor chat; no legal name provided) |
| Interpretation | Accept Phase 1 foundation exit record; Phase 2 may start |
| Phase status | `complete` |

## Packet 6 audit-clean re-verification — 2026-08-13

### Requirement

> Prove one-command local startup and all Phase 1 fast gates, then record
> evidence before Phase 2 starts.

This re-verification repairs stale Phase 1 evidence without changing the
accepted phase scope or the canonical plan.

### Files and behavior repaired

- `dev.ps1`, `stop.ps1`, `reset.ps1`, and `verify-local.ps1` now use the same
  `.env.compose` then `.env` precedence and the workspace-pinned Supabase CLI.
  Startup suppresses CLI credential output, stop preserves data, and reset
  returns exit code 2 unless `-ConfirmReset` is explicit.
- Runtime verification now fails on a missing private service and proves both
  authenticated Valkey policies, unauthenticated denial, ParadeDB `pg_search`,
  crawl-proxy denial, private ports, non-root application users, and the
  mock-model runtime profile.
- PR CI now runs SHA-pinned Gitleaks v3 with scanner 8.30.1, strict pip-audit,
  and pnpm audit. Checkout uses the current Node 24 action runtime pin in all
  workflows. Narrow `.gitleaks.toml` rules allow only canonical plan prose and
  generated SHA-256 manifest lines that were demonstrated as false positives.
- The initial dependency scan found vulnerable `PyJWT 2.10.1`; the direct pin
  is now `2.13.0`. PyJWT exception handling remains fail closed.
- Strict typing, centralized environment settings, documentation lint scope,
  and the worker one-shot smoke contract were repaired without ignores,
  disabled gates, or changes to authorization behavior.

### Passed

| Command or proof | Exit | Result |
| --- | ---: | --- |
| `.\scripts\dev.ps1` | 0 | Pinned Supabase CLI plus all Compose services started; no AWS or OpenAI credential required |
| `.\scripts\verify-local.ps1` before and after restart | 0 / 0 | All Phase 1 runtime, private-network, policy, denial, extension, UID, and mock-profile assertions passed |
| Set and save `phase1:volume-proof`, `.\scripts\stop.ps1`, restart, then `GET` | 0 | Returned `preserved`; stop/restart retained the Valkey volume |
| `uv run python scripts/check.py --tier fast` | 0 | 18 unit passed; 100 contract passed; maintained docs, frontend lint/types/Vitest/build, and Playwright version passed |
| `uv run pyright` | 0 | 0 errors, 0 warnings |
| Split-plan integrity verifier | 0 | 82 canonical files verified |
| `scripts/ci/check_migrations.py` | 0 | 17 reviewed migrations passed policy |
| `scripts/ci/check_openapi.py` | 0 | Foundation OpenAPI snapshot matched |
| `docker compose --env-file .env.compose config --quiet` | 0 | Compose rendered successfully |
| Frozen uv and pnpm installs | 0 / 0 | 95 Python packages checked; Node lockfile current |
| `pip-audit --strict` over frozen uv export | 0 | No known vulnerabilities |
| `pnpm audit --audit-level high` | 0 | No known vulnerabilities |
| Gitleaks 8.30.1 pinned image over repository history | 0 | 19 commits and about 2.09 MB scanned; no leaks |
| `.\scripts\reset.ps1` without confirmation | 2 | Destructive reset refused before any data removal |
| Intentional missing-docstring fixture through the scanner | 1 expected | One violation detected; clean tree remained enabled |

The six contract skips are not Phase 1 gates: four require an explicitly paid
OpenAI embedding run, one requires a managed Supabase access token for signing
key rollover, and one requires a managed database URL. Their existing Phase 2
evidence and ownership remain unchanged.

### Failed and repaired during this run

- The first strict audit found 12 PyJWT advisories for one vulnerable pin.
  Upgrading to 2.13.0 removed all findings.
- The first fast attempt exposed 105 strict-type errors. Precise JSON
  narrowing, typed fixtures, row assertions, and the supported PyJWT exception
  contract reduced the result to zero without weakening Pyright.
- A later unit run hung because the worker smoke test called its intentionally
  long-running process without `WORKER_ONCE`. The flag is now typed in
  `WorkerSettings`; the complete unit suite finishes normally.
- The environment boundary rejected direct reads in the worker and rollover
  script. Both now load through `smart_rag_core.settings`.
- Markdown lint initially included preserved historical reviews and generated
  Stitch source exports. Those non-maintained inputs are explicitly excluded;
  all 48 maintained documents pass lint, links, and Mermaid rendering.
- Gitleaks initially reported eight plan prose/hash false positives. No broad
  path exclusion was added; exact path-and-line allowlists were verified
  against a second full-history scan.
- The first updated PR-fast run exposed a clean-checkout ordering defect:
  standalone TypeScript ran before Next.js generated global `LayoutProps`.
  The frontend tier now runs `next typegen` first; the same tier passed locally
  and in remote CI without relying on a stale `.next` directory.

### Remote CI

- [Main run 31692522152](https://github.com/Nagdy8888/smart-rag/actions/runs/31692522152)
  passed on commit `2f4f3ec9624adfd010d1954fb3a8668eb2ec95ca`.
- [PR fast run 31692522176](https://github.com/Nagdy8888/smart-rag/actions/runs/31692522176)
  passed on the same commit, including secret scanning, frozen installs,
  dependency audits, plan integrity, fast quality, OpenAPI drift, and migration
  policy.

### Blocked

- None for Phase 1.

### Not run

- The confirmed destructive reset was not run against the current Phase 2
  local database. Packet 2's deterministic double-reset proof owns that
  disposable reset and schema comparison. The required fail-closed confirmation
  route is proven above.

### Final Phase 1–2 closeout revalidation — 2026-08-13

- **Passed:** the uninterrupted fast tier passed again with 32 unit tests,
  118 contract tests, maintained-document lint/link/Mermaid checks, strict
  frontend lint/types/Vitest/build, and Playwright discovery. Compose startup
  and `verify-local.ps1` passed all public-health, private-network, Valkey,
  ParadeDB, crawl-denial, non-root, and mock-model assertions.
- **Passed:** frozen Python and Node dependency audits reported no known
  vulnerabilities; the SHA-pinned Gitleaks 8.30.1 image scanned 22 commits and
  about 2.17 MB with no leaks. Plan integrity, migration policy, and OpenAPI
  snapshot checks passed.
- **Failed:** none remain. The first closeout health probe correctly failed
  while the developer-facing Compose services were stopped; `dev.ps1` started
  the documented stack and both subsequent health proofs passed.
- **Blocked:** none for Phase 1.
- **Not run:** no new destructive Phase 1 negative fixture was introduced.
  Phase 2's dedicated gate owns the final clean-reset and mandatory integration
  proofs; paid embedding and managed signing-key mutations were intentionally
  not repeated.

### Handoff and rollback

Phase 1 remains accepted and is audit-clean locally and in remote CI. Dependency
rollback would reintroduce known PyJWT advisories and is prohibited;
script/workflow rollback is ordinary source reversion after preserving this
evidence. Phase 2 Packet 2 owns the next destructive proof, requiring two
confirmed disposable resets.
