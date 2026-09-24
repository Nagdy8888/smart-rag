# P2 - A finished answer is never labeled `deadline_exhausted`

## Goal

Today, in `verify_answer_node`, when the one verifier LLM call raises
`AnswerError("deadline_exhausted")` (from `sync_bridge.run_coro`, whose
timeout is the remaining run deadline capped at 45 s) or any other
`AnswerError` / `QueryCeilingError`, the node **returns early** with
`status="verified_partial", detail="deadline_exhausted"`. Three things go
wrong:

1. `apps/backend/.../sse/mapping/verified.py::_graceful_reason` treats
   `detail in DEADLINE_REASONS` as a deadline, so the stream ends with
   `deadline` + `partial(reason=deadline_exhausted)` even though the
   answer text passed every deterministic check and was streamed.
2. The scorer (`dual_metric.py::_is_deadline`) ranks that above phrase
   matching, so correct answers are counted as deadline failures.
3. The early return skips `maybe_persist_verified_citations` and never
   writes `verification` into state, so `app.citations` has no rows for
   an answer the user saw with citation chips.

Fix: do not return early. Record the verifier failure reason, fall
through to the normal terminal assignment, force `verified_partial` with
`detail="verifier_skipped:<reason>"`, persist citations as usual, and emit
an SSE `limitation` with code `verifier_skipped`. The `deadline` event
stays reserved for runs that produced no answer.

This does not change the run deadline (SQL `app.query_route_envelope`)
or `remaining_deadline_seconds`.

## Read first

- `apps/agents/src/smart_rag_agents/query/nodes/verify.py` lines
  ~154-208 (verifier call and the `except` block) and ~213-330 (terminal
  assignment, persistence, `VerificationResult`).
- `packages/core/src/smart_rag_core/query_answer/models.py`
  `class VerificationResult` (line ~211).
- `packages/core/src/smart_rag_core/query_routing/constants.py`
  (`LIMITATION_VERIFIER_OMITTED_LINKS`).
- `apps/backend/src/smart_rag_api/services/sse/mapping/contracts.py`
  (`DEADLINE_REASONS`, `PARTIAL_STATUSES`).
- `apps/backend/src/smart_rag_api/services/sse/mapping/verified.py`
  `_graceful_reason`.
- `apps/backend/src/smart_rag_api/services/sse/mapping/limitations.py`
  and `mapper.py` lines ~146-148.
- `apps/frontend/src/lib/limitations.ts` `LIMITATION_COPY`.
- Tests: `tests/unit/test_answer_citations_persist.py`
  (`test_verify_bound_persist_failure_is_not_verified` shows how to drive
  `verify_answer_node` with monkeypatches),
  `tests/unit/test_query_sse_mapping.py`
  (`test_mapper_verified_partial_is_not_a_deadline`).

## Steps

### 1. Constants

In `packages/core/src/smart_rag_core/query_routing/constants.py`, next to
`LIMITATION_VERIFIER_OMITTED_LINKS`, add (exact code):

```python
LIMITATION_VERIFIER_SKIPPED = "verifier_skipped"
"""Limitation code when the one verifier call failed or timed out and the
deterministically checked answer was released as ``verified_partial``."""

VERIFIER_SKIPPED_DETAIL_PREFIX = "verifier_skipped:"
"""Prefix for ``detail`` when the verifier was skipped. Never equal to a
``DEADLINE_REASONS`` member, so the SSE mapper does not emit ``deadline``."""
```

### 2. `VerificationResult`

In `models.py`, add to `VerificationResult` after `omitted_link_ids`
(exact code) and document it in `Attributes`:

```python
    verifier_skipped_reason: str | None = Field(default=None, max_length=64)
```

Import `Field` from pydantic if the module does not already.

### 3. `verify_answer_node`

a. Import `LIMITATION_VERIFIER_SKIPPED` is not needed here; import
`VERIFIER_SKIPPED_DETAIL_PREFIX` from
`smart_rag_core.query_routing.constants` (extend the existing import).

b. Before the `if checked.atomic_links and not is_web:` block add:

```python
    verifier_skipped_reason: str | None = None
```

c. Replace the whole `except (AnswerError, QueryCeilingError) as exc:`
block (both `return {...}` branches) with (exact code):

```python
        except (AnswerError, QueryCeilingError) as exc:
            reason = getattr(exc, "reason", None) or str(exc) or "verifier_failed"
            verifier_skipped_reason = str(reason)[:64]
```

d. After the terminal assignment `if/elif/else` that ends with
`terminal = "verified"; detail = "answer verified"` and **before** the
`if terminal == "verified" and deps.model_gateway is None ...` check, add
(exact code):

```python
    if verifier_skipped_reason is not None and terminal in {
        "verified",
        "verified_partial",
    }:
        terminal = "verified_partial"
        detail = f"{VERIFIER_SKIPPED_DETAIL_PREFIX}{verifier_skipped_reason}"[:128]
```

Refusals and insufficient-evidence terminals are unchanged.

e. In the `VerificationResult(...)` construction add
`verifier_skipped_reason=verifier_skipped_reason,`.

f. Update the node docstring: state inputs/outputs now include
`verifier_skipped_reason`; failure route: verifier failure degrades to
`verified_partial` and still persists citations.

### 4. SSE limitation

In `limitations.py` add a list-returning function and keep the old one
delegating to it (exact code):

```python
def limitations_from_update(
    update: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Return every signed limitation carried by a verify update.

    Args:
        update: Node return mapping.

    Returns:
        ``limitation`` events in emission order: omitted links first, then
        skipped verifier. Empty when the update carries none.
    """

    verification = update.get("verification")
    if not isinstance(verification, dict):
        return []
    typed_verification = cast(dict[object, object], verification)
    events: list[tuple[str, dict[str, object]]] = []
    if typed_verification.get("omitted_link_ids"):
        events.append(("limitation", {"code": LIMITATION_VERIFIER_OMITTED_LINKS}))
    if typed_verification.get("verifier_skipped_reason"):
        events.append(("limitation", {"code": LIMITATION_VERIFIER_SKIPPED}))
    return events


def limitation_from_update(
    update: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return the first signed limitation, kept for existing callers.

    Args:
        update: Node return mapping.

    Returns:
        First ``limitation`` event or None.
    """

    events = limitations_from_update(update)
    return events[0] if events else None
```

Import `LIMITATION_VERIFIER_SKIPPED`. In `mapper.py` replace

```python
            limitation = limitation_from_update(update)
            if limitation is not None:
                events.append(limitation)
```

with

```python
            events.extend(limitations_from_update(update))
```

and fix the import. P3 adds a third code to this same function.

### 5. Frontend copy

In `apps/frontend/src/lib/limitations.ts` `LIMITATION_COPY` add:

```ts
  verifier_skipped:
    "The answer passed citation checks, but the final verification step timed out. Treat it as partial.",
```

### 6. Docs

- `docs/api/SSE.md`: add `verifier_skipped` to the limitation code list
  with the sentence above and note that `deadline` is emitted only when
  no answer was produced.
- The agent doc that describes `verify_answer` terminal states (search
  `docs/agent` for `verified_partial`): add the `verifier_skipped:<reason>`
  detail and that citations persist on that path.

## Tests

### New file `tests/unit/test_verify_verifier_skipped.py`

Model it on `test_verify_bound_persist_failure_is_not_verified` in
`tests/unit/test_answer_citations_persist.py` (same imports, same runtime
mock, same state construction). Differences:

- `deps = QueryGraphDeps(connection=MagicMock(), model_gateway=MagicMock(), verifier_prompt_text="verifier")`
  so a verifier caller is built.
- `monkeypatch.setattr("smart_rag_agents.query.nodes.verify.run_verifier_batch", MagicMock(side_effect=AnswerError("deadline_exhausted")))`
  with `from smart_rag_core.query_answer.exceptions import AnswerError`.
- `monkeypatch.setattr("smart_rag_agents.query.nodes.verify.assert_call_available", lambda remaining: remaining)`
  if `assert_call_available` would otherwise raise for the test state.
- `persist = MagicMock(return_value=())`; monkeypatch
  `smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations`
  to it. (P3 changes this return type; if P3 already landed, return
  `CitationPersistResult(ids=(), skipped=())`.)

Assertions (exact):

```python
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "verifier_skipped:deadline_exhausted"
    assert verified["verification"]["verifier_skipped_reason"] == "deadline_exhausted"
    assert verified["verification"]["status"] == "verified_partial"
    persist.assert_called_once()
```

Add a second test where `run_verifier_batch` raises
`AnswerError("gateway_failed")` and assert
`detail == "verifier_skipped:gateway_failed"`.

### `tests/unit/test_query_sse_mapping.py`

Add (exact code; reuse the file's `_payload` helper and
`VERIFY_ANSWER_NODE` import):

```python
def test_mapper_verifier_skipped_is_partial_not_deadline() -> None:
    """A skipped verifier releases the answer as partial with a limitation."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {
            VERIFY_ANSWER_NODE: {
                "status": "verified_partial",
                "detail": "verifier_skipped:deadline_exhausted",
                "answer": _payload("Refund period is 30 days.", status="complete"),
                "verification": {
                    "omitted_link_ids": [],
                    "verifier_skipped_reason": "deadline_exhausted",
                },
            }
        }
    )
    types = [item[0] for item in events]
    assert "deadline" not in types
    assert ("limitation", {"code": "verifier_skipped"}) in events
    assert types[-1] == "partial"
    assert events[-1][1] == {"reason": "verified_partial"}
```

If `consume_chunk` validates `verification` against `VerificationResult`,
build a full `VerificationResult(...).model_dump(mode="json")` instead of
the bare dict.

## Commands

```powershell
uv run python -m pytest tests/unit/test_verify_verifier_skipped.py tests/unit/test_answer_citations_persist.py tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_verified_final.py tests/unit/test_answer_verifier.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
uv run python scripts/check.py --tier docs
```

## Done when

- [ ] `verify_answer_node` has no early `return` inside the verifier
      `except` block.
- [ ] Verifier failure => `status == "verified_partial"`,
      `detail == "verifier_skipped:<reason>"`, citations persisted once,
      `verification.verifier_skipped_reason` set.
- [ ] Mapper emits `limitation(code=verifier_skipped)` and no `deadline`
      for that update; existing deadline tests
      (`test_mapper_answer_deadline_reserve_emits_deadline_then_partial`)
      still pass.
- [ ] Frontend copy added; lint/typecheck pass.
- [ ] Docs updated; unit, lint, types, docs tiers pass.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
fix(verify): keep deterministically checked answers when the verifier times out (P2)
```

## Do not

- Do not add `verifier_skipped:*` to `DEADLINE_REASONS`.
- Do not change `sync_bridge.py`, `remaining_deadline_seconds`, or any
  SQL envelope.
- Do not release a `refused` or `insufficient_evidence` answer because
  the verifier was skipped; only `verified`/`verified_partial` are
  affected.
