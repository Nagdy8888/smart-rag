# P08-09 co-owned amendment — durable input and verified-final SSE

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Phase 8 packet 9 repairs production executor durability without unchecking
completed Phase 6 packets. Existing admission, budget true-up, deadline,
cancellation, ownership, idempotency, one-terminal, and replay/resume suites
are preserved:

- Fixture executors may still yield empty `completed`.
- `test_pending_orphan_without_input_emits_worker_unavailable` still holds
  when process input is missing and durable load is unavailable.
- Production mapping now holds `generate_answer` draft text until
  `verify_answer`, emits non-empty `token_delta`, and refuses empty
  `completed`.

Commands: `.\.venv\Scripts\pytest.exe tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_executor.py -q` → 31 passed, 1 skipped.

P08-20 documentation integrity: frontend action inventory and Phase 8
docs now treat this co-owned SSE repair as closed. Do not restore empty
`completed` success or typewriter streaming.

P08-22 live stack (2026-08-25): local admit now inserts `app.runs` after
the API image was rebuilt past MFA removal and pinned to
`host.docker.internal:54322`. One bounded browser Composite run
(`952d26fd-4c19-4fab-bcac-4c135854c772`) persisted `schema` then
sanitized `error`/`run_failed` 14 ms after `query.sse.started`, with
zero `token_delta` and zero usage. That is not verified-final delivery.
Details are in
[`phase-08-frontend-integration-evidence.md`](../phase-08-frontend-integration-evidence.md).
