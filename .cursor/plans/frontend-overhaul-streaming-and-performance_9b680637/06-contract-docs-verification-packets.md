# Candidate Contract, Documentation, and Verification Packets

Status: **candidate, non-canonical**

No feature packet is complete until its public contract, deterministic proof,
and evidence handoff are updated.

## CTR-01 — Surface catalog-backed diagnostics

**Objective:** expose only diagnostics that have an authoritative runtime
source. Do not invent missing data to fill the UI.

**Backend owners**

- `apps/backend/src/smart_rag_api/services/sse/mapping/diagnostics.py`;
- `packages/core/src/smart_rag_core/sse/catalog.py`;
- actual agent update producers.

**Allowed mappings**

- `optional_tool_disclosure {tool_keys}` only from role-filtered
  `optional_selected_keys`;
- `route_correction {from_route, to_route, reason}` only when the correction
  decision says it was applied;
- `coverage {coverage_score}` only from the actual bounded branch/fusion score;
- `deadline {route_family}` from authorized runtime context before the
  `partial` terminal;
- existing citation preview/origin/usage events from their current authoritative
  sources.

`cache` remains absent until the retriever emits a real cache outcome. An absent
event means unknown/not emitted; it must not be rendered as a miss.

**Rules**

- every payload validates through the central catalog;
- no evidence/source/passage text;
- no model reasoning;
- no duplicated diagnostic after replay;
- `deadline` is diagnostic and `partial` is the terminal; do not count both as
  two protocol terminals.

**Frontend**

Extend existing diagnostics rendering with explicit unknown/absent semantics.
Never convert disclosure into tool execution; execution uses `tool_progress`.

**Tests:** positive source, absent source, malformed update, replay, leakage,
and deadline→partial ordering.

## DOC-01 — Synchronize public documentation

**Update only when the related implementation lands**

- `docs/frontend/workspace-screens.md`: waiting timeline, verified-display
  label, skip/reduced-motion, history behavior;
- `docs/frontend/PHASE8_JOURNEY_MATRIX.md`: deterministic progress/reveal
  journeys and hosted proof;
- `docs/frontend/action-inventory.json`: Show full answer, expand timeline,
  jump-to-latest, retry actions;
- the canonical SSE API document under `docs/api/`: `status.phase`,
  `tool_progress`, ordering, replay, allowed/forbidden fields;
- `docs/development/phase-08-frontend-integration-evidence.md`;
- Phase 6 co-owned evidence for LangGraph custom mode;
- the paced-reveal/custom-streaming ADR;
- `docs/README.md` only if a new document is added.

**Required diagrams**

- sequence diagram: custom node start → update completion → verify → token
  deltas → terminal/reveal;
- state diagram: idle/waiting/verifying/revealing/complete/interrupted;
- component ownership diagram after god-file extraction.

Document:

- no prose before verification;
- server progress may be too fast for an active paint but remains in history;
- presentation deadline/publication cap;
- reduced motion and screen-reader policy;
- cancellation/reconnect/replay;
- security fields omitted by design;
- local deterministic fixture versus hosted proof.

Run the repository docs checker; do not copy stale test counts.

## VER-01 — Deterministic contract and browser gate

**Objective:** prove behavior without a live provider or hosted credentials.

### A. Checked-in SSE fixtures

Add under `apps/frontend/tests/fixtures/sse/`:

- `company-progress.sse`;
- `general-progress.sse`;
- `invalid-progress.sse`;
- `reconnect-progress.sse`;
- `verified-long-answer.sse`;
- sidecar expected metadata or typed fixture builder.

Every fixture has:

- schema/run ID;
- monotonic event IDs;
- explicit required/forbidden nodes;
- optional selected/executed tool keys;
- verify-completion sequence;
- first token sequence;
- one terminal sequence.

Fixture data must be synthetic and contain a marker proving no secret/query/draft
leakage.

### B. Unit/component matrix

```text
catalog validation        status phase/tool event/legacy rows/forbidden fields
LangGraph contract        observed 1.2.11 v2 custom+updates shape
backend mapper            ordering, route skips, verified-final, cancel, replay
frontend parser/reducer   split bytes, duplicate IDs, first terminal, early token
progress UI               real stages only, tools only when executed, a11y
reveal hook               Unicode, >=2 paints, <=2.5s, <=90, skip, reduced motion
run controller            send/resume/non-OK/abort/latest cursor/idempotency
scroll                    pin/unpin/prepend/race/failure
architecture              line/import/single-owner budgets
security                  redirect matrix, subject cache isolation, revoked session
```

### C. Playwright fixture journey

Add `apps/frontend/tests/e2e/sse-progress-fixture.spec.ts` and intercept the
exact stream endpoint used by the app.

Assert in order:

1. send action creates a waiting surface;
2. emitted node start is visible and no answer prose exists;
3. emitted tool start/completion is visible;
4. forbidden route nodes never appear;
5. verify stage appears;
6. long verified answer has a strict intermediate prefix in deterministic
   clock/component coverage;
7. browser reaches full answer by the bounded deadline;
8. terminal controls/citations are available without waiting for reveal;
9. Show full answer completes immediately;
10. reduced-motion context renders full answer;
11. reconnect after N does not duplicate progress or answer;
12. user cancellation persists one cancelled terminal, does not fabricate
    completed progress, and does not start duplicate provider work;
13. no hydration or uncaught console errors.

Do not rely on a screenshot alone to prove timing. Timing/publication bounds are
unit tests with a fake clock; Playwright proves the integrated states.

### D. Deterministic visual capture

Wait for explicit fixture state markers:

- readiness settled;
- route data settled;
- progress fixture sequence reached;
- reveal completed or intentionally paused at a named test seam.

Capture 390px and desktop. Never bless a loading-state mismatch as the new
baseline.

### E. Commands

```powershell
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
uv run python scripts/check.py --tier docs
uv run python scripts/check.py --tier frontend
uv run python scripts/ci/check_openapi.py
uv run python scripts/ci/check_migrations.py
uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
git diff --check
```

The root `frontend` tier already runs lint, Next type generation, TypeScript,
Vitest, build, and Playwright. Record actual counts and failures; do not reuse
the draft's stale 47-file/327-test baseline.

**Done when**

- every packet-specific focused test and applicable root tier passes;
- architecture budgets are machine-enforced;
- required browser job has no unexpected skip;
- deterministic progress/reveal/security fixtures pass;
- docs and OpenAPI checks pass;
- unrelated pre-existing failures are listed as `UNVERIFIED` or `FAIL`, never
  hidden.

## VER-02 — Hosted P08-22 production-like proof

**Objective:** prove the real provider, hosted Supabase persistence, settlement,
roles, and UI behavior. This is not replaceable by the deterministic fixture.

### Prerequisites

- Docker running;
- hosted Supabase environment wired without printing values;
- hosted migrations match repository;
- `MOCK_MODEL_MODE=false`;
- bounded real-provider credential and budget;
- holdout access absent;
- Compose frontend on its hosted profile;
- at least member and owner/admin browser roles.

If any prerequisite is missing, mark `BLOCKED`; do not skip and pass.

### Known blockers from the current evidence

1. live `Verifying` was not captured;
2. `app.llm_usage` settlement rows were absent;
3. UI could remain `running` after durable `partial`;
4. hosted schema lagged repository migrations.

Each blocker requires its own promoted repair packet and regression test before
this proof can pass.

### Procedure

1. Start with `.\scripts\dev.ps1`.
2. Verify live/ready/meta and `query_ready=true`.
3. Confirm the API points to hosted auth/database, while local fixture remains
   clearly separate.
4. Run one bounded real Ask from the hosted-profile frontend.
5. Observe real server-originated progress, including verify.
6. Confirm no answer prose appears before verified release.
7. Confirm the verified reveal is presentation-only and skippable.
8. By `run_id`, inspect hosted conversation, user/assistant messages, run,
   ordered run events, one terminal, and usage settlement.
9. Confirm those IDs are absent from local Supabase.
10. Disconnect/reconnect and prove monotonic resume with no duplicate provider
    call/cost.
11. Verify member and owner/admin surfaces and forbidden requests.
12. Capture 390px and desktop screenshots after deterministic settled markers.
13. Stop with `.\scripts\stop.ps1`.

Do not print SQL rows containing private source text or credentials. Evidence
uses IDs, counts, status, sequence, and redacted screenshots.

### Mandatory outcome

`PASS` requires all four known blockers closed, one terminal, one settled usage
record, hosted-only persistence, visible verify progress, no pre-verify prose,
and no unexpected skips.

## Evidence handoff

Append to `docs/development/phase-08-frontend-integration-evidence.md`:

```markdown
## <canonical packet ID> — <title>

**Status:** PASS | FAIL | BLOCKED | PARTIAL

### Requirement and acceptance
- [status] exact check — evidence

### Changed paths
- path — ownership/purpose

### Commands
| Command | Exit | Duration | Counts/result |
|---|---:|---:|---|

### Runtime proof
- profile:
- run ID (non-secret):
- route:
- progress sequences:
- verify sequence:
- first token sequence:
- terminal sequence/type:
- settlement count:

### Architecture
- file before → after:
- import/single-owner checks:

### Security, authorization, replay, fallback
- …

### Unverified or blocked
- …

### ADR/deviation
- …

### Rollback
- …
```

Only after this evidence proves every `Done when` item may the canonical packet
status and wrapper checkbox change.
