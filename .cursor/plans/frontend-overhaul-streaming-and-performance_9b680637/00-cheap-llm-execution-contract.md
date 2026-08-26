# Cheap-LLM Execution Contract

Status: **candidate, non-canonical, do not execute directly**

This contract exists because the implementation model may be weak, literal, or
unable to retain the complete architecture. Give that model this file plus
**exactly one selected candidate packet**. Never give it the whole packet suite
and ask it to implement everything.

## 1. Authority and promotion

The authority order is:

1. `../hybrid-graph-rag/00-global-contracts.md`
2. `../hybrid-graph-rag/08-phase-frontend-integration.md`
3. `../hybrid-graph-rag/08-phase-frontend-integration/00-shared-contracts.md`
4. exactly one promoted canonical packet;
5. contracts explicitly linked by that canonical packet;
6. this candidate packet only as supporting detail.

Before application-code edits, promote one candidate packet into the canonical
Phase 8 wrapper and integrity lock. If this suite conflicts with canonical
authority, canonical authority wins and the model stops.

The paced verified-answer reveal intentionally changes the prior
`no artificial delay` presentation rule. It requires:

- explicit user approval, already recorded on August 26, 2026;
- a new ADR;
- an additive canonical Phase 8 amendment;
- co-owned Phase 6/8 approval for LangGraph `custom` streaming.

The amendment must explicitly supersede the conflicting requirements in Phase
8 shared contracts and the existing P08-09/P08-15 packets, update the frontend
visual contract, and add a linked Phase 6 SSE-progress packet. BEP-01 and later
backend-progress work, and FEP-01 and later frontend-progress/reveal work, are
hard-blocked until that amendment and the integrity lock pass.

## 2. Invocation template

Use this prompt shape with the implementation model:

```text
Implement candidate packet <PACKET-ID> only.

Repository: C:\Nagdy\Mustafa\Work\Upwork\Demo_Project_3
Read first:
1. .cursor/plans/hybrid-graph-rag/00-global-contracts.md
2. .cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md
3. .cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-shared-contracts.md
4. <ONE PROMOTED CANONICAL PACKET>
5. .cursor/plans/frontend-overhaul-streaming-and-performance_9b680637/00-cheap-llm-execution-contract.md
6. <ONE CANDIDATE PACKET FILE AND SECTION>

Before editing, quote the objective, allowed paths, forbidden changes, stop
conditions, and acceptance checks. Inspect every referenced file/symbol.
Implement no sibling packet. Run all packet commands. Do not commit or push
unless explicitly asked. Report PASS/FAIL/BLOCKED/UNVERIFIED honestly.
```

## 3. Mandatory preflight

The model must:

1. read `git status` and preserve unrelated user changes;
2. verify every referenced path and symbol exists;
3. verify pinned dependency versions before using their APIs;
4. run the packet's narrow baseline test before editing;
5. record the current line count of every touched god file;
6. state whether external services, credentials, Docker, or hosted writes are
   required;
7. stop if the packet has not been canonically promoted.

Never infer an endpoint, event field, module, environment variable, migration,
test result, or library API from this plan. Search/read it first.

## 4. One-packet workflow

```text
LOAD       Read authority + one packet.
QUOTE      Restate exact acceptance and forbidden outputs.
INSPECT    Read implementation, tests, schemas, versions, and callers.
BASELINE   Run narrow tests and record pass/fail.
EXTRACT    Create the packet's ownership seam without behavior change.
VERIFY     Run characterization tests after extraction.
CHANGE     Implement only the requested behavior.
TEST       Run positive, failure, authorization, replay, and fallback tests.
DOCUMENT   Update contracts/docs named by the packet.
EVIDENCE   Append the evidence handoff.
REPORT     State proven, failed, blocked, and unverified items.
STOP       Do not begin another packet.
```

Extraction and behavior edits may occur in one model run only when the packet
explicitly requires both. Keep them as separately testable changes.

## 5. Global product invariants

- Before deterministic verification: no answer prose is rendered or persisted
  as an assistant answer.
- While waiting: only server-originated node/tool progress is shown.
- Skipped nodes/tools never appear.
- Progress payloads never contain prompts, queries, arguments, results,
  passages, snippets, source text, HTML, exceptions, traces, tokens, or secrets.
- `token_delta` contains verified/refused/partial prose only.
- The authoritative reducer receives verified text immediately.
- The visual reveal is presentation-only, skippable, reduced-motion aware,
  Unicode safe, at most 2.5 seconds, and at most 90 React publications.
- Presentation never delays terminal persistence, settlement, citations,
  reconnect cursors, cancellation, or a new send.
- First terminal wins. Resume never starts paid work again.
- All server authorization, RLS, quota, SSRF, quarantine, and role checks remain
  authoritative.

## 6. No-god-file invariants

Current total file-line baselines:

- `apps/frontend/src/components/chat/chat-app.tsx`: 1201 total lines;
- `apps/frontend/src/lib/api.ts`: 2350 total lines;
- `apps/frontend/src/lib/types.ts`: 685 total lines;
- `apps/backend/src/smart_rag_api/services/query_sse_mapping.py`: 363 total
  lines;
- `apps/backend/src/smart_rag_api/services/sse/executors.py`: 527 total lines;
- `apps/backend/src/smart_rag_api/services/sse/executor_support.py`: 321 total
  lines;
- `apps/backend/src/smart_rag_api/services/sse/service.py`: 492 total lines;
- `apps/backend/src/smart_rag_api/services/sse/service_persist.py`: 358 total
  lines;
- `apps/agents/src/smart_rag_agents/query/graph.py`: 476 total lines.

Exit targets:

- all budgets use physical lines counted by
  `len(Path.read_text(encoding="utf-8").splitlines())`; blank lines,
  comments, and documentation count;
- `chat-app.tsx` ≤300 physical lines and composition-only;
- `api.ts` and `types.ts` ≤100 physical lines and exports-only;
- `query_sse_mapping.py` ≤100 physical lines as a compatibility facade;
- `executors.py`, `executor_support.py`, and `service_persist.py` ≤100 physical
  lines as retained compatibility facades/exports after callers migrate;
- `service.py` ≤300 physical lines and public attach/orchestration only;
- `graph.py` ≤300 physical lines and topology-only;
- new production modules ≤300 physical lines and one concern;
- tests split by owner; no replacement god test file;
- every packet touching a god file leaves it smaller;
- no second SSE parser, consumer, reducer, or chat-run engine.

Do not satisfy limits by compressing formatting, combining unrelated functions,
removing documentation, deleting supported behavior, dropping public exports,
or hiding logic in one giant hook. Refactor by moving cohesive behavior behind
retained typed barrels/facades.

## 7. Coding rules for a weak model

- Preserve public signatures unless the packet says otherwise.
- Prefer move-only extraction before behavior changes.
- Keep compatibility barrels during migration.
- Add explicit types; do not add broad `any`, unvalidated casts, or open
  `Record<string, unknown>` at public boundaries.
- Every authored Python function/class/module gets a Google-style docstring.
- Every exported TypeScript function/hook/component gets TSDoc.
- Every LangGraph node/progress adapter documents state, external calls,
  persistence, budget/deadline behavior, and fallback.
- Do not add TODOs, placeholders, fake success, swallowed core errors, disabled
  checks, `.skip`, `.only`, snapshot auto-approval, or test-only production
  branches.
- Do not add a dependency unless the packet requires it and current primary
  documentation is verified.
- Use `Intl.Segmenter`; if unavailable, reveal the full string. Never implement
  an unsafe home-grown Unicode slicer.

## 8. Forbidden shortcuts

- No provisional answer tokens before verification.
- No client-invented active node, tool, route, score, timer, or timestamp.
- No arbitrary reduction of backend chunk size to fake animation.
- No persisting presentation cursor/offset.
- No raw tool arguments/results in SSE.
- No blanket timeout on long-lived SSE.
- No client validation described as authoritative security.
- No new fetch/SSE logic in React presentation components.
- No global query `staleTime` for all resources.
- No broad refactor outside the selected packet.
- No mutation of canonical plan hashes merely to silence integrity failures.

## 9. Hard stop conditions

Stop and report `BLOCKED` when:

- the selected candidate has not been canonically promoted;
- repository reality contradicts security, data, cost, or event semantics;
- a required pinned API cannot be verified;
- baseline tests fail for unrelated reasons and the packet cannot isolate them;
- a required real integration is unavailable and only a fake/skip would pass;
- P08-22 hosted credentials, schema, provider budget, or Docker are required but
  unavailable;
- a change would expose source/tool text or weaken authorization;
- an architecture budget would be exceeded without the named extraction seam;
- a mandatory test is skipped.

Do not mark a packet complete when a stop condition occurs.

## 10. Secrets, Git, and remote safety

Never print or commit `.env*`, JWTs, API keys, service-role keys, DSN passwords,
checkpoint pickles, `.next`, or unredacted secret-scan reports.

Never:

- use destructive Git reset/checkout;
- amend, commit, push, or force-push unless explicitly requested;
- reset a hosted Supabase project;
- apply a hosted migration without explicit approval and rollback;
- use mock-model mode as hosted P08-22 proof.

Local diagnostic reads and deterministic tests are allowed.

## 11. Required evidence report

```markdown
## <PACKET-ID> — <title>

**Status:** PASS | FAIL | BLOCKED | PARTIAL

### Requirement quoted
> Exact packet requirement.

### Baseline
- Commit/worktree state:
- Narrow test before change:
- Touched-file line counts:

### Changed paths
- path — why

### Acceptance
- [PASS|FAIL|BLOCKED|UNVERIFIED] check — evidence

### Commands
| Command | Exit | Duration | Result |
|---|---:|---:|---|

### Security / authorization / replay / fallback
- …

### Architecture budget
- before → after

### Unverified
- …

### Deviation / ADR
- …

### Rollback
- …
```

`PASS` requires an exercised assertion and exit code 0. `UNVERIFIED` means not
run. `BLOCKED` means an external prerequisite is unavailable. Never write
“should pass” or “likely fixed.”
