---
name: verify-release-gates
description: Runs and reports phase, staging, or production readiness gates with reproducible evidence. Use when claiming a phase complete, preparing a release, deploying, or auditing readiness.
---

# Verify Release Gates

Read the global targets, one active Phase 9–11 wrapper, its phase shared contract, exactly one selected packet, and only that packet's linked `shared/release/` contracts plus the wrapper exit gate. Do not load sibling packets or infer release requirements from legacy section numbers.

## Gate procedure

1. Record commit, environment, dependency/model versions, ParadeDB image digest/`pg_search`/BM25 schema/index/normalization versions, migrations, dataset version, and configuration profile.
2. Require `docs/QUALITY_TARGETS.md` with owner/client-approved values before Phase 4; until then, use the global contract's provisional gates.
3. Run fast static/unit checks before expensive integration/evaluation/load checks.
4. Run every mandatory gate. A skipped, missing, empty, flaky, or unavailable mandatory test is a failed gate.
5. Capture machine-readable results, logs/traces, latency percentiles, token/cost totals, and artifact locations without secrets or raw sensitive text.
6. Compare to signed-off targets, or the plan's provisional thresholds when sign-off is not yet due.
7. Classify failures by owner and severity; do not average away critical ACL, grounding, deletion, budget, or restore failures.

## Minimum release evidence

- clean build, lint, type, unit, integration, contract, and E2E;
- migrations and RLS matrix;
- chunk/cleaning/dedup structure and naive-split retrieval ablation;
- disjoint embedding qualification/tuning/immutable-holdout/regression evidence;
- query-profile field metrics, byte-identical Arabic Supabase-projection/core/ParadeDB normalization, seeded code/alias recall, and retrieval/answer evaluation by query type/language;
- dense/BM25/term candidate-depth curves, typed BM25 query safety, field/tokenizer/phrase ablations, selective-filter authorization recheck, projection lag/replay/purge/rebuild, BM25 outage degradation, always-versus-conditional rerank counterfactuals, and calibrated coverage/refusal curves;
- Combined fusion ablation against naive union;
- graph mapping/survival, entity collision, version, deletion, and ACL tests;
- tool routing/disclosure and structured table determinism;
- injection, SSRF, parser sandbox, secrets/redaction, and audit integrity;
- asymmetric JWKS rollover/HS256 prohibition, upload MFA, protected migration credentials, and conversation cascade deletion;
- fresh ClamAV signature/re-scan plus category/URL approval and egress isolation;
- Valkey ACL/memory/outage degraded limits and reserve-once budget contention/true-up;
- load/deadline/cancellation/event-loop lag/heartbeat jitter/SSE resume, including a slow run through staging CloudFront;
- embedding model/dimension/HNSW memory, ParadeDB index/RAM/query/rebuild resources, and database/search maintenance/isolation triggers;
- graph single-writer throughput, backlog ETA, and bulk-onboarding duration/cost;
- worker/API restart and queue recovery;
- audit chain/KMS anchors, origin-secret dual rotation, Supabase/Storage backup restore followed by clean derived BM25 rebuild/parity, instance rebuild, staging rollback, and smoke test;
- documented RTO/RPO, retention, offboarding, and incident runbooks.

## Report format

Return Passed, Failed, Blocked, and Not Run sections. For every non-pass include exact evidence and required next action. Never say “production ready” while a release gate is blocked or unrun.
