---
title: OpenAI data governance
owner: product-owner
status: accepted
last-reviewed: 2026-09-09
audience: client-approver, security
approver: "user (Cursor chat; Phase 1–5 mandate; no legal name provided)"
approval_date: 2026-08-13
policy_version: openai-gov-v1
real_company_content_external_processing: laptop-pdf-overlay-accepted
---

# OpenAI data governance

**Status: accepted for this laptop PDF overlay (2026-09-09).** Framework
from 2026-08-13 remains. The product owner named this Cursor session as
approver for sending **this one** `real_company` PDF through the laptop
Hybrid path. Org console Data Retention / ZDR tabs were **not** readable
via the API key (HTTP 404/403). Rows below record public API defaults the
owner accepted, plus residual 30-day abuse monitoring. **ZDR is not
claimed.**

Related: [SUBPROCESSOR_GOVERNANCE.md](./SUBPROCESSOR_GOVERNANCE.md) · [Phase 3 evidence](../development/phase-03-ingestion-evidence.md) · [docs index](../README.md)

## 1. Covered OpenAI data flows

| Flow ID | Application path | Exact data fields sent | Trigger | Gate |
| --- | --- | --- | --- | --- |
| OAI-EMB | Shared model gateway embeddings | Contextual embedding string (title + heading path + passage); no raw file bytes | Ingestion after scan + governance approval | `external_processing_allowed` |
| OAI-CHAT | Query answer / summary / verifier | Bounded authorized evidence passages, citations IDs, user question | Chat run (Phase 6+) | Same + budget reservation |
| OAI-RERANK | Accuracy-first rerank | Candidate passage texts (top-20 bound) | Hybrid retrieval (Phase 4+) | Same |
| OAI-EXTRACT | LightRAG extraction callbacks | Graph-eligible chunk text only | Phase 5 graph indexing | Same + graph eligibility |
| OAI-SUPPORT | Provider support/abuse logs | Provider-side abuse monitoring of prompts/responses | Any live API call | Org retention/ZDR setting |

No undocumented company-content path to OpenAI is authorized. Direct SDK use outside the shared gateway is forbidden.

## 2. Provider settings matrix (do not invent org commitments)

Public defaults below are from OpenAI primary docs as of 2026-09-09
([Your data](https://developers.openai.com/api/docs/guides/your-data)).
Live org/project console Data Retention and ZDR tabs were not readable with
the configured API key (`/v1/organization` 404, `/v1/organization/projects`
403). The product owner accepted these recorded values for **laptop ingest
of this one PDF** on 2026-09-09. Staging and production remain prohibited
until a console/DPA review.

| Setting | Public / documented default | Org/project value | Verification status | Source | Verification owner |
| --- | --- | --- | --- | --- | --- |
| Training on API customer content | Not used for training by default (since 2023-03-01) | accepted public default; no training opt-in claimed | verified-accepted 2026-09-09 | [Data controls](https://developers.openai.com/api/docs/guides/your-data) | product-owner (Cursor chat) |
| Abuse-monitoring retention | Up to 30 days unless ZDR/MAM approved | accepted residual 30-day window | verified-accepted 2026-09-09 | Same | product-owner (Cursor chat) |
| Zero Data Retention (ZDR) | Opt-in; prior OpenAI approval; endpoint-limited | not enabled; not claimed | verified-accepted as off 2026-09-09 | Same | product-owner (Cursor chat) |
| Data residency / region | Eligible customers may pin residency | default API region; no pin claimed | verified-accepted default 2026-09-09 | Same | product-owner (Cursor chat) |
| Encryption in transit/at rest | TLS + provider-controlled at-rest controls (public claims) | accepted public claims | verified-accepted 2026-09-09 | OpenAI trust/security pages | product-owner (Cursor chat) |
| DPA / enterprise MSA | Available to qualifying customers | not attached in-repo; owner accepted residual | verified-accepted without DPA-in-repo 2026-09-09 | OpenAI legal / sales | product-owner (Cursor chat) |
| Incident contact | Provider status + account team | product-owner | verified-accepted 2026-09-09 | — | product-owner (Cursor chat) |
| Deletion / export | Account deletion and ZDR endpoint rules | residual 30-day abuse logs; ZDR off | verified-accepted 2026-09-09 | Data controls | product-owner (Cursor chat) |
| Subprocessors | OpenAI published subprocessors | accepted published list | verified-accepted 2026-09-09 | OpenAI trust portal | product-owner (Cursor chat) |

**Rule:** Staging and production still cannot send real company content until a
console/DPA review. This laptop overlay is a named/date acceptance of the
public defaults above, not a ZDR claim.

## 3. Data categories

Policy version: `openai-gov-v1`. Category provenance must record uploader attestation, authority, reviewer (when required), expiry, and re-review trigger.

| Category ID | Description | Disposition | Authority | Local-only alternative |
| --- | --- | --- | --- | --- |
| CAT-PUBLIC-CORPUS | Ordinary company knowledge intended for Hybrid/Graph search | allowed after attestation + clean detectors | member+ with upload rights; owner/admin for URL | none |
| CAT-INTERNAL-OPS | Internal process docs without regulated markers | allowed after attestation + clean detectors | member+ | none |
| CAT-PII-ROUTINE | Business contact PII incidental in docs | mandatory-review | owner/admin review | redact before upload |
| CAT-PAYMENT | Payment-card numbers / financial account secrets | prohibited | n/a | never upload; purge quarantine |
| CAT-NATIONAL-ID | National identifiers (configured patterns) | prohibited unless owner exception ADR | owner exception only | local-only store (not in v1) |
| CAT-CREDENTIALS | API keys, passwords, private keys | prohibited | n/a | rotate + purge |
| CAT-HEALTH | Health/regulated markers (configured) | prohibited unless ADR | owner + ADR | out of scope v1 |
| CAT-UNKNOWN | Missing/contradictory/expired attestation | mandatory-review (deny external) | owner/admin | remain quarantined |
| CAT-SYNTHETIC | Licensed/synthetic fixtures for CI | allowed for mock/external test keys only | engineering | preferred for all Phase 3 proof |

Exceptions require an ADR and named owner approval; they never flip deny-by-default for missing evidence.

## 4. Deterministic local detector coverage

Detectors are layered gates, **not** complete semantic classification. Detection never auto-approves.

| Detector | Patterns (version `detectors-v1`) | FN limit (documented) | FP limit (documented) | On hit |
| --- | --- | --- | --- | --- |
| Payment card | Luhn-valid 13–19 digit sequences with common issuer prefixes | High residual FN for exotic formats; not PCI scope claim | Prefer review over silent allow; FP may hold quarantine | quarantine + review |
| National ID | Configurable regex set (company-supplied); empty set = no match | FN when patterns not configured | FP on overlapping numeric IDs | quarantine + review |
| Credentials/secrets | `sk-`, `AKIA`, PEM headers, `password=`, bearer tokens | FN for novel secret shapes | FP on example placeholders in docs | quarantine + review |
| Health/regulated markers | Keyword/marker list from policy pack | FN for narrative clinical text | FP on ordinary vocabulary | quarantine + review |
| Client-specific labels | Owner-supplied denylist | FN when list stale | FP when over-broad | quarantine + review |

False-negative statement: pattern detectors **will miss** obfuscated or novel sensitive content. That is an accepted limit of this control layer, not a completeness claim.

## 5. `external_processing_allowed` decision (deny-by-default)

Inputs: category attestation, authority, policy version, detector results, scan evidence freshness, provider-setting verification status, approval expiry.

Deny (`false`) when any of:

1. attestation missing, unknown, contradictory, or expired;
2. category disposition is `prohibited` or `mandatory-review` without active owner/admin approval record;
3. any detector result is positive or unknown;
4. any required provider setting for the target flow is `unverified` **and** content class is real company content;
5. scan evidence missing/stale/failed;
6. policy version mismatch with signed packet.

Allow (`true`) only when all inputs are present, category is `allowed` (or approved exception), detectors clean, scan current, and for real company content every required provider setting is `verified`.

Default for missing evidence: **deny**. Never default `external_processing_allowed=true`.

## 6. Retention, deletion, incident

| Topic | Commitment |
| --- | --- |
| Application retention | Canonical corpus retention per `QUALITY_TARGETS.md` QT-RET-001 (365 days default) |
| OpenAI retention | Per org settings matrix; until verified, assume public 30-day abuse window may apply |
| Deletion | Canonical delete excludes retrieval immediately; provider-side deletion follows verified org controls |
| Incident contact | product-owner escalates to OpenAI account/status channels; local durable admin alerts per [LOCAL_ADMIN_ALERT_CONTRACT.md](./LOCAL_ADMIN_ALERT_CONTRACT.md) |
| Review schedule | Re-review this packet on provider policy change, new subprocessor, region change, or every 90 days |

## 7. Approver sign-off

| Field | Value |
| --- | --- |
| Approver | user (Cursor chat; Phase 1–5 mandate; no legal name provided) |
| Date | 2026-08-13 |
| Decision | Accept framework, categories, detectors, and deny-by-default decision |
| Real company content to OpenAI | **prohibited** in staging/production until console/DPA review |
| Approved exceptions | none |
| Synthetic fixture + mock gateway | allow for tests only (not real content) |

## 9. 2026-09-09 Hybrid PDF overlay named approval

Phase 3 Packet 9 obtained named/date owner approval in this Cursor session
after OpenAI `GET /v1/models` succeeded (200) and org console endpoints
returned 404/403. Public data-control defaults were re-fetched from
[Your data](https://developers.openai.com/api/docs/guides/your-data).

| Control | Overlay record |
| --- | --- |
| Approver | user (Cursor chat; product-owner; no legal name provided) |
| Date | 2026-09-09 |
| Decision | Accept residual 30-day abuse monitoring, no-training API default, ZDR off, laptop Hybrid embeddings/rerank/chat for this PDF only |
| `SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED` | set `true` in ignored `.env` / `.env.compose` after this record |
| `LANGSMITH_EXPORT_IO` | forced `false` |
| `WORKER_GRAPH_ENABLED` | forced `false` |
| ZDR | **not** enabled; not claimed |
| Staging / production | still prohibited |

Detector false-positive reviews for this PDF use hash-bound finding IDs
([ADR-detector-finding-reviews.md](../adr/ADR-detector-finding-reviews.md)).
`payload_ref.review_approved` is not an authoritative override.

Related: [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md)
