---
title: High production-readiness findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, ops
reviewed_commit: 09a102a
---

# High findings

High means: must fix, disable, or ADR with a named owner before production users. Several are also production blockers when combined with the Critical launch gates.

Related: [critical](./01-critical.md) · [medium](./03-medium.md)

## PRD-H-001 — Unauthenticated FastAPI `/docs`, `/redoc`, `/openapi.json`

- **Location:** `apps/backend/src/smart_rag_api/main.py:174-182` (`FastAPI(...)` with default docs); `apps/backend/src/smart_rag_api/middleware/preauth.py:19-24`
- **Evidence:** No `docs_url=None` / `redoc_url=None` / `openapi_url=None`. Pre-auth limiter **skips** `/health`, `/api/meta`, `/openapi.json`, `/docs`, `/redoc`. Distroless image still serves the default Swagger UI.
- **Impact:** Anyone who can reach the origin (mis-set security group, placeholder CloudFront, or direct IP) gets the full API map: admin, invitations, runs, uploads. Information disclosure and a free recon surface. Rate-limit skip makes scraping cheap.
- **Remediation:** In `staging`/`production`, set `docs_url=None`, `redoc_url=None`, and either disable OpenAPI or protect it with the same JWKS dependency plus admin role. Do not skip `/openapi.json` from limits if it stays enabled.
- **Production blocker:** yes
- **Tests:** None found that assert docs are off outside `test`.

## PRD-H-002 — Production Next CSP still allows localhost and `'unsafe-inline'` scripts

- **Location:** `apps/frontend/next.config.ts:16-30`
- **Evidence:** `connect-src` is a compile-time string: `'self'` plus loopback `:8000`/`:54321` and `https://*.supabase.co`. It does **not** include `NEXT_PUBLIC_API_BASE_URL`. Production `script-src` is `'self' 'unsafe-inline'` (no nonce). `prohibited-patterns.test.ts` asserts that unsafe-inline string, so CI locks the weakness in.
- **Impact:** A hosted Vercel build cannot `fetch` CloudFront/staging API while Auth to `*.supabase.co` still works. Localhost in production CSP also widens XSS exfil. Wildcard `*.supabase.co` is broader than one project.
- **Remediation:** Build `connect-src` from `NEXT_PUBLIC_API_BASE_URL` + the exact Auth origin; loopback only for local. Drop `'unsafe-inline'` via nonces. Playwright must assert the API origin is in CSP.
- **Production blocker:** yes for Vercel production
- **Tests:** Playwright only asserts CSP exists and has no Tailwind CDN.

## PRD-H-003 — CORS allow-list advertises test identity headers

- **Location:** `apps/backend/src/smart_rag_api/middleware/cors.py:18-22`
- **Evidence:** Credentialed CORS allows `X-Test-User-Id`, `X-Test-Role`, `X-Test-Authorization-Version`, `X-Test-Email` on every environment. Bypass still requires `APP_ENV=test` (see PRD-C-008), but browsers are told these headers are expected.
- **Impact:** Helps an attacker who finds a test-env leak. Combined with C-008 this is how a total bypass would be invoked from a browser.
- **Remediation:** Inject test headers into CORS only when `APP_ENV=test`. Production allow-headers: `Authorization, Content-Type, Idempotency-Key, Last-Event-ID, X-Client-Version, X-Request-ID`.
- **Production blocker:** yes with C-008; otherwise High hygiene

## PRD-H-004 — Request size gate trusts `Content-Length` only

- **Location:** `apps/backend/src/smart_rag_api/middleware/request_limits.py:29-34`
- **Evidence:** Oversized bodies are rejected only when `Content-Length` is present and numeric. Missing or chunked length skips the cap (`return await call_next(request)`).
- **Impact:** A client that omits `Content-Length` can stream a large JSON/SSE-adjacent body and pressure memory on the API event loop. Upload paths may have their own caps; JSON mutation routes may not.
- **Remediation:** Fail closed on missing `Content-Length` for methods with bodies, or wrap `receive` and count bytes up to `request_max_body_bytes`. Add a test with chunked/missing length.
- **Production blocker:** no (DoS / stability), but High before internet exposure

## PRD-H-005 — Live query execution is process-local memory

- **Location:** `apps/backend/src/smart_rag_api/services/sse_stream.py:398-509,638-656`; `apps/backend/src/smart_rag_api/main.py:105`; `infra/ec2/docker-compose.staging.yml` `api-blue` + `api-green`
- **Evidence:** `QueryRunRegistry` holds live tasks in process dicts. If GET `/runs/{id}/events` lands on another replica while status is `running`/`pending` and the local registry is empty, `_emit_worker_unavailable` persists a **terminal** `error` `{code: worker_unavailable}`. Unique index `run_events_one_terminal_uq` then blocks the still-running replica from appending `completed`.
- **Impact:** Paid LangGraph continues while the client sees a fatal error; cancel/resume on the other slot cannot attach. Staging Compose always starts two API colors (H-020).
- **Remediation:** One active API color. Resume must replay only and must **not** write `worker_unavailable` while status is `running`. Move the graph to a leased worker or shared Postgres lease before any second replica.
- **Production blocker:** yes for multi-instance / blue-green; High for single-host restarts

## PRD-H-006 — Hosted Supabase reuse is not isolated staging

- **Location:** `docs/deployment/MANAGED_STAGING.md:12-15`, `docs/adr/ADR-phase10-hosted-supabase-reuse.md`
- **Evidence:** Staging uses existing project `qsjivtwtmlmtksufqjik`, not a Pro/us-east-1/PITR isolated freeze.
- **Impact:** Staging experiments, pentest, or a bad migration can touch the same Auth/Postgres that a future production might keep. Backup/PITR assumptions in QUALITY_TARGETS may be false for this project tier.
- **Remediation:** Isolated staging project with PITR, or a signed ADR that production will be a **new** project and this one stays forever non-prod. Never promote this project ID to production DNS.
- **Production blocker:** yes if this project would become prod

## PRD-H-007 — Private ParadeDB/Valkey TLS still omitted; staging revisit is due

- **Location:** `docs/adr/ADR-private-service-tls.md:15-38`
- **Evidence:** TLS omit is accepted for **local same-host Docker**. Staging/production must reopen when services span hosts or compliance needs encryption in transit. Phase 10 Packet 1 already notes the revisit.
- **Impact:** On EC2 Compose, a compromised sidecar on the Docker network reads BM25 projections and rate-limit keys in cleartext. BM25 is not canonical evidence, but IDs + projection text are still corpus.
- **Remediation:** Reopen the ADR before starting staging Compose. Require TLS or an equivalent private-link story for ParadeDB and both Valkey instances.
- **Production blocker:** yes for managed deploy

## PRD-H-008 — First-token / completion p95 is not a live OpenAI proof

- **Location:** `docs/deployment/phase-09/candidate-packet4-gate-matrix.json` (five-stream p95 not re-run / first_token null), `docs/development/phase-09-local-release-candidate-evidence.md:559-684`, `docs/QUALITY_TARGETS.md` QT-LAT-002..011
- **Evidence:** Retrieve first-evidence p95 passed on a 7-case subset. Stream first-token p95 is frequently `null`. Later completion p95 ~1.8s is **mock streams**, not live OpenAI. Combined/Hybrid answer-token gates remain unproven.
- **Impact:** Users will wait on embeddings, rerank, LightRAG, and the answer model. The 5s/10s first-token story is not measured on the real path.
- **Remediation:** After C-001, run Packet-style five-stream load against live models on staging hardware. Publish p50/p95. Reduce advertised latency or add UX "slow route" copy if missed.
- **Production blocker:** yes for latency SLOs; not for a labeled mock demo

## PRD-H-009 — Arabic product chrome is forced LTR English

- **Location:** `apps/frontend/src/app/layout.tsx:23`, journey matrix RTL requirements vs implementation
- **Evidence:** Root is `<html lang="en" dir="ltr">`. User/citation text uses `dir="auto"` isolates (good). There is no `lang="ar"` document, no logical-property audit of the 280px nav, no mirrored shell.
- **Impact:** For an Arabic-first corpus, the console fights the reader: menus, drawers, and composer stay LTR. This is a product defect, not just polish, given QUALITY_TARGETS multilingual gates.
- **Remediation:** Locale switch or `dir` from profile; logical CSS for shell; Arabic UI copy for errors/limitations; Playwright RTL fixtures. Keep bidi isolates.
- **Production blocker:** yes if the launch company is Arabic-primary; otherwise High UX

## PRD-H-010 — Hybrid live Recall@10 and alias recall are far below launch gates

- **Location:** phase-09 evidence Recall@10 **0.25**, alias Recall@10 **0.0**; QT-EVAL-006/008
- **Evidence:** Same as PRD-C-005 but this is the retrieval-engineering defect inside the quality gate. Locators can be perfect while ranking is not.
- **Impact:** Auto answers will miss the documents users typed an exact alias or mixed Arabic query for. Combined cannot rescue ordinary Hybrid facts.
- **Remediation:** Treat alias and arabic_mixed misses as P0 retrieval bugs. Re-run ranked-ID on a larger open split **without** opening holdout. Only then collect a new holdout.
- **Production blocker:** yes for Hybrid as default Auto

## PRD-H-011 — Privileged Auth Admin secret lives in the API process

- **Location:** `apps/backend/src/smart_rag_api/auth_admin/settings.py:10-37`, ADR-privileged-auth-administration-boundary
- **Evidence:** Settings class is isolated from `SharedSettings` (good) but `load_privileged_auth_settings()` reads `SUPABASE_AUTH_ADMIN_SECRET` in the FastAPI deployable. Same for worker Storage Admin (`privileged_storage.py`).
- **Impact:** RCE or memory dump of the API container is `service_role`-equivalent. The ADR accepted this isolation shape; production still needs a tighter runtime (separate admin job, IAM to Secrets Manager just-in-time, no long-lived env).
- **Remediation:** Staging/production: inject the secret only into a sidecar/job that is not the query API; or SSM parameter fetched per mutation with no process-wide cache. Prove general health endpoints cannot import the class (already intended). Add runtime env scan that query replicas lack the secret.
- **Production blocker:** no if replicas are split; High if one fat API task has the secret (current Compose)

## PRD-H-012 — GraphRAG default is a 15-document envelope

- **Location:** `docs/development/RISK_REGISTER.md` R-03, QT-CAP-005-P8
- **Evidence:** Bulk onboarding blocked. Rebuild cost unmeasured. Reserve is USD 800 floor with `4× measured` unevaluable.
- **Impact:** Turning Combined/Auto relationship routing on for a real corpus will either index ACL-visible company docs into the **shared** LightRAG workspace (plan: only company-visible) at unknown cost, or sit in Graph Pending forever.
- **Remediation:** Keep Auto → Hybrid until a measured Graph Ready throughput exists. UI must show graph-pending/ineligible honestly (partially implemented). Do not advertise GraphRAG in sales copy.
- **Production blocker:** yes for Combined-as-default

## PRD-H-013 — Origin / WAF / CloudFront path is placeholder

- **Location:** `docs/deployment/MANAGED_STAGING.md` CloudFront 90/90 with placeholder origin; origin-secret runbook exists but live dual-rotation unproven
- **Evidence:** Internet EIP probe closed common ports on an instance that is not running the stack. That does not prove origin-header deny, WAF rules, or Caddy 403 for unmatched origins against a live API.
- **Impact:** When Compose starts, a direct origin hit may skip CloudFront controls. SSE 90s timeout is configured in IaC, not proven through a slow staging stream.
- **Remediation:** After Compose is up: origin-secret mismatch 403, WAF smoke, CloudFront 90s hang test, SSE resume through CDN.
- **Production blocker:** yes for internet exposure

## PRD-H-014 — CI remote green is unverified; compose/RLS not on every PR

- **Location:** `docs/development/CI_TIERS.md:21-22,60`
- **Evidence:** "Remote GitHub conclusion remains unverified until a run URL is recorded." Future work names Supabase reset/RLS, LightRAG, retrieval evals, load, restore as not fake-green. PR fast does not run full RLS matrix against a real DB unless contract jobs do with secrets.
- **Impact:** Merge confidence is local-developer-shaped. A broken migration can land if contract job is skipped.
- **Remediation:** Record a main-branch CI URL. Make RLS contract non-skippable on main. Do not use `continue-on-error` for security suites.
- **Production blocker:** no for local RC; High before production merge discipline

## PRD-H-015 — Hosted RLS disabled on session-revocation tables

- **Location:** `docs/deployment/phase-10/packet1-live-supabase.json` (advisor `rls_disabled_in_public` / `app.revoked_sessions`, `app.mfa_recovery_requests`)
- **Evidence:** Same reused Free project as C-013. FastAPI session-revocation contract assumes RLS; hosted advisor says those tables are not protected.
- **Impact:** Logout/MFA recovery rows are not tenant-isolated on the project operators would promote.
- **Remediation:** Isolated project; `ENABLE ROW LEVEL SECURITY` + policies matching local migrations; advisor clean.
- **Production blocker:** yes for promoting that project

## PRD-H-016 — Local Compose API/worker use the postgres superuser DSN

- **Location:** `docker-compose.yml:173,222`
- **Evidence:** `SUPABASE_DB_URL=postgresql://postgres:postgres@…:54322/postgres`. Retrieval also `SET ROLE postgres` for temporal dates (`hybrid_run.py` temporal load).
- **Impact:** App RLS is bypassed on the live local path. Combined with C-010 (`USING (true)` for `app_api` SELECT), ACL is RPC-shaped, not table-shaped.
- **Remediation:** Compose must use `app_api` / least-privilege DSNs. Temporal metadata via invoker RPC over already-authorized IDs.
- **Production blocker:** yes for any environment that copies this Compose env into staging

## PRD-H-017 — Query reservation true-up is never scheduled

- **Location:** `packages/core/src/smart_rag_core/query_admission/service.py:317,414`; `packages/core/src/smart_rag_core/memory/reaper.py:51`; `apps/` has no caller
- **Evidence:** `true_up_query_reservation` and `reconcile_expired_query_runs` exist and are tested. No worker/API schedule invokes them. Reaper docs say it does not true-up.
- **Impact:** Crashed SSE after reserve leaves tokens reserved until expiry; concurrent users starve.
- **Remediation:** Periodic worker job; true-up on every terminal query; alert on expired-unsettled count.
- **Production blocker:** no for a demo; High for concurrent paid users

## PRD-H-018 — Model ceilings omit Hybrid embed, rerank, and LightRAG consume

- **Location:** query graph ceiling math (Phase 6 evidence / `query` budget nodes)
- **Evidence:** Admission ceilings count answer/verifier-class tokens, not retrieve-time embedding of the query, OpenAI rerank of the pool, or LightRAG consume.
- **Impact:** After C-009, a Combined run can exceed the reserved USD while the graph still thinks it is under ceiling.
- **Remediation:** Include embed + rerank + graph consume in the same reservation; fail closed when remaining cannot cover them.
- **Production blocker:** yes once live models are bound

## PRD-H-019 — LangGraph checkpointer pool (4) vs five concurrent query runs

- **Location:** checkpointer / query concurrency settings vs QT concurrent-run gate
- **Evidence:** Signed envelope allows 5 concurrent queries. Checkpointer pool is 4. Dual `api-blue` + `api-green` on staging doubles pools (H-020).
- **Impact:** Fifth concurrent run waits on a connection while admission already reserved budget.
- **Remediation:** Pool ≥ concurrent runs × replicas; one active API color unless explicitly draining.
- **Production blocker:** no at 1 user; High at the signed 5-run envelope

## PRD-H-020 — Staging Compose keeps api-blue and api-green both up

- **Location:** staging compose / Phase 10 host evidence
- **Evidence:** Both API colors reported running, doubling DB/Valkey/checkpointer connections on a host that already cannot run ParadeDB (C-002).
- **Impact:** Connection exhaustion and split in-memory `QueryRunRegistry` (H-005) across two processes.
- **Remediation:** Single active color; drain the other. Do not start Compose on t3.micro.
- **Production blocker:** yes if that compose file is started as-is

## PRD-H-021 — Frontend SSE cancel aborts the reader, not the admission fetch

- **Location:** `apps/frontend/src/components/chat-app.tsx:228-303`; `apps/frontend/src/lib/sse-consume.ts:23-55`; `apps/frontend/src/lib/api.ts:1830-1866`
- **Evidence:** Cancel and a new send call `abortRef.current?.abort()`. `consumeSse` honors `AbortSignal` and `reader.cancel()`. `startOrResumeMessageStream` / `resumeEventStream` do **not** take a `signal`, so the POST admit and GET resume fetches keep the TCP body until the server closes. Cancel also `POST`s `/runs/{id}/cancel` (good) which is a no-op on the other API color (H-005).
- **Impact:** The UI stops applying frames; the billed graph continues until the cancel RPC hits the owning process, or until the deadline if it does not.
- **Remediation:** Pass `signal` into both fetches. Ignore frames whose `query_run_id` is not current. Pin one API color until H-005.
- **Production blocker:** no for a single-tab demo; High for billed UX

## PRD-H-022 — 1M-chunk HNSW RAM vs Nano / 60% rule

- **Location:** capacity notes vs `QT-CAP` / embedding ADR
- **Evidence:** ~8.84 GB for 1M 1024-d HNSW vs Nano RAM and the 60% RAM gate. Live envelope is 16 chunks.
- **Impact:** Phase 1 10k/1M remains an aspiration. Shipping “1M ready” is false.
- **Remediation:** Re-sign capacity on measured hardware; do not quote 1M from Docker.
- **Production blocker:** yes for any 1M/10k claim (pairs with C-006)

## PRD-H-023 — Graph writer throughput vs 7-day Graph Ready SLA

- **Location:** graph `process_once` / 600s job vs QT-CAP-005
- **Evidence:** ~600s × 7 days ≈ 1008 documents if serial. Envelope is 15 mapping docs.
- **Impact:** A 10k corpus cannot become Graph Ready in the advertised window.
- **Remediation:** Keep Combined off; publish Graph Pending as the default; measure rebuild before raising envelope.
- **Production blocker:** yes for GraphRAG-as-default

## PRD-H-024 — Combined empty citation text can pass the deterministic check

- **Location:** `packages/core/src/smart_rag_core/query_routing/branches.py`; `query_answer/deterministic.py`
- **Evidence:** Graph locators set `citation_text=""`. Empty span is treated as a whole-passage citation. Combined graph-only units allowed up to 40%.
- **Impact:** Citation/faithfulness gates can pass with no canonical `raw_text`.
- **Remediation:** After fusion, load `fetch_authorized_chunk_context` for every ID; drop empty text; fail empty spans.
- **Production blocker:** yes for Combined-as-default

## PRD-H-025 — Admin can invite `owner`; accept overwrites an existing profile role

- **Location:** `apps/backend/src/smart_rag_api/auth_admin/invitations.py:93-94`; `supabase/migrations/20260813120000_auth_jwks_invitations_v1.sql:225-230`
- **Evidence:** Allowed invitation roles include `owner`. Accept does `INSERT … ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role, upload_enabled = EXCLUDED.upload_enabled`.
- **Impact:** An admin can mint an owner invite (privilege escalation). A later member invite for the same email can silently demote an existing owner and change upload flags without session revoke.
- **Remediation:** Only `owner` may invite `owner`, or forbid owner invites. On accept, refuse existing profiles or apply monotonic upgrades after AAL2 and revoke sessions on privileged/upload change.
- **Production blocker:** yes

## PRD-H-026 — Lost-factor MFA recovery and owner bootstrap have no HTTP surface

- **Location:** `apps/frontend/src/lib/auth/mfa-recovery.ts:1-17`; `apps/backend/src/smart_rag_api/auth_admin/mfa_recovery.py`; `apps/backend/src/smart_rag_api/auth_admin/bootstrap.py`
- **Evidence:** `MFA_RECOVERY_HTTP_ENABLED = false`. Recovery and `bootstrap_owner` exist as services without routers (GAP-07-07/08).
- **Impact:** Required MFA for owner/admin/upload cannot be recovered in-product. Operators will use SQL/`service_role` (forbidden) or lock the company out. First-owner bootstrap is undefined for production.
- **Remediation:** AAL2 owner/admin recovery with rate limits and Auth Admin isolation. Keep bootstrap operator-only. Document break-glass; do not ship MFA-required production without it.
- **Production blocker:** yes for MFA-required production users

## PRD-H-027 — No god-file, complexity, or 300-line documentation gate

- **Location:** `.cursor/rules/70-documentation-standards.mdc`; `.cursor/rules/10-python-quality.mdc`; `pyproject.toml` Ruff `select`; `scripts/check_docs.py`; `tests/contract/test_docstrings.py`
- **Evidence:** Ruff selects `B,D,E4,E7,E9,F,I,RUF,S,UP` — not `C901`. Docstring CI checks **presence** only. `check_docs.py` has no max-line split. At `09a102a`, 23 authored `.py`/`.ts`/`.tsx` files are ≥800 lines; 11 docs are ≥300 lines (Phase 6 evidence is 1259).
- **Impact:** The project's own “split past 300 lines / no catch-all file” rule is unenforced. Defects such as C-009 (empty `QueryGraphDeps`) and C-014 (`asyncio.run`) sat inside 800–1800 line modules. Future ACL and event-loop bugs will hide the same way.
- **Remediation:** Architecture test: fail authored runtime modules above an agreed cap (start at 800, ratchet toward 400) excluding `generated/`. Enable Ruff complexity on new code. Fail docs/check on Markdown >300 lines outside an explicit evidence exception list, then split those exceptions by packet.
- **Production blocker:** no for a labeled local RC; High before a multi-engineer production code line — see [code-quality](./domain/code-quality.md)

## PRD-H-028 — Runtime god files mix transport, retrieval, and graph compile

- **Location:** `apps/frontend/src/lib/api.ts` (1819); `packages/core/src/smart_rag_core/retrieval/hybrid_run.py` (1251); `lightrag_adapter.py` (1232); `apps/agents/src/smart_rag_agents/query/nodes/pipeline.py` (959); `apps/backend/src/smart_rag_api/services/sse_stream.py` (842); `query_routing/branches.py` (839)
- **Evidence:** `api.ts` exports query SSE, documents, crawl, admin, tables, tools, and usage in one module. `sse_stream.py` owns persist-then-flush **and** compiles the query graph with unbound retrievers. `pipeline.py` owns every query node plus `_run_coro`. `hybrid_run.py` also `SET ROLE postgres` for temporal metadata.
- **Impact:** Thin-router / one-concern rules from `05-monorepo-boundaries.mdc` and `10-python-quality.mdc` are violated at the hottest paths. Reviewers cannot see the production retrieve wiring without reading a thousand-line file.
- **Remediation:** Split **after or as a dedicated PR from** C-009/C-014 fixes. Extract a `build_query_graph_deps()` with a contract test that Hybrid/Graph/table/gateway are non-null. Split `api.ts` by surface. Do not combine refactors with fusion or sandbox behavior changes.
- **Production blocker:** no by itself; High because it conceals production blockers already on the Critical list

## PRD-H-029 — Unbound gateway still emits `verified` from mock answer + skipped verifier

- **Location:** `apps/agents/src/smart_rag_agents/query/nodes/pipeline.py:760-804,878-937`; `packages/core/src/smart_rag_core/query_answer/generate.py:75-77`; `packages/core/src/smart_rag_core/query_answer/verifier.py:113-114`
- **Evidence:** When `model_gateway` is `None`, generate uses `mock_answer_payload` (`caller is None`). Verifier sets `caller = None` and `run_verifier_batch` returns the payload unchanged. If deterministic checks pass, terminal is `verified`. Live SSE compiles empty `QueryGraphDeps` (C-009), so this is the production chat path.
- **Impact:** The UI can show a verified answer that never called OpenAI and never retrieved Hybrid evidence. Faithfulness dashboards that key off `verified` will be green and false.
- **Remediation:** Fail closed: unbound gateway or unbound retrievers must be `verified_partial` / `insufficient_evidence`, never `verified`. Require a non-null gateway before that status.
- **Production blocker:** yes (pairs with C-009)

## PRD-H-030 — Embedding ledger does not skip a completed batch

- **Location:** `packages/core/src/smart_rag_core/ingestion/embeddings/service.py:121-154`
- **Evidence:** Every call inserts a `pending` ledger row, then `asyncio.run(self._gateway.embed(...))`. There is no read of a prior `completed` row for the same `operation_key` / `chunk_set_hash` before the provider call.
- **Impact:** Worker crash/retry after a successful embed re-spends OpenAI and re-reserves budget. The ledger is an accounting log, not an idempotent skip-cache.
- **Remediation:** SELECT completed ledger + stored vectors first; skip the provider when hashes match. Keep fail-closed if vectors are missing.
- **Production blocker:** no for a demo; yes before live embeddings at any volume

## PRD-H-031 — Document delete HTTP does not exist; Storage bytes remain

- **Location:** `apps/frontend/src/lib/citation-drawer.ts:16-18`; `apps/frontend/src/lib/api.ts` (no `deleteDocument`); OpenAPI `/documents/{document_id}` is GET-only
- **Evidence:** Copy states GAP-07-14. Frontend tests assert the client does not export delete. Quarantine cleanup can `delete_object`; user/offboard document delete has no FastAPI route and no Storage purge of promoted objects.
- **Impact:** A company that must remove a file cannot. ACL hide is not deletion. Offboarding and mistaken uploads leave bytes in Storage and vectors in pgvector/ParadeDB until an operator runbook (unproven).
- **Remediation:** Owner/admin delete RPC: tombstone document, drop current_version, enqueue Storage + BM25 + graph cleanup with the existing tombstone SLA. Do not add a member self-serve wipe without dual-control.
- **Production blocker:** yes for any tenant that needs deletion/offboarding

## PRD-H-032 — Operator AWS access keys were pasted in chat and must be rotated

- **Location:** `docs/development/phase-10-managed-staging-evidence.md:179-181`
- **Evidence:** The evidence file records that keys for IAM user `Muna` / profile `Nagdy-iam` were pasted in chat, are **not** in git, and must be rotated. This pack does not reproduce secret material.
- **Impact:** Anyone with that chat history can call AWS as that operator until rotation + credential-report proof. Staging account blast radius includes the live EC2, CloudFront, and KMS artifacts already applied.
- **Remediation:** Rotate the access keys now; disable the old pair; confirm CloudTrail. Never paste long-lived IAM user keys into chat again (SSO/`aws login` or OIDC).
- **Production blocker:** yes until rotation is proven

## PRD-H-033 — Audit export is still HMAC; live KMS/Object Lock anchors are unproven

- **Location:** `packages/core/src/smart_rag_core/security/audit_export.py:306`; `tests/contract/test_phase10_packet5.py` asserts `"kms": False`
- **Evidence:** Postgres triggers block UPDATE/DELETE on the chain (good). The running exporter writes `"kms": False`. Phase 10 packet 5 treats live KMS/Object Lock as a gate, not a wired job. SNS/Secrets Manager rotation Lambda were not proven subscribed in this pass.
- **Impact:** `app_api` cannot tamper. A compromised superuser DSN (H-016) can. There is no independent WORM head in the running app.
- **Remediation:** Ship the SSM/KMS anchor job; prove GetObject fails after overwrite; keep HMAC labeled HMAC until that probe is green.
- **Production blocker:** yes for the signed audit-integrity invariant; no for a local RC demo
