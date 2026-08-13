---
title: Subprocessor governance
owner: product-owner
status: accepted
last-reviewed: 2026-08-13
audience: client-approver, security
approver: "user (Cursor chat; Phase 1–5 mandate; no legal name provided)"
approval_date: 2026-08-13
policy_version: subprocessors-gov-v1
real_company_content_external_processing: prohibited
---

# Subprocessor governance

**Status: accepted (framework).** Together with [OPENAI_DATA_GOVERNANCE.md](./OPENAI_DATA_GOVERNANCE.md) this is the Phase 3 external-processing governance packet. Real company content remains **prohibited** from covered external processors until each flow's required org settings are `verified`.

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
| Trace retention tiers | Base 14 days; extended 400 days (Enterprise customizable) | unverified | unverified | product-owner |
| Input/output logging | Configurable; can hide/mask/anonymize client-side | require hide or anonymizer before real content | unverified org enablement | engineering-lead |
| Secrets redaction | SDK `create_anonymizer` | mandatory when tracing enabled | policy accepted; runtime Phase 6 | engineering-lead |
| DPA | Available via LangChain enterprise process | not attached in-repo | unverified | product-owner |
| Region / residency | Cloud vs self-hosted options | unverified | unverified | product-owner |
| Incident / deletion | API delete by trace ID/metadata; retention purge | unverified contacts | unverified | product-owner |

**Application rule:** Until verified, production-like runs keep LangSmith disabled or send only synthetic traces. Raw private source content is disabled or sampled only under an explicit development setting (global contracts).

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
