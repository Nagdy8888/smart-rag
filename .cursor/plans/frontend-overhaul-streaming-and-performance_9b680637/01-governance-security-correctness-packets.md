# Candidate Governance, Security, and Correctness Packets

Status: **candidate, non-canonical**

Execute one packet ID per model run. First read
`00-cheap-llm-execution-contract.md`. The order in this file is mandatory.

## GOV-00 — Canonical promotion and policy ADR

**Objective:** authorize one implementation slice without pretending this draft
is canonical.

**Read**

- `.cursor/plans/hybrid-graph-rag/00-global-contracts.md`
- `.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md`
- `.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-shared-contracts.md`
- `docs/adr/ADR-frontend-functional-overhaul.md`
- `docs/development/phase-08-frontend-integration-evidence.md`

**Steps**

1. Reconcile the unchecked P08-07 wrapper item with its existing evidence.
   If every recorded acceptance item is complete, check P08-07 and synchronize
   packet status; otherwise leave it unchecked and list each missing proof.
2. Select exactly one candidate packet from this suite.
3. Create one additive P08 packet with allowed outputs, forbidden outputs,
   acceptance checks, stop routes, rollback, and evidence requirements.
4. For verified pacing, write an ADR that distinguishes:
   - immediate authoritative verified-text ingestion;
   - bounded presentation reveal;
   - no pre-verification prose;
   - skip/reduced-motion behavior;
   - terminal/settlement independence.
5. For LangGraph custom progress, amend the co-owned Phase 6/8 contract and pin a
   LangGraph 1.2.11 contract test.
6. Add explicit superseding amendments/links for:
   - Phase 8 `00-shared-contracts.md`;
   - P08-09 execution durability;
   - P08-15 verified-final presentation;
   - `docs/frontend/workspace-screens.md`;
   - a new additive
     `.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/16-sse-custom-progress.md`
     packet covering SSE custom progress, linked from the Phase 6 wrapper and
     relevant shared contract.
7. Mark BEP-01+ and FEP-01+ blocked until these amendments pass integrity.
8. Run integrity without refreshing hashes. Fix structure first.
9. Update the lock only after explicit approval, then run integrity again.

**Commands**

```powershell
uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
# Only after approved structural amendments:
uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update
uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
```

**Done when**

- one packet is canonical and no sibling is activated;
- the ADR explicitly supersedes the old presentation rule;
- the integrity verifier passes;
- no application code changed.

**Forbidden:** hash-only repair, renumbering P08-22/P08-23, or checking a packet
without evidence.

## SEC-01 — Same-origin auth callback redirect

**Objective:** reject slash/backslash and encoded open-redirect forms at the
server callback.

**Paths**

- modify `apps/frontend/src/app/(auth)/auth/callback/route.ts`;
- add
  `apps/frontend/src/app/(auth)/auth/callback/safe-next-path.ts`;
- add
  `apps/frontend/src/app/(auth)/auth/callback/safe-next-path.test.ts`.

**Contract**

```typescript
export function safeNextPath(raw: string | null, requestOrigin: string): string;
```

Return `/` unless the decoded value is a same-origin, root-relative path.
Reject absolute URLs, `//`, any `\`, encoded slash/backslash ambiguity,
control characters, user-info, and a parsed origin different from
`requestOrigin`. Preserve valid path, query, and fragment components only after
same-origin parsing. Keep PKCE exchange and anon-client behavior unchanged.

**Required test matrix**

- valid: `/`, `/documents`, `/chat?run=1`, `/graph#node`;
- invalid: `https://evil.example`, `//evil.example`, `/\evil.example`,
  `/\\evil.example`, `%2f%2fevil.example`, `/%5cevil.example`,
  mixed-case encodings, CR/LF, and malformed percent encoding.

**Commands**

```powershell
pnpm --filter smart-rag-frontend exec vitest run "src/app/(auth)/auth/callback/safe-next-path.test.ts"
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
```

**Done when:** every invalid case redirects to `/`, every valid case remains on
the request origin, and no client-side check is described as the security gate.

**Stop:** if URL normalization behavior differs between the pinned Node runtime
and tests, add runtime contract cases; do not weaken validation.

## SEC-02 — Revoked-session contract and lint repair

**Objective:** align backend and frontend on the machine-readable
`session_revoked` code and remove synchronous effect mirroring.

**Paths**

- `apps/backend/src/smart_rag_api/dependencies/identity.py`;
- `apps/frontend/src/lib/api.ts` or its extracted
  `apps/frontend/src/lib/api/errors.ts`;
- `apps/frontend/src/lib/failure-copy.ts`;
- `apps/frontend/src/components/chat/chat-app.tsx`;
- `apps/frontend/src/lib/api.test.ts`;
- `apps/frontend/src/components/chat-app.test.tsx`.

**Steps**

1. Change the backend authorization detail from human text
   `Session revoked` to `session_revoked`.
2. Keep a narrow frontend compatibility alias for both values during rollout.
3. Do not loosen the safe-detail validator to arbitrary sentences.
4. Remove the effect that calls `setFailure` synchronously from `/me` query
   state. Derive `meFailure` from query data/error and combine it at render.
5. Preserve the existing user-safe banner and sign-out path.

**Tests**

- both backend spellings classify as `session_revoked`;
- arbitrary human detail remains sanitized;
- revoked session renders the existing safe banner;
- ESLint no longer reports `react-hooks/set-state-in-effect`.

**Commands**

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/api.test.ts src/components/chat-app.test.tsx
pnpm --filter smart-rag-frontend lint
uv run pytest tests/contract/test_jwks_auth.py tests/contract/test_auth_lifecycle.py -q
```

**Forbidden:** exposing raw backend detail or disabling the lint rule.

## COR-03 — JWT-sub cache isolation

**Objective:** prevent one signed-in subject from observing another subject's
cached conversation messages after token replacement.

**Paths**

- `apps/frontend/src/lib/query-keys.ts`;
- `apps/frontend/src/lib/query-keys.test.ts`;
- current `ChatApp` owner, later
  `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`;
- `apps/frontend/src/components/chat-app.test.tsx`.

**Steps**

1. Add
   `conversationMessages(conversationId)` to `sessionQueryKeys(accessToken)`.
2. Key it with the existing non-secret session scope derived from JWT `sub`.
3. Replace all bare conversation/message invalidations with scoped factories.
4. Track previous session scope. On a `sub` change, remove session-owned cache,
   pagination maps, current transcript, live run, and persisted run pointer.
5. Abort an in-flight stream before clearing state.

**Invariants**

- raw JWT and role never appear in a query key;
- server authorization remains required for every fetch;
- sign-out behavior still clears all private state;
- no UI-only filtering is called a security boundary.

**Tests:** user A cache, replace token with user B, assert no A title/message/run
renders before B fetch resolves; also test malformed token scope isolation.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/query-keys.test.ts src/components/chat-app.test.tsx
pnpm --filter smart-rag-frontend typecheck
```

## COR-04 — Resume classification, latest cursor, and abort

**Objective:** make reconnect deterministic and prevent 401/403/500 responses
from being parsed as empty SSE.

**Paths**

- current `apps/frontend/src/components/chat/chat-app.tsx`, then
  `apps/frontend/src/components/chat/hooks/use-chat-run.ts` after extraction;
- `apps/frontend/src/lib/sse-consume.ts`;
- `apps/frontend/src/lib/stream-reconnect.ts`;
- `apps/frontend/src/components/chat-app.test.tsx`;
- `apps/frontend/src/lib/stream-reconnect.test.ts`.

**Steps**

1. Preserve the special deleted-run 404 branch.
2. Before `consumeSse`, classify every other non-OK response through the
   existing API error classifier.
3. Stop automatic retry on revoked/unauthorized/forbidden responses.
4. Read `lastSequence`, run ID, terminal state, and failure from refs updated on
   every reducer publication, not stale render closures.
5. On effect cleanup, conversation switch, sign-out, or unmount:
   `AbortController.abort()`, clear retry timers, and ignore late results.
6. Keep resume header/query cursor monotonic. Never reset it merely to recover.

**Tests**

- resume 401/403: one safe failure, no retry loop;
- resume 500: bounded retry policy, then retry action;
- resume 404: existing deleted UX;
- unmount/switch: network abort and no late state write;
- duplicate/replayed sequence: reducer ignores it;
- terminal frame: no reconnect.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/stream-reconnect.test.ts src/components/chat-app.test.tsx
pnpm --filter smart-rag-frontend lint
```

**Forbidden:** generic SSE timeout, swallowing non-OK in `consumeSse`, or
starting a second paid run.

## SEC-03 — Response-header ownership

**Objective:** remove the framework disclosure header and document HSTS at the
real HTTPS edge without unsafe preload assumptions.

**Paths**

- `apps/frontend/next.config.ts`;
- the deployment/security document selected by canonical promotion;
- focused configuration/header tests.

**Steps**

1. Add `poweredByHeader: false` to the existing Next configuration.
2. Inspect the deployed topology and identify the component that terminates
   public HTTPS (for example Vercel or CloudFront); do not assume both.
3. Record one HSTS owner. Define `max-age`, `includeSubDomains`, and `preload`
   only after confirming all covered subdomains are HTTPS-safe.
4. Add a production-profile response assertion for the reviewed value.
5. Do not emit contradictory HSTS values from Next and an edge proxy.

**Done when**

- `X-Powered-By` is absent from the production build response;
- exactly one documented edge owns HSTS;
- the assertion tests the deployed/profile configuration;
- preload is omitted unless its irreversible prerequisites are proven.

**Commands**

```powershell
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend build
uv run python scripts/check.py --tier docs
```

**Stop:** if the active production edge cannot be identified, ship only
`poweredByHeader: false` and mark HSTS `BLOCKED`; do not guess.
