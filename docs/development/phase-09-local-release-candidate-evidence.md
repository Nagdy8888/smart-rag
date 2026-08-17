---
title: Phase 9 local release candidate — packet evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: engineering, reviewers
---

# Phase 9 local release candidate evidence

Canonical packet evidence for Phase 9. Each packet appends its handoff. Do not
check a packet from file presence alone. Phase 9 wrapper remains `pending`.

Related: [LOCAL_RELEASE_CANDIDATE.md](../deployment/LOCAL_RELEASE_CANDIDATE.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·
[QUALITY_COMMANDS.md](./QUALITY_COMMANDS.md) ·
[docs index](../README.md)

## Proceed decision

Phases 1–8 have implementation evidence. Phase 8 wrapper remains `pending`
awaiting user acceptance. The user explicitly ordered Phase 9 implementation
on 2026-08-17. Holdout stays `HoldoutAccess.denied()`.
`SMART_RAG_HOLDOUT_ACCESS` was not set to `true`.

## Packet 1 — Build exact candidate images and seed the approved corpus

Requirement ID: **P09-01**.

### Requirement (quoted)

> Build the exact candidate images and seed only the approved local evaluation
> corpus through all readiness states.

### Concrete acceptance checks

- **P09-01-A:** Digest-bound builds and health pass. Evidence: build/scan/health
  artifacts. Failure: rebuild; changed identity invalidates evidence.
- **P09-01-B:** Migrations reset/reapply and runtime pins match. Evidence:
  migration/version inventory. Failure: stop on drift.
- **P09-01-C:** Only approved disjoint corpus is seeded. Evidence: immutable
  manifest. Failure: reset and reseed.
- **P09-01-D:** Real state transitions cover all required readiness states.
  Evidence: job/state export. Failure: stop on fake or unreachable state.
- **P09-01-E:** Counts/resources map to the signed local envelope without
  managed claims. Evidence: sizing baseline. Failure: use sizing ladder.

```mermaid
flowchart TD
  freeze["Freeze identities"] --> build["Build Dockerfiles"]
  build --> scan["Scan exact images"]
  scan --> seed["Seed open-split corpus"]
  seed --> export["Export readiness events"]
```

### Inspected paths (before edit)

| Path | Result |
| --- | --- |
| `docker-compose.yml` | Candidate identity; ParadeDB/Valkey/crawl-proxy have no host ports |
| `docker-compose.packet8.yml` | Host-pytest overlay; not candidate identity |
| `apps/*/Dockerfile`, `infra/crawl-proxy/Dockerfile`, `infra/parser-sandbox/Dockerfile` | Local-built images, user 10001 |
| `tests/contract/hybrid_ready_driver.py` | Parse→chunk→embed→canonical→BM25; not SQL-stamped |
| `packages/core/.../evaluation/holdout.py` | Default deny |
| `packages/core/.../jobs/graph_mapping_service.py` | Graph Ready via mapping/writer |
| `scripts/dev.ps1`, `scripts/verify-local.ps1`, `scripts/reset.ps1` | Existing lifecycle |

### Files changed (allowed outputs only)

| File | Action |
| --- | --- |
| `packages/core/src/smart_rag_core/release/` | Created — freeze, ports, corpus, readiness, seed, mapping, health |
| `scripts/phase09_candidate.py` | Created — host freeze/build/scan/up/seed |
| `scripts/ci/check_phase09_packet1.py` | Created — zero-collection fail-closed gate |
| `tests/unit/test_phase09_candidate.py` | Created — negative gates always run |
| `tests/contract/test_phase09_candidate.py` | Created — live compose/supabase/artifact contracts |
| `docs/deployment/LOCAL_RELEASE_CANDIDATE.md` | Created |
| `docs/deployment/phase-09/*.json` | Created by freeze/build/seed (no secrets) |
| `docs/development/QUALITY_COMMANDS.md` | Packet 1 commands |
| `docs/development/CONFIGURATION.md` | `SMART_RAG_REQUIRE_PHASE09_CANDIDATE` |
| `docs/development/LOCAL_SETUP.md` | Candidate freeze step |
| `docs/development/CI_TIERS.md` | Local-only gate note |
| `docs/architecture/04-deployment.md` | Reciprocal link |
| `docs/README.md` | Index rows |
| `.cursor/plans/.../09-phase-local-release-candidate.md` | Packet 1 checkbox `[x]` after live Passed |
| `.cursor/plans/.../packets/01-build-exact-candidate-images.md` | `status: complete` after live Passed |

### Identities frozen

Source: `docs/deployment/phase-09/candidate-identity-freeze.json`. No secrets.

| Field | Value |
| --- | --- |
| git | `7438b54abe70a57652f85c90f678d5ad2f58192a` (`git_dirty`: true) |
| `uv.lock` sha256 | `d05ce6ea28378999c7a95118bd482f89399f61ffb20e11b0f70228dc7674cfbc` |
| `pnpm-lock.yaml` sha256 | `ba5c198c44a586dfcd128e19cc2db713d08e255dae2e95165d06e48051f0bcc7` |
| frozen retrieval profile | `hybrid_default_v1` |
| embedding | `text-embedding-3-large` / 1024 |
| prompts | `query_profile_v1`, `rerank_v1`, `answer_v1`, `verifier_v1` |
| BM25 | schema `bm25_v1`, normalization `arabic_norm_v1` |
| LightRAG | `1.5.6` / handoff `lightrag_v1` |
| ParadeDB image digest | `dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb` |
| `pg_search` (at freeze, stack was up) | `0.25.2` |
| migrations | 51 SQL files hashed |
| profile | `APP_ENV=local`, `MOCK_MODEL_MODE=true` |
| proceed decision | Phase 8 wrapper pending; user ordered Phase 9 on 2026-08-17 |

### Candidate images (P09-01-A build)

Built from repository Dockerfiles via `docker-compose.yml` plus profile
`parser-build`. User `10001:10001`. Local `repo_digest` is
`name@sha256:<image_id>` (no registry push). API/worker images bake tiktoken
`cl100k_base` encodings because the worker has no public DNS on Compose
`private`.

| Service | Image | Id |
| --- | --- | --- |
| api | `smart-rag-api` | `sha256:d697ab32a5456e30a93363371811f65b69d8e720528f8877c9b7e4d403368632` |
| worker | `smart-rag-worker` | `sha256:045fae20209c13c897904c978dfb9a450110b6d6649dc49a1757606b40620990` |
| frontend | `smart-rag-frontend` | `sha256:4d15cd9aed7e8d48f640e5044251d39288bd472cc08a0daef8baae50beecd93e` |
| crawl-proxy | `smart-rag-crawl-proxy` | `sha256:a43503851112064514eb15140f724d774c4ecb3e9758e4a25195771b98d5a604` |
| parser-sandbox | `smart-rag-parser-sandbox:local` | `sha256:6798b6a5ee79cf711c3afc8ad4dcf21662af90008cb25d62e8d6ee60c58feeec` |

A later rebuild that changes any Id invalidates this freeze. Later packets
consume these Ids, not git SHA (`git_dirty` was true while Packet 1 completed).

### Classifications

Packet 1 live health, migrations, corpus, readiness, and sizing **Passed**.
Trivy via docker.sock remains **Blocked** (not retried). Gitleaks **Passed**
after allowlisting published local demo JWT / inert test canaries. pip-audit
and pnpm audit **Passed**. Phase 9 wrapper stays `pending`.

| Check | Classification | Notes |
| --- | --- | --- |
| P09-01-A digest/health | Passed | Candidate compose without overlay. API/frontend live. `pg_search` 0.25.2. Valkey AUTH. Private publishers empty. `MOCK_MODEL_MODE=true`. Overlay `false`. |
| P09-01-B migrations | Passed | 51 repository files hashed. Applied `schema_migrations` match; `drift: false`. |
| P09-01-C corpus | Passed | 8 open-split cases, `holdout_opened: false`. One each exact_code, alias, arabic_mixed, latest_as_of, tabular_aggregation, media_limitation, acl_negative (restricted), graph_mapping. |
| P09-01-D readiness | Passed | All required public states observed. Hybrid Ready used `Bm25ProjectionService.process_upsert_job`. Graph Ready used `GraphMappingService.map_after_vendor_success`. No SQL stamps. Restricted LightRAG rejected live. |
| P09-01-E sizing | Passed | 8 versions, 16 chunks, 2 graph-eligible. Docker NCPU 20 / MemTotal 8131035136. No managed claims. Local subset, not QT-CAP envelope. |
| Digest mismatch negative | Passed | `tests/unit/test_phase09_candidate.py` |
| Holdout/unapproved/production negative | Passed | Same |
| Restricted LightRAG negative | Passed | Unit plus live restricted rejection during seed |
| Fake/duplicate readiness negative | Passed | Same |
| Public ParadeDB/Valkey/LightRAG port negative | Passed | Unit, static Compose, and live `compose ps` after overlay removal |
| Identity freeze fields | Passed | `APP_ENV=local`, ParadeDB digest `dca046b8…883bb` |
| Trivy Critical | Blocked | docker.sock Trivy hung Docker Desktop on 2026-08-17. Not retried. Packet 6 re-runs full SBOM/Trivy. |
| Gitleaks | Passed | Pinned image; allowlists cover local demo JWT, LangSmith canary, glossary idempotency keys |
| pip-audit / pnpm audit | Passed | Compact scan summary |
| Managed EC2/Supabase | Not Run | Phase 10 handoff; not claimed |

### Corpus seed counts

Frozen manifest is the labeled 8-row subset. Holdout closed. Production paths
rejected. Seed ran from **host Python** against a temporary Packet 8 ParadeDB
`:54329` overlay because unpublished ParadeDB is unreachable from Windows
localhost and the then-running worker image lacked the `graph_eligible`
insert-order fix. Overlay was removed; candidate health re-proved unpublished
ports. Worker/API were then rebuilt so later worker-exec seed uses the same
code. A first failed seed (deletion constraint) left extra unlabeled versions
in local Supabase; later packets must use `candidate-corpus-manifest.json` ids,
not “all documents”.

| Split / visibility / state | Frozen manifest |
| --- | --- |
| development | 7 cases |
| qualification | 1 (`p4-media_limitation-0002`) |
| company_visible | 7 |
| restricted | 1 (`p4-acl_negative-0003`, graph-ineligible) |
| Hybrid Ready events (BM25 verified) | 8 |
| Graph Ready | 1 (`p4-exact_code-0003`, maps verified) |
| graph_pending left unlabeled | 1 (`p4-graph_mapping-0003`) |
| seeded_document_versions / chunks / graph-eligible | 8 / 16 / 2 |

### Readiness states proven vs not

Required: uploading, uploaded, scanning, parsing, hybrid_ready, graph_pending,
graph_ready, graph_ineligible, deletion_pending, failed.

| State | Live proof |
| --- | --- |
| uploading | `app.reserve_upload_quota` |
| uploaded | `app.finalize_quarantine_upload` |
| scanning | `app.transition_document_version_status` |
| parsing | `app.transition_document_version_status` |
| failed | `app.transition_document_version_status` |
| hybrid_ready | `Bm25ProjectionService.process_upsert_job` (`bm25_verified`) |
| graph_ineligible | `app.finalize_hybrid_ready` |
| graph_pending | `app.finalize_hybrid_ready/enqueue_graph_pending_handoff` |
| graph_ready | `GraphMappingService.map_after_vendor_success` (`maps_verified`) |
| deletion_pending | `app.exclude_version_from_retrieval` on a graph-ineligible version |
| Fake/duplicate Hybrid/Graph Ready | **Rejected in unit tests** |
| Restricted LightRAG index | **Rejected in unit tests and live seed** |

### Artifact paths

| Path | Role |
| --- | --- |
| `docs/deployment/phase-09/candidate-identity-freeze.json` | Identity freeze |
| `docs/deployment/phase-09/candidate-image-manifest.json` | Image Ids above |
| `docs/deployment/phase-09/candidate-scan-summary.json` | Trivy Blocked; Gitleaks/pip-audit/pnpm Passed |
| `docs/deployment/phase-09/candidate-health.json` | All live checks passed; overlay false |
| `docs/deployment/phase-09/candidate-migrations.json` | File inventory; applied versions; drift false |
| `docs/deployment/phase-09/candidate-corpus-manifest.json` | 8 open-split rows |
| `docs/deployment/phase-09/candidate-readiness-export.json` | Required states; `missing_states: []` |
| `docs/deployment/phase-09/candidate-sizing-baseline.json` | Local envelope map; counts 8/16/2 |
| `docs/deployment/phase-09/candidate-seed-counts.json` | Blockers empty |
| `docs/deployment/phase-09/candidate-command-log.json` | Host orchestrator commands and exit codes |
| `.tmp-phase09/` | Gitignored scanner dumps |

Later packets must consume these image Ids and corpus/version ids.

### Failures and repairs

1. Trivy via `docker run -v /var/run/docker.sock aquasec/trivy:latest image`
   hung Docker Desktop (`HTTP 500` on `_ping`). Orchestrator was killed.
2. Host disk filled (`ENOSPC`). Docker updater leftover was deleted from Temp.
3. `vmmemWSL` stayed **StopPending** until Docker recovered. Packet 1 did
   **not** retry docker.sock Trivy.
4. Worker health failed: tiktoken tried to download encodings with no DNS on
   `private`. Repair: prefetch encodings in API/worker Dockerfiles.
5. Worker could not reach host Supabase: `private` is `internal: true`.
   Repair: worker also joins `edge` (still no published ports), matching API.
6. `documents_graph_eligible_requires_company_visible`: `graph_eligible` cannot
   be true before `current_version_id`. Repair: set eligibility after the
   current-version pointer.
7. `document_versions_graph_eligible_requires_open`: deletion cannot keep
   `graph_eligible`. Repair: drive `deletion_pending` on a graph-ineligible
   version.
8. Worker rootfs is read-only; host code was not `docker cp`'d in. Repair:
   rebuild API/worker after the seed-path fixes.
9. Gitleaks reported 4 fixture findings (local demo JWT, leak canary,
   glossary idempotency keys). Repair: path-scoped `.gitleaks.toml` allowlists.
   Compact scan now fails closed on Gitleaks/pip-audit/pnpm `failed`.

### Managed blockers / Phase 10 handoff

- No AWS, Vercel, KMS, CloudFront, WAF, or managed Supabase provisioned.
- Packet 1 does not prove instance-equivalent sizing or restore drills
  (Packets 4 and 6).
- Canonical evidence remains local Supabase; ParadeDB is derived.
- Full SBOM/Trivy remains Packet 6.

### Commands and exit codes

| Command | Exit code | Notes |
| --- | --- | --- |
| `uv run python scripts/phase09_candidate.py ports-static` | 0 | Candidate Compose has no private host ports |
| `uv run python scripts/phase09_candidate.py freeze` | 0 | Identity freeze written; `git_dirty` true |
| `uv run python scripts/phase09_candidate.py supabase` | 0 | Local CLI stack |
| `docker compose -f docker-compose.yml build api worker` | 0 | Tiktoken bake + seed-path core |
| `uv run python scripts/phase09_candidate.py up` | 0 | `--no-build --force-recreate --remove-orphans`; no overlay |
| `uv run python scripts/phase09_candidate.py health` | 0 | Private ports unpublished |
| `uv run python scripts/phase09_candidate.py migrations` | 0 | drift false |
| Host `smart_rag_core.release.cli seed` (overlay then removed) | 0 | 8 labeled cases; all required states |
| `uv run python scripts/phase09_candidate.py sizing` | 0 | Counts 8/16/2; NCPU 20 |
| `uv run python scripts/phase09_candidate.py scan` | 0 | Trivy Blocked (not retried); Gitleaks/pip/pnpm Passed |
| `uv run python -m pytest tests/unit/test_phase09_candidate.py tests/contract/test_phase09_candidate.py -q` | 0 | 24 passed, 0 skipped |
| `uv run python scripts/ci/check_phase09_packet1.py` | 0 | tests=24 failures=0 errors=0 skipped=0 |

Packet file `status` is `complete`. Phase 9 wrapper `status` remains
`pending`. Holdout was not opened (`HoldoutAccess.denied()`).
