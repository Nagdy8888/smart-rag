# Candidate P08-22 Blocker Packets

Status: **candidate, non-canonical**

The four recorded P08-22 symptoms are not one implementation packet. Execute
these IDs separately. Hosted writes require explicit approval.

Run P08B-00 first as diagnosis only. P08B-01 through P08B-03 are blocked until
BMOD-01 through BMOD-09 finish, so repairs land in the extracted owners.

## P08B-00 — Reproduce and classify the hosted failures

**Objective:** obtain one redacted run record that assigns each symptom to an
owner before code changes.

**Read**

- canonical P08-22 packet;
- `docs/development/phase-08-frontend-integration-evidence.md`;
- hosted-runtime ADR;
- current SSE executor/service/persistence code;
- frontend reducer/run controller;
- hosted migration list.

**Procedure**

1. Verify prerequisites without printing values.
2. Start the hosted-profile stack.
3. Run one bounded real-provider Ask.
4. Record only non-secret run ID, event type/sequence/status, terminal, assistant
   row count, usage row count, and migration names.
5. Compare UI terminal with durable run/event terminal.
6. Confirm matching IDs are absent locally.
7. Stop the stack.

**Classification output**

```text
schema parity       PASS|FAIL|BLOCKED + missing migration names
settlement          PASS|FAIL|BLOCKED + reservation/finalization/usage counts
terminal sync       PASS|FAIL|BLOCKED + durable vs UI terminal
verify visibility   PASS|FAIL|BLOCKED + emitted/received/rendered sequence
```

No production code changes. If credentials/provider budget are unavailable,
record `BLOCKED`.

## P08B-01 — Hosted migration parity

**Objective:** make the hosted schema match repository migrations without
destructive reset.

**Preflight**

- compare repository migration ledger with hosted `list_migrations`;
- inspect each missing migration and its rollback/forward-fix implications;
- run local migration/openAPI checks;
- obtain explicit approval before remote apply.

**Rules**

- apply missing migrations in repository order only;
- never edit an already-applied migration;
- never reset hosted Supabase;
- never print DSNs or keys;
- if an apply fails, stop and write a forward-repair plan.

**Verification**

- hosted migration names/versions equal expected ledger;
- health/readiness still pass;
- role/RLS advisor results have no new critical finding;
- one safe read for the affected tables succeeds under expected role.

```powershell
uv run python scripts/ci/check_migrations.py
uv run python scripts/check.py --tier contract
```

Remote tool output and approval are recorded in evidence. This packet does not
repair settlement or UI code.

## P08B-02 — Exactly-once durable usage settlement

**Objective:** every terminal paid run finalizes its reservation and writes the
expected durable usage record exactly once.

**Inspect**

- `apps/backend/src/smart_rag_api/services/sse/run_settlement.py`;
- `apps/backend/src/smart_rag_api/services/sse/event_append.py`;
- `apps/backend/src/smart_rag_api/services/sse/answer_persistence.py`;
- the thin `apps/backend/src/smart_rag_api/services/sse/service.py`
  orchestrator;
- executor usage accounting and store interfaces;
- `tests/unit/test_query_sse_settlement.py`;
- actual hosted schema/functions after P08B-01.

**Required behavior**

- terminal success/refusal/partial/error/cancel follows the documented
  reservation-finalization policy;
- retry/replay cannot insert a second settlement;
- persistence failure is observable and does not report false success;
- connection commit order avoids the current deadlock boundary;
- usage events/UI derive from durable outcome, not an optimistic client counter.

**Tests**

- successful terminal;
- verified partial;
- cancellation before/after provider usage;
- executor error;
- duplicate terminal/replay;
- settlement write failure;
- zero-token safe path where applicable;
- exactly one row/ledger transition per idempotency key.

```powershell
uv run pytest tests/unit/test_query_sse_settlement.py tests/unit/test_query_sse_lifecycle.py tests/contract/test_sse_resume.py -q
```

**Hosted proof:** one bounded run has one terminal, one final reservation state,
and the expected non-zero/zero usage row according to the real outcome.

**Forbidden:** creating a fake row in the UI, swallowing settlement errors, or
changing prices/budget semantics without a separate approved packet.

## P08B-03 — Durable terminal and frontend synchronization

**Objective:** a durable `partial`, `cancelled`, `error`, or `completed` event
always leaves the UI in the same terminal state.

**Backend checks**

- exactly one terminal event is sequenced;
- `deadline` is a diagnostic immediately before `partial`, not a second
  terminal;
- replay after the terminal returns it;
- persisted run status and terminal event agree.

**Frontend checks**

- `applySseFrame` treats every catalog terminal as terminal;
- first terminal wins;
- `consumeSse` publishes the terminal state even if terminal shares a byte
  chunk with prior events;
- reconnect stops and clears retry timers;
- active progress remains historical but is not shown as still running;
- reveal may finish independently when verified text exists.

**Tests**

- add/extend reducer fixtures for deadline→partial, cancel, error, completed;
- split terminal frame across reads;
- terminal with empty answer;
- duplicate conflicting terminal ignored;
- reload/resume reconstructs terminal;
- component no longer shows `running`.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/chat-view.test.ts src/lib/sse-consume.test.ts src/components/chat-app.test.tsx
uv run pytest tests/unit/test_query_sse_lifecycle.py tests/contract/test_sse_resume.py -q
```

**Forbidden:** polling over the bug, clearing durable partial, or inventing a
client terminal.

## P08B-04 — Real Verifying progress proof

**Dependency:** GOV-00, MOD-01–06, BEP-01–07, FEP-01–02, VER-01.

**Objective:** prove the hosted UI receives and renders the server-originated
`verify_answer` start, then completion/failure, without provisional prose.

**Proof**

1. event store contains `status(stage="verify_answer", phase="started")`;
2. browser receives that sequence;
3. timeline renders `Verifying`;
4. no answer prose exists before verify completion;
5. completed update precedes first verified token;
6. fast completion may appear only as completed history, but the event remains;
7. skipped routes show only their actual stage set.

No minimum display duration, backend sleep, fake timer, or forced React paint is
allowed.

If the event is stored but absent in UI, fix frontend reduction/presentation in
a new narrow packet. If it is absent in storage, fix producer/mapper in a new
narrow packet. Do not patch both layers blindly.

## P08B-05 — Final hosted closure

**Objective:** rerun the complete canonical P08-22 proof after all repairs.

Require:

- current hosted migrations;
- health/readiness/query readiness;
- role-correct member and owner/admin behavior;
- real node/tool progress and Verifying;
- no pre-verification prose;
- non-empty verified answer or grounded refusal;
- bounded/skippable verified reveal;
- one durable terminal;
- durable assistant message and exactly-once settlement;
- monotonic reconnect with no duplicate provider cost;
- matching IDs absent locally;
- settled 390px and desktop captures;
- no unexpected test skip.

Any missing requirement means `FAIL` or `BLOCKED`, never a partial phase pass.
