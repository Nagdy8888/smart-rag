---
title: ADR — Parser sandbox isolation
owner: engineering-lead
status: accepted
last-reviewed: 2026-08-18
audience: engineering, security, ops
---

# ADR: Parser sandbox isolation (accepted risk v1)

## Context

Phase 3 Packet 5 parses untrusted uploads (PDF, DOCX, PPTX, XLSX/CSV, HTML, Markdown/text, OCR) locally before chunking or external model calls. Parsers run in dedicated containers/subprocesses with **no network**, **no application/database/provider secrets**, **non-root** credentials, **read-only root**, **tmpfs** working storage, **seccomp/cap-drop**, and **PID/CPU/memory/file** limits.

## Decision

1. **Shared-kernel blast radius (v1 accepted):** Parser containers on the developer/EC2 host share the Linux kernel with API/worker processes. This is documented accepted risk for the trusted company-uploader model.
2. **Network isolation:** `docker run --network none` (or equivalent subprocess launcher). Parser containers **never** join `egress`, crawl-proxy, provider, Valkey, or database networks.
3. **Immutable parser image:** `infra/parser-sandbox` bundles pinned parser/OCR libraries and Tesseract trained data. Image tag `smart-rag-parser-sandbox:local` for development; production uses digest-pinned promotion.
4. **Patch cadence:** Monthly review of parser image base OS (Alpine), Tesseract, PyMuPDF, python-docx/python-pptx, openpyxl, and BeautifulSoup/lxml advisories. Emergency patch within 5 business days for critical applicable CVEs touching the parser image or host kernel. OS pin: [ADR-alpine-application-bases-trivy.md](./ADR-alpine-application-bases-trivy.md).
5. **Upgrade triggers (mandatory gVisor/Kata/separate-host review):**
   - Confirmed sandbox escape affecting parser workloads
   - Critical applicable kernel/runtime CVE without timely patch
   - Regulated external-upload requirement beyond trusted company uploader
   - Expansion to multi-tenant/no-trust uploads

## Consequences

- Parser failures return `failed` disposition with **zero canonical elements**; no partial publication.
- OCR/figure/chart pixels remain `media_only`; no visual understanding claims in v1.
- Docker unavailable in CI falls back to in-process adapter tests with explicit skip for live `--network none` proofs.

## Related

- [INGESTION_LIMITS.md](../ingestion/INGESTION_LIMITS.md) parser bounds
- [Phase 3 evidence](../development/phase-03-ingestion-evidence.md) Packet 5
- Plan Phase 3 Packet 5 acceptance checks
- [ADR-anydoc-local-parser-bakeoff.md](./ADR-anydoc-local-parser-bakeoff.md) experiment-only AnyDoc image; production parser selection unchanged

## Approval

| Role | Name | Date |
| --- | --- | --- |
| Engineering lead | user (Cursor chat; Phase 3 mandate) | 2026-08-13 |
