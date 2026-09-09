---
title: ADR — Detector findings and hash-bound false-positive reviews
adr_id: ADR-detector-finding-reviews
status: accepted
owner: engineering-lead
last-reviewed: 2026-09-09
approver: engineering-lead
approval_date: 2026-09-09
audience: engineering, security, reviewers
---

# ADR: Detector findings and hash-bound false-positive reviews

## Status

`accepted` for the Hybrid PDF overlay. Historical Phase 3 Packet 1
framework remains accepted. This records the security-semantic change that
`ingestion_jobs.payload_ref.review_approved` is no longer an authoritative
override.

## Context

Metadata and extraction detectors can hold a real-company PDF. False positives
must be reviewed by owner/admin against worker-authored finding ids. Local
`APP_ENV=local` is an export waiver, not a reclassification of `real_company`
jobs as synthetic.

## Decision

1. Persist append-only `app.detector_findings` and `app.detector_finding_reviews`.
   Findings store fingerprints and locators, never raw matched secrets.
2. An approval is active only when content hash, scan evidence, attestation
   policy, detector policy, and the complete positive-family set still match.
3. Parse governance and the embedding gate use persisted coverage, not payload
   override.
4. Owner/admin review transport is IDOR-safe 404 for members/viewers.
5. Local unsigned LangSmith waiver may export redacted traces of real jobs; it
   must not flip content class to synthetic.

## Consequences

- Overlay ingest stays stopped until Phase 3 Packet 9 named matrix approval.
- Extraction governance still runs in `hybrid_index` after promotion of a
  metadata-clean version. Metadata holds block promotion; extraction holds block
  embeddings. That ordering is recorded as an overlay deviation, not a fake
  `Hybrid Ready` path.

## Links

- [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md)
- [OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md)
- [SCAN_BEFORE_INDEX.md](../ingestion/SCAN_BEFORE_INDEX.md)
- [docs index](../README.md)
