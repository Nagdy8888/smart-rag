# Fix execution plan

Status: **proposed; implementation has not started**.

Prepared: 20 October 2026. Based on the [comprehensive review](README.md) and [remediation priorities](10-prioritized-remediation.md).

## Objective

Repair the reviewed answer-integrity, provider-governance, PDF-isolation, execution-lifecycle, and verification weaknesses, then improve the affected UI. Preserve factual answer coverage, authorized citations, bilingual behavior, existing source modes, and the accepted product design.

This document proposes the execution order and acceptance checks. It does not replace the canonical project plan, mark old packets complete, authorize deployment, or claim a completed fix.

## Execution rules

- Recheck current code and working-tree changes before starting each packet; review findings are a snapshot.
- Preserve existing completed to-dos. Associate repairs with the appropriate canonical phase and active packet before implementation; add evidence rather than rewriting historical completion.
- Use the current Phase 6 agent, Phase 3 ingestion, Phase 8 frontend, and Phase 9/10 verification contracts as applicable. Read the selected packet and its required shared contracts before code changes.
- The older `agent_brain_repair_8c84c1f7.plan.md` is explicitly superseded; do not execute it as the active brain plan.
- Make small, reviewable changes. Keep behavioral repairs separate from broad refactors and dependency upgrades where possible.
- Start with synthetic/local tests. Use an isolated integration target for database tests and live provider checks; never repurpose production data for destructive fixtures.
- Retain both a frozen original baseline and a cumulative patched result. Capture code/image, dataset, corpus, model, prompt, profile, and scorer versions.
- Do not accept a security/authorization failure to recover an answer score. Do not accept a targeted answer improvement that regresses the full fixed dataset.
- Preserve the accepted MFA-removal decision. Broader architectural restructuring and a nonce-CSP migration are separate follow-up decisions, not prerequisites for these repairs.

## Packet 0 — Establish a trustworthy baseline

- [ ] Record current commit, working-tree state, dependencies, configuration names, and existing failing checks without exporting secrets.
- [ ] Re-run the saved synthetic reproductions and the narrow tests around each affected path.
- [ ] Classify each existing red gate as a product defect, outdated contract/fixture, typing issue, or timing-sensitive test.
- [ ] Select a fixed regression corpus covering English/Arabic, ordinary prose, code, tables, figures, multiple sources, refusals, and correct-page citations.
- [ ] Record which hosted/authenticated checks can actually run and which prerequisites are missing.

**Deliverable:** baseline evidence and a finding-to-test map.

**Exit:** each priority issue has a current reproduction or documented source confirmation, and existing unrelated failures are separately recorded. Do not delay the trust-boundary fixes while cleaning unrelated formatting.

## Packet 1 — Ensure only the final checked answer can be released

**Findings:** AG-01, AG-02, AG-04, AG-05; verification wording from UI-04. **Depends on:** Packet 0.

**Implementation direction:** use deterministic presentation of immutable verified claims. Remove the model-based post-verification semantic rewrite rather than add another paid verifier round. Preserve headings, groups, code, tables, and figures through structured rendering and validated layout metadata; never manufacture headings that introduce new claims.

- [ ] Define one final release result containing checked claims, stable paragraph/claim IDs, authorized citation mappings, limitations, and release status.
- [ ] Stop restoring an unchecked original draft when verifier/release logic raises an unexpected exception.
- [ ] Return a typed verification-unavailable refusal unless already-checked claims with successfully persisted citations can safely be retained.
- [ ] Preserve paragraph-specific evidence; remove the global link-union/remap-to-paragraph-zero behavior.
- [ ] Eliminate silent truncation of native blocks. Fit content before final verification or explicitly mark supported content as incomplete.
- [ ] Ensure the SSE buffer, durable assistant answer, citation rows, replay, and historical transcript use the same final release artifact.
- [ ] Distinguish supported partial, verifier unavailable, persistence failure, deadline exhaustion, and source unavailable in public status/copy.

**Tests:** negation, relationship/order reversal, new lowercase claims, Arabic/mixed-language substitutions, three disjoint paragraph/source sets, over-cap code/table/figure blocks, and injected checker/persistence failures. Repeat through live stream, reconnect, and history restore.

**Exit:** no changed-meaning rewrite or unchecked draft can be released as verified; checked and displayed text/mappings agree. Model-call usage cannot increase as a consequence of this repair.

**Rollback/containment:** if presentation regresses, retain exact checked text and existing safe block rendering. Do not re-enable the unsafe rewrite or draft-release fallback.

## Packet 2 — Govern and account for every external AI request

**Findings:** SEC-01, AG-03, tracing failure from QA-01. **Depends on:** Packet 1's organizer decision; figure-boundary work can be prepared after Packet 0.

- [ ] Inventory actual provider sends across preparation, retrieval/embedding/rerank, answer, verification, figures, and ingestion.
- [ ] Remove the organizer provider send under Packet 1; verify that no alternative presentation path reintroduces uncounted calls.
- [ ] Move figure vision behind the complete external-processing decision, including provider-setting verification, scan/attestation/category/review requirements.
- [ ] Reserve/debit the appropriate job/batch budget before each permitted figure send and use the approved traced gateway.
- [ ] Perform completed-operation replay checks before provider work. Give each figure operation and provider attempt stable, appropriate identities.
- [ ] Record actual usage and conservative timeout-after-send/unknown-outcome accounting; reconcile on completion, cancellation, crash, and retry.
- [ ] Capture explicit pending/unknown/completed attempt state so an ambiguous provider outcome is not treated as a free retry.
- [ ] Close provider resources and preserve safe error reporting.

**Tests:** denied provider settings, missing attestation, prohibited category, exhausted budget, duplicate job delivery, retry after success, crash before/after send, provider timeout, and rejected output.

**Exit:** every permitted provider request is governed and durably accounted for; denied work sends nothing. Local operation replay does not repeat completed work. A crash after a provider accepted a request can create an inherently uncertain external outcome; use provider-supported idempotency where available, otherwise charge conservatively and avoid claiming universal exactly-once provider execution.

**Rollback/containment:** retain cropped images/captions without external descriptions when vision authorization/accounting is unavailable. Do not restore a direct ungoverned provider path.

## Packet 3 — Isolate PDF rendering and control its resource cost

**Findings:** SEC-02, BE-03. **Depends on:** Packet 0; integrate figure changes from Packet 2.

- [ ] Reuse or extend the parser sandbox boundary for page rendering and figure cropping, with no credentials, no network, and constrained filesystem access.
- [ ] Define a typed bounded input/output contract for render tasks.
- [ ] Stream source downloads with an enforced byte ceiling instead of buffering an unlimited response before validation.
- [ ] Enforce page geometry/pixels, memory, CPU, output bytes, timeout, and kill grace in the constrained execution path.
- [ ] Apply a preview-specific concurrency/admission policy, including degraded limiter behavior.
- [ ] Preserve the authorized single-page API and supporting-passage fallback.
- [ ] Prefer bounded on-demand rendering for the first repair. Add a version/page/render-keyed artifact cache only if measured preview latency/load justifies it, with authorization on every read.

**Tests:** malformed PDF, excessive page size, oversized source, stalled renderer, concurrent preview requests, cancellation, document deletion, ACL downgrade, and secret/network access attempts from the child.

**Exit:** render failures cannot exhaust or compromise the main API/worker; previews stay bounded and unauthorized/deleted sources cannot be returned.

**Rollback/containment:** temporarily show the authorized passage with a truthful page-preview-unavailable state. Do not fall back to parsing in a credential-bearing process.

## Packet 4 — Make execution ownership and lifecycle durable

**Findings:** BE-01, BE-02. **Depends on:** Packet 0; final answer/accounting integration follows Packets 1–2.

- [ ] Remove registry inputs/contexts on completion, cancellation, failed start, and conversation deletion. Bound any transient pending-state retention with a defined TTL/cap.
- [ ] Add an exclusive durable execution claim with owner token, lease expiry, renewal, and recovery semantics.
- [ ] Ensure every start path, including admission and attach/recovery, requires that claim.
- [ ] Stop on rejected authorization/claim transitions; a process without ownership replays/attaches rather than executes.
- [ ] Add ownership fencing to writes/usage transitions where needed so an old executor cannot continue authoritative work after losing its lease.
- [ ] Use additive migrations and explicit grants if the existing schema cannot express this safely.

**Tests:** two separate processes racing to start, stale owner after takeover, process crash, reconnect during restart, cancellation during claim, terminal-event races, budget settlement, and thousands of completed/deleted runs.

**Exit:** one authoritative executor per run; takeover does not accept stale-owner writes; one terminal result; bounded in-process retention; durable replay remains usable. Keep a single-executor deployment constraint until this proof passes.

## Packet 5 — Bound authentication refresh and patch dependencies

**Findings:** SEC-03, SEC-04. **Depends on:** Packet 0. Keep changes separately reviewable from run-ownership migrations.

- [ ] Add JWKS refresh single-flight, bounded invalid-key negative caching/cooldown, and appropriate token/header limits.
- [ ] Preserve legitimate key rollover and fail-closed signature verification under concurrent traffic.
- [ ] Re-run current dependency audits before choosing upgrades; advisory versions from the review may have changed.
- [ ] Patch reachable runtime dependencies first, then test/documentation tools.
- [ ] Record owner, exposure, rationale, and expiry for any retained exception.

**Tests:** burst of unknown key IDs, simultaneous valid rotation, unavailable Auth, expired cache, malformed/oversized tokens, and affected runtime/tool test suites after upgrades.

**Exit:** invalid requests cannot force one upstream fetch each; rotation still works; remaining dependency advisories have explicit evidence-based dispositions.

## Packet 6 — Restore all deterministic checks

**Findings:** QA-01, FE-01. **Depends on:** behavioral changes in Packets 1–5. Repair checks alongside their owner packet rather than postpone all testing until here.

- [ ] Fix strict typing at organizer/native-content/vendor boundaries without globally weakening type checks.
- [ ] Reconcile retrieval-call fixtures with the intended answer reserve; prove route envelopes still allow required retrieval/answer work.
- [ ] Inspect the media-route snapshot difference and update the expectation only if the intended behavior is established.
- [ ] Extract a cohesive ChatApp responsibility to satisfy its existing composition budget.
- [ ] Await the actual citation-image failure transition in its timing-sensitive test.
- [ ] Run formatting/import cleanup and the complete required local check commands.

**Exit:** formatting, lint, Python/frontend types, unit/contract tests, frontend tests, and production build pass. Missing mandatory integration evidence is reported separately and does not become a fabricated pass.

## Packet 7 — Improve affected UI and accessibility

**Findings:** UI-01, UI-02, UI-03, UI-04. **Depends on:** corrected answer status from Packet 1 and stable preview contract from Packet 3.

- [ ] On compact Ask, use one Sessions entry and prioritize conversation/composer space.
- [ ] Add accessible page zoom, fit controls, scrolling/panning behavior, and image retry within the current authorized single-page contract.
- [ ] Filter hidden/inert focus candidates, handle empty dialogs, and manage background and stacked-overlay focus.
- [ ] Verify final answer headings/groups remain readable without adding model rewriting.
- [ ] Verify accurate partial/refusal/error copy and supporting-passage availability.

**Tests:** authenticated desktop/mobile, actual zoom/text resizing, RTL/mixed language, keyboard and screen-reader checks, long answers/tables/code, failed preview retry, conversation switching, and historical citations.

**Exit:** the user can read and verify a source-rich answer on mobile/desktop, with reliable focus and truthful status. Preserve the existing visual identity.

## Packet 8 — Prove the complete repair and prepare rollout

**Findings:** QA-02, OP-01, OP-02; all preceding fixes. **Depends on:** Packets 1–7.

- [ ] Make required authenticated/database integration checks fail explicitly when prerequisites are absent; keep optional developer skips separately classified.
- [ ] Run the fixed full RAG regression with verbose per-question progress and stage-attributed loss; retry infrastructure crashes separately from content misses.
- [ ] Compare strict answer correctness, grounded facts, correct document/page citations, refusals, p95 latency, and provider cost against the frozen baseline and accepted project targets.
- [ ] Exercise isolated hosted RLS/role changes, deletion, provider denial, worker restart/reclaim, run takeover, SSE reconnect/cancel, and constrained rendering.
- [ ] Add SSM invocation completion/result checks and readiness/journey evidence to deployment automation.
- [ ] Correct the quick-start local-versus-hosted topology and frontend public build-time configuration instructions.
- [ ] Prepare migration sequencing, image identifiers, monitoring, rollback/containment, and the deployment evidence checklist.

**Exit:** exact checked commit/image and executed checks are recorded, mandatory skips are unresolved gates, no critical authorization/grounding/budget regressions remain, and full-set results meet the accepted targets. If a safety repair reveals previously hidden unsupported answers, classify that change openly and repair coverage within the safe boundary rather than restore unsafe behavior.

Deployment is a later concrete action. This planning request does not itself publish code, apply hosted migrations, or claim production readiness. Complete and present the reviewable local changes and rollout evidence first.

## Progress reporting

For each packet, report: behavior changed, files/migrations, acceptance checks with results, RAG accuracy/latency/cost changes where measured, and remaining live requirements. Check a task only after its evidence passes. Keep a concise current packet/finding status so unfinished work remains visible across sessions.

## Completion standard

The repair is complete when the exact released answer is checked and correctly cited; every external request is authorized and accounted for; PDF work is isolated and bounded; execution ownership and retention are safe; deterministic and required live checks pass; the full fixed evaluation meets accepted targets; and the affected UI is usable and truthful. A passing build alone is insufficient.
