# Prioritized remediation plan

See [scope and evidence conventions](README.md). This is a proposed implementation sequence, not a claim that fixes have been made. Existing approved plans and completed to-dos should remain intact; attach these findings to the appropriate current work packets.

## First: restore the answer trust boundary

**Owner:** query-agent/answer-release maintainer. **Findings:** AG-01, AG-02, AG-04, AG-05, UI-04.

- Prefer a deterministic formatter over a new model rewrite after verification.
- Ensure the exact released text and paragraph/source map are checked and persisted together.
- Fail closed on unexpected checker/release errors; distinguish supported partials from verification-unavailable refusals.
- Preserve native blocks or explicitly mark omitted content.
- Align UI trust language with actual checks, including generic exceptions and unavailable citations.

**Exit proof:** adversarial English/Arabic semantic cases; disjoint paragraph citation sets; native-block overflow; injected verifier/release/persistence failures; live, replayed, and restored historical answers match. Then run a fixed full answer-quality regression, not only the repaired subset.

## Second: put every provider call behind governance and accounting

**Owner:** provider gateway/ingestion maintainer. **Findings:** AG-03, SEC-01, QA-01 tracing failure.

- Route organizer work through the durable query attempt ledger, or remove that model call.
- Gate figure vision on the full external-processing decision and a job-level reservation.
- Check operation replay before sending; use stable artifact/attempt identifiers.
- Record usage and timeout-after-send results, including rejected output and retry cases.
- Keep provider errors sanitized and close provider-client resources correctly.

**Exit proof:** denied provider policy/budget produces zero sends; success, timeout, crash, retry, and replay settle once; provider usage totals match durable ledger and UI summaries; traced-helper contract passes.

## Third: isolate native document processing and bound preview costs

**Owner:** ingestion/security/backend maintainer. **Findings:** SEC-02, BE-03.

- Move crop/render into a credential-free, no-network constrained process.
- Enforce input bytes during streaming, plus pixel/memory/CPU/time bounds before expensive work where possible.
- Add preview-specific concurrency/admission controls.
- Consider immutable pre-rendered artifacts with authorization on every read.

**Exit proof:** malformed/oversize PDF and stalled render cannot affect API liveness or access secrets/network; repeated authorized preview load stays bounded; revocation blocks cached reads.

## Fourth: make run lifecycle safe for long-lived and scaled processes

**Owner:** backend/SSE maintainer. **Findings:** BE-01, BE-02, SEC-03.

- Expire/remove registry inputs and contexts at lifecycle completion and deletion.
- Add an exclusive durable executor claim with defined recovery behavior.
- Stop execution after failed ownership/authorization transitions.
- Coalesce and bound unknown-key JWKS refresh while preserving rollover.

**Exit proof:** multi-process race yields one executor; restart/reconnect/cancel produces one terminal; thousands of runs leave bounded state; invalid-key bursts cause bounded upstream fetches.

Do not enable additional query executor replicas before BE-02's proof. This restriction does not imply that the currently deployed app is multi-replica.

## Fifth: repair deterministic gates and dependency exceptions

**Owner:** relevant module owners, coordinated by CI maintainer. **Findings:** QA-01, SEC-04, FE-01.

- Resolve the intended answer-stage reserve and route snapshot behavior before changing test fixtures.
- Fix source/test types at vendor boundaries without globally disabling strict checking.
- Repair the ChatApp composition budget and asynchronous citation test timing.
- Apply formatting/import cleanup after behavioral changes settle.
- Patch affected runtime dependencies and then developer/docs tools; review exception reachability, owner, and expiry.

**Exit proof:** formatting, lint, Python/frontend types, unit/contract, frontend tests, and production build all pass. Audit results have explicit accepted dispositions. Record skips separately.

## Sixth: improve the operating UI

**Owner:** frontend maintainer. **Findings:** UI-01, UI-02, UI-03.

- Make compact Ask conversation-first with one Sessions access path.
- Add readable page zoom and retry without broadening document access.
- Fix hidden/inert modal candidate handling and background/stacked-overlay focus behavior.
- Verify real text scaling/zoom, touch use, RTL, and long populated conversations.

**Exit proof:** authenticated desktop/mobile/browser checks with a source-rich answer; keyboard/screen-reader focus, error/retry, history restore, and cancellation work. Do not replace the incumbent visual design merely to complete these fixes.

## Seventh: close deployment and live-evidence gaps

**Owner:** operations/release maintainer. **Findings:** OP-01, OP-02, QA-02, SEC-05 hardening decision.

- Wait for actual remote SSM deployment outcome and check readiness/journeys.
- Correct quick-start local/hosted topology and public build-time configuration instructions.
- Make required authenticated/RLS release jobs fail on missing prerequisites instead of silently skipping.
- Run restore, egress, lease/reaper, role-change, deletion, and audit-anchor scenarios.
- Decide whether stricter nonce CSP is appropriate, including dynamic-rendering/cache implications.

**Exit proof:** the release evidence identifies exact commit/image, environment, executed checks, skip disposition, full evaluation result, and rollback/restore outcome. A green dispatch-only workflow is insufficient.

## Longer-term architecture work

AR-01 should follow the high-impact correctness/security work. Define internal core layers, move offline tooling where it reduces deployment coupling, and enforce import direction. Keep refactors small enough that behavior can be reviewed and regression-tested independently.

## Decisions to preserve

- MFA removal is an explicitly accepted decision. Do not restore it as an incidental security patch; record residual risk and resolve stale skill guidance separately.
- Keep canonical evidence authorization after derived retrieval and cache hits.
- Keep General/Web sources explicit and distinct from company evidence.
- Keep structured-table execution deterministic and provenance-aware.
- Keep credentials and corpus data out of review/CI logs.
- Do not retain a targeted RAG improvement unless the full regression also holds.
