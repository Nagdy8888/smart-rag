---
title: Comprehensive audit medium and low findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, operations, frontend
---

# Medium and low findings

## Medium

### AUD-M-001: Ingestion status RPC is query-heavy

`20260819100000_ingestion_status_acl_v1.sql:83-335` assembles status through
many counts and JSON subqueries. Several job, ledger, and scan tables lack a
simple or partial `version_id` index. Polling can become a database hot path.

Add missing indexes, capture `EXPLAIN (ANALYZE, BUFFERS)` at realistic history,
and consider an event-updated status projection.

### AUD-M-002: Large migrations are difficult to review and recover

Five SQL files exceed roughly 35 KB; query admission exceeds 1,300 lines.
Atomic application is useful, but concern mixing makes failures difficult to
bisect and authorization changes easy to miss.

Keep immutable history unchanged. Split future migrations by independently
reviewable concern and add migration-size review guidance.

### AUD-M-003: Pagination uses unnecessary definer privilege

`20260819102000_list_pagination_v1.sql:99-136` defines a visible-document
pagination RPC with `SECURITY DEFINER` while related listing functions use
invoker semantics.

Use `SECURITY INVOKER` unless a documented privilege requirement and negative
role tests prove otherwise.

### AUD-M-004: Invitation RPC replacement is not expand-contract

`20260819103000_invitation_accept_guard_v1.sql` drops the three-argument
signature before creating and granting a four-argument replacement. A partial
or branched rollout can break invitation acceptance.

Add the new signature first, migrate callers, verify, and remove the old
signature in a later migration.

### AUD-M-005: Valkey transport and memory policy limit scale

`packages/core/src/smart_rag_core/runtime/valkey.py:184-188` opens per-command
TCP connections. Compose config uses a 64 MB `noeviction` limits instance.
High-cardinality buckets can create connect storms or fail-closed denial.

Use bounded connection pooling/pipelining and alert on memory, rejected
connections, and limiter fallback.

### AUD-M-006: Emergency rate limits weaken with replicas

`auth_rate_limits.py:279-296` falls back to a per-process limiter for approved
reads when shared stores fail. Effective allowance grows with each API replica.

Document this degradation explicitly or use the durable Postgres fallback for
reads that must remain globally bounded.

### AUD-M-007: Scanner outages are not distinguished from malicious content

`scan_graph.py` allows a ClamAV availability exception to fail the job. This is
secure fail-closed behavior, but it blocks all promotion and provides no
separate transient disposition.

Record infected, unavailable, timeout, and unscannable states separately; alert
operators and retry only transient scanner failures.

### AUD-M-008: Query execution state is process-local

The runtime registry and cancellation/resume behavior assume one active API
process. Enabling multiple colors or replicas can route attach/cancel requests
to a process that does not own the run.

Keep one active API until ownership is durable, or move execution leases and
attach metadata into a shared store.

### AUD-M-009: Signed-out users see the entire protected navigation

The live login page listed Chat, Documents, Graph, Tables, Team, Tools,
Curation, Usage, and Profile before authentication. Server authorization
remains authoritative, but the UI is noisy and implies access that is not yet
known.

Use a minimal auth layout and render role-aware navigation after profile load.

### AUD-M-010: Internationalization is fixture-tested, not product-supported

`apps/frontend/src/app/layout.tsx` fixes `lang="en"` and `dir="ltr"`.
Mixed-direction hostile fixtures reduce rendering risk but do not provide
Arabic localization, RTL navigation, translated errors, or locale-aware forms.

State English/LTR as the supported launch scope or implement locale-driven
`lang`/`dir` plus RTL visual and keyboard tests.

### AUD-M-011: Accessibility state and destructive-action UX need tightening

Several interactive states rely on visual text without complete pressed/busy
semantics; multiple alert/live-region paths can duplicate announcements.
Destructive conversation actions need a clear confirmation or undo pattern.
Mobile auth buttons measured 40 pixels high, below a common 44-pixel target.

Run authenticated axe plus keyboard/screen-reader journeys and add explicit
state semantics, focus restoration, and destructive-action safeguards.

### AUD-M-012: Documentation enforcement trails documentation policy

The repository has complete frontmatter, but the index omits maintained files,
broken review links remain, several contract documents lack required Mermaid
diagrams, 11 documents exceed the preferred 300-line size, and most documents
share one owner and draft status.

Enforce index completeness, link validity, topic diagrams, size exceptions,
and meaningful domain ownership in CI.

### AUD-M-013: Release traceability is weak in the dirty working tree

Before this report, 68 tracked files were modified and 26 were untracked across
runtime, tests, infrastructure, documentation, and demo tooling. Audit results
can change without a commit boundary, and generated/cache artifacts previously
appeared in status snapshots.

Create a clean candidate commit, exclude runtime artifacts, generate an SBOM
and image digest manifest, then rerun every gate from a clean checkout.

### AUD-M-014: Health and supply-chain coverage is incomplete

Worker health checks primarily prove importability, Caddy lacks a strong
service health check in staging Compose, Caddy uses a tag rather than an image
digest, and CI does not run a container image vulnerability scan.

Add dependency-aware health probes, pin all image digests, and gate candidate
images with Trivy or an equivalent scanner.

### AUD-M-015: HSTS is not asserted in repository edge configuration

No `Strict-Transport-Security` policy was found in the Next.js, Caddy, or
CloudFront IaC inspected by the audit. The deployed edge may add it outside the
repository, so this remains a configuration gap rather than a proven live
header omission.

Add HSTS at the HTTPS edge with a reviewed lifetime and subdomain policy, then
verify the deployed response rather than relying on application headers.

### AUD-M-016: Readiness polling is fixed at five seconds per open tab

`chat-app.tsx:159-163` and `auth-screens.tsx:130-134` poll readiness every five
seconds, including the public login route. Many idle tabs create avoidable API,
battery, and edge load.

Pause polling when hidden, back off after stable success/failure, and remove
operator readiness from the normal public auth journey.

## Low

### AUD-L-001: Length-required request handling is strict but surprising

Mutation requests without numeric `Content-Length` return 411. This is a valid
fail-closed choice but must be documented for clients that use chunked bodies.

### AUD-L-002: The data model assumes one company

Profile loading and graph workspace defaults use a single-company contract.
This is not an IDOR in the current product, but it is unsafe to market as
multi-tenant SaaS without a schema and authorization redesign.

### AUD-L-003: Worker policies intentionally have broad corpus authority

`app_worker` policies use broad access for ingestion and projection work. Treat
worker credentials as high-impact, rotate them, keep them off user-facing
paths, and document the accepted trust boundary.

### AUD-L-004: Local browser session showed stale development asset failures

The audited dev session logged 403 responses for several Turbopack chunks and
failed HMR WebSocket handshakes. The rendered page was already available, so
this may be stale dev-server state rather than a product defect.

Reproduce from a clean dev start and production build before opening a runtime
bug.

### AUD-L-005: URL safety is delegated to API helper callers

`src/lib/api.ts:130-135` accepts any absolute HTTP(S) URL. Current production
calls pass local path literals, so no bearer leak was found, but a future
server-supplied stream URL could send authorization off-origin.

Reject absolute URLs or require the configured API origin inside `apiUrl()`.

### AUD-L-006: Citation and TOTP URL validation is caller-dependent

`CitationChip` renders a supplied `href` without validating the scheme, while
current callers intentionally pass null/sanitized values. TOTP QR handling
accepts any `data:image/*` subtype for an `<img>`.

Enforce HTTP(S) citation URLs inside the component and restrict QR data URLs to
the exact image formats required.

### AUD-L-007: Invitation acceptance has avoidable sign-in friction

`/invitations/accept` is not a public auth path. The proxy sends unsigned users
to login, but the login component does not explicitly complete the preserved
invitation intent after successful sign-in.

Preserve and validate the relative destination through sign-in, then return the
user to invitation acceptance without exposing the invitation token.
