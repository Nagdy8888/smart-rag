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
[COVERAGE_CALIBRATION.md](../evaluation/COVERAGE_CALIBRATION.md) ·
[COVERAGE_QUALIFICATION.md](../evaluation/COVERAGE_QUALIFICATION.md) ·
[PHASE4_FREEZE.md](../evaluation/PHASE4_FREEZE.md) ·
[PHASE4_ABLATIONS.md](../evaluation/PHASE4_ABLATIONS.md) ·
[PHASE4_HOLDOUT.md](../evaluation/PHASE4_HOLDOUT.md) ·
[HYBRID_TUNING.md](../retrieval/HYBRID_TUNING.md) ·
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

## Packet 4 — bounded channels, RRF, temporal policy, coverage

### Quoted requirement

> Implement bounded parallel channels and query variants, normalized weighted
> RRF, UTC-anchored temporal policies, whole-document coverage/refusal, and
> conflict behavior.

### Acceptance checks restated

- Caps hold across all variants: 100 dense, 75 authorized BM25, 30 term, 205
  unique pre-fusion IDs. BM25 scanning never exceeds 300 IDs / one top-N query
  (Packet 2: keyset not qualified).
- Zero unauthorized/stale/deleted/wrong-current IDs from this seed reach fusion.
  BM25 IDs are rechecked through Supabase before fusion.
- RRF is invariant to variant order/duplicates and uses max-not-sum; metadata
  product is clamped to `[1.0, 1.15]`; `rrf_k=60`.
- UTC temporal policies `latest`, `current`, `recent`, `as_of`, none; unknown
  dates cannot win `latest`; naive/Hijri timestamps are rejected.
- Conflict, whole-document uncovered headings, unscoped negation, and media
  limitation emit signed routes. BM25 kill/version/timeout degrades visibly to
  dense+term with `bm25_unavailable`.
- Cache keys include principal/ACL-scope hash, profile/index/normalizer
  versions, and visibility generation; payloads are IDs/ranks only and must be
  rechecked before evidence. No Valkey store in this packet.

### Negative tests restated

Client limit override, unqualified relevance cursor, score mixing,
sum-across-variants, stale cache key reuse across visibility generation,
forged actor (Packet 2 RPCs), unauthorized BM25 ID, unknown date winning
`latest`, full-summary claim with uncovered headings, or silent BM25 outage
fails.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/retrieval/fusion.py` | Max-across-variant RRF, weighted sum, 205 cap, metadata clamp |
| `packages/core/src/smart_rag_core/retrieval/temporal.py` | UTC `latest`/`current`/`recent`/`as_of` |
| `packages/core/src/smart_rag_core/retrieval/coverage.py` | Summary, media, negation, conflict signals |
| `packages/core/src/smart_rag_core/retrieval/hybrid.py` | Assemble + parallel deadline |
| `packages/core/src/smart_rag_core/retrieval/cache_key.py` | Versioned SHA-256 key; ID-only payload |
| `packages/core/src/smart_rag_core/retrieval/profiles.py` | Frozen Packet 4 constants |
| `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` | Packet 4 tunables |
| `tests/unit/test_hybrid_fusion.py` | RRF/temporal/coverage/deadline |
| `tests/contract/test_hybrid_fusion.py` | Live dense+term fusion; ParadeDB recheck |

Frozen Packet 4 values: `RRF_K=60`, channel weights `1.0`, `PREFUSION_UNION_CAP=205`,
metadata clamp `[1.0, 1.15]`, `RECENT_WINDOW_DAYS=90` (provisional),
`HYBRID_DEADLINE_SECONDS=25`. BM25 scan remains one top-300 query.

### Primary documentation sources (2026-08-14)

- Reciprocal rank fusion (`k=60` plan-fixed):
  [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- UTC temporal policy QT-TZ-001: [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- concurrent.futures wait/timeout:
  <https://docs.python.org/3/library/concurrent.futures.html>

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 4 retrieval + fusion tests) | 0 |
| `uv run pyright packages/core/src/smart_rag_core/retrieval` | 0 |
| `uv run pytest tests/unit/test_hybrid_fusion.py tests/contract/test_hybrid_fusion.py -q` | 0 (16 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (60 markdown files, 0 lint issues) |

Holdout manifests were not read. No rerank, DuckDB, or LightRAG code was added.

### Negative tests

| Fixture | Result |
| --- | --- |
| `rrf_k=59` | `FusionError` |
| Duplicate/reversed variants | identical fused ID order; max credit once |
| Dense 120 × 3 variants | unique fused IDs ≤ 205 |
| Metadata factor 9.0 | clamped to 1.15 |
| Fourth variant | `more_than_three_variants` |
| Unknown `effective_at` vs dated | dated wins `latest` |
| Naive datetime | `naive_datetime_forbidden` |
| `as_of` before effective day | empty |
| Expired version + `current` | dropped |
| Uncovered heading + full summary | `scoped_summary` |
| BM25 unavailable | `BM25_DEGRADED` + `bm25_unavailable` |
| Media dependence | `MEDIA_LIMITATION` |
| `set_complement` negation | `NEGATION_UNSCOPED` |
| Two contradictory IDs | `CONFLICT` |
| Historical with one unit | `WEAK_EVIDENCE` |
| Unknown retrieval profile in cache key | `unknown_retrieval_profile` |
| Deadline 0 | channels not started; `deadline_exhausted` |
| Restricted/stale/deleted seed IDs | absent from fused live results |
| ParadeDB restricted projection row | dropped by recheck before fusion |

### Deviations

- Channel weights are equal `1.0` until Packet 6 measures development then
  qualification. The 90-day `recent` window is the same class of provisional
  value.
- Coverage emits signed signals; numeric supported/refusal thresholds are
  Packet 6.
- Cache is a versioned key plus ID-only payload interface. Valkey TTL is not
  implemented.
- Live contract dense results may include leftover company-visible chunks from
  earlier seeds; assertions require this seed's restricted/stale/deleted IDs
  to be absent and expected seed hits to be present.
- Recheck RPC caps survivors at 75, so dense's 100 IDs are not re-passed
  through that RPC; dense/term authorization remains the security-invoker
  retrieve RPCs from Packet 2.

### Rollback

- Revert Packet 4 Python modules; Packet 2 RPCs/indexes stay.
- Restore `HYBRID_RETRIEVAL_CONTRACT.md` Packet 4 rows to "not applied".
- Keep `rrf_k=60` and caps if a later packet retunes weights only.

### Packet 5 handoff

Packet 5 may start after this Packet 4 evidence is accepted in-repo (checkbox).
It implements the accuracy-first top-20 OpenAI reranker, deterministic RRF
fallback, skipped-case counterfactuals, MMR, quotas, and parent expansion.
It must not calibrate coverage thresholds on holdout, implement DuckDB
structured tables, or add a local rerank model.

## Packet 5 — accuracy-first rerank, fallback, MMR, parent expansion

### Quoted requirement

> Implement the accuracy-first top-20 OpenAI reranker contract, deterministic
> fallback, skipped-case counterfactuals, MMR, quotas, and parent expansion.

### Acceptance checks restated

- Strict schema plus application set-equality rejects unknown, duplicate,
  missing, extra, and malformed IDs; fallback preserves deterministic
  authorized RRF order.
- All non-trivial eligible cases rerank; every development/qualification skip
  has counterfactual evidence before trigger tightening.
- MMR/quotas improve duplicate/source diversity without violating citation
  gates; parent expansion stays authorized/current and inside 12 units / 3500
  tokens.
- Repository dependency scan proves no local rerank model/runtime.
- One Responses operation, `max_retries=0`, no tools; support is a ranking
  feature, not a probability.
- Skip only trivial exact identifier/quoted-phrase with complete terms/filters
  and two independent channel signals; never score-gap skip.
- Live OpenAI is unused while `MOCK_MODEL_MODE=true`.

### Negative tests restated

Prompt/schema injection, unknown/duplicate/missing IDs, refusal/incomplete
response, support out of bounds, timeout-after-success, 429, budget/cancel/
version mismatch, single-document crowding, stale parent, and over-budget
context take deterministic safe routes.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `supabase/migrations/20260814140000_hybrid_rerank_context_v1.sql` | `app.fetch_authorized_chunk_context` SECURITY INVOKER, `app_api` only |
| `packages/core/src/smart_rag_core/retrieval/rerank.py` | Pool, skip policy, schema, MMR, quotas, token trim |
| `packages/core/src/smart_rag_core/retrieval/reranker.py` | One-shot gateway adapter; empty rankings on failure |
| `packages/core/src/smart_rag_core/retrieval/context.py` | Select, parent recheck, adjacent from authorized pool |
| `packages/core/src/smart_rag_core/gateways/openai_rerank.py` | `OpenAI(max_retries=0)` + `responses.create`, no `tools` |
| `apps/agents/src/smart_rag_agents/prompts/rerank_v1.md` | Prompt `rerank_v1` |
| `scripts/eval_rerank_counterfactual.py` | Holdout-blind always vs skip |
| `docs/evaluation/RERANK_COUNTERFACTUAL.md` | Counterfactual report |
| `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` | Frozen Packet 5 tunables |
| `openai==2.26.0` | Pinned SDK |

Prompt SHA-256 `4767049107cfe6e8591c84d3b1d202393dfd2564383e6c5bfa0bd5fece8f1925`.
Allow-listed model `gpt-4o-mini`. Frozen: `RERANK_POOL_SIZE=20`,
`RERANK_MAX_PER_DOCUMENT=5`, `RERANK_EXCERPT_CHARS=400`, `MMR_LAMBDA=0.7`
(provisional), document/section quota `2/2`, final `12` units / `3500` tokens.

### Primary documentation sources (2026-08-14)

- OpenAI Python `OpenAI(max_retries=0, timeout=...)` and
  `client.responses.create` with `text.format` `json_schema` `strict=True`,
  `store=False`, optional `tools` omitted:
  Context7 `/openai/openai-python` (v2.11.0 README + Responses create
  signature) and
  <https://github.com/openai/openai-python>
- Structured Outputs JSON Schema:
  <https://platform.openai.com/docs/guides/structured-outputs>
- Token Jaccard MMR on `arabic_norm_v1` (in-repo normalizer)

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 5 rerank/context/gateway/tests) | 0 |
| `uv run pyright` (Packet 5 modules only; not whole `gateways/`) | 0 |
| `uv run pytest tests/unit/test_hybrid_rerank.py tests/unit/test_openai_rerank.py tests/unit/test_hybrid_fusion.py tests/unit/test_model_gateway.py -q` | 0 (35 passed) |
| `uv run pytest tests/contract/test_hybrid_rerank.py -q` | 0 (2 passed; local migration applied) |
| `uv run python scripts/eval_rerank_counterfactual.py` | 0; 293 open-split cases, 43 skipped, 250 reranked, nDCG@5 delta 0.0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (36 reviewed files) |
| `pnpm exec supabase gen types typescript --local --schema app,public,storage,auth` | 0; UTF-8 `database.ts` includes `fetch_authorized_chunk_context` |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (61 markdown files, 0 lint issues) |

Holdout manifests were not read. Live OpenAI was not called
(`MOCK_MODEL_MODE=true`).

### Negative tests

| Fixture | Result |
| --- | --- |
| Duplicate candidate ID | `rerank_duplicate_id` |
| Unknown candidate ID | `rerank_unknown_or_missing_id` |
| Extra ranking row | `rerank_ranking_length` |
| Support 1.5 | `rerank_support_out_of_bounds` |
| Status `incomplete` | `rerank_incomplete` |
| Input hash mismatch | `rerank_input_hash_mismatch` |
| Schema/timeout rerank fn | fused RRF order preserved |
| HTTP 429 | `rerank_budget_denied` |
| API timeout | `rerank_timeout` |
| Incomplete status after usage | `rerank_incomplete` |
| `tools` kwarg | omitted from `responses.create` |
| SDK retries | `max_retries=0` |
| Zero deadline | `BUDGET_DENIED`, no gateway call |
| Single-document crowding | document quota drops extras |
| Stale parent ID | omitted after recheck |
| Over-budget parent | `trim_token_budget` drops units over 3500 |
| Restricted/deleted context IDs | omitted by RPC |
| `sentence-transformers` / `flashrank` in pyproject/uv.lock | absent |
| Counterfactual AST `HOLDOUT` / `load_holdout` | absent |

### Deviations

- Live OpenAI always-rerank quality, latency, and cost are **unverified**.
  Mock identity rankings equal fused RRF order; skip-versus-always deltas on
  the 43 exact-code skip cases are MMR/quota-only and measured 0.0 nDCG@5.
- `MMR_LAMBDA=0.7` and document/section quotas `2/2` are provisional until
  Packet 6 measures development then qualification.
- Adjacent expansion uses already-authorized pool neighbors
  (`chunk_index ± 1` on the same version). Parents use the context RPC because
  they may be non-representative.
- Chat and query-profile OpenAI adapters remain unavailable; only rerank is
  wired when `MOCK_MODEL_MODE=false`.
- Durable token ledger rows for live rerank calls are **unverified** until a
  live key is configured.

### Rollback

- Revert Packet 5 Python modules, prompt, tests, and
  `20260814140000_hybrid_rerank_context_v1.sql`.
- Restore `HYBRID_RETRIEVAL_CONTRACT.md` Packet 5 rows to "not applied".
- Keep Packet 4 fusion RPCs and `rrf_k=60`.

### Packet 6 handoff

Packet 6 may start after this Packet 5 evidence is accepted in-repo (checkbox).
It calibrates coverage/refusal by query class on development then
qualification, never holdout, and freezes retrieval profiles. It must not
implement DuckDB structured tables, LightRAG, or a local rerank model.

## LangSmith gateway tracing (user gate, 2026-08-14)

User instruction: every LLM/embedding call must be traced in LangSmith before
further Phase 4 packets. This is not a Phase 4 plan packet. Phase 6 still owns
production query-graph feedback and online evaluators.

### Acceptance restated

- `OpenAI()` construction in packages/apps/scripts exists only in
  `traced_openai_client`.
- Gateway `generate` / `generate_query_profile` / `generate_rerank` / `embed`
  emit redacted spans when `LANGSMITH_TRACING=true`.
- Exported payloads omit prompts, queries, excerpts, vectors, and API keys.
- Tracing defaults off; `LANGSMITH_API_KEY` is required when tracing is on.
- `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` are forced true.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/observability/langsmith_tracing.py` | Redacting `@traceable` helpers and OpenAI factory |
| `packages/core/src/smart_rag_core/settings/base.py` | Typed `LANGSMITH_*` settings and SDK flag writes |
| `packages/core/src/smart_rag_core/gateways/openai_rerank.py` | `traced_openai_client` plus `openai.responses.rerank` span |
| `docs/development/LANGSMITH_TRACING.md` | Operator contract |
| `langsmith==0.10.18` | Pinned SDK |
| `openai==2.26.0` | Pinned on `smart-rag-core` |

Primary docs: Context7 `/websites/langchain_langsmith` (`wrap_openai`,
`LANGSMITH_TRACING`, `LANGSMITH_HIDE_INPUTS` /
`LANGSMITH_HIDE_OUTPUTS`, `tracing_context`) and
<https://docs.langchain.com/langsmith/mask-inputs-outputs>.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (tracing/gateway/settings/tests listed above) | 0 |
| `uv run pyright` (langsmith_tracing, openai_rerank, model, embedding, settings.base) | 0 |
| `uv run pytest tests/unit/test_langsmith_tracing.py tests/unit/test_openai_rerank.py tests/unit/test_model_gateway.py tests/unit/test_settings.py tests/unit/test_hybrid_rerank.py tests/unit/test_query_profile.py -q` | 0 (48 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (62 markdown files, 0 lint issues) |

Holdout manifests were not read. Live LangSmith and live OpenAI were not
called (`LANGSMITH_TRACING` default false, `MOCK_MODEL_MODE=true`).

### Deviations

- Live LangSmith project visibility is **unverified** until a real
  `LANGSMITH_API_KEY` is used.
- Real OpenAI embedding adapter remains unimplemented; mock `embed` is traced.
- Phase 6 still owns agent/SSE production tracing and feedback taxonomy.

## Packet 6 — coverage/refusal calibration and frozen retrieval profiles

### Quoted requirement

> Calibrate coverage/refusal by query class before the immutable holdout and
> prohibit unsupported advanced methods.

### Acceptance checks restated

- Per-class answer/refusal curves support frozen thresholds; every tightened
  depth/skip has recall/counterfactual evidence.
- Qualification confirms once without holdout access; config is
  immutable/version-addressed with rollback.
- First-failing-stage reports prevent ranking claims when
  profile/candidate/authorization/context failed.
- Dependency lock proves prohibited methods are absent.

### Negative tests restated

Tuning script holdout read, config mutation after freeze, unknown runtime
profile, hardcoded untethered threshold, unsupported method import, or failed
qualification relabeled pass fails.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/retrieval/coverage_score.py` | Formula, support feature, first-failing stage |
| `packages/core/src/smart_rag_core/retrieval/frozen/hybrid_default_v1.json` | Immutable profile artifact |
| `packages/core/src/smart_rag_core/retrieval/frozen_profile.py` | Hash pin and unknown-id refusal |
| `packages/core/src/smart_rag_core/retrieval/prohibited.py` | v1 method lock scan |
| `packages/core/src/smart_rag_core/evaluation/calibration.py` | Development-only `load_tuning_cases` |
| `packages/core/src/smart_rag_core/evaluation/coverage_eval.py` | Occupancy metrics; holdout-blind |
| `scripts/eval_coverage_calibration.py` | Development sweep report |
| `scripts/eval_coverage_qualification.py` | One-shot qualification confirm |
| `FROZEN_HYBRID_PROFILE_SHA256` | `def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c` |

### Primary documentation sources (2026-08-14)

- Plan Packet 6 formula and class minima in
  [04-phase-hybrid-rag.md](../../.cursor/plans/hybrid-graph-rag/04-phase-hybrid-rag.md)
- Pydantic frozen models:
  <https://docs.pydantic.dev/latest/concepts/models/#frozen-models>

### Frozen values

| Field | Value |
| --- | --- |
| Profile id | `hybrid_default_v1` |
| Rollback id | `hybrid_packet5_v1` (not a live runtime profile) |
| Coverage threshold | `0.65` every labeled class |
| `rrf_k` / channel weights | `60` / equal `1.0`; unequal weights not selected |
| Channel depths / rerank skip | Packet 5 values retained |
| Qualification | **PASS**, false supported `0` on `77` cases |
| Development occupancy n | `216`; weighted loss `0.4583` at frozen `0.65` |

Rejected occupancy sweep values below `0.65` (single-channel
`support_confidence=0.60` or one gold link versus a two-unit minimum) are in
[COVERAGE_CALIBRATION.md](../evaluation/COVERAGE_CALIBRATION.md). They were
not written into the frozen artifact.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check` (Packet 6 modules, scripts, tests) | 0 |
| `uv run pyright` (coverage, frozen_profile, prohibited, eval, scripts, tests) | 0 |
| `uv run pytest tests/unit/test_hybrid_coverage.py tests/unit/test_phase4_dataset.py tests/unit/test_hybrid_fusion.py tests/contract/test_hybrid_fusion.py -q` | 0 (43 passed) |
| `uv run python scripts/eval_coverage_calibration.py` | 0 |
| `uv run python scripts/eval_coverage_qualification.py` | 0 (`PASS`, false supported 0) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (65 markdown files, 0 lint issues) |

Holdout manifests were not materialized. Live Hybrid ranked IDs were not used;
occupancy uses visible gold evidence links.

### Negative tests

| Fixture | Result |
| --- | --- |
| `load_tuning_cases()` | development IDs only; disjoint from qualification |
| Calibration/eval AST | no `HOLDOUT` / `load_holdout` |
| `load_frozen_profile("hybrid_packet5_v1")` | `UnknownRetrievalProfileError` |
| Mutated JSON hash | `FrozenProfileMutationError` |
| Threshold source | hashed profile, not a bare literal |
| Qualification script | records `FAIL` when false-supported is non-zero; does not sweep |
| ACL occupancy | first-failing stage `authorization`; ranking claim blocked |
| `uv.lock` / pyproject / imports | prohibited methods absent |
| Single-channel factual | score `0.60`, refuse at `0.65` |
| Two-channel exact | support `1.0`, answer |
| BM25 degraded + score `0.60` | signal stays `BM25_DEGRADED`, still refuses |

### Deviations

- Occupancy is not a live ranked-ID ablation. Channel depths, rerank skip,
  MMR, and `rrf_k` were **not** retuned.
- Unnecessary-refusal on occupancy for non-exact Hybrid classes is expected:
  unknown channel mix yields `support_confidence=0.60`, which is below the
  weak-coverage floor.
- Combined, structured-table, and graph-inspection labels are not Hybrid
  gold answers. Packet 7 owns table calculation.
- Live LangSmith/OpenAI remain **unverified**. SME 12–20 hours remain
  **unverified**. Holdout stays sealed.

### Rollback

- Restore Packet 5 signal-only coverage (omit numeric attach) and delete
  `retrieval/frozen/hybrid_default_v1.json`.
- Runtime rollback id `hybrid_packet5_v1` is documented only; it is not a
  second executable profile.

### Packet 7 handoff

Packet 7 may start after this Packet 6 evidence is accepted in-repo (checkbox).
It implements sandboxed DuckDB structured tables with exact workbook/sheet/
range provenance. It must not read holdout, add LightRAG, or install a
prohibited retrieval method.

## Packet 7 — sandboxed structured tables (2026-08-14)

Quoted requirement: implement the declarative, sandboxed structured-table path
with exact workbook/sheet/range provenance.

### Plan requirement

Ordinary spreadsheet cell/text lookup stays Hybrid. Calculation uses
`structured_table_query` with a strict `TableQueryPlan`, server-side
`app.resolve_structured_table`, and an isolated DuckDB process. DuckDB
settings are defense in depth, not the sole sandbox.

### Inspected pins and primary docs

| Item | Value | Source |
| --- | --- | --- |
| DuckDB | `1.2.1` on `smart-rag-core` and workspace | `packages/core/pyproject.toml`, `uv.lock` |
| PyArrow | `19.0.1` | Phase 3 table artifacts |
| `connect` | `:memory:`, `config={enable_external_access: false, ...}` | Context7 `/duckdb/duckdb-python` 2026-08-14; live 1.2.1 |
| `lock_configuration` | `SET lock_configuration=true` | [DuckDB securing extensions](https://duckdb.org/docs/current/operations_manual/securing_duckdb/securing_extensions.html) 2026-08-14 |
| External access | false blocks `ATTACH`, `COPY`, `read_parquet` of files | [CLI safe mode](https://duckdb.org/docs/current/clients/cli/safe_mode.html); live Permission Error |
| Arrow register | `connection.register("allowed_table", arrow)` | Context7 Python register API; live 1.2.1 with external access off |
| Parquet schema | `table_parquet_v1` plus `__provenance_json` | Phase 3 ingestion |

Live 1.2.1 finding: `enable_external_access=false` blocks `read_parquet` of
the authorized file, so the read path is PyArrow `read_table` then register.
DuckDB settings remain locked afterward.

### Files

- `packages/core/src/smart_rag_core/tables/` plan, builder, sandbox worker,
  executor, resolver, refusals, service
- `packages/core/src/smart_rag_core/settings/base.py`
  `snapshot_process_environ` (environment-boundary compliant)
- `supabase/migrations/20260814150000_structured_table_v1.sql`
- `tests/unit/test_structured_table.py`
- `tests/contract/test_structured_table.py`
- `docs/retrieval/STRUCTURED_TABLE.md`
- Hybrid contract, data dictionary, docs index, components

No public HTTP route. Phase 6 owns API/SSE.

### Limits frozen

| Bound | Value |
| --- | --- |
| Statement deadline | 3.0s then terminate, 0.5s kill |
| DuckDB memory / temp / threads | 64MB / 32MB / 1 |
| Output rows / bytes / scanned LIMIT | 1000 / 1 MiB / 100000 |
| Timezone | UTC |
| POSIX `RLIMIT_AS` / `RLIMIT_CPU` | 512MiB / 4s when `resource` exists; unverified on Windows |

### Commands

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_structured_table.py tests/contract/test_structured_table.py tests/unit/test_langsmith_tracing.py -q` | 0 (32 passed, 1 skipped: symlink privileges) |
| `uv run pyright packages/core/src/smart_rag_core/tables packages/core/src/smart_rag_core/settings/base.py packages/core/src/smart_rag_core/settings/__init__.py` | 0 |
| `uv run ruff check` (Packet 7 modules and tests) | 0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (37 files) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (66 markdown files) |

Local `app.resolve_structured_table` applied to Postgres at `127.0.0.1:54322`.

### Negative tests

| Fixture | Result |
| --- | --- |
| Extra `sql` field / path-shaped predicate | `ValidationError` |
| Ordinary lookup with no operation | `ordinary lookup stays Hybrid` |
| Unknown table id / disabled caller / wrong version | `TableResolveError` |
| Member vs restricted table RPC | no row; owner can read ACL grant |
| Stale version / deleted document | no row |
| Anon `EXECUTE` | `InsufficientPrivilege` |
| Hidden sheet / formula column / mixed USD+EUR | typed refusals |
| Duplicate original header used as id | `duplicate_header_reference` |
| `ATTACH` / `COPY` / `https://` SQL | `blocked_sql` |
| `read_parquet` of another local file | Permission / filesystem disabled |
| Catalog SHA-256 mismatch | `artifact_hash_mismatch` |
| Output byte / row abuse | fail closed |
| Hung worker | terminate then kill (`statement_deadline`) |
| Secret env inheritance | KEY/SECRET/TOKEN/JWT/OPENAI/SUPABASE/LANGSMITH stripped |
| Infinity aggregation | `non_finite_result` |
| Process reuse after `INSTALL` | later allowed SUM still 32 |
| Symlink to another file | skip on this Windows host without privilege; path mismatch when created |

### Provenance

Filtered SUM of ops rows returns `budget.xlsx!Summary!B2` (and B3) from
`__provenance_json` cell locators, not sheet-only labels.

### Deviations

- DuckDB `read_parquet` cannot load the authorized file when external access
  is disabled. Arrow register is the read path. Documented, not an ADR: same
  isolation outcome, stronger than SQL-path reads.
- Windows has no `resource.setrlimit`. Deadline plus DuckDB `memory_limit`
  are the Windows bounds.
- No FastAPI table route (Phase 6). No holdout use. No LightRAG.
- Junction/symlink escape is unit-tested when the OS allows symlink creation.

### Rollback

Replace `app.resolve_structured_table` with `RETURN;` and revoke `app_api`.
Stop binding `should_bind_structured_table`. Ordinary lookup remains Hybrid.

### Packet 8 handoff

Packet 8 publishes ablations, quality/latency/cost/citation/ACL/fallback
evidence, and one immutable holdout run. Holdout stays sealed until freeze
hashes are recorded. Do not tune on holdout. Do not set phase `status`
complete until the user accepts Packet 8.

[PHASE4_FREEZE.md](../evaluation/PHASE4_FREEZE.md)
[PHASE4_ABLATIONS.md](../evaluation/PHASE4_ABLATIONS.md)
[PHASE4_HOLDOUT.md](../evaluation/PHASE4_HOLDOUT.md)
[docs index](../README.md)
[STRUCTURED_TABLE.md](../retrieval/STRUCTURED_TABLE.md)
[HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
[LANGSMITH_TRACING.md](./LANGSMITH_TRACING.md)
[RERANK_COUNTERFACTUAL.md](../evaluation/RERANK_COUNTERFACTUAL.md)
[COVERAGE_CALIBRATION.md](../evaluation/COVERAGE_CALIBRATION.md)
[COVERAGE_QUALIFICATION.md](../evaluation/COVERAGE_QUALIFICATION.md)
[HYBRID_TUNING.md](../retrieval/HYBRID_TUNING.md)
[PROHIBITED_V1_METHODS.md](../retrieval/PROHIBITED_V1_METHODS.md)

## Packet 8 — freeze, ablations, and holdout no-go (2026-08-14)

Quoted requirement: publish ablations, quality, latency, cost, citation, ACL,
and fallback evidence; freeze winning versioned profiles.

### Plan requirement

Packet 8 records code/config/prompt/SDK hashes, the required simpler-baseline
matrix on development/qualification, signed-gate comparison, Phase 3
reconfirm, and one immutable holdout run **or** an honest no-go. Holdout
must not be opened for tuning. Phase status stays pending until the user
accepts. Phase 5 does not start in this run.

### Acceptance checks restated

- Ablation matrix and freeze hashes are reproducible from commands.
- Signed Hybrid/profile/citation/ACL/latency/cost gates pass, **or** Phase 4
  remains pending with no-go evidence.
- Unexecuted Phase 5/6 labels are not counted as passes.
- Continue-versus-pilot is requested; not silently decided.

### Negative tests restated

Holdout access during freeze, invented Recall@10, occupancy treated as
ranked-ID recall, or marking the phase complete without user acceptance
fails.

### LangSmith (user gate, before Packet 8)

Gateway tracing was already landed in `1a90fd3`. Reconfirmed this packet:
every production `OpenAI()` ctor remains in `traced_openai_client`;
embeddings.create remains in `traced_embeddings_create`; mock generate/embed
emit redacted spans when tracing is enabled. Live LangSmith project
visibility is still **unverified** (no real key in this run).

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/evaluation/phase4_freeze.py` | Holdout-blind freeze report |
| `scripts/eval_phase4_freeze.py` | Writes freeze markdown; prints git SHA |
| `docs/evaluation/PHASE4_FREEZE.md` | Generated freeze snapshot |
| `docs/evaluation/PHASE4_ABLATIONS.md` | Ablation matrix |
| `docs/evaluation/PHASE4_HOLDOUT.md` | No-go holdout record |
| `FROZEN_HYBRID_PROFILE_SHA256` | `def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c` |
| Parent git SHA at freeze | `b1282f7c246b5417dca5b279ab190dc1bfe3ae08` (Packet 7) |
| OpenAI / LangSmith / DuckDB / PyArrow | `2.26.0` / `0.10.18` / `1.2.1` / `19.0.1` |

### Dataset counts (open splits only)

| Split | n |
| --- | --- |
| Development | 216 |
| Qualification | 77 |
| Open total | 293 |
| Holdout ids in sealed manifest (labels not loaded) | 112 |
| Deferred later-phase labels on open splits | 81 |

SME corpus status remains `synthetic_provisional`.

### Launch decision

**no-go.** Holdout was not opened. Live Hybrid Recall@10, citation
correctness/completeness, faithfulness, and envelope p95 are unverified.
Query-profile QT-QP-001 through QT-QP-006 passed on development and
qualification with `model_calls=0` (mock extract). ACL is fixture-only.
Winning profile remains `hybrid_default_v1`. Cache TTLs and unequal RRF
weights stay unselected.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run python scripts/eval_phase4_freeze.py` | 0 (`launch_decision=no_go`, `holdout_opened=false`) |
| `uv run python scripts/eval_query_profile.py` | 0 (development 216 and qualification 77 passed) |
| `uv run ruff check` (freeze module, script, tests) | 0 |
| `uv run pyright` (same freeze paths) | 0 |
| `uv run pytest tests/unit/test_phase4_freeze.py tests/unit/test_langsmith_tracing.py tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py tests/unit/test_phase4_dataset.py tests/unit/test_hybrid_coverage.py -q` | 0 (52 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (69 markdown files, 0 lint issues) |

Live Hybrid Ready E2E, ParadeDB overlay, and envelope p95 were **not**
re-run in this packet. Phase 3 chunking unit tests passed.

### Negative tests

| Fixture | Result |
| --- | --- |
| Freeze AST `load_holdout` / `DatasetSplit` / `load_cases` | absent |
| Freeze while holdout access enabled | `HoldoutSealedError` |
| Live recall claimed on any ablation | false |
| Occupancy PASS as Recall@10 | rejected in freeze/ablation docs |
| Phase wrapper `status: complete` | not set |

### Deviations

- Honest no-go instead of a fake holdout run. The synthetic holdout
  manifest exists as ids/hashes only and is not independently SME-sealed.
- Arrow-register DuckDB path and mock rerank remain as Packets 5–7.
- Gateway LangSmith tracing is present; Phase 6 still owns query-graph
  feedback and online evaluators.
- No ADR for the no-go itself; Hybrid Pilot continue-versus-pilot vote is
  still pending user action
  ([ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md)).

### Rollback

Delete Packet 8 freeze docs/script/module and uncheck wrapper box 8.
Restore Hybrid contract "Not selected" wording. Frozen profile
`hybrid_default_v1` stays; Packet 8 did not mutate it.

### Phase 5 inputs (do not start)

- Hybrid runtime profile: `hybrid_default_v1` at the pinned SHA-256 above.
- Coverage threshold 0.65 all classes; `rrf_k=60`; equal channel weights.
- Structured tables: Packet 7 sandbox; no HTTP route.
- Graph/Combined/LightRAG: not implemented; relationship/multi-hop/
  graph_mapping/prompt_injection labels are deferred.
- Blockers for a Hybrid launch claim: live ranked-ID Recall@K, citation
  assembler metrics, independently SME-sealed holdout, envelope p95/cost,
  named Knowledge Owner hours.
- User must choose continue-to-Phase-5 versus `0.x Hybrid Pilot` before
  Phase 5 work starts.

Phase 4 wrapper checkbox 8 is checked because the no-go evidence is
complete. Wrapper `status` remains `pending` until explicit user
acceptance.
