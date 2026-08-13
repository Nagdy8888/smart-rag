---
name: hybrid-graph-rag-phase-03-ingestion
phase: 3
status: pending
depends_on: [1, 2]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 3: Ingestion

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Treat this file as the only implementation scope for Phase 3. Later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before every work packet, state the requirement and concrete acceptance checks. Implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md)

## Relevant workspace skills

- [`.cursor/skills/implement-ingestion-pipeline/SKILL.md`](../../../.cursor/skills/implement-ingestion-pipeline/SKILL.md)
- [`.cursor/skills/implement-structured-table/SKILL.md`](../../../.cursor/skills/implement-structured-table/SKILL.md)

## Scope lock

**In scope:** Durable ingestion, scanning, governance gates, safe crawling, sandboxed parsing/OCR, typed elements/tables, chunking, embeddings, versioning, and deletion.

**Out of scope:** Hybrid ranking/tuning, LightRAG graph extraction details, query-agent routing, production frontend, and cloud deployment.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] Finalize and sign the OpenAI/LangSmith/Supabase/Vercel external-processing governance packet before any real company content reaches an external processor.
2. [x] Implement leased, idempotent, priority-aware jobs with heartbeat, reclaim, retry, backpressure, spend admission, and dead-letter handling.
3. [x] Implement quota-bounded quarantine, orphan TTL cleanup, fresh-signature malware scanning, category approval, safe promotion, append-only provenance, and durable local admin alerts.
4. [x] Implement approved-URL crawling only through the restricted proxy with redirect, DNS, peer-IP, scope, byte, page, and time bounds.
5. [x] Implement no-network parser/OCR isolation and typed format adapters with deterministic cleaning, format-specific source locators, and explicit media-only figure/chart diagnostics.
6. [ ] Implement hierarchical chunking, bounded parents/overlap, exact and near-duplicate provenance, typed Parquet artifacts, and stable replay IDs.
7. [ ] Implement governed embeddings, durable idempotent ParadeDB BM25 projection, verified `Hybrid Ready`, graph eligibility plus idempotent `Graph Pending` handoff, canonical/Hybrid version transitions, immediate deletion exclusion, and status APIs.
8. [ ] Exercise positive, failure, authorization, idempotency, crash-recovery, resource-limit, malware, sensitive-data, and SSRF fixtures.

## Cheap-model execution protocol

The eight checkboxes above are separate work packets. One model run may execute only one packet, in order. Before editing, the model must quote the active packet, restate its positive and negative acceptance tests, inspect every target path plus the Phase 1/2 exit records, and verify that both prerequisite phases are complete and user-accepted. This plan expansion does not satisfy those prerequisites.

Use [`docs/development/phase-03-ingestion-evidence.md`](../../../docs/development/phase-03-ingestion-evidence.md) as the canonical packet evidence and exit record. Packet 1 creates it and links it from `docs/README.md`. Every packet appends inspected files/schema/pins, primary-documentation links, exact commands and exit codes, fixtures, measured limits, authorization/idempotency/failure/crash tests, external calls and cost, unverified assumptions, rollback, and next-packet handoff.

For LangGraph/checkpointers, Supabase Storage, ClamAV, crawl/proxy libraries, parser/OCR/table dependencies, tokenizers, OpenAI embeddings, Arrow/Parquet, and ParadeDB:

1. inspect the repository pin, image digest, license, selected configuration, and current primary documentation;
2. run a real adversarial contract test for every capability used;
3. record the exact version/digest, configuration, source URL, and known limitations;
4. select operational bounds from signed targets plus representative measurements on supported hardware; and
5. stop rather than guessing a config key, parser guarantee, provider limit, coordinate system, retry semantic, or SQL API.

LangGraph is durable but not exactly once. Plain nodes restart from the beginning after interruption, checkpoints are committed at super-step boundaries, unfinished tasks may rerun, and deliberate replay can repeat downstream provider calls. Every node side effect therefore uses a stable operation/idempotency key and a durable result ledger. A checkpoint never proves an OpenAI, Storage, Supabase, or ParadeDB side effect ran exactly once. Raw files, complete OCR text, embeddings, signed capabilities, secrets, and large payloads never enter graph state; state stores typed IDs, versions, hashes, small counters, and durable Storage references.

Queue delivery, provider calls, Storage promotion, and Supabase-to-ParadeDB projection are also at least once. Worker leases prevent concurrent ownership only while valid; retries may duplicate provider cost; Storage operations cannot share the application database transaction; ParadeDB ACID does not span Supabase. Correctness comes from authoritative Supabase state, stable IDs/hashes, durable operation ledgers, upserts, verification, reconciliation, and authoritative candidate rechecks—not an exactly-once claim.

Create [`docs/ingestion/INGESTION_LIMITS.md`](../../../docs/ingestion/INGESTION_LIMITS.md) in packet 2 and update it in packets 3–7. It is the single source for lease/heartbeat/reclaim, attempts/backoff, worker concurrency, parser/OCR resources, archive expansion, format/page/sheet/row, crawl, ClamAV, OpenAI batch/retry, Parquet, and BM25 batch/verification bounds. Every entry records unit, default, hard maximum, source or benchmark, owner, failure route, and review trigger. Values fixed by the global contract or this phase must not change without ADR approval; unspecified values must be measured/approved before implementation and must not be silently invented.

The ingestion skill's instructions to perform real LightRAG mutation, mapping, `Graph Ready`, targeted cleanup, or clean-workspace rebuild do not apply in Phase 3. This phase ends the graph branch at exactly one durable `Graph Pending` handoff or `Graph Ineligible`. Phase 5 exclusively owns all graph mutation and `Graph Ready`.

Provenance is format-specific, not a false universal physical-coordinate promise:

- PDF uses page index plus verified text span and, when the selected parser reliably supplies it, normalized bounding boxes/rotation metadata.
- OCR uses page plus pixel/normalized boxes, confidence, engine/trained-data/preprocessing versions.
- DOCX uses ordered OOXML block/table/list paths and relationships; physical page geometry is unsupported unless a separately qualified renderer supplies it.
- PPTX uses slide, shape/group IDs, geometry, z-order, and a versioned reading-order decision; z-order alone is not asserted as reading order.
- XLSX uses workbook/sheet/cell/range, formula text, cached value and cache-authority state, hidden-sheet state, date epoch, type, unit, and number format.
- CSV uses file/record/column ordinals, original header text/ordinal, encoding/dialect/null policy, and line/byte spans when the selected parser proves them.
- HTML uses source URL/crawl version, DOM path, element order, and retained/removed-node diagnostics.
- Markdown/text uses source line/character spans, encoding decision/confidence, and parser token path where available.

Unsupported or uncertain coordinates are explicit diagnostics, never fabricated. Formula caches are not recalculated by the parser and are not authoritative when absent, stale, conflicting, unsupported, or unevaluated.

At most two bounded repair attempts may be made for the same external/integration failure. Skipped real-boundary tests, TCP-only health, mock malware success, unchecked parser output, an unbounded crawler, a green job with zero tests, or a partial index cannot close a packet.

## Work packet implementation contracts

### Packet 1 — external-processing governance sign-off

#### Packet 1 preconditions

- Phase 1 is complete and accepted; its governance drafts, quality targets, docs index, risk register, and evidence exist.
- Inspect the exact contracted/current settings for OpenAI, LangSmith, Supabase, and Vercel. Do not copy public defaults as company commitments.
- No real company content has been sent through a covered external flow before sign-off.

#### Packet 1 allowed outputs

- Final updates to `docs/security/OPENAI_DATA_GOVERNANCE.md` and `docs/security/SUBPROCESSOR_GOVERNANCE.md`.
- Data-category/authority, allowed/prohibited/mandatory-review, detector-coverage, incident/contact, retention/deletion, and external-processing decision records.
- Initial Phase 3 evidence and docs-index links.

#### Packet 1 forbidden outputs

- Pipeline code, live company-content provider calls, provider secrets, fabricated DPA/zero-retention/region settings, or `external_processing_allowed=true` as a default.
- Calling deterministic pattern detectors complete semantic classification.

#### Packet 1 ordered actions

1. Inventory every covered flow and exact data fields: embeddings, LangSmith traces/metadata, managed Supabase corpus/auth/storage, Vercel logs/client telemetry, and any support/abuse logging.
2. Record contracted retention/training, region/residency, encryption, backup, subprocessor, DPA/zero-retention/enterprise settings, incident contact, deletion/export, and verification owner for each provider. Mark unavailable facts unverified.
3. Define categories that are allowed, prohibited, or require owner/admin review. Include category provenance, uploader authority attestation, policy version, reviewer, expiry/re-review trigger, and local-only alternatives where approved.
4. Define deterministic local detector coverage and false-negative/false-positive limits for payment-card checksum patterns, national identifiers, credentials/secrets, health/regulated markers, and client-specific labels. Detection never auto-approves.
5. Define the `external_processing_allowed` decision as deny-by-default for missing, unknown, contradictory, expired, or positive-review-required evidence.
6. Obtain named owner/client approval and date for both documents. Record approved exceptions and review schedule.
7. Prove documentation links/lint and append the exact sign-off evidence.

#### Packet 1 acceptance checks

- Every provider/data flow has verified settings or an explicit blocker; no undocumented company-content path remains.
- Allowed/prohibited/review categories and the deny-by-default decision route are complete and versioned.
- Both governance documents contain named approver/date and reciprocal links, and the evidence records whether real content remains prohibited.
- No implementation or real-content external call occurred in this packet.

#### Packet 1 negative tests

- Missing/expired approval, contradictory category, positive sensitive detector, or unavailable provider setting cannot produce an allowed decision.
- Documentation checks reject `signed` or `verified` without approver/evidence fields.

#### Packet 1 stop routes

- Client/owner sign-off or contracted provider facts are unavailable: leave documents draft/proposed and stop before real content or packet 7.
- A requested exception changes security/data-processing scope: require ADR/plan approval.

#### Packet 1 required evidence

- Dated provider-setting sources, complete data-flow/category matrices, detector limits, both named approvals, documentation command results, and a declaration that no pre-approval real-content external call occurred.

### Packet 2 — durable leased jobs, checkpoints, admission, and dead letters

#### Packet 2 preconditions

- Phase 2 schema/roles/RLS/job tables/checkpoint store are complete and accepted.
- Inspect real queue columns, role grants, checkpointer pin/setup, budget schema, worker process model, and repository-defined test commands.
- Select and document lease, heartbeat, reclaim, retry, polling, concurrency, and job-size bounds in `INGESTION_LIMITS.md`. Heartbeat must leave enough margin to detect/renew before lease expiry under the longest qualified node.

#### Packet 2 allowed outputs

- Worker polling/claim/heartbeat/reclaim/release/cancel/dead-letter code in `apps/worker`.
- Core job repositories, admission/backpressure services, typed lease/idempotency contracts, and tests.
- Ingestion graph state/checkpointer wiring sufficient to validate a claimed job and execute a harmless boundary probe; later business stages remain unavailable.
- Job/lease state-machine documentation and evidence.

#### Packet 2 forbidden outputs

- LangGraph nodes polling/claiming/renewing/releasing jobs, Valkey as queue authority, bytes/local paths in graph inputs, unbounded retries, or a fake successful ingestion graph.
- Schema invention when Phase 2 objects are missing; return the gap to Phase 2.

#### Packet 2 durable invariants

- Claim uses `FOR UPDATE SKIP LOCKED`, ordered by priority, age, then estimated size, inside one transaction.
- Claim writes lease owner, opaque lease token, expiry, attempt count, heartbeat timestamp, and running state atomically.
- Every write from the graph validates job ID, lease token, non-expired ownership, operation key, and expected prior state.
- Lease loss or cancellation prevents new side effects and marks the graph run non-authoritative; already-started external work is reconciled through its ledger.
- Enqueue idempotency returns the existing logical job for the same operation key.
- Dead-letter replay creates a traceable new attempt/requeue action without erasing original failure evidence.
- Checkpointer setup runs once through the approved bootstrap path; runtime does not auto-migrate schema.

#### Packet 2 ordered actions

1. Create the limits document and state machine before code. Distinguish ingestion, BM25, graph-handoff, deletion/ACL, and cleanup priorities.
2. Implement atomic enqueue/claim/heartbeat/complete/fail/reclaim/cancel and terminal dead-letter transitions with typed domain exceptions.
3. Invoke the ingestion graph only with job ID, lease token, canonical document/version IDs, operation/version, and durable Storage reference.
4. Make every node rerunnable from its start and every side effect ledger-backed. Document checkpoint super-step boundaries and graph-version compatibility for in-flight runs.
5. Add daily ingestion spend admission, per-job estimate/reservation, durable true-up, default 100-pending cap, bounded worker concurrency, and visible queued/budget-exhausted behavior.
6. Prioritize deletion/ACL/security cleanup over normal ingestion. Pause additional graph-handoff admission when pending handoffs exceed 50 while continuing scan/parse/Hybrid work within budget.
7. Add bounded exponential backoff with jitter, retry classification, maximum attempts, safe diagnostics, and dead-letter actions from measured limits.
8. Prove real PostgreSQL concurrency and checkpointer contracts; mocks may supplement but cannot replace the boundary.
9. Append limits, state diagrams, commands, race/crash evidence, and unresolved later stages.

#### Packet 2 acceptance checks

- Competing workers never concurrently own the same valid lease; expired jobs reclaim; heartbeat renews; cancellation/lease loss blocks further writes.
- Duplicate enqueue/replay produces one logical job and no duplicate ledger effect.
- Priority/age/size ordering, 100-pending backpressure, budget reservation/true-up, graph-handoff pause, bounded retries, and dead-letter replay are observable.
- Graph state contains no raw/large/secret data and checkpointer retention/encryption policy matches the approved Phase 2/1 docs.
- Intentional zero-test selection and invalid lease/token fixtures fail.

#### Packet 2 crash tests

- Crash after enqueue, claim, checkpoint, heartbeat, node start, side-effect request, side-effect completion before ledger write, ledger write before node return, completion before lease release, and dead-letter replay.
- In every case, recovery yields one canonical logical result, stable IDs, bounded duplicate provider risk, and an auditable attempt history.

#### Packet 2 stop routes

- Phase 2 schema/roles/checkpointer or Phase 1 command surface is missing.
- Real `SKIP LOCKED`, lease-loss, or checkpointer replay cannot be tested.
- Operational bounds lack measured/approved evidence.

#### Packet 2 required evidence

- The limits/state-machine documents, inspected migrations/roles/pins, real concurrency traces, every crash result, job/ledger row counts before and after replay, budget/backpressure metrics, and exact lint/type/test/migration commands.

### Packet 3 — quarantine, ClamAV, governance hold, promotion saga, and alerts

#### Packet 3 preconditions

- Packets 1–2 pass; Phase 2 private buckets, upload capabilities, quotas, scan/provenance schema, Storage privilege ADR, and RLS are accepted.
- Verify official ClamAV image digest, license, engine/functionality level, signature database behavior, `clamd` protocol, scan-limit alerts, and `freshclam` update/reload memory on supported hardware.
- Update `INGESTION_LIMITS.md` with scan bytes/archive/recursion/files/time/concurrency, signature reload memory, quarantine, promotion, and cleanup bounds.

#### Packet 3 allowed outputs

- Upload-finalization checks, quarantine state/reconciliation, ClamAV/freshclam integration, scan events, category/authority gate foundations, Storage promotion saga, provenance/audit, durable admin notifications, Inbucket delivery, and tests.
- ClamAV/scan and promotion runbook documentation.

#### Packet 3 forbidden outputs

- Directory scanning, caller-supplied local paths, treating `PING` as scan readiness, treating limit-skipped/encrypted/unscannable files as clean, parser/OCR/chunking, or broad Storage secrets outside the approved boundary.
- Pretending Storage copy/move and application database writes are atomic.

#### Packet 3 ordered actions

1. Finalize incomplete uploads through Phase 2's approved capability/reservation contract. Verify immutable random path, expected user/session, object existence, actual size/hash/metadata, no-upsert rule, and quota reconciliation before enqueuing.
2. Set public lifecycle to `Uploaded`, then `Scanning` when the claimed scan begins. Do not report `Parsing` until scan gates pass.
3. Use official pinned ClamAV with persistent signature storage where required. Read engine/database versions and signed database metadata; `PING` proves only daemon response. Reject signatures older than 24 hours, incompatible functionality levels, failed self-check/reload, or unknown database state.
4. Scan the exact downloaded object stream/file, not a directory. Fail closed on malware, encrypted/uninspectable content, scan-limit exceeded/skipped, nested/archive bomb, timeout, daemon/update failure, stale signatures, or hash mismatch.
5. Persist append-only scan evidence including object hash, engine/functionality level, signature database IDs/timestamps, config/limit version, result category, bytes examined, and safe diagnostics. Re-scan when evidence is older than 24 hours or active signatures/config changed.
6. Record uploader category/authority attestation and metadata-level local detector results. Extracted-text detectors are integrated after packet 5; until then promotion requires an approved synthetic/reviewer decision and cannot enable external processing for real content.
7. Implement promotion as a resumable saga: record intent/idempotency; copy/move through the qualified Storage API to immutable `documents-originals` path; verify destination hash/size/metadata; transactionally switch the application object reference/status; then idempotently delete the quarantine source through Storage API. A reconciler repairs/cleans crashes at every step.
8. Never mutate/delete `storage.objects` metadata directly as object management. Promotion failure leaves one authoritative quarantined reference and no parse/index success.
9. Add bounded 24-hour never-finalized quarantine cleanup, quota release, append-only provenance, and anomaly notifications for upload spikes, byte spikes, accumulation, scan failures, and promotion/orphan failures. Local email uses Inbucket.
10. Test real ClamAV/Storage boundaries and append signature, saga, authorization, quota, and alert evidence.

#### Packet 3 acceptance checks

- Clean qualified content has current scan evidence and a verified promotion; EICAR/malicious, stale/incompatible database, healthy daemon with unusable databases, encrypted/unscannable, scan-limit, oversize/quota, hash mismatch, and archive-bomb fixtures remain quarantined.
- Promotion is replayable across every copy/verify/DB-switch/source-delete crash with one authoritative object reference and no orphaned accepted object.
- Cross-user/wrong-path upload and broad worker bucket access deny under real credentials.
- Orphan cleanup is idempotent and anomaly fixtures create durable admin notification plus Inbucket evidence.
- No parser, external model, BM25, or graph success is claimed.

#### Packet 3 stop routes

- Official immutable ClamAV pin, current signatures, scan-limit fail-closed behavior, Storage promotion API, or privileged Storage boundary cannot be verified.
- Phase 2 quota/capability/RLS semantics are missing or inconsistent.

#### Packet 3 required evidence

- ClamAV image/engine/functionality/signature/config identities, freshness/self-check/scan outputs, Storage capability and role tests, promotion crash ledger, object/hash reconciliation, quarantine/quota rows, audit events, notification/Inbucket records, and cleanup proof.

### Packet 4 — approved bounded crawling through the restricted proxy

#### Packet 4 preconditions

- Packets 1–3 pass; Phase 2 source approval and audit objects plus Phase 1 deny-by-default crawl proxy/egress ADR are accepted.
- Select crawl URL, port, host, redirect, DNS, robots, header, wire/decoded byte, page/depth, concurrency, and timeout bounds in `INGESTION_LIMITS.md`.
- Verify URL parser, DNS resolver, HTTP/TLS client, proxy peer-address exposure, decompression behavior, and RFC 9309 parser contracts.

#### Packet 4 allowed outputs

- Core crawl adapter/policy, proxy service changes, approved-source orchestration, immutable `web-snapshots`, crawl provenance/audit, and SSRF/limits tests.
- Crawl policy/runbook documentation and diagrams.

#### Packet 4 forbidden outputs

- Direct public egress from API/worker/parser, arbitrary URL tools, unapproved URLs, automatic redirects, cookies/credentials forwarded across hops, browser-only validation, or robots policy used as SSRF protection.
- LightRAG/BM25/query behavior.

#### Packet 4 ordered actions

1. Normalize once and reject non-HTTP(S), credentials/userinfo, fragments where disallowed, ambiguous IP forms, IPv6 zone IDs, malformed IDNA/hostnames, disallowed ports, overlong URLs, and scope violations.
2. Require an active owner/admin approval bound to normalized start URL/domain, requester, policy version, limits, and expiry. Members cannot broaden scope after approval.
3. Resolve all A/AAAA results for every request/hop and reject private, loopback, link-local, multicast, unspecified, reserved, metadata, IPv4-mapped-private, mixed-safe/unsafe answer sets, and prohibited ranges.
4. Connect to a validated/pinned address while retaining the hostname for TLS SNI/certificate validation; verify the actual peer IP. A mismatch or unobservable peer fails closed.
5. Disable automatic redirects. Re-run normalization, approval scope, DNS/IP, TLS/peer, method, and limit checks at every hop. Strip authorization, cookies, and sensitive headers.
6. Bound DNS/connect/TLS/first-byte/read/total time, redirects, depth, pages, concurrent requests, wire bytes, decoded bytes, headers, decompression ratio, content types, and snapshot count. Do not trust `Content-Length`.
7. Apply documented robots policy after security checks. Robots failure cannot broaden access; all cross-authority robots redirects use the same SSRF/scope gate.
8. Persist immutable snapshots plus canonical URL, redirect chain, title, content type, wire/decoded sizes, crawl timestamp, policy version, DNS/peer decision metadata, hash, and safe failure reason.
9. Prove proxy-only egress at the network boundary and append the selected bounds plus full negative fixture evidence.

#### Packet 4 acceptance checks

- An approved public fixture crawl stores bounded snapshots and complete provenance.
- Localhost/private/link-local/metadata, decimal/octal/IPv6-mapped forms, mixed DNS answers, DNS rebinding, peer mismatch, redirect-to-private, IDNA/userinfo confusion, loop, compression bomb, chunked oversize, unsupported MIME, robots failure, time/page/depth/byte excess, and proxy bypass all fail closed.
- API/worker/parser cannot reach the public fixture except through the proxy.

#### Packet 4 stop routes

- Actual peer IP cannot be observed/verified, network isolation cannot be proven, or a library auto-follows redirects/decompresses without enforceable decoded bounds.
- Requested crawl behavior exceeds approved egress scope.

#### Packet 4 required evidence

- Approved-source rows, proxy/network topology and commands, chosen limits, normalized URLs, DNS/redirect/peer decision logs, snapshot hashes, robots decisions, every SSRF/limit fixture result, and proof that direct egress fails.

### Packet 5 — parser/OCR sandbox and typed format adapters

#### Packet 5 preconditions

- Packets 1–4 pass; current scan evidence exists; parser isolation ADR is proposed/accepted.
- Select parser/OCR libraries and immutable sandbox image through adversarial fixture comparison, licensing review, coordinate fidelity, maintenance/security posture, deterministic output, and resource behavior.
- Record CPU/memory/PID/file/temp/expanded bytes/pages/sheets/rows/OCR pixels/time/concurrency and parser-specific bounds in `INGESTION_LIMITS.md`.

#### Packet 5 allowed outputs

- No-network sandbox launcher and format/OCR adapters in core; ingestion graph orchestration nodes in agents; typed element/locator/result contracts; versioned cleaning; parser isolation ADR; tests/docs.
- Temporary sandbox input/output handling with immediate cleanup and no durable local path.

#### Packet 5 forbidden outputs

- Network, provider/database/application secrets, root execution, writable root filesystem, ambient host paths, unsupported file interpretation, direct external calls, or flatten-only output.
- Claiming OCR/PDF malware sanitization, physical DOCX page coordinates, PPTX z-order as reading order, formula recalculation, or visual figure/chart understanding.

#### Packet 5 ordered actions

1. Accept only a canonical Storage object reference and expected hash. Fetch through the core gateway into a unique bounded temporary input owned by the graph runtime after lease/scan validation.
2. Launch parsers non-root with no network namespace, no inherited environment/secrets, read-only root, isolated temporary directory, seccomp/capability restrictions, PID/CPU/memory/file/expanded-size limits, and hard kill timeout. Parser containers never join provider/crawl/Valkey networks.
3. Emit a closed typed result: supported, conditional, unsupported, or failed; element tree; format-specific locators above; reading-order evidence; warnings; media regions; parser/version/config hashes; coverage accounting; and resource metrics.
4. PDF: preserve page/order/text spans and qualified boxes; detect scanned pages; remove repeated headers/footers only after cross-page evidence; represent tables/media/captions explicitly.
5. OCR: use pinned engine/trained-data/languages/DPI/preprocessing/OEM/PSM/thread settings; retain page, boxes, confidence, and original rendered-page hash. Low-confidence/unsupported scripts remain diagnostics.
6. DOCX: recursively traverse body blocks, nested tables/lists, relationships, revisions, headers/footers, and media/captions in logical order. Record unsupported layout/page geometry.
7. PPTX: traverse slides, groups, shapes, tables, notes/master content policy, geometry, z-order, and versioned reading-order decisions. Mark SmartArt/unsupported visual-only regions `media_only`.
8. XLSX/CSV: preserve original/unique internal headers and ordinals, typed values, formulas and cached values separately, cache authority, hidden/veryHidden state, number formats, units, 1900/1904 date epoch, timezone-naive status, merged cells, sheet/range coordinates, dialect/encoding/null policy, and malformed rows. Never calculate formulas.
9. HTML/Markdown/text: disable network/entity expansion/unsafe huge recovery, apply deterministic main-content/boilerplate policy, preserve DOM/token/line spans, original snapshots, removed-node diagnostics, encoding decision/confidence, code/lists/tables/links.
10. After local extraction, run the complete governance detectors. Missing/positive/unknown/contradictory content remains quarantined/review-pending and never reaches OpenAI. Approved content may complete the packet-3 promotion saga.
11. Update parser isolation ADR with shared-kernel blast radius, patch cadence, and mandatory gVisor/Kata/separate-host review triggers.
12. Run real sandbox escape/resource/parser fixtures and append pins, capabilities, limitations, outputs, and approval evidence.

#### Packet 5 acceptance checks

- Every supported format emits deterministic typed elements, reading order, format-valid locators, complete coverage/removal accounting, version hashes, and explicit unsupported/media-only diagnostics.
- Network/socket/DNS, secret/env, path traversal, fork/PID, memory, CPU, file/zip-bomb, timeout, malformed, encrypted, and parser-crash attempts fail within bounds without partial canonical publication.
- Scanned PDF OCR retains page/boxes/confidence; figure/chart-only regions remain `media_only`.
- Formula/cache, hidden sheets, duplicate headers, dates/epochs, mixed Arabic/English, revisions/groups, and coordinate round-trip fixtures preserve truth without fabricated geometry or values.
- Governance detectors run before promotion/external calls and fail closed.

#### Packet 5 stop routes

- Sandbox isolation or resource limits cannot be verified on the supported host.
- No parser candidate meets fixture/licensing/provenance requirements for a format; mark the format unsupported and obtain scope approval rather than silently degrading.

#### Packet 5 required evidence

- Dependency/image/license matrix, sandbox runtime configuration and network/secret/resource denial proof, parser capability/limitation matrix, golden typed outputs and coverage metrics per format, governance decisions, promotion result, ADR approval, and exact verification commands.

### Packet 6 — chunking, deduplication, and typed Parquet artifacts

#### Packet 6 preconditions

- Packet 5 typed element trees and format locators pass.
- Inspect the Phase 2 tokenizer/model ADR and typed-table schema.
- Pin/qualify Arrow/Parquet tooling and choose schema/compression/row-group/checksum/timestamp/decimal settings in `INGESTION_LIMITS.md`.

#### Packet 6 allowed outputs

- Final `docs/ingestion/CHUNKING_CONTRACT.md`, hierarchical chunk/dedup/table artifact services, explicit Arrow schema/manifest, stable-ID/provenance tests, and docs.
- Private Parquet artifacts under `table-artifacts`; no table query executor.

#### Packet 6 forbidden outputs

- Embeddings, retrieval ranking, DuckDB `TableQueryPlan`, arbitrary SQL, flatten-only tables, cross-document hard deletion, silent row/list/code/caption split, lossy timestamp/decimal coercion, or derived values presented as source values.

#### Packet 6 ordered actions

1. Define stable identities from source/version, element path/locator, normalized content hash, parser/cleaning/chunking/tokenizer versions, and fragment ordinal. Replay of identical inputs/config returns identical IDs.
2. Build document → section → passage hierarchy. Preserve heading ancestry, ordered child references, source locators, media/coverage diagnostics, and parent reconstruction.
3. Ordinary prose targets 200–400 embedding tokens; at least 90% of ordinary prose fixtures meet it; adjacent prose-sibling overlap is 40–60 tokens; normal passages never exceed 600; parents cap at 1,500.
4. Split tables only between rows while repeating headers, lists only between top-level items with introduction, and preserve code/caption atomicity. Oversized atomic fallback retains shared atomic ID, all coordinates/header/context, order, fragment flags, and reconstruction.
5. Exact-deduplicate by documented normalized SHA-256. Evaluate provisional 0.92 near-duplicate similarity only within a document/site version. Require at least 99% precision and 85% recall or fall back to exact-only. Keep representative plus every duplicate locator and `duplicate_of_chunk_id`; never hard-delete cross-document variants.
6. Materialize explicit Arrow tables and Parquet with typed source values. Preserve decimals with precision/scale, dates/timestamps with unit/timezone/epoch policy, nulls, non-finite diagnostics, original/unique headers, formulas/caches, hidden sheets, cell/range locators, units/currencies, row counts, schema/version, and artifact hash in columns/manifest.
7. Disable unapproved precision truncation. Run Arrow→Parquet→Arrow and Arrow→Parquet→qualified reader round trips, including DuckDB read-only sandbox contract tests where the later tool will consume artifacts; do not implement query planning.
8. Store artifacts through the approved Storage boundary and verify provider bytes/hash/manifest linkage.
9. Record cleaning/parser/chunking/tokenizer/dedup/table schema versions and metrics; append fixture evidence.

#### Packet 6 acceptance checks

- PDF header/footer and multi-page table, DOCX nested structures, PPTX groups/captions, Markdown code/list/table, HTML boilerplate, Arabic mixed direction, oversized atomics, exact/near/cross-document duplicates, and typed spreadsheet fixtures meet content/provenance gates.
- Chunk IDs are stable on replay; parent/atomic reconstruction and citation locator round-trip succeed.
- Fuzzy policy meets its precision/recall gate or exact-only fallback is active and documented.
- Parquet round trips preserve schema/values/provenance for decimals, nulls, dates/timezones, formulas/caches, duplicate headers, hidden sheets, units, and coordinates without unsafe coercion.

#### Packet 6 negative tests

- Mid-row/list-item/code/caption split without exception metadata, >600 normal passage, overlap outside bounds, orphaned provenance, cross-document hard delete, stale formula presented authoritative, timestamp truncation, or artifact/hash mismatch fails.
- DuckDB test sandbox blocks URLs, path traversal, globs, `ATTACH`, `COPY`, extension install/autoload, unsigned/community extensions, and mutation while allowing only the exact fixture Parquet.

#### Packet 6 stop routes

- Tokenizer/schema/tool pin is unavailable, table round-trip is lossy, fuzzy precision misses without exact-only fallback, or stable IDs change on replay.

#### Packet 6 required evidence

- Final chunking contract, tokenizer/schema/policy versions, per-fixture size/overlap/coverage/reconstruction metrics, stable-ID comparison, duplicate precision/recall or exact-only decision, artifact/manifest hashes, and both Parquet round-trip reports.

### Packet 7 — governed embeddings, BM25 projection, lifecycle/version transitions, and graph handoff

#### Packet 7 preconditions

- Packets 1–6 pass; Phase 2 embedding/model/dimension/normalization/index ADR and ParadeDB contract are accepted.
- OpenAI gateway, durable budget/reservation schema, canonical chunk schema, BM25 jobs/index versions, graph eligibility, and real least-privilege credentials are available.
- Select synchronous embedding batch size, request tokens, timeout, retry/concurrency, ledger, and BM25 projection batch/sample/tie-break/rebuild bounds in `INGESTION_LIMITS.md` using current provider limits and account tier.

#### Packet 7 allowed outputs

- Complete ingestion graph through canonical writes, governed embeddings, BM25 projection/verification, Hybrid lifecycle, graph handoff, replacement/deletion/ACL transitions, status APIs, and tests/docs.
- Core `Bm25Indexer` only; no query fusion or LightRAG mutation.

#### Packet 7 forbidden outputs

- External call before governance approval, SDK retries hidden beneath unbounded gateway retries, exactly-once billing claims, `Hybrid Ready` before cross-system verification, `Graph Ready`, LightRAG insertion/mappings/cleanup/rebuild, retrieval ranking/tuning, or signed capabilities/bytes/local paths in graph jobs.

#### Packet 7 ordered actions

1. Revalidate lease, current scan/governance approval, object/version hash, parser/chunk versions, authorization visibility, model/dimension, normalization, and budget before embedding.
2. Build contextual embedding input from title + heading path + original passage without changing citation text. Deterministically populate approved filenames/headings/glossary/regex-checksum codes and owner/admin aliases; exclude unreviewed graph entities.
3. Create a durable embedding operation ledger keyed by content/input-order/model/dimension/policy hash. Reserve budget once per bounded batch/job, record attempts/provider request IDs safely, reconcile actual usage, and tolerate timeout-after-provider-success without duplicate canonical rows. Provider duplicate cost remains observable.
4. Bound each request by current documented per-input/request/account limits and pinned tokenizer. Honor provider retry guidance without multiplying SDK and gateway retries; handle 429/`Retry-After`, timeout, partial/reordered batch response, dimension mismatch, and non-finite output.
5. Batch-write canonical chunks/vector/term/normalized projection state to Supabase and enqueue exactly one idempotent BM25 outbox operation in the same Supabase transaction.
6. Worker claims BM25 jobs with packet-2 lease semantics. Upsert/delete bounded batches through the version-qualified core adapter using stable canonical IDs and writer credentials. The Supabase-to-ParadeDB boundary is a reconciled saga, not one transaction.
7. Verify ParadeDB extension/index version agreement, row count and canonical-ID/content hash equivalence, structural index check where supported, deterministic sample queries with canonical-ID tie-break, current active version, and absence of unexpected rows. Structural verification alone is insufficient.
8. Mark `Hybrid Ready` only after canonical/vector/term plus BM25 verification. Transient projection failure stays in the preceding lifecycle with BM25 retry diagnostics; terminal failure becomes `Failed`. A stale projection can never bypass Supabase candidate recheck.
9. For current company-visible graph-eligible versions, enqueue exactly one `lightrag_index_jobs` row keyed by document version/content hash/pinned LightRAG/graph-pipeline version and report `Graph Pending`. Restricted/ineligible versions report `Graph Ineligible`. The handoff contains IDs/hashes/versions/internal reference only.
10. Replacement: build new canonical/BM25 state with `is_current=false`. Graph-ineligible verified versions may atomically flip current/Hybrid/BM25 visibility in Phase 3. Graph-eligible replacements remain non-current/Graph Pending until Phase 5 verifies graph and performs the full switch.
11. Deletion/ACL downgrade: atomically exclude Supabase/table retrieval, increment authorization/BM25 visibility generations, make graph maps ineligible, and enqueue high-priority BM25 cleanup. Verify projection cleanup while authoritative recheck prevents stale evidence.
12. Implement status APIs with public lifecycle plus separate scan/review/OCR/chunk/table/embedding/BM25/index-version/lag/retry/dead-letter/queue-age/graph-handoff diagnostics and safe role-scoped retry actions.
13. Append provider cost/idempotency, cross-database reconciliation, lifecycle, version, deletion, API, and graph-scope evidence.

#### Packet 7 acceptance checks

- Approved representative file and website versions reach `Hybrid Ready` only after complete canonical and cross-system BM25 verification.
- Timeout/retry/replay produces stable chunks/vectors/jobs/projection rows and auditable provider-cost attempts.
- Graph eligible creates exactly one `Graph Pending`; restricted creates `Graph Ineligible`; Phase 3 never emits `Graph Ready` or graph mappings.
- Version replacement exposes exactly one current version under the phase-specific switch rules.
- Deletion/ACL downgrade excludes authoritative evidence immediately and projection cleanup converges without stale evidence leakage.
- Status/OpenAPI contracts expose all Phase 3 states and diagnostics without leaking secrets/raw sensitive content.

#### Packet 7 negative tests

- Prohibited/unknown governance, stale scan, lease loss, budget exhaustion, provider dimension/non-finite/reordered response, Supabase transaction rollback, BM25 mid-batch crash, row/hash/version mismatch, invalid index, deterministic tie, stale delete, duplicate handoff, and unauthorized retry action all fail safely.
- Repository search/test fails if Phase 3 writes `Graph Ready` or populates Phase 5 mapping tables.

#### Packet 7 stop routes

- Governance, embedding pin, budget, ParadeDB version/API, real writer role, cross-system verifier, or authoritative recheck is unavailable.
- A later-phase graph/retrieval implementation appears necessary for false readiness.

#### Packet 7 required evidence

- Governance/scan/lease gate traces, embedding ledgers/reservations/usage/cost, canonical and outbox transaction proof, ParadeDB version/integrity/equivalence/sample checks, lifecycle/version/replay rows, deletion/ACL cleanup and stale-candidate denial, OpenAPI tests, and search proof of no Phase 5 writes.

### Packet 8 — complete adversarial, crash, throughput, and exit proof

#### Packet 8 preconditions

- Packets 1–7 have complete evidence and no unresolved launch-blocking stop condition.
- Real local boundaries run with supported resources; synthetic company-like fixtures are approved for tests.

#### Packet 8 allowed outputs

- Test fixtures/harnesses, crash/fault injection, bounded benchmark scripts, corrections to Phase 3-owned behavior/docs, and completed Phase 3 evidence.
- No new product feature.

#### Packet 8 ordered actions

1. Build a fixture manifest with source/license/hash, expected elements/locators/status, sensitivity class, allowed external-processing mode, and owning test for every required format/security/failure case.
2. Run format fixtures for PDF repeated headers/multi-page table, scanned OCR, DOCX revisions/nested structures, PPTX groups/SmartArt/media, XLSX/CSV formulas/caches/hidden sheets/duplicate headers/date epochs, HTML boilerplate, Markdown code/list/table, text encodings, Arabic mixed direction, media-only, oversized atomics, and duplicates.
3. Run malware/quarantine/governance fixtures: EICAR, stale/incompatible/reload failure, encrypted/unscannable, scan limits, archive bomb, oversize/quota/orphan, missing/prohibited/unknown/contradictory category, sensitive patterns, and reviewer denial.
4. Run crawl fixtures: localhost/private/link-local/metadata, encoded/mapped IPs, mixed DNS, rebinding, peer mismatch, redirect, IDNA/userinfo, robots, loops, compression/chunked oversize, MIME, timeout/page/depth/byte, and egress bypass.
5. Inject crashes before/after claim, heartbeat, Storage download, scan, promotion copy/verify/DB switch/source delete, parser, checkpoint, canonical transaction, embedding request/ledger, BM25 batch/verify, lifecycle flip, graph handoff, deletion/ACL update, and dead-letter replay.
6. Prove authorization/MFA/URL approval/RLS, idempotency, cancellation, lease loss, bounded resource use, no-secret/no-network sandbox, and zero-test failure.
7. Measure text and OCR pages/hour through verified `Hybrid Ready`, projection lag, queue fairness, resource peaks, and cost on the selected launch hardware. Require the signed 500 text pages/hour and 100 OCR pages/hour gates or obtain an approved capacity/envelope change.
8. Run repository-defined lint, strict type, unit/contract/integration/security/E2E, migration, build, docs/Mermaid, container, and plan-integrity commands.
9. Map every `Done when` clause to exact evidence, list managed/production-only items separately, request explicit user acceptance, and do not begin Phase 4 in the same run.

#### Packet 8 acceptance checks

- The full fixture and crash matrix passes with real Storage/Postgres/ParadeDB/ClamAV/proxy/sandbox boundaries; mocks are limited to provider-cost fixtures where explicitly approved.
- No partial/unverified version becomes current or Hybrid Ready; no stale BM25/ACL/deleted evidence survives authoritative checks.
- Throughput, lag, resources, and cost meet signed targets or the phase remains pending.
- Exit evidence contains exact commands/results, versions/digests, limits, provider calls/cost, authorization/failure/idempotency/fallback proof, unverified managed items, deviations, and rollback.
- User acceptance precedes completion/status change.

#### Packet 8 stop routes

- Any required boundary can only be skipped/mocked, a signed target misses without approved change, or a launch-blocking fixture fails after bounded repair.

#### Packet 8 required evidence

- The immutable fixture manifest, complete command log with exit codes, real-boundary service/version report, crash matrix, authorization/failure/idempotency/resource results, throughput/lag/resource/cost report, every `Done when` mapping, managed-only gaps, deviations/rollback, and explicit user acceptance.

## Authoritative lifecycle and transition ownership

Do not add public lifecycle enums for internal normalize/chunk/embed/project nodes. Use the public lifecycle plus orthogonal diagnostic/review fields:

- `Uploading`: Phase 2/3 upload admission exists but provider bytes are incomplete or unconfirmed.
- `Uploaded`: immutable quarantine object, actual size/hash, authorization, and durable ingestion job are confirmed.
- `Scanning`: Phase 3 scan claimed and current signature/limit checks are running.
- `Parsing`: clean current scan passed and local parser/OCR work is running; governance review may still block promotion/external work.
- `Hybrid Ready`: Phase 3 canonical vector/term state and ParadeDB projection both verify for the advertised current version.
- `Graph Pending`: Phase 3 created one valid idempotent Phase 5 handoff; this is not graph availability.
- `Graph Ineligible`: current policy/ACL prevents graph handoff while authorized Hybrid may remain available.
- `Graph Ready`: Phase 5 only.
- `Deletion Pending`: Phase 3 immediately excludes canonical/Hybrid/table evidence and enqueues derived cleanup; Phase 5 completes graph cleanup.
- `Failed`: terminal Phase 3 ingestion/BM25 failure with dead-letter/retry evidence. Review/quarantine holds remain explicit diagnostic states and are not fake success.

Graph-ineligible replacement current-pointer flips belong to Phase 3 after Hybrid verification. Graph-eligible replacement pointer/graph visibility flips belong to Phase 5 after graph mapping verification. Any implementation that writes `Graph Ready` or active LightRAG mapping state in Phase 3 fails scope checks.

## Cross-packet invariants

- Worker owns queue leases; graph nodes own orchestration only; core owns framework-independent adapters/repositories/gateways.
- Scan and local governance gates precede promotion/external processing; parser/OCR may inspect clean quarantine content only inside the no-secret sandbox.
- Original bytes and snapshots are preserved privately; temporary files are bounded and deleted; source text/locators remain distinct from search-normalized/contextual strings.
- Unknown, conditional, unsupported, stale, mismatched, or over-limit content fails closed with observable diagnostics.
- Every node and cross-system effect is idempotent/reconcilable under at-least-once execution.
- `Hybrid Ready` requires verified canonical and ParadeDB state; graph work stops at handoff.
- Deletion/ACL authority changes are immediate in Supabase even when derived cleanup is delayed.
- Numeric limits come only from signed targets or the limits document with measurement/approval.
- Each packet appends evidence. Phase 3 remains pending until packet 8 evidence is accepted.

## Phase sequence requirement

Phase 3 implements core ingestion: leased queues, budget/backpressure, pinned ClamAV with fresh signatures, data-category gates, a no-secret parser sandbox with accepted-risk ADR, approved crawl/egress, typed extraction, deterministic cleaning, structure-aware passages/parents, exact/fuzzy deduplication, typed tables, embeddings, durable ParadeDB BM25 projection, checkpoints, deletion, and status APIs.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update the phase evidence document specified by the repository documentation index with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

The following requirements are redistributed from the original comprehensive plan. They remain normative. Legacy section numbers are preserved so cross-references still resolve through the [section map](../hybrid-graph-rag_ab5281ef.plan.md#legacy-section-map).

## 5. Durable rich-ingestion graph

> **Phase 3 ownership note:** Phase 3 implements canonical ingestion through verified `Hybrid Ready`, graph-eligibility decisions, the idempotent `lightrag_index_jobs` handoff, immediate canonical deletion/ACL exclusion, and observable pending/fallback states. Real LightRAG insertion, graph evidence mapping, serialized workspace mutation, `Graph Ready`, targeted graph cleanup, and clean-workspace rebuild are specified and implemented only in [Phase 5](./05-phase-graphrag.md). Phase 3 must not fake `Graph Ready` or introduce a temporary LightRAG implementation.

`apps/worker` owns dispatch before graph execution: it polls and claims `pending` jobs with `FOR UPDATE SKIP LOCKED`, ordered by priority, age, and estimated size; sets `lease_owner`, `lease_expires_at`, attempt count, and lease token; runs the heartbeat/reclaim/release loop; and invokes the graph with an already-claimed `job_id`, lease token, and durable Supabase Storage reference. It does not download bytes or pass a worker-local path, so a later remote LangGraph deployment preserves the same input contract. Losing the lease cancels the graph before further writes. No LangGraph node polls, claims, renews, reclaims, or releases queue rows. Queue and graph execution are at least once: an interrupted node can restart from its beginning, so every external/database/Storage side effect validates the current lease and uses a durable idempotency/result ledger.

Implement the checkpointed ingestion `StateGraph` in [`apps/agents/src/smart_rag_agents/ingestion/`](../../../apps/agents/src/smart_rag_agents/ingestion/) with these stages:

1. Validate the claimed job/lease token, use the core Storage gateway to download the exact referenced object into graph-runtime temporary storage, move status to `Scanning`, validate metadata/magic bytes/archive expansion/page/sheet limits/timeouts, run the Section 4 current-signature malware scan, persist scan-version evidence, and quarantine failures. Move to `Parsing` only after a clean current scan passes. Never scan directories or trust a caller-supplied local path.
2. For owner/admin-approved URLs, send requests only through the dedicated crawl-egress proxy; enforce HTTP/HTTPS, block private/link-local/metadata IPs before and after DNS resolution, limit host scope, depth, pages, bytes, and duration, and respect crawl policy. Every redirect hop repeats DNS/IP validation and pins/checks the actual connection peer IP to prevent DNS rebinding.
3. Parse through format-specific adapters in a no-network, non-root sandbox subprocess/container with no application/database/OpenAI secrets, read-only root filesystem, temporary working storage, seccomp, PID/CPU/memory/file-size limits, and a kill timeout. OCR scanned pages under the same boundary. Emit a typed element tree—heading, paragraph, list/list-item, table/header/row/cell, code block, page/slide break, figure/media region, caption, and link—with format-specific locators and versioned reading-order evidence rather than flattening structure immediately. Never fabricate unsupported physical coordinates: DOCX may have logical paths without page geometry, PPTX geometry/z-order is not automatically reading order, and complex PDF boxes require parser qualification. Preserve adjacent caption/OCR text, but do not claim interpretation of figure/chart/diagram pixels in v1; mark regions with no usable text as `media_only=true` so downstream coverage can return the signed limitation notice instead of silently dropping them.
4. Clean and normalize with a versioned format policy while preserving untouched source text for citations. Remove repeated PDF headers/footers only after cross-page repetition checks. For HTML snapshots, retain the main article/body and remove navigation, cookie banners, menus, ads, sidebars, and high-link-density boilerplate using deterministic DOM rules; preserve removed-node diagnostics and the original snapshot. For XLSX/CSV, preserve typed cells, formula text and cached values as separate fields, cache-authority state, original/unique headers, hidden-sheet state, workbook/sheet/range coordinates, date epoch/timezone status, units/number formats, and versioned Parquet/table manifests. The parser never recalculates formulas or presents a missing/stale cache as an authoritative value.
5. Before promotion or any external OpenAI call, enforce the data-governance gate. Require uploader category/authority attestation, then run local deterministic detectors over metadata/extracted text for configured high-risk patterns such as payment-card checksums, national identifiers, credentials/secrets, health/regulated markers, and policy-specific labels. A positive, missing, contradictory, or unknown result remains quarantined for owner/admin review; only an approved `external_processing_allowed` decision may proceed. This is layered enforcement, not a claim of complete semantic classification. After clean scan and approval, promote with the idempotent Storage saga: copy/move to an immutable original path, verify destination hash/size, transactionally switch the authoritative application reference, then delete the quarantine source through the Storage API and reconcile crashes.
6. Build hierarchical document → section → passage chunks under [`docs/ingestion/CHUNKING_CONTRACT.md`](../../../docs/ingestion/CHUNKING_CONTRACT.md). Ordinary prose targets 200–400 tokens under the pinned embedding tokenizer, uses 40–60 tokens of overlap only between adjacent prose siblings, and has a hard 600-token passage ceiling. Keep heading ancestry on every child. Split long tables only between rows while repeating the header; split long lists only between top-level items while retaining the list introduction; never silently split a normal row/cell, list item, code block, or caption away from its element. An atomic element that alone exceeds 600 tokens may use a documented sentence/cell-fragment fallback, but every fragment retains the same atomic-element ID, full coordinates/header/context, order, and an exception flag so it can be reconstructed. Parent sections are assembled from ordered child references and bounded to 1,500 tokens for expansion; they are not blindly duplicated into every vector.
7. Deduplicate before indexing without deleting provenance. Use normalized SHA-256 for exact duplicates and an evaluated shingle/MinHash-style similarity threshold (provisional 0.92) for near duplicates within one document version or one crawled site/version. Keep one searchable representative plus every duplicate's source coordinates and `duplicate_of_chunk_id`. Do not hard-delete cross-document duplicates because authority/date may differ; cluster them at retrieval and apply quotas. Record cleaning, element-parser, chunking, tokenizer, and dedup-policy versions plus token/overlap/duplicate metrics.
8. Generate a lightweight contextual embedding string from document title + heading path + original passage while preserving untouched citation text. Populate `document_search_terms` deterministically from filenames, titles/headings, the approved SME glossary, and versioned regex/checksum extraction of product/reference/ticket/invoice codes; add only owner/admin-approved aliases from `search_aliases`. Materialize the Phase 2 versioned normalized BM25 fields for title, heading/aliases/codes, and body; do not copy unreviewed LightRAG entities into the Hybrid index.
9. Generate custom hybrid embeddings through the shared OpenAI gateway and batch-write canonical chunks/vector/term data to Supabase. In the same transaction, enqueue one idempotent `bm25_index_jobs` projection job keyed by document version, chunk-set hash, normalization version, active BM25 schema/index version, and operation.
10. The worker claims BM25 projection jobs with the same lease/reclaim discipline and invokes only the core `Bm25Indexer` adapter. Upsert/delete bounded batches into private ParadeDB using stable canonical chunk IDs, separate writer credentials, and no model calls. Supabase and ParadeDB are separate transactions, so replay/reconciliation is mandatory. Verify extension/index version agreement, canonical ID/content hash and row-count equivalence, structural index integrity where supported, deterministic sampled queries with canonical-ID tie-breaks, and absence of unexpected rows; only then mark `Hybrid Ready`. A transient projection failure remains in the preceding lifecycle state with a BM25-specific diagnostic/retry action; a terminal failure becomes `Failed`. Neither path invents a new public status or claims full Hybrid readiness.
11. If and only if the current version is company-visible and `graph_eligible`, create an idempotent `lightrag_index_jobs` row keyed by document version, content hash, pinned LightRAG version, and graph-pipeline version; otherwise mark `Graph Ineligible` and stop the graph branch.
12. Persist `Graph Pending` and end Phase 3 graph work after the idempotent job handoff. The job contains only canonical IDs, hashes, pipeline versions, and a non-secret internal source reference—never bytes, signed URLs, or worker-local paths. Phase 5 owns adapter insertion, graph evidence mapping, serialized mutation, and the transition to `Graph Ready`.
13. Retry transient failures with bounded jitter; send terminal failures to the durable dead-letter table with a safe retry action. Dense/exact-term degraded retrieval may remain available during a later ParadeDB outage, but a newly ingested version is not called `Hybrid Ready` before its BM25 projection verifies. Hybrid remains available when LightRAG indexing fails.

Chunking acceptance is content-based, not only a token-size assertion. Fixtures include a PDF with repeated headers/footers and multi-page table, DOCX nested headings/lists/table, PPTX grouped text/caption, Markdown code/list/table, Arabic mixed-direction document, and HTML pages with navigation/cookie/sidebar boilerplate. Tests prove source coverage after declared boilerplate removal, exact heading paths and reading order, intact table/list units, bounded overlap, stable chunk IDs on replay, exact/fuzzy duplicate behavior, parent reconstruction, and citation coordinates back to the original.

Canonical parsing and Hybrid jobs may execute in parallel across bounded worker slots. Admission enforces the daily ingestion budget, per-file estimate, and a default maximum of 100 pending jobs. When pending graph handoffs exceed 50, pause additional graph-job admission and prioritize scan/parse/`Hybrid Ready`; exhausted normal budget leaves work visibly queued. Phase 3 creates high-priority deletion/ACL cleanup handoffs charged to the separate maintenance reserve, while Phase 5 serializes and executes graph mutations.

The Phase 3 status API reports upload, scan, approval, parse/OCR, chunk/table, embedding, BM25 projection/index version/lag/retry, dead-letter, `Hybrid Ready`, `Graph Ineligible`, and `Graph Pending` state plus queue age and safe retry actions. Phase 5 adds measured graph-writer throughput, Graph Ready ETA/cost, workspace state, and graph-cleanup status.

The parser sandbox still shares the EC2 host kernel in v1. Record this accepted blast radius in [`docs/adr/ADR-parser-isolation.md`](../../../docs/adr/ADR-parser-isolation.md), patch host/kernel/parser images on a defined cadence, and treat any sandbox escape, critical applicable runtime/kernel CVE, regulated external-upload requirement, or expansion beyond the trusted company uploader model as a mandatory review for gVisor/Kata or a separate no-trust parser instance. Parser containers never join the provider/crawl/Valkey networks.

Do not checkpoint raw files, full OCR output, or large base64 blobs. State carries Storage keys and database IDs. Renaming a title, changing headings, changing extraction/chunking, or changing contextual-embedding inputs enqueues a new version/re-embedding job; old and new indexes coexist until verified switchover.

Document-version replacement in Phase 3 builds and verifies the new canonical/vector/term and BM25 projection with `is_current=false`. For graph-ineligible documents, one transaction may flip the canonical pointer, Hybrid visibility, and BM25 visibility generation after verification; the old BM25 projection is deleted asynchronously afterward. For graph-eligible documents, create the versioned `Graph Pending` handoff with retrieval eligibility off and keep the old version current; Phase 5 performs the atomic canonical/Hybrid/BM25-visibility/graph pointer switch only after graph insertion and mappings verify. Failure before that switch leaves the old version current.

Document deletion and ACL downgrade immediately exclude the affected version from Hybrid/table retrieval, increment the BM25 visibility generation, create a high-priority idempotent BM25 delete/update job, and make graph source-map entries ineligible in the same transaction. Every BM25 candidate is still batch-rechecked against Supabase, so stale projection rows cannot leak evidence while purge catches up. Phase 3 verifies BM25 cleanup; Phase 5 performs targeted graph deletion, resolver verification, quarantine/degradation, and clean rebuild. Canonical/Storage retention work never re-enables the deleted source.

### Example: what happens after a user uploads a PDF

1. The frontend requests the Phase 2-approved upload capability from FastAPI; its effective provider lifetime is reported truthfully.
2. FastAPI verifies that the user may upload and creates a `documents` row with status `Uploading`.
3. The browser uploads directly to `documents-quarantine`; OpenAI and privileged database/Storage credentials never reach the browser.
4. The frontend confirms completion. FastAPI verifies that the expected object exists, creates one durable `ingestion_jobs` row containing its bucket/path, and returns the document/job IDs.
5. The worker does not scan directories or download bytes. It atomically claims that database job and invokes the ingestion graph with the job ID, lease token, and exact durable Storage reference.
6. The graph's first node downloads that object through the core Storage gateway into temporary sandbox input, changes status to `Scanning`, verifies file signature/limits/current malware evidence, and changes status to `Parsing` only after the scan passes.
7. If the PDF contains selectable text, it is extracted directly. Scanned pages go through OCR while retaining page numbers.
8. The parser creates sections and passages with page coordinates. The UI can now show document structure but not yet answer from it.
9. After local parsing, governance approval, and the verified promotion saga, the authoritative original points to `documents-originals`. The graph embeds chunks, writes canonical vector/term data, and enqueues the private BM25 projection. Status becomes `Hybrid Ready` only after the ParadeDB upsert/cross-database hash/index-version/sample-query verification, so chat never advertises an incomplete Hybrid index.
10. For a company-visible graph-eligible PDF, Phase 3 creates one idempotent graph job and reports `Graph Pending`; restricted PDFs become `Graph Ineligible` while remaining Hybrid-searchable to authorized users.
11. Phase 5 consumes that job, owns graph success/failure and `Graph Ready`, and must preserve Hybrid availability. Replaying the Phase 3 handoff returns the same job rather than duplicating work.

For a website source, FastAPI first creates a `document_sources` row and an `ingestion_jobs` row containing the approved start URL. The worker claims and invokes the ingestion graph; a node uses the core crawl adapter to perform the safe bounded crawl, stores snapshots in `web-snapshots`, then follows the same canonical Hybrid stages and optional `Graph Pending` handoff. Each page keeps its canonical URL, title, headings, crawl timestamp, and content hash.

Use private Supabase Storage buckets for originals and URL snapshots. Issue only the Phase 2-approved user-JWT, signed, resumable, or backend-mediated upload capability under Storage RLS; the browser never receives privileged credentials, and the effective provider capability lifetime is not mislabeled as the shorter application reservation. Treat declared size as advisory; enforce the Phase 2 global/bucket/object/method, per-user rolling-byte, company-quarantine, and admission limits, then validate actual size, MIME signature, archive structure, parser limits, and malware status before promotion. Promotion is a verified resumable Storage saga because object copy/move cannot share the application database transaction. Oversize or never-finalized objects never parse, are purged through the Storage API by the audited idempotent quarantine cleanup after the configured default 24 hours, and count toward anomaly detection until removed. Pin and patch the ClamAV engine image, but update digitally signed malware databases with `freshclam` at least daily. Record engine version, functionality level, signature database versions/timestamps, limit/config version, result, bytes examined, and object hash in `document_scan_events`. Daemon `PING` proves responsiveness only. Production readiness fails when signatures are older than 24 hours, incompatible with the engine, unavailable after reload, or when scan limits cause skipped/unexamined content; the frozen signature fixture is CI-only. Detected, encrypted/unscannable, stale-signature, limit-exceeded, or over-limit objects remain quarantined and never parse/index. Re-scan a quarantined object before promotion whenever its prior scan is older than 24 hours or the active signature/config version changed. Signed download capabilities use the qualified provider lifetime and authorization is rechecked before issuance.

Every corpus write records uploader user/session, source/hash, declared data category, approval, scan version, and network provenance in append-only audit events. Members submit URL sources as pending requests; an owner/admin approves the domain/start URL before the crawl job exists. Configurable anomaly detectors alert admins on upload-rate/byte spikes, quarantine accumulation/orphan cleanup, repeated scan failures, unusual/new crawl domains, or abrupt corpus-write patterns through the durable in-app notification queue plus Inbucket locally; they do not silently auto-approve or label content as trustworthy.

### Exact file-storage layout

Files are never committed to Git and are not permanently stored in the FastAPI or worker containers.

- `documents-quarantine`: the browser uploads new files here through the Phase 2-approved scoped capability. Users cannot browse this bucket directly, and the capability's effective provider lifetime is recorded honestly.
- `documents-originals`: accepted, validated originals are promoted here. A versioned path such as `documents/{document_id}/versions/{version_id}/{safe_filename}` prevents name collisions.
- `web-snapshots`: downloaded HTML/text snapshots from approved URL crawls, grouped by source ID and crawl version.
- `table-artifacts`: versioned Parquet files generated from CSV/XLSX sheets, with typed schema, source sheet/range mapping, and no public access.
- `exports`: optional generated exports. Objects expire automatically unless the user explicitly keeps them.

In local development these buckets are provided by the local Supabase Docker stack and their bytes live in Docker-managed development volumes, outside the repository. In production the same logical buckets live in managed Supabase Storage. Database rows store the bucket name, object path, hash, media type, size, status, and version; application code passes IDs/paths rather than file bytes between stages.

The canonical text extracted from accepted files is stored as `document_chunks`; Hybrid embeddings/trigram/search-term data, normalized BM25 projection fields, and durable projection jobs live beside it in Supabase. Private ParadeDB stores only the rebuildable BM25 copy keyed to those canonical IDs. Typed spreadsheet data is private Parquet plus a manifest with workbook/sheet/cell provenance. Phase 3 writes canonical data, verifies the BM25 projection, and creates the source-level graph handoff. Phase 5 populates `lightrag_source_map`, `lightrag_chunk_map`, and `graph_evidence_map` from independent LightRAG chunks/vectors and enforces their authorized canonical resolution before answer generation or inspection.

Before sending any company content externally, finalize one owner/client-signed governance packet. [`docs/security/OPENAI_DATA_GOVERNANCE.md`](../../../docs/security/OPENAI_DATA_GOVERNANCE.md) records OpenAI retention/training terms, region/project controls, DPA/zero-retention or enterprise setting if required, allowed/prohibited/mandatory-review categories, PII handling/redaction, incident/contact process, and the `external_processing_allowed` decision. [`docs/security/SUBPROCESSOR_GOVERNANCE.md`](../../../docs/security/SUBPROCESSOR_GOVERNANCE.md) records LangSmith trace retention/redaction/DPA, Supabase region/encryption/backups/subprocessors, Vercel hosting/subprocessors, and which query/entity/usage/corpus-derived metadata each service receives. Enforce the packet through the Section 5 uploader attestation, local deterministic sensitive-pattern detector, owner/admin review state, and provider-specific gates before embeddings, graph extraction, tracing, or deployment. Prohibited content is rejected/purged under policy or uses an explicitly approved local-only path; unknown/contradictory cases remain quarantined. Document detector coverage and false-negative limits so this is not presented as a complete semantic classifier. Do not claim provider behavior beyond the signed settings.

## Phase deliver, review, and done gate

### Phase 3 — Ingestion

- Deliver: finalized owner/client-signed OpenAI/subprocessor governance packet, [`docs/ingestion/CHUNKING_CONTRACT.md`](../../../docs/ingestion/CHUNKING_CONTRACT.md), RLS-scoped uploads, enforceable quota/TTL quarantine, uploader/category provenance and URL approval, pinned ClamAV engine + daily `freshclam` + versioned scans/re-scan, leased `SKIP LOCKED` ingestion/BM25 queues, heartbeats/reclaim, priority/backpressure/budgets, no-secret parser sandbox and isolation ADR, dedicated crawl egress, local data-governance detectors/review gate, durable in-app/Inbucket anomaly alerts, typed elements/OCR/media-only diagnostics, versioned format cleaning, hierarchical passages/parents, exact/fuzzy dedup provenance, canonical/table provenance, normalized BM25 fields and verified ParadeDB projection, retries/dead-letter handling, canonical/BM25 deletion exclusion plus Phase 5 cleanup handoff, idempotent `Graph Pending` handoff, and status APIs.
- Review: contracted OpenAI, LangSmith, Supabase, and Vercel retention/region/encryption/subprocessor settings before the first relevant external flow; allowed/prohibited/mandatory-review categories; BM25 projection field/version/ACL scope, batch size, lag, replay and cleanup; signature freshness/failure/re-scan; quota/orphan cleanup and prohibited/unknown-category handling; member MFA and URL approval; parser shared-kernel boundary/upgrade triggers; egress/redirect/IP checks; structure/boilerplate/reading order; media-only limitations; chunk token/overlap/atomic-element/parent rules; duplicate precision; format/table behavior; crawl/OCR limits; queue fairness; costs; and idempotency.
- Done when: the full governance packet has owner/client sign-off before any real company content reaches OpenAI, LangSmith, managed Supabase, or Vercel under its covered flow; RLS-scoped upload, member-MFA, category/authority attestation, owner/admin URL approval, quota-bounded quarantine, orphan TTL cleanup, truthful upload-capability lifetime, resumable verified Storage promotion, and append-only provenance paths pass positive and negative authorization/crash tests; anomaly fixtures create durable local admin notifications; current-signature scan/re-scan evidence exists and malicious, stale, incompatible, encrypted/unscannable, scan-limit, oversize/quota, sensitive, missing/unknown-category, archive-bomb, parser-resource, SSRF, DNS-rebinding, redirect, decompression, peer-IP, and egress fixtures fail closed before external model work; leased `SKIP LOCKED` ingestion and BM25 jobs plus LangGraph checkpoints prove at-least-once heartbeat, lease-loss cancellation, reclaim, bounded retry, dead-letter replay, priority, backpressure, spend admission, and idempotent/reconciled replay without duplicate canonical chunks/projection rows/jobs; no-secret parser/OCR adapters and the complete format/chunk fixture matrix meet typed-element, format-specific locator, reading-order, token/overlap, parent, deduplication, typed-table/formula-cache, and citation-provenance gates while unsupported geometry and figure/chart-only regions are flagged rather than fabricated or treated as answerable text; representative approved file and website fixtures reach `Hybrid Ready` only after canonical vector/term plus BM25 extension/index-version, row-count/ID/hash/structural/sample-query verification; graph-eligible versions produce exactly one `Graph Pending` job while restricted versions are `Graph Ineligible`; canonical/Hybrid/BM25 visibility transitions expose one current version and graph-eligible replacements wait for Phase 5; deletion/ACL downgrade immediately removes Supabase retrieval eligibility, increments visibility generation, prevents stale BM25 evidence through authoritative recheck, and creates/verifies projection cleanup; signed ingestion throughput/lag/resource/cost targets pass; and status APIs expose every ingestion, review, retry, quarantine, BM25, Hybrid, and graph-handoff state. Phase 4 owns the fixed-size chunk/BM25 retrieval ablations, Phase 5 owns real graph mutation/`Graph Ready`, and Phase 11 re-confirms production provider settings.
