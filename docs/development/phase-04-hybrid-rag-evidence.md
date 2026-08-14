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

## Packet 2 — versioned dense, BM25, term, normalization, and authorization

### Quoted requirement

> Implement versioned indexed representations, Arabic normalization parity,
> private ParadeDB BM25 queries, filtered HNSW iterative scans, and populated
> trigram terms.

### Acceptance checks restated

- Data API/direct protocol fixtures return identical authorized IDs and zero
  rows for missing, forged, expired, disabled, revoked, cross-scope,
  stale-snapshot, service-role, and table-owner misuse.
- Filtered HNSW meets fixture candidate recall against an exact authorized
  oracle; HNSW settings are transaction-local; exact fallback cannot exceed
  10,000 authorized rows.
- ParadeDB typed queries return canonical IDs only; injection cannot alter
  fields/operators; Arabic/mixed parity is byte-identical.
- Populated term channel meets exact-code/alias gates; raw citation text is
  unchanged.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `supabase/migrations/20260814130000_hybrid_retrieval_v1.sql` | HNSW/trigram indexes, `GRANT USAGE ON SCHEMA search TO app_api`, security-invoker RPCs |
| `infra/paradedb/migrations/20260814130000_bm25_search_index.sql` | Typed BM25 index (`pdb.unicode_words`, no stemmer) |
| `packages/core/src/smart_rag_core/retrieval/` | Session, dense, term, BM25, recheck, profiles |
| `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` | Frozen Packet 2 tunables |
| `tests/contract/test_hybrid_retrieval.py` | Auth, ANN vs exact, EXPLAIN, BM25, terms, parity |
| `tests/unit/test_hybrid_retrieval_foundations.py` | Caps, typed query constructor, exact-admission |

Live local extensions after `pnpm exec supabase db reset --yes` (exit 0):
`vector` **0.8.0**, `pg_trgm` **1.6**. Indexes:
`document_chunks_embedding_hnsw_idx`, `document_search_terms_term_trgm_idx`,
`search_aliases_alias_trgm_idx`. `app_api` has `USAGE` on `search`.

ParadeDB image remains
`paradedb/paradedb:pg17@sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb`
(`pg_search` 0.25.2 per Phase 2 evidence). Compose API uses `paradedb_reader`;
tests may SELECT as writer login and must not `SET ROLE paradedb_reader` from
that login.

HNSW profiles (fixture-measured, **not** holdout-tuned): `iterative_scan=strict_order`;
`ef_search` 40/80/120; `max_scan_tuples` 8000/16000/20000; `scan_mem_multiplier` 2;
`work_mem` 32MB SET LOCAL; statement timeout 8000 ms.

### Primary documentation sources (2026-08-14)

- pgvector iterative scan: <https://github.com/pgvector/pgvector#iterative-index-scans>
- pgvector HNSW: <https://github.com/pgvector/pgvector#hnsw>
- ParadeDB match/phrase operators: <https://docs.paradedb.com/documentation/full-text/overview>
- psycopg 3 `SET LOCAL`: <https://www.psycopg.org/psycopg3/docs/basic/usage.html>
- PostgreSQL `set_config(..., is_local)`: <https://www.postgresql.org/docs/current/functions-admin.html>

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 2 retrieval + contract tests) | 0 |
| `uv run pyright packages/core/src/smart_rag_core/retrieval` | 0 |
| `uv run pytest tests/unit/test_hybrid_retrieval_foundations.py tests/contract/test_hybrid_retrieval.py -q` | 0 (25 passed) after auth-version, unique seed text, search USAGE, BM25 role, GUC leak fixes |
| `uv run python scripts/ci/check_migrations.py` | 0 (35 reviewed files) |
| `pnpm exec supabase db reset --yes` | 0; applied `20260814130000_hybrid_retrieval_v1.sql` |
| `npx supabase gen types typescript --local --schema app,public,storage,auth` | 0; UTF-8 write of `packages/core/src/smart_rag_core/generated/database.ts` includes `retrieve_dense_candidates` |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (60 markdown files, 0 lint issues) |

`strict_order` is **not** treated as exact recall. Fixture ANN top-5 IDs matched
the exact authorized oracle (`test_ann_matches_exact_oracle_on_fixture`).
`EXPLAIN` of cosine order with `enable_seqscan=off` uses
`document_chunks_embedding_hnsw_idx`. After `retrieval_transaction(..., HIGH)`,
`hnsw.ef_search` and `current_user` return to the pre-transaction values.

### Negative tests

| Fixture | Result |
| --- | --- |
| Missing / forged / disabled caller | zero rows or `RetrievalSessionError` |
| Stale `authorization_version` | zero rows |
| Cross-scope member vs restricted | restricted chunk absent |
| Soft-deleted / non-current version | absent |
| `service_role` EXECUTE | denied |
| PostgREST/anon Data API RPC | HTTP error / no EXECUTE |
| Exact fallback when authorized count > 10,000 | `weak_evidence`; no seqscan disable |
| BM25 injection / `pdb.parse` | typed constructor rejects; bound parameter cannot change operators |
| Writer DSN `SET ROLE paradedb_reader` | aborted txn; adapter uses reader DSN or SELECT-as-login |
| Cold term channel | `empty_channel` |
| Raw citation vs search form | `raw_text` unchanged; `search.normalize_arabic_v1` matches core hash |

### Deviations

- BM25 scan uses one bounded top-N query (cap 300). Relevance-preserving
  keyset pagination is **not** qualified on `pg_search` 0.25.2.
- HNSW profile numbers are fixture-measured, not development-set calibrated
  (Packet 6). Holdout was not read.
- Managed Supabase has no `pg_search`. Local ParadeDB remains private Compose.

### Rollback

- Drop forward via a later expand/contract migration replacing
  `20260814130000_hybrid_retrieval_v1.sql`. Do not `DROP TYPE` in place.
- ParadeDB index rebuild from
  `infra/paradedb/migrations/20260814130000_bm25_search_index.sql`.
- HNSW rollback values are in
  [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md).

### Packet 3 handoff

Packet 3 may start after this Packet 2 evidence is accepted in-repo (checkbox).
It implements typed query profiling and first-stage attribution. It must not
implement fusion/RRF, rerank, coverage calibration, DuckDB tables, or holdout
tuning. It must not add a second Arabic normalizer or install `pg_search` on
managed Supabase.

## Packet 3 — typed query profiling and first-stage attribution

### Quoted requirement

> Implement typed query profiling including negation, document scope, media
> dependence, and historical-relationship signals; independently score every
> field before attributing misses to retrieval.

### Acceptance checks restated

- Signed provisional gates pass separately on development then qualification:
  language/configuration ≥95%; temporal macro-F1 ≥90%; exact code/date F1 ≥98%;
  entity/alias macro-F1 ≥90%; metadata-filter P/R ≥95%;
  query-type/relationship/table/decomposition macro-F1 ≥90%.
- Negation, document scope, media, historical relationship, and variant
  fidelity are reported separately.
- Every value has confidence/provenance; deterministic contradictions and
  unknown hard fields cannot pass.
- No profile fixture requires a second hidden model/keyword operation.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/query_profile/` | Extract, date parser, profiler, merge, metrics, runner |
| `apps/agents/src/smart_rag_agents/prompts/query_profile_v1.md` | Sole Packet 3 prompt |
| `packages/core/src/smart_rag_core/gateways/model.py` | One structured `query_profile` mock operation |
| `docs/evaluation/QUERY_PROFILE_EVAL.md` | Gates, versions, failure routes |
| `tests/fixtures/evaluation/phase4/fewshots.json` | Empty approved few-shot list |
| `scripts/eval_query_profile.py` | Open-split scorer |

Prompt SHA-256
`01f33dfbb98720b3cb08a89fdd7d8d8be48941e834e15deb53a8e8142ae20693`.
Model version `query-profile-mock-v1`. Date parser `gregorian_v1`. Retrieval
profile ID `hybrid_default_v1`. Live OpenAI profile calls are not configured
(`MOCK_MODEL_MODE=true`).

### Primary documentation sources (2026-08-14)

- Pydantic models: <https://docs.pydantic.dev/latest/concepts/models/>
- QUALITY_TARGETS QT-QP-001–006 in-repo
- Packet 1 sealed corpus `phase4-dataset-v1` / `phase4-labels-synthetic-v1`

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 3 paths) | 0 |
| `uv run pyright` (Packet 3 production/scripts) | 0 |
| `uv run pytest tests/unit/test_query_profile.py -q` | 0 (11 passed) |
| `uv run python scripts/eval_query_profile.py` | 0; development 216 and qualification 77 passed; `model_calls=0` |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (60 markdown files, 0 lint issues) |

Gated scores were 1.0 on both open splits. Historical-relationship F1 is 0.61
development / 0.80 qualification because Packet 1 labels `true` only on even
multi-hop indexes while every multi-hop query shares the same "after the …
handoff" span. That field is reported, not used to fail QT-QP-001–006.

### Negative tests

| Fixture | Result |
| --- | --- |
| Unknown retrieval profile ID | keep `hybrid_default_v1`; `unknown_hard_field` |
| Low-confidence extra filter | soft diagnostic; not a hard predicate |
| Variant that changes a code | `VariantFidelityError` |
| More than three variants | Pydantic `ValueError` |
| Timeout / budget / malformed model | typed fallback; deterministic extract kept |
| Holdout few-shot id | `FewShotManifestError` |
| Prompt-injection JSON profile id | ignored; original query unchanged |
| Second model call (`model_calls=2`) | `second_profile_model_call_forbidden` |
| Runner AST | no `load_cases` / holdout purposes |

### Deviations

- The labeled corpus is covered by deterministic extract; the optional
  structured model call is mock-empty and used only when `force_model` is set.
- Code F1 scores gold codes that appear in the query. Packet 1 index codes
  absent from query text are not extraction misses.
- Historical-relationship F1 is not a signed QT-QP row; even/odd labeling is
  not recoverable from query text.

### Rollback

- Revert `query_profile_v1` via prompt changelog; keep `hybrid_default_v1`.
- Few-shot manifest stays empty until SME approval on open splits only.

### Packet 4 handoff

Packet 4 may start after this Packet 3 evidence is accepted in-repo (checkbox).
It implements bounded parallel channels, weighted RRF (max across variants),
UTC temporal policies, and coverage/refusal signals. It must not rerank,
calibrate on holdout, or implement DuckDB structured tables.

[docs index](../README.md)
