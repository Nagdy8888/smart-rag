---
title: Subprocessor governance
owner: product-owner
status: accepted
last-reviewed: 2026-09-09
audience: client-approver, security
approver: "user (Cursor chat; Phase 1–5 mandate; no legal name provided)"
approval_date: 2026-08-13
policy_version: subprocessors-gov-v1
real_company_content_external_processing: laptop-pdf-overlay-accepted
---

# Subprocessor governance

**Status: accepted for this laptop PDF overlay (2026-09-09).** Together with [OPENAI_DATA_GOVERNANCE.md](./OPENAI_DATA_GOVERNANCE.md) this is the Phase 3 external-processing governance packet. Staging and production still **prohibit** real company content on covered external processors until a console/DPA review. This laptop overlay is named/date acceptance of public defaults plus application hide-I/O.

Related: [Phase 3 evidence](../development/phase-03-ingestion-evidence.md) · [docs index](../README.md) · [LOCAL_ADMIN_ALERT_CONTRACT.md](./LOCAL_ADMIN_ALERT_CONTRACT.md)

## 1. Covered subprocessors and data classes

| Subprocessor | Purpose | Data classes received | When | Gate |
| --- | --- | --- | --- | --- |
| OpenAI | Chat, embeddings, rerank, extraction | Bounded prompts/evidence; never raw Storage credentials | After governance allow | OpenAI packet |
| LangSmith | Traces, evals, prompt versions | Redacted run trees, latency, token counts, optional masked I/O, entity/usage metadata | Optional; off by default in mock | Trace redaction + allow |
| Supabase (local Docker) | Auth, Postgres, Storage, RLS | Full application + file bytes (trust boundary = local stack) | Always in local dev | Local-only; not “external” for real-content gate |
| Supabase (managed) | Auth, Postgres, Storage, backups | Corpus, Auth PII, Storage objects, audit | Staging/production | Region/DPA verified |
| Vercel | Next.js hosting | Public config, browser telemetry/logs, no privileged secrets | Frontend deploy | Hosting matrix verified |
| AWS (staging+) | EC2, SES, CloudFront/WAF | Runtime, email, CDN logs | Phase 10+ | Out of Phase 3 live use |

Local ParadeDB, Valkey, ClamAV, and crawl-proxy are private stack components, not customer-content subprocessors for this packet.

## 2. LangSmith settings matrix

Sources (2026-08-13): [Usage and billing / retention](https://docs.langchain.com/langsmith/usage-and-billing), [Data purging](https://docs.langchain.com/langsmith/data-purging-compliance), [Mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs), [Redact secrets](https://docs.langchain.com/langsmith/redact-secrets).

| Setting | Documented default | Org value | Status | Verification owner |
| --- | --- | --- | --- | --- |
| Trace retention tiers | Base 14 days; extended 180 days (Enterprise customizable, docs 2026-09-09) | accepted base 14-day default; workspace API returned no retention field | verified-accepted 2026-09-09 | product-owner (Cursor chat) |
| Input/output logging | Configurable; can hide/mask/anonymize client-side | application hide I/O; `LANGSMITH_EXPORT_IO=false` | verified-accepted 2026-09-09 | product-owner (Cursor chat) |
| Secrets redaction | SDK hide I/O plus application `process_inputs` hashes | mandatory; hide flags forced | verified-accepted 2026-09-09 | engineering-lead |
| DPA | Available via LangChain enterprise process | not attached in-repo; owner accepted residual | verified-accepted without DPA-in-repo 2026-09-09 | product-owner (Cursor chat) |
| Region / residency | Cloud vs self-hosted options | cloud default | verified-accepted 2026-09-09 | product-owner (Cursor chat) |
| Incident / deletion | API delete by trace ID/metadata; retention purge | product-owner | verified-accepted 2026-09-09 | product-owner (Cursor chat) |

**Application rule:** Until org rows are `verified`, keep `LANGSMITH_TRACING`
false for real company content in **staging and production**. Local
(`APP_ENV=local`, `MOCK_MODEL_MODE=false`) may enable tracing with operator
keys. Default export is hashes/counts/usage only. `LANGSMITH_EXPORT_IO=true`
is a laptop-only debug switch that attaches the user message, assistant
reply, prompts, and completions; staging and production reject it. Token
counts and estimated USD export even when the flag is false. See
[LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md) and
[ADR-local-langsmith-export-io.md](../adr/ADR-local-langsmith-export-io.md).
This local waiver is not org verification.

Dedicated hosted online evaluators are a second LangSmith export class.
They attach only to `smart-rag-agent-eval-online` and may receive the
bounded synthetic envelope (question, answer, reference, ≤12 excerpts of
≤600 characters). They must never receive real-company content, holdout
labels, BM25 snippets, graph prose, JWTs, API keys, DSNs, emails, or
signed URLs. The weekly hosted-judge spend cap is USD 2.00 with no
backfill. The normal `smart-rag` project must not gain these evaluator
rules. Rollback is disable/delete those two project rules, then delete
the two evaluator resources if unreferenced. 2026-08-26: both
dedicated rules exist only on `smart-rag-agent-eval-online`. The
application project `smart-rag-demo-3` has zero evaluator rules. The
hosted-judge spend cap could not be enforced on this org. See
[LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md)
and
[phase-06-agent-intelligence-evidence.md](../development/phase-06-agent-intelligence-evidence.md).

## 3. Supabase settings matrix

Sources: [GDPR / residency](https://supabase.com/docs/guides/security/gdpr-compliance), [DPA](https://supabase.com/legal/dpa), [Backups](https://supabase.com/docs/guides/platform/backups), Phase 2 evidence for local stack.

| Setting | Documented / local fact | Org/managed value | Status | Verification owner |
| --- | --- | --- | --- | --- |
| Local Docker region | Developer machine volumes | n/a | verified-local | engineering-lead |
| Managed primary region | Chosen at project create | unverified for Smart RAG project | unverified | product-owner |
| Encryption | TLS + provider at-rest | unverified contract detail | unverified | product-owner |
| Backups | Plan-dependent automatic backups | unverified | unverified | product-owner |
| Subprocessors | Supabase published list | unverified acceptance | unverified | product-owner |
| DPA | Available at supabase.com/legal/dpa | not attached in-repo | unverified | product-owner |
| Auth / Storage retention | Application QT-RET-001 + Auth provider | local proven; managed unverified | mixed | engineering-lead / product-owner |
| Incident contact | Supabase support | unverified local owner mapping | unverified | product-owner |

**Application rule:** Local Supabase may hold synthetic and development fixtures. Managed Supabase must not receive real company corpus until region/DPA/backup rows are `verified`.

### 3.1 2026-09-10 hosted quiz residual-risk exception

User named/date approval on 2026-09-10: quiz questions, expected answers, gold
metadata, and exam state may be stored in the existing hosted project that
already holds the laptop-runtime corpus. This exception does **not** change
the unverified region/DPA/backup/subprocessor rows above and does **not**
authorize staging or production evaluation UI. Recorded in
[ADR-hosted-webapp-evaluation-workspace.md](../adr/ADR-hosted-webapp-evaluation-workspace.md).

## 4. Vercel settings matrix

| Setting | Documented posture | Org value | Status | Verification owner |
| --- | --- | --- | --- | --- |
| Hosting role | Frontend + public Supabase config only | planned | unverified | product-owner |
| Logs / analytics | Platform logs; no privileged API secrets in NEXT_PUBLIC_* | unverified | unverified | engineering-lead |
| Subprocessors | Vercel published subprocessors | unverified acceptance | unverified | product-owner |
| DPA / region | Plan-dependent | unverified | unverified | product-owner |
| Corpus storage | None (forbidden) | n/a | accepted policy | engineering-lead |

Vercel must never receive Storage service-role keys, OpenAI keys, or canonical corpus bytes.

## 5. Category authority (shared with OpenAI packet)

Categories, detector limits, and the deny-by-default `external_processing_allowed` decision in [OPENAI_DATA_GOVERNANCE.md](./OPENAI_DATA_GOVERNANCE.md) apply to every row in this document. A flow is allowed only when both packets agree.

## 6. Decision and incident ownership

| Role | Responsibility |
| --- | --- |
| product-owner | Named approvals, DPA collection, exception ADRs |
| engineering-lead | Runtime gates, redaction defaults, verification evidence |
| owner/admin (app) | Category review queue, URL approvals |
| Verification cadence | 90 days or on provider/policy change |

## 7. Approver sign-off

| Field | Value |
| --- | --- |
| Approver | user (Cursor chat; Phase 1–5 mandate; no legal name provided) |
| Date | 2026-08-13 |
| Decision | Accept subprocessor inventory, matrices, and reciprocal OpenAI packet |
| Real company content to LangSmith / managed Supabase / Vercel covered flows | **prohibited** until required matrix rows are `verified` |
| Approved exceptions | none |
| Next review | 2026-11-11 or earlier on provider change |

## 8. Negative fixtures (normative)

| Fixture | Expected |
| --- | --- |
| LangSmith enabled without redaction config for real content | deny |
| Managed Supabase region unverified + real corpus upload to managed | deny |
| Vercel env containing privileged secrets | reject deploy config |
| Missing/expired packet approval | deny all external real-content flows |
| Status `signed`/`verified` without approver + evidence fields | documentation check fail |

## 9. 2026-09-09 Hybrid PDF overlay named approval

LangSmith `GET /api/v1/info` and `/api/v1/workspaces` returned 200. Workspace
id `02a8641a-ecd6-462c-b80c-13beca9ebd90` exposed no retention-day field.
Application hide-I/O remains the control: `LANGSMITH_EXPORT_IO=false`.
Product owner accepted base 14-day metadata traces without source I/O for
this PDF.

`SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED=true` is set only in ignored local
env after this named/date record. Staging and production stay prohibited.
ZDR is not claimed.

Related: [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md)
· [LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md)
