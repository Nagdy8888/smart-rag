# P3 - One unresolvable citation must not kill the answer

## Goal

`app.insert_run_citation_v2` (migration
`20260915140000_pdf_paragraph_citations_v1.sql`, lines ~162-190) requires
a passage citation's span to sit inside **exactly one** search-representative
child of the cited chunk (or inside the chunk itself when it has no
children). It raises `query_citation:span_not_contained` (0 matches) or
`query_citation:leaf_ambiguous` (>1 matches). The Python span check in
`bind.py` only guarantees the span is inside the cited chunk's
`raw_text`, so a span that straddles two children, or a sentence repeated
in two children, fails at the database.

Today `persist_answer_citations` raises on the first failure. The
transaction is then aborted for every later citation, and
`verify_answer_node` terminates the run `insufficient_evidence`
(`detail="citation_persist_failed"`). Three KA50 answers (`k31`, `k34`,
`k49`) died this way with correct text.

Fix, in order of preference per citation:

1. Wrap each passage insert in its own `SAVEPOINT` so a failure does not
   poison the transaction.
2. On `span_not_contained` / `leaf_ambiguous` / `page_ambiguous`, retry
   once with the span's leading sentence (>= 24 chars). A straddling span
   usually starts inside one child.
3. If the retry also fails for a leaf-resolution reason, **skip that
   citation**, record it, and continue. Any other reason
   (`authorization_rejected`, `run_forbidden`, `replay_conflict`,
   `answer_bounds_exceeded`, `database_rejected`, ...) still raises and
   still fails closed as today.
4. In `verify_answer_node`: skipped citations are removed from the
   released payload (no unbacked chips). If at least one citation
   persisted, terminal is `verified_partial` with
   `detail="citation_leaf_unresolved"` and an SSE limitation
   `citation_leaf_unresolved`. If none persisted, terminal stays
   `insufficient_evidence` with `detail="citation_leaf_unresolved"`
   (fail closed: a released answer must have durable citations).

No SQL change.

## Read first

- `packages/core/src/smart_rag_core/query_answer/citations.py`:
  `_raise_citation_error`, `persist_answer_citations` (line ~128),
  `maybe_persist_verified_citations` (line ~253), `LOGGER`.
- `apps/agents/src/smart_rag_agents/query/nodes/verify.py` lines
  ~295-330 (the `else:` branch that calls
  `maybe_persist_verified_citations`, and `VerificationResult(...)`).
- `packages/core/src/smart_rag_core/query_answer/models.py`
  `VerificationResult`, `AnswerCitation` fields (`chunk_id`, `span`,
  `paragraph_index`, `atomic_link_id`, `table_id`, `inference`,
  `source_ranges`).
- `packages/core/src/smart_rag_core/query_routing/constants.py`.
- `apps/backend/src/smart_rag_api/services/sse/mapping/limitations.py`
  (after P2 it has `limitations_from_update`; if P2 has not landed, do P2
  step 4 first as part of this packet).
- `apps/frontend/src/lib/limitations.ts`.
- `tests/unit/test_answer_citations_persist.py` whole file (imports at
  the top: `verifier_fusion`, `verifier_passage`, `MagicMock`, `patch`).
- `supabase/migrations/20260915140000_pdf_paragraph_citations_v1.sql`
  lines 100-260 (read only; list of `RAISE EXCEPTION` codes).

## Steps

### 1. Result types and helpers in `citations.py`

Add imports `import re` and `from dataclasses import dataclass` (check
what is already imported). Add after `_REASON_PREFIX` (exact code):

```python
LEAF_RESOLUTION_REASONS = frozenset(
    {"span_not_contained", "leaf_ambiguous", "page_ambiguous"}
)
"""``insert_run_citation_v2`` reasons that describe one citation's leaf
resolution rather than the run, the caller, or the transaction."""

MIN_RETRY_SPAN_CHARS = 24
"""Shortest leading sentence worth retrying as a narrower span."""

_SENTENCE_END = re.compile(r"[.!?\u061f\u3002]\s|\n")


@dataclass(frozen=True, slots=True)
class SkippedCitation:
    """One passage citation that could not be pinned to a single leaf.

    Attributes:
        chunk_id: Cited chunk id as text.
        paragraph_index: Paragraph the citation belonged to, if any.
        span: Span the model cited (already contained in the chunk text).
        reason: Last ``insert_run_citation_v2`` leaf-resolution reason.
    """

    chunk_id: str
    paragraph_index: int | None
    span: str
    reason: str


@dataclass(frozen=True, slots=True)
class CitationPersistResult:
    """Outcome of one citation batch.

    Attributes:
        ids: Inserted ``app.citations`` ids in write order.
        skipped: Passage citations skipped for leaf-resolution reasons.
    """

    ids: tuple[UUID, ...] = ()
    skipped: tuple[SkippedCitation, ...] = ()


def _citation_error_reason(exc: BaseException) -> str:
    """Extract the ``query_citation:`` reason from a database error.

    Args:
        exc: Driver or database error.

    Returns:
        Reason token, or ``database_rejected`` when the message has none.
    """

    message = str(exc)
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        return tail.split("\n")[0]
    return "database_rejected"


def leading_sentence(span: str, *, minimum: int = MIN_RETRY_SPAN_CHARS) -> str:
    """Return the first sentence of a span when it is a strictly shorter retry.

    Args:
        span: Verbatim span already contained in the cited chunk text.
        minimum: Shortest acceptable retry length.

    Returns:
        Leading sentence including its terminal punctuation, or an empty
        string when the span has one sentence or the head is too short.
    """

    stripped = span.strip()
    match = _SENTENCE_END.search(stripped)
    if match is None:
        return ""
    head = stripped[: match.start() + 1].strip()
    if len(head) < minimum or head == stripped:
        return ""
    return head


def drop_skipped_citations(
    answer: AnswerPayload,
    skipped: Sequence[SkippedCitation],
) -> AnswerPayload:
    """Remove passage citations that were not persisted.

    Args:
        answer: Verified answer payload.
        skipped: Citations skipped by ``persist_answer_citations``.

    Returns:
        Payload without the skipped citations. Paragraphs and atomic links
        are unchanged. Unchanged when nothing was skipped.
    """

    if not skipped:
        return answer
    keys = {(item.chunk_id, item.paragraph_index, item.span) for item in skipped}
    kept = tuple(
        citation
        for citation in answer.citations
        if (
            str(citation.chunk_id or ""),
            citation.paragraph_index,
            (citation.span or "").strip(),
        )
        not in keys
    )
    if len(kept) == len(answer.citations):
        return answer
    return answer.model_copy(update={"citations": kept})
```

Rewrite `_raise_citation_error` to call `_citation_error_reason` (same
behavior). Import `Sequence` from `collections.abc`.

### 2. Per-citation savepoint in `persist_answer_citations`

Change the return annotation to `-> CitationPersistResult`, update the
docstring (`Returns: Inserted ids and skipped leaf-unresolved citations.`
and `Raises:` now says "Any non-leaf reason: ACL, replay, cap, chunk or
span required, database error."). Add a helper (exact code):

```python
def _insert_passage_citation(
    cursor: psycopg.Cursor[Any],
    *,
    caller: CallerContext,
    run_id: UUID,
    index: int,
    citation: AnswerCitation,
    span: str,
    provenance: dict[str, object],
) -> UUID | None:
    """Run ``insert_run_citation_v2`` for one span attempt.

    Args:
        cursor: Open cursor inside the run transaction.
        caller: Server-derived caller.
        run_id: Admitted run.
        index: Write index within the run.
        citation: Passage citation.
        span: Span attempt, at most 1000 chars.
        provenance: Expand-only provenance jsonb.

    Returns:
        Inserted citation id, or None when the function returned no row.

    Raises:
        psycopg.Error: Any database rejection, including leaf resolution.
    """

    cursor.execute(
        """
        SELECT citation_id
        FROM app.insert_run_citation_v2(
          %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s::jsonb
        )
        """,
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            str(run_id),
            index,
            citation.chunk_id,
            span[:1000],
            citation.paragraph_index,
            _json(provenance),
        ),
    )
    row = cursor.fetchone()
    return UUID(str(row[0])) if row is not None else None
```

Match the `_json(provenance)` call and cursor typing to what the file
already uses. Then replace the passage loop body (from
`provenance = citation_provenance_payload(` through `index += 1`) with
(exact code):

```python
            provenance = citation_provenance_payload(
                fusion=fusion,
                answer=answer,
                chunk_id=citation.chunk_id,
                table_id=citation.table_id,
                atomic_link_id=citation.atomic_link_id,
                inference=citation.inference,
                source_ranges=citation.source_ranges,
            )
            attempts: tuple[str, ...] = (span,)
            retry = leading_sentence(span)
            if retry:
                attempts = (span, retry)
            inserted: UUID | None = None
            last_reason = ""
            for attempt in attempts:
                cursor.execute("SAVEPOINT citation_leaf")
                try:
                    inserted = _insert_passage_citation(
                        cursor,
                        caller=caller,
                        run_id=run_id,
                        index=index,
                        citation=citation,
                        span=attempt,
                        provenance=provenance,
                    )
                except psycopg.Error as exc:
                    cursor.execute("ROLLBACK TO SAVEPOINT citation_leaf")
                    cursor.execute("RELEASE SAVEPOINT citation_leaf")
                    last_reason = _citation_error_reason(exc)
                    if last_reason not in LEAF_RESOLUTION_REASONS:
                        raise QueryAdmissionError(last_reason) from exc
                    continue
                cursor.execute("RELEASE SAVEPOINT citation_leaf")
                break
            if inserted is None:
                skipped.append(
                    SkippedCitation(
                        chunk_id=str(citation.chunk_id),
                        paragraph_index=citation.paragraph_index,
                        span=span,
                        reason=last_reason or "span_not_contained",
                    )
                )
                LOGGER.info(
                    "citation leaf unresolved",
                    extra={
                        "event": "query.verify.citation_leaf_unresolved",
                        "run_id": str(run_id),
                        "reason": last_reason,
                    },
                )
                continue
            ids.append(inserted)
            index += 1
```

Declare `skipped: list[SkippedCitation] = []` next to `ids`. Leave the
`table_citations` loop as is. Change the final `return tuple(ids)` to
`return CitationPersistResult(ids=tuple(ids), skipped=tuple(skipped))`.

Why the savepoint: after a `RAISE EXCEPTION` inside the run transaction
Postgres rejects every later statement until a rollback; `ROLLBACK TO
SAVEPOINT` undoes only the failed insert. Autocommit stays off and the
SSE consume loop still commits after verify, unchanged.

### 3. `maybe_persist_verified_citations`

Return annotation `-> CitationPersistResult`. Replace each `return ()` with
`return CitationPersistResult()`. The `return persist_answer_citations(...)`
already returns the new type. Update the docstring `Returns`.

### 4. `VerificationResult`

Add after `verifier_skipped_reason` (or after `omitted_link_ids` if P2 has
not landed):

```python
    skipped_citation_count: int = Field(default=0, ge=0)
```

Document it in `Attributes`.

### 5. `verify_answer_node`

Import `drop_skipped_citations` from
`smart_rag_core.query_answer.citations` (extend the existing import).
Add `skipped_citation_count = 0` before the `if is_web:` block. Replace
the `else:` branch that calls `maybe_persist_verified_citations` with
(exact code):

```python
    else:
        try:
            persisted = maybe_persist_verified_citations(
                deps.connection,
                caller=caller_from_runtime(context) if context is not None else None,
                run_id=context.run_id if context is not None else None,
                fusion=fusion,
                answer=checked,
            )
        except (QueryAdmissionError, psycopg.Error):
            if deps.connection is not None and context is not None:
                terminal = "insufficient_evidence"
                detail = "citation_persist_failed"
        else:
            if persisted.skipped:
                skipped_citation_count = len(persisted.skipped)
                checked = drop_skipped_citations(checked, persisted.skipped)
                if not persisted.ids:
                    terminal = "insufficient_evidence"
                    detail = "citation_leaf_unresolved"
                elif terminal in {"verified", "verified_partial"}:
                    terminal = "verified_partial"
                    detail = "citation_leaf_unresolved"
```

Add `skipped_citation_count=skipped_citation_count,` to
`VerificationResult(...)`. Update the node docstring (failure route).

### 6. Constants, SSE, frontend

- `constants.py`: `LIMITATION_CITATION_LEAF_UNRESOLVED = "citation_leaf_unresolved"`
  with a docstring.
- `limitations.py` `limitations_from_update`: after the
  `verifier_skipped_reason` check add

```python
    if int(typed_verification.get("skipped_citation_count") or 0) > 0:
        events.append(("limitation", {"code": LIMITATION_CITATION_LEAF_UNRESOLVED}))
```

- `limitations.ts` `LIMITATION_COPY`:

```ts
  citation_leaf_unresolved:
    "Some citations could not be pinned to a single page and were left out. The remaining citations are verified.",
```

### 7. Docs

- `docs/development/phase-06/p06-46-pdf-citation-persistence-2026-09-15.md`:
  add a section "Leaf-unresolved citations (2026-09)" describing the
  savepoint, retry, skip rule, the two terminals, and the limitation
  code; include a `sequenceDiagram` (verify node -> citations.py ->
  Postgres) showing the savepoint retry.
- `docs/api/SSE.md`: add `citation_leaf_unresolved` to the limitation
  codes.
- `docs/README.md`: update last-reviewed for the touched docs.

## Tests (`tests/unit/test_answer_citations_persist.py`)

### Update existing assertions

- `test_maybe_persist_skips_without_connection`: `== ()` becomes
  `== CitationPersistResult()`.
- `test_maybe_persist_delegates_once_when_bound`: patch `return_value=CitationPersistResult(ids=inserted)`;
  `assert first.ids == inserted`; `assert second == CitationPersistResult()`.
- `test_live_persist_does_not_backfill_fusion_citations` and
  `test_persist_answer_citations_lists_for_owned_run` (integration, skip
  without DB): wherever they use the return value as a tuple, use `.ids`.
- `test_maybe_persist_reraises_bound_failure` and
  `test_verify_bound_persist_failure_is_not_verified`: unchanged.

Import `CitationPersistResult`, `SkippedCitation`, `leading_sentence`,
`drop_skipped_citations` from `smart_rag_core.query_answer.citations`.

### New fake cursor (exact code, put near the top of the file)

```python
class _FakeCursor:
    """Cursor that fails chosen ``insert_run_citation_v2`` attempts."""

    def __init__(self, failures: dict[int, str]) -> None:
        self.statements: list[str] = []
        self.params: list[object] = []
        self._failures = failures
        self._attempts = 0
        self._pending: tuple[object, ...] | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        """Record the statement and fail configured insert attempts."""

        text = " ".join(sql.split())
        self.statements.append(text)
        self.params.append(params)
        if "insert_run_citation_v2" in text:
            self._attempts += 1
            reason = self._failures.get(self._attempts)
            if reason:
                raise psycopg.errors.RaiseException(f"query_citation:{reason}")
            self._pending = (uuid4(),)

    def fetchone(self) -> tuple[object, ...] | None:
        row, self._pending = self._pending, None
        return row


def _connection_with(cursor: _FakeCursor) -> MagicMock:
    """Return a connection whose ``cursor()`` yields ``cursor``."""

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection
```

### New tests (exact code)

```python
_TWO_SENTENCES = "Refund period is 30 days from purchase. Shipping is refunded too."


def test_persist_retries_with_leading_sentence_then_succeeds() -> None:
    """A straddling span is retried once with its first sentence."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    chunk_id = fusion.evidence[0].chunk_id
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(AnswerCitation(chunk_id=chunk_id, span=_TWO_SENTENCES, paragraph_index=0),),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "span_not_contained"})
    result = persist_answer_citations(
        _connection_with(cursor),
        caller=MagicMock(user_id=uuid4()),
        run_id=uuid4(),
        fusion=fusion,
        answer=answer,
    )
    assert len(result.ids) == 1
    assert result.skipped == ()
    inserts = [p for s, p in zip(cursor.statements, cursor.params) if "insert_run_citation_v2" in s]
    assert len(inserts) == 2
    assert inserts[1][6] == leading_sentence(_TWO_SENTENCES)
    assert "SAVEPOINT citation_leaf" in cursor.statements
    assert "ROLLBACK TO SAVEPOINT citation_leaf" in cursor.statements


def test_persist_skips_leaf_unresolved_and_keeps_other_citations() -> None:
    """Two leaf failures skip one citation; the next citation still persists."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    chunk_id = fusion.evidence[0].chunk_id
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(
            AnswerCitation(chunk_id=chunk_id, span=_TWO_SENTENCES, paragraph_index=0),
            AnswerCitation(chunk_id=chunk_id, span="Shipping is refunded too.", paragraph_index=0),
        ),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "leaf_ambiguous", 2: "span_not_contained"})
    result = persist_answer_citations(
        _connection_with(cursor),
        caller=MagicMock(user_id=uuid4()),
        run_id=uuid4(),
        fusion=fusion,
        answer=answer,
    )
    assert len(result.ids) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "span_not_contained"
    assert result.skipped[0].chunk_id == str(chunk_id)
    assert cursor.statements.count("ROLLBACK TO SAVEPOINT citation_leaf") == 2


def test_persist_non_leaf_reason_still_fails_closed() -> None:
    """ACL and replay reasons raise as before."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(AnswerCitation(chunk_id=fusion.evidence[0].chunk_id, span=_TWO_SENTENCES, paragraph_index=0),),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "authorization_rejected"})
    with pytest.raises(QueryAdmissionError, match="authorization_rejected"):
        persist_answer_citations(
            _connection_with(cursor),
            caller=MagicMock(user_id=uuid4()),
            run_id=uuid4(),
            fusion=fusion,
            answer=answer,
        )


def test_leading_sentence_rules() -> None:
    """Retry spans are strictly shorter, long enough, and end at a sentence."""

    assert leading_sentence(_TWO_SENTENCES) == "Refund period is 30 days from purchase."
    assert leading_sentence("Short one. Two.") == ""
    assert leading_sentence("No terminal punctuation at all here") == ""
    assert leading_sentence("Only one sentence but a long one indeed.") == ""


def test_drop_skipped_citations_removes_only_matching_span() -> None:
    """Dropping is keyed on chunk, paragraph, and span."""

    chunk = uuid4()
    answer = AnswerPayload(
        answer_text="x",
        citations=(
            AnswerCitation(chunk_id=chunk, span="A sentence.", paragraph_index=0),
            AnswerCitation(chunk_id=chunk, span="Another one.", paragraph_index=0),
        ),
        status="complete",
    )
    dropped = drop_skipped_citations(
        answer,
        (SkippedCitation(chunk_id=str(chunk), paragraph_index=0, span="A sentence.", reason="leaf_ambiguous"),),
    )
    assert [c.span for c in dropped.citations] == ["Another one."]
```

If `AnswerCitation.chunk_id` is typed `str` rather than `UUID`, pass
`str(chunk_id)`; check the model.

### Verify node tests (same file, next to `test_verify_bound_persist_failure_is_not_verified`)

Copy that test twice and change only the persist mock and assertions:

- `test_verify_partial_when_some_citations_skipped`: the state answer has
  two citations on `chunk_id` with spans `"Refund period"` and
  `"30 days"`; mock returns
  `CitationPersistResult(ids=(uuid4(),), skipped=(SkippedCitation(chunk_id=str(chunk_id), paragraph_index=0, span="30 days", reason="leaf_ambiguous"),))`.
  Assert `verified["status"] == "verified_partial"`,
  `verified["detail"] == "citation_leaf_unresolved"`,
  `verified["verification"]["skipped_citation_count"] == 1`,
  `len(verified["answer"]["citations"]) == 1`.
- `test_verify_insufficient_when_every_citation_skipped`: mock returns
  `CitationPersistResult(ids=(), skipped=(...one...))`. Assert
  `status == "insufficient_evidence"` and
  `detail == "citation_leaf_unresolved"`.

### SSE (`tests/unit/test_query_sse_mapping.py`)

Add a test like P2's, with `"verification": {"omitted_link_ids": [], "skipped_citation_count": 1}`
and `status="verified_partial"`, asserting
`("limitation", {"code": "citation_leaf_unresolved"}) in events` and the
terminal is `partial(reason=verified_partial)`.

## Commands

```powershell
uv run python -m pytest tests/unit/test_answer_citations_persist.py tests/unit/test_query_sse_mapping.py tests/unit/test_answer_paragraph_citations.py tests/unit/test_pdf_paragraph_citation_fixture.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
uv run python scripts/check.py --tier docs
```

Optional live proof: rebuild the `api` image first
(`00-rules-and-commands.md`, "Docker rebuild before any live run"; probe
must print `P3 present`), then run the KA50 subset
`k31 k34 k49` into `.private-eval/runs/p3/`. Expected: no
`citation_persist_failed`; terminals `verified_partial` or `completed`;
`app.citations` rows exist for each run id
(`SELECT count(*) FROM app.citations WHERE run_id = %s`).

## Done when

- [ ] `persist_answer_citations` returns `CitationPersistResult`, uses a
      savepoint per attempt, retries once with `leading_sentence`, skips
      only `LEAF_RESOLUTION_REASONS`, raises everything else.
- [ ] `verify_answer_node`: some skipped => `verified_partial` +
      `citation_leaf_unresolved` and skipped chips removed; all skipped =>
      `insufficient_evidence` + `citation_leaf_unresolved`; raise =>
      `citation_persist_failed` unchanged.
- [ ] SSE emits `limitation(code=citation_leaf_unresolved)`; frontend
      copy exists.
- [ ] All listed tests pass; unit, lint, types, docs, frontend checks
      pass.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
fix(citations): savepoint per citation, retry leading sentence, skip unresolvable leaves (P3)
```

## Do not

- Do not modify the SQL function or add a migration.
- Do not tolerate `authorization_rejected`, `run_forbidden`,
  `conversation_forbidden`, `unauthorized_or_missing_passage`,
  `replay_conflict`, `answer_bounds_exceeded`, `duplicate_run_index`,
  `chunk_required`, `citation_span_required`, `invalid_*`, or
  `database_rejected`.
- Do not commit inside `persist_answer_citations`.
- Do not release an answer with zero persisted citations as
  `verified_partial`.
