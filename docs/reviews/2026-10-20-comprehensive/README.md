# Smart RAG comprehensive review

Review date: **20 October 2026, Africa/Cairo**. Reviewed commit: `a2164952a3ea4bfd87879b2d6d6d0dadf5643f27`. The working tree was clean before this review. Only review documents, evidence, and generated local build/test artifacts were produced; application source was not changed.

See [CI repair follow-up](15-ci-repair-follow-up.md) for subsequent publication
checks and the boundary between historical live evaluation and the pushed build.

## Overall assessment

Implementation update: the review below describes the original snapshot. See
[12 - Agent fix results](12-agent-fix-results.md) for the subsequent local changes,
versioned test set, validation, and remaining release blockers.
The [checkpoint repair follow-up](14-checkpoint-failure-repairs.md), continued on
21 October, records the subsequent authenticated API/SSE evaluations and read-only
hosted-checkpoint diagnosis. The original probe limits below describe the review
snapshot, not those later runs. The final local run passes 25/25 fixed development
checks (20 completed, five partial); the [aggregate evidence](evidence/checkpoint-repair-validation.json)
preserves that distinction and the remaining release blockers.

Smart RAG has a substantial, deliberately designed foundation: separate deployables, server-derived identity, canonical evidence authorization, deterministic routing, durable budgets, explicit answer origins, private document storage, and extensive tests. The main concern is that newer answer-presentation and figure-processing paths do not consistently preserve those foundations.

**I would not treat this checkout as release-ready.** This is a judgment about the code and local checks reviewed here, not a claim that the hosted application was tested or compromised. Several required local gates fail, and there are concrete gaps in answer integrity, provider accounting, and document-processing isolation.

The highest-priority findings are:

1. **AG-01:** The model can change an answer's meaning after verification. A local reproduction accepted “Alpha never runs first” in place of “Alpha runs first,” retaining `complete` status. Arabic text also escapes the English-only word guard.
2. **SEC-01:** PDF figure descriptions make direct provider requests without the standard external-processing decision, durable cost accounting, or operation replay protection.
3. **AG-03:** The final organizer decrements a state counter but does not consume the durable run reservation or record its provider attempt in the normal usage ledger.
4. **SEC-02:** Figure extraction and citation previews parse PDFs inside credential-bearing worker/API processes, outside the ingestion parser sandbox.
5. **AG-04:** Unexpected verification/release exceptions explicitly restore the generated draft, mark it `verified_partial`, and skip citation persistence.
6. **QA-01:** Python unit tests, frontend tests, Ruff, and Python type checking are currently red.

## Topic files

- [01 — Architecture and repository structure](01-architecture-and-structure.md)
- [02 — UI, UX, and accessibility](02-ui-ux-and-accessibility.md)
- [03 — Frontend engineering](03-frontend-engineering.md)
- [04 — Backend and API](04-backend-and-api.md)
- [05 — Agent brain and answer integrity](05-agent-brain.md)
- [06 — Security](06-security.md)
- [07 — Ingestion, retrieval, graph, and tables](07-data-ingestion-and-retrieval.md)
- [08 — Testing, evaluations, and observability](08-testing-evaluation-and-observability.md)
- [09 — Infrastructure and deployment](09-infrastructure-and-deployment.md)
- [10 — Prioritized remediation plan](10-prioritized-remediation.md)
- [11 — Detailed fix execution plan](11-fix-execution-plan.md)
- [Evidence and reproduction guide](evidence/README.md)
- [12 - Agent fix results and regression evidence](12-agent-fix-results.md)
- [13 - Real user-flow questions and observed live results](13-live-user-flow-results.md)
- [14 - Checkpoint diagnosis, repairs, and live validation](14-checkpoint-failure-repairs.md)

## Verification results

- Python unit suite: **1,906 passed, 5 failed, 4 skipped**.
- Selected security/API contracts: **42 passed, 11 skipped**. Skips are not security passes.
- Frontend suite: **695 passed, 2 failed** on the first full run. A focused repeat passed the citation-image failure test and reproduced the architecture-budget failure: **17 passed, 1 failed**. The citation failure is therefore classified as a timing-sensitive test, not a confirmed product defect.
- Frontend TypeScript: **passed**.
- Frontend production build: **passed**.
- Frontend ESLint: **passed**.
- Python Pyright: **107 errors**.
- Ruff lint: **1 import-order error**.
- Ruff formatting: **16 files need formatting**.
- Chromium login checks: **3 passed**: skip-link focus, constrained-viewport visibility, and generic error-text check. The “200% zoom” test changes viewport size; it does not actually prove browser zoom behavior.
- Node dependency audit: **11 reported vulnerabilities: 3 low, 7 moderate, 1 high; the high finding is ignored by existing policy**. The high-threshold command exits successfully; that does not mean there are no advisories.
- Python dependency audit: **3 nonignored advisory entries for `aiohttp 3.14.3`**, with `3.14.4` listed as a fix. The configured ignored advisory also suppresses two entries. Advisory entries are not necessarily independent root causes.

Logs are in [evidence/](evidence/README.md). Some PowerShell-native stderr messages look like shell errors; assess the actual test/audit summary as explained there.

## Scope and confidence

This is a broad code review with targeted executable proofs, not a line-by-line audit of the entire repository. Approximately 12,900 agent source lines, 19,538 backend source lines, 57,513 frontend source/test lines, and 137,769 core source/generated lines were inventoried. These counts include tests under the frontend source tree and generated TypeScript under core; they are scale indicators, not production-code measurements.

Evidence labels used throughout:

- **Reproduced:** executed locally with synthetic inputs or an existing check.
- **Confirmed by code:** the control flow is present; exploit frequency or runtime cost was not measured.
- **Conditional risk:** requires a deployment, traffic, or failure condition that was not exercised.
- **Verification gap:** the relevant live behavior remains untested here.
- **Accepted decision:** an intentional documented choice, not an accidental regression.

Priorities: **P0** immediate critical incident/blocker; **P1** material correctness/security/release issue; **P2** bounded weakness or maintainability concern; **P3** polish. No P0 incident was established. These are engineering priorities, not CVSS scores.

## Important limits

The existing API on port 8000 and frontend on port 3000 were unreachable during probes. A temporary Playwright development server was used for the three unauthenticated checks. Authenticated UI flows, a hosted deployment, actual RLS grants, migration application, production traffic, external telemetry issues, backup restoration, multi-replica races, and live paid model quality were not verified. Existing screenshots were examined and cross-checked against current CSS/components; screenshots are historical fixtures, not current browser captures.

No credentials, private questions, source documents, or raw customer content were exported into these reports. Existing evaluation summaries were inspected only for aggregate context; no fresh live evaluation was run. Recommendations that would change accepted product decisions need a new decision, especially MFA restoration.
