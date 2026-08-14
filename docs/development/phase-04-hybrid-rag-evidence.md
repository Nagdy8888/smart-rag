---
title: Phase 4 hybrid RAG evidence
owner: engineering-lead
status: pending
last-reviewed: 2026-08-14
audience: engineering, reviewers
phase: 4
---

# Phase 4 — Hybrid RAG evidence

Canonical packet evidence and exit record for
[Phase 4](../../.cursor/plans/hybrid-graph-rag/04-phase-hybrid-rag.md).
Packet 1 creates this file; later packets append. Phase status remains
`pending` until Packet 8 and explicit user acceptance.

Related: [DATASET_SPEC.md](../evaluation/DATASET_SPEC.md) ·
[QUERY_PROFILE_LABELING.md](../evaluation/QUERY_PROFILE_LABELING.md) ·
[GLOSSARY_IMPORT.md](../api/GLOSSARY_IMPORT.md) ·
[docs index](../README.md)

## Prerequisites

| Prerequisite | Evidence |
| --- | --- |
| Phase 1 complete/accepted | [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) status `accepted` |
| Phase 2 complete/accepted | [phase-02-identity-data-evidence.md](./phase-02-identity-data-evidence.md) status `accepted` |
| Phase 3 complete/accepted | [phase-03-ingestion-evidence.md](./phase-03-ingestion-evidence.md) status `accepted` |
| User mandate | Implement Phase 4 (Cursor chat 2026-08-14) |
| SME 12–20 hours | **unverified**; corpus is `synthetic_provisional` |
| Phase 2 embedding slice | `tests/fixtures/embedding_qualification/slice_v1.json` (immutable) |

## Packet 1 — frozen datasets and private glossary seed

### Quoted requirement

> Freeze disjoint development/qualification/holdout datasets and import the
> private approved glossary, identifiers, acronyms, and aliases.

### Acceptance checks restated

- The full labeled corpus meets every minimum class count; split manifests are
  pairwise disjoint by case and source family; the embedding slice is disjoint.
- Every case has ACL actor, canonical source/evidence or explicit
  no-evidence/refusal truth, complete expected profile fields, and adjudication
  status.
- Tuning tooling cannot read the holdout by default; any authorized final
  access is auditable and version-pinned.
- Glossary import is owner/admin-only, rejects cycles/conflicts/duplicates/
  cross-scope aliases, records source/version/approval, and populates term
  fixtures.

### Negative tests restated

Duplicate/source-family leakage, missing actor/evidence/profile label,
malformed class, unapproved glossary row, alias cycle, identifier collision,
private-value trace/log, or holdout access from calibration code fails.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/evaluation/` | Schema, class matrix, generator, splits, holdout, calibration, seal |
| `packages/core/src/smart_rag_core/glossary/` | Validation and owner/admin RPC client |
| `packages/core/src/smart_rag_core/settings/evaluation.py` | `SMART_RAG_HOLDOUT_*` gates |
| `supabase/migrations/20260814120000_glossary_import_v1.sql` | Tables, RLS, import/approve/rollback RPCs |
| `apps/backend/src/smart_rag_api/routers/glossary.py` | Owner/admin HTTP surface |
| `tests/fixtures/evaluation/phase4/` | Manifests, identifier rules, term-coverage hashes |
| `tests/fixtures/embedding_qualification/slice_v1.json` | Phase 2 disjointness baseline |
| `scripts/seal_phase4_dataset.py` / `scripts/validate_phase4_dataset.py` | Seal and hash verify |

### Primary documentation sources (2026-08-14)

- Pydantic Settings: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- FastAPI routing: <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- psycopg 3 execute: <https://www.psycopg.org/psycopg3/docs/basic/from_pg2.html>
- Supabase RLS: <https://supabase.com/docs/guides/database/postgres/row-level-security>

### Frozen corpus

| Field | Value |
| --- | --- |
| Cases | 405 |
| Schema | `phase4-dataset-v1` |
| Label revision | `phase4-labels-synthetic-v1` |
| Schema hash | `996fb7553dcffa1805020444b2c4e22eebf05d6a9909882468a2cc7b80d151c9` |
| Development (216) | `9dcbe2c564d33a38fba096253d60d2c8172fb9dd6c76bf95627446c857f89264` |
| Qualification (77) | `716ea031255217a82fa8ce2a1d7f89dbf17e841a99e7b1f4dc4de3a51d42cc14` |
| Holdout (112) | `7c70b4267efbd9df46247c099333ef7e82ed4ccc6df906727d8997e7bcacada2` |
| SME posture | `synthetic_provisional`; named Knowledge Owner hours unverified |
| LangSmith dataset | **not uploaded**; governance still prohibits unverified real-content processors. Local fixtures are the sealed source |

Identifier prefixes `INV-SR-*`, `SKU-P4-*`, `PRJ-*`, and `p4-*` are disjoint from
the Phase 2 slice (`PO-7781`, `TKT-4412`, `SKU-90B`, `ar-01`, `q-ar-sem-01`).
Holdout manifests store ordered ids and content hashes only.

`smart_rag_core.evaluation.calibration.load_tuning_cases` loads open splits
only and does not call `load_cases` or allow-listed holdout purposes.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 1 paths) | 0 |
| `uv run pyright` (Packet 1 production/scripts) | 0 |
| `uv run pytest tests/unit/test_phase4_dataset.py tests/unit/test_glossary_validation.py tests/unit/test_glossary_openapi.py -q` | 0 (20 passed) |
| `uv run python scripts/validate_phase4_dataset.py` | 0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (34 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 0 after additive allowlist + snapshot refresh |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |
| `uv run pytest tests/contract/test_glossary_import.py -q` | 0 (4 passed after local `db reset`) |
| `npx supabase gen types typescript --local --schema app,public,storage,auth` | 0; wrote `packages/core/src/smart_rag_core/generated/database.ts` |

Pyright on `tests/unit/test_glossary_openapi.py` matches the existing FastAPI
`TestClient` unknown-type pattern in Phase 3 OpenAPI tests. Production Packet 1
modules typecheck clean.

### Negative tests

| Fixture | Result |
| --- | --- |
| Family leakage across splits | `DatasetValidationError` / `family_leakage` |
| Missing evidence and refusal | Pydantic `ValueError` |
| Malformed query class | Pydantic `ValueError` |
| Holdout without token | `HoldoutSealedError` |
| Calibration AST | no `load_cases` / holdout purposes |
| Member glossary import HTTP | HTTP 403 `forbidden` |
| Member glossary import RPC | `GlossaryImportRejectedError` / `forbidden` |
| Alias cycle / conflict / duplicate / cross-scope | `GlossaryValidationError` reason codes |
| SQL alias cycle | Postgres `alias_cycle` |
| High-collision `\d{1,3}` | rejected |
| Redaction | reason codes contain no private alias text |

### Deviations

- Corpus is synthetic and provisionally sealed so Hybrid packets can proceed.
  Packet 8 launch claims still require a named SME holdout seal.
- `docs/api/openapi.foundation.json` now includes additive Phase 3 ingestion
  and Phase 4 glossary paths. Compatibility remains additive per
  [ADR-api-sse-compatibility.md](../adr/ADR-api-sse-compatibility.md).

### Rollback

- Drop forward migration `20260814120000_glossary_import_v1.sql` via a later
  expand/contract migration if the RPC contract must change; do not `DROP TYPE`
  in place.
- Dataset fixtures regenerate from `generate_corpus()`; hashes must match
  `scripts/validate_phase4_dataset.py`.
- Holdout stays denied unless `SMART_RAG_HOLDOUT_ACCESS` plus allow-listed
  purpose and actor are set.

### Packet 2 handoff

Packet 2 may start after this Packet 1 evidence is accepted in-repo (checkbox).
It must create `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` and implement
versioned dense/BM25/term retrieval. It must not read holdout labels, must not
install `pg_search` on managed Supabase, and must not treat this synthetic
corpus as a named-SME launch seal.

[docs index](../README.md)
