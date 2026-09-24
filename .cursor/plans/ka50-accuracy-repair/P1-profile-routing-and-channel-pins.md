# P1 - Route small corpora to `hybrid_long_document_v2` and pin channel heads

## Goal

Stop the two measured retrieval-side losses:

1. **Cap drop (19/50).** `hybrid_default_v1` reranks at most 5 chunks per
   document and keeps at most 2 per document in final evidence
   (`document_quota: 2`). In a 4-document corpus where one document holds
   1015 of 1814 representatives, the gold page is routinely the 6th-12th
   chunk of its own document in fused order and never reaches the
   reranker. `hybrid_long_document_v2` (cap 20, quota 12, already frozen
   and digest-pinned) never ran because its only trigger is an exact-one
   title match in the question.
2. **RRF demotion.** With `rrf_k=60` and equal weights, a chunk found by
   both dense and BM25 always outranks a chunk found only by dense, even
   dense rank 1. `k11`, `k28`, `k32` are dense rank 1 and fused rank
   22-26.

Two changes, both bounded and both recorded in one ADR:

- **A.** `select_runtime_profile` also chooses
  `hybrid_long_document_v2` when the caller's authorized corpus is small
  (<= 8 current documents) and its largest document has more than 5
  representatives. Resolution stays `unscoped`; no version filter is
  applied; only the frozen profile changes.
- **B.** The top 5 authorized dense IDs and top 5 authorized BM25 IDs are
  pinned into the rerank pool. Pins bypass the per-document cap, count
  toward `pool_size`, never add unauthorized IDs (they must already be in
  the fused list), and never reorder the pool (fused order is kept). The
  reranker still decides the final order.

Depends on P0 (so the effect is visible as `rerank_pool_ids`).

## Read first

- `packages/core/src/smart_rag_core/retrieval/source_scope.py` whole file.
  Confirm `select_runtime_profile(*, resolution, version_id,
  representative_count, query_class) -> tuple[str, str]`,
  `ResolvedRetrievalScope`, `resolve_retrieval_scope`,
  `_count_representatives`, `_fetch_exact_title` (SQL pattern with
  `app.caller_can_read_document(%s, %s, d.id)`).
- `packages/core/src/smart_rag_core/retrieval/rerank.py` functions
  `rerank_preload_ids` (line ~229) and `build_rerank_pool` (line ~300),
  and `collapse_exact_duplicate_passages`, `content_hash`,
  `excerpt_text`.
- `packages/core/src/smart_rag_core/retrieval/context.py`
  `select_hybrid_context` (line ~169) where it calls `build_rerank_pool`.
- `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py`
  lines ~296-300 (`dense_ids`, `bm25_ids`, `term_ids`), ~377
  (`fused_ids`), ~392-397 (`rerank_preload_ids`), ~412-422
  (`select_hybrid_context`).
- `tests/unit/test_long_document_profile.py`,
  `tests/unit/test_source_scope.py`, `tests/unit/test_hybrid_rerank.py`
  (helpers `_candidate`, `_passage`).
- `docs/adr/ADR-hybrid-long-document-profile.md`,
  `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md`.

## Part A - profile routing

### A1. Constants and signature in `source_scope.py`

After `RERANK_PER_DOCUMENT_LEGACY_CAP` add (exact code):

```python
SMALL_CORPUS_MAX_DOCUMENTS = 8
"""Authorized current-document count at or below which the five-per-document
rerank cap silences a long document instead of balancing many documents."""
```

Replace `select_runtime_profile` with (exact code; keep the docstring and
add the new argument and the new reason to it):

```python
def select_runtime_profile(
    *,
    resolution: SourceResolution,
    version_id: UUID | None,
    representative_count: int,
    query_class: str | None,
    authorized_document_count: int = 0,
) -> tuple[str, str]:
    scoped_long = (
        resolution is SourceResolution.EXACT_ONE
        and version_id is not None
        and representative_count > RERANK_PER_DOCUMENT_LEGACY_CAP
    )
    small_corpus_long = (
        resolution is not SourceResolution.EXACT_ONE
        and 0 < authorized_document_count <= SMALL_CORPUS_MAX_DOCUMENTS
        and representative_count > RERANK_PER_DOCUMENT_LEGACY_CAP
    )
    if not (scoped_long or small_corpus_long):
        return HYBRID_DEFAULT_PROFILE_ID, "default_profile_required"
    if not long_document_runtime_enabled():
        return HYBRID_DEFAULT_PROFILE_ID, "unfrozen_long_document_denied"
    if query_class in TRIVIAL_DEFAULT_QUERY_CLASSES:
        return HYBRID_DEFAULT_PROFILE_ID, "trivial_exact_default_profile"
    if scoped_long:
        return LONG_DOCUMENT_PROFILE_ID, "long_document_eligible"
    return LONG_DOCUMENT_PROFILE_ID, "small_corpus_long_document"
```

Docstring additions: `authorized_document_count: Current documents the
caller may read. ``0`` means unknown and never triggers the small-corpus
rule.` and the `Returns` sentence naming
`small_corpus_long_document`.

### A2. Scope dataclass

In `ResolvedRetrievalScope` add the last field (exact code) and document
it in `Attributes`:

```python
    authorized_document_count: int = 0
```

Update the `representative_count` attribute doc to: `Authorized
representative passages for the resolved version, or the largest
authorized document's count when the small-corpus rule applied, else 0.`

### A3. Corpus count helper

Add after `_count_representatives` (exact code):

```python
def _count_authorized_corpus(
    connection: psycopg.Connection,
    caller: CallerContext,
) -> tuple[int, int]:
    """Count authorized current documents and the largest representative set.

    The second query runs only when the corpus is small enough for the
    small-corpus rule, so large tenants pay one cheap count.

    Args:
        connection: Canonical Postgres ``app_api`` connection.
        caller: Server-derived identity.

    Returns:
        ``(document_count, largest_representative_count)``. The second
        value is ``0`` when the corpus is empty or larger than
        ``SMALL_CORPUS_MAX_DOCUMENTS``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)::int
            FROM app.documents AS d
            INNER JOIN app.document_versions AS dv
              ON dv.id = d.current_version_id
            WHERE d.deleted_at IS NULL
              AND dv.deleted_at IS NULL
              AND app.caller_can_read_document(%s, %s, d.id)
            """,
            (caller.rpc_user_id(), caller.rpc_role()),
        )
        row = cursor.fetchone()
        documents = int(row[0]) if row is not None else 0
        if documents == 0 or documents > SMALL_CORPUS_MAX_DOCUMENTS:
            return documents, 0
        cursor.execute(
            """
            SELECT COALESCE(max(per_version.n), 0)::int
            FROM (
              SELECT count(*) AS n
              FROM app.document_chunks AS c
              INNER JOIN app.documents AS d
                ON d.current_version_id = c.version_id
              WHERE d.deleted_at IS NULL
                AND c.deleted_at IS NULL
                AND c.is_search_representative
                AND app.caller_can_read_document(%s, %s, d.id)
              GROUP BY c.version_id
            ) AS per_version
            """,
            (caller.rpc_user_id(), caller.rpc_role()),
        )
        largest = cursor.fetchone()
    return documents, int(largest[0]) if largest is not None else 0
```

### A4. Use it in `resolve_retrieval_scope`

Replace the block that starts at `counted = representative_count` and ends
at the `return ResolvedRetrievalScope(...)` with (exact code):

```python
    counted = representative_count
    document_count = 0
    if (
        connection is not None
        and version_id is not None
        and counted <= 0
        and resolution is SourceResolution.EXACT_ONE
    ):
        counted = _count_representatives(connection, version_id)
    if connection is not None and resolution is not SourceResolution.EXACT_ONE:
        document_count, largest = _count_authorized_corpus(connection, caller)
        counted = max(counted, largest)
    profile_id, reason = select_runtime_profile(
        resolution=resolution,
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        representative_count=counted,
        query_class=query_class,
        authorized_document_count=document_count,
    )
    return ResolvedRetrievalScope(
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        whole_document=whole_document and resolution is SourceResolution.EXACT_ONE,
        representative_count=counted,
        query_class=query_class,
        candidate_profile_id=profile_id,
        eligibility_reason=reason,
        resolution=resolution,
        selector_texts=selector_texts
        if resolution is SourceResolution.EXACT_ONE
        else (),
        authorized_document_count=document_count,
    )
```

Update the function docstring: remove "The long-document candidate
remains runtime-denied until freeze" and add one sentence describing the
small-corpus rule.

### A5. Tests for Part A

`tests/unit/test_long_document_profile.py` - add (exact code):

```python
def test_small_corpus_long_document_selects_v2() -> None:
    """Unscoped questions on a small corpus with a long document use v2."""

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class="factual_definition",
        authorized_document_count=4,
    )
    assert profile_id == LONG_DOCUMENT_PROFILE_ID
    assert reason == "small_corpus_long_document"


def test_large_corpus_and_short_documents_stay_default() -> None:
    """Nine documents, or only short documents, keep the default profile."""

    large, large_reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class=None,
        authorized_document_count=9,
    )
    short, short_reason = select_runtime_profile(
        resolution=SourceResolution.AMBIGUOUS,
        version_id=None,
        representative_count=5,
        query_class=None,
        authorized_document_count=2,
    )
    unknown, unknown_reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class=None,
    )
    assert (large, large_reason) == (HYBRID_DEFAULT_PROFILE_ID, "default_profile_required")
    assert (short, short_reason) == (HYBRID_DEFAULT_PROFILE_ID, "default_profile_required")
    assert (unknown, unknown_reason) == (
        HYBRID_DEFAULT_PROFILE_ID,
        "default_profile_required",
    )


def test_small_corpus_trivial_exact_stays_default() -> None:
    """Trivial exact classes stay on the default profile even when eligible."""

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class="exact_code",
        authorized_document_count=4,
    )
    assert profile_id == HYBRID_DEFAULT_PROFILE_ID
    assert reason == "trivial_exact_default_profile"
```

Import `HYBRID_DEFAULT_PROFILE_ID` from `smart_rag_core.retrieval.profiles`
if the file does not already.

`tests/unit/test_source_scope.py`:

- In `test_ambiguous_and_empty_matches_stay_unscoped` add, before the
  first `resolve_retrieval_scope` call:

```python
    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._count_authorized_corpus",
        lambda connection, caller: (0, 0),
    )
```

  (the test already receives `monkeypatch`; check the signature).

Then add a new test (exact code):

```python
def test_unscoped_small_corpus_selects_long_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A small authorized corpus with one long document routes to v2 unscoped."""

    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._search_authorized_versions",
        lambda *args, **kwargs: (),
    )
    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._count_authorized_corpus",
        lambda connection, caller: (4, 1015),
    )
    scope = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=(),
        whole_document=False,
        connection=SimpleNamespace(),  # type: ignore[arg-type]
        query_text="What does chapter three say about refunds?",
    )
    assert scope.resolution is SourceResolution.UNSCOPED
    assert scope.version_id is None
    assert scope.selector_texts == ()
    assert scope.authorized_document_count == 4
    assert scope.representative_count == 1015
    assert scope.candidate_profile_id == LONG_DOCUMENT_PROFILE_ID
    assert scope.eligibility_reason == "small_corpus_long_document"
```

  Import `LONG_DOCUMENT_PROFILE_ID` from
  `smart_rag_core.retrieval.frozen_profile`.

## Part B - channel-head pins

### B1. `rerank.py`

Add near `RERANK_POOL_SIZE` imports/constants (exact code):

```python
CHANNEL_HEAD_PIN = 5
"""Top-N authorized IDs from dense and from BM25 that always enter the pool."""
```

Add a new function before `rerank_preload_ids` (exact code):

```python
def channel_head_pins(
    *,
    dense_ids: Sequence[UUID],
    bm25_ids: Sequence[UUID],
    fused_ids: Sequence[UUID],
    head: int = CHANNEL_HEAD_PIN,
) -> tuple[UUID, ...]:
    """Return the channel-head IDs that must enter the rerank pool.

    RRF with ``rrf_k=60`` ranks any chunk returned by two channels above a
    chunk returned by one channel at rank 1. Pinning the first ``head``
    authorized IDs of each channel keeps single-channel top hits visible to
    the reranker without changing fusion weights.

    Args:
        dense_ids: Dense IDs in channel-rank order.
        bm25_ids: BM25 IDs in channel-rank order.
        fused_ids: Authorized fused IDs. Pins outside this set are dropped,
            so pins can never add an ID the ACL recheck removed.
        head: Per-channel pin count.

    Returns:
        Distinct pins, dense first then BM25, each within ``fused_ids``.
    """

    authorized = set(fused_ids)
    pins: list[UUID] = []
    for channel in (dense_ids, bm25_ids):
        for chunk_id in tuple(channel)[: max(0, head)]:
            if chunk_id in authorized and chunk_id not in pins:
                pins.append(chunk_id)
    return tuple(pins)
```

Add `from collections.abc import Sequence` if the module does not import
it already (it may import it for `collapse_exact_duplicate_passages`).

Replace `rerank_preload_ids` with (exact code; keep its docstring and add
`pinned_ids: Channel-head IDs that bypass the per-document cap.`):

```python
def rerank_preload_ids(
    fused: tuple[RetrievalCandidate, ...],
    *,
    pool_size: int = RERANK_POOL_SIZE,
    max_per_document: int = RERANK_MAX_PER_DOCUMENT,
    pinned_ids: Sequence[UUID] = (),
) -> tuple[UUID, ...]:
    pinned = set(pinned_ids)
    selected: list[UUID] = []
    for item in fused:
        if item.chunk_id in pinned and item.chunk_id not in selected:
            selected.append(item.chunk_id)
            if len(selected) >= pool_size:
                return tuple(selected)
    seen: set[UUID] = set(selected)
    per_document: dict[UUID, int] = {}
    for item in fused:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        used = per_document.get(item.document_id, 0)
        if used >= max_per_document:
            continue
        per_document[item.document_id] = used + 1
        selected.append(item.chunk_id)
        if len(selected) >= pool_size:
            break
    return tuple(selected)
```

Replace `build_rerank_pool` with (exact code; keep the docstring, add the
`pinned_ids` arg doc and one sentence: "Pins bypass the per-document cap,
count toward ``pool_size``, and keep fused order."):

```python
def build_rerank_pool(
    passages: tuple[RerankPassage, ...],
    *,
    pool_size: int = RERANK_POOL_SIZE,
    max_per_document: int = RERANK_MAX_PER_DOCUMENT,
    excerpt_chars: int = RERANK_EXCERPT_CHARS,
    query: str | None = None,
    excerpt_strategy: str = "prefix",
    pinned_ids: Sequence[UUID] = (),
) -> tuple[RerankPassage, ...]:
    ordered = collapse_exact_duplicate_passages(passages)
    pinned = set(pinned_ids)
    chosen: set[UUID] = set()
    seen_content: set[str] = set()
    for item in ordered:
        chunk_id = item.candidate.chunk_id
        if chunk_id not in pinned or chunk_id in chosen:
            continue
        digest = content_hash(item.raw_text)
        if digest in seen_content:
            continue
        seen_content.add(digest)
        chosen.add(chunk_id)
        if len(chosen) >= pool_size:
            break
    seen: set[UUID] = set(chosen)
    per_document: dict[UUID, int] = {}
    for item in ordered:
        if len(chosen) >= pool_size:
            break
        chunk_id = item.candidate.chunk_id
        if chunk_id in seen:
            continue
        digest = content_hash(item.raw_text)
        if digest in seen_content:
            continue
        seen.add(chunk_id)
        seen_content.add(digest)
        document_id = item.candidate.document_id
        used = per_document.get(document_id, 0)
        if used >= max_per_document:
            continue
        per_document[document_id] = used + 1
        chosen.add(chunk_id)
    emitted: set[UUID] = set()
    selected: list[RerankPassage] = []
    for item in ordered:
        chunk_id = item.candidate.chunk_id
        if chunk_id not in chosen or chunk_id in emitted:
            continue
        emitted.add(chunk_id)
        selected.append(
            _pool_passage(
                item,
                excerpt_chars=excerpt_chars,
                query=query,
                excerpt_strategy=excerpt_strategy,
            )
        )
    return tuple(selected)


def _pool_passage(
    item: RerankPassage,
    *,
    excerpt_chars: int,
    query: str | None,
    excerpt_strategy: str,
) -> RerankPassage:
    """Copy one pool member with its bounded rerank excerpt.

    Args:
        item: Authorized passage in fused order.
        excerpt_chars: Excerpt character budget.
        query: Original query for query-aware excerpts.
        excerpt_strategy: ``prefix`` or ``query_aware``.

    Returns:
        Passage with ``excerpt`` set; citation ``raw_text`` unchanged.
    """

    return RerankPassage(
        candidate=item.candidate,
        raw_text=item.raw_text,
        section_path=item.section_path,
        page_number=item.page_number,
        parent_chunk_id=item.parent_chunk_id,
        chunk_index=item.chunk_index,
        token_count=item.token_count or max(1, len(item.raw_text.split())),
        channels=item.channels,
        excerpt=excerpt_text(
            item.raw_text,
            limit=excerpt_chars,
            query=query,
            strategy=excerpt_strategy,
        ),
    )
```

With `pinned_ids=()` the first loop is a no-op and the second loop is
byte-for-byte today's behavior, so every existing pool test keeps passing.

### B2. `context.py`

Add `pinned_ids: Sequence[UUID] = ()` as the last keyword parameter of
`select_hybrid_context`, document it (`Channel-head IDs that bypass the
per-document pool cap. Must already be authorized fused IDs.`), and pass
`pinned_ids=pinned_ids` into the `build_rerank_pool(...)` call.

### B3. `retriever.py`

- Import: change
  `from smart_rag_core.retrieval.rerank import RerankFallbackReason, rerank_preload_ids`
  to also import `channel_head_pins`.
- Right before `preload_ids = rerank_preload_ids(` add:

```python
        pinned_ids = channel_head_pins(
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            fused_ids=fused_ids,
        )
```

- Pass `pinned_ids=pinned_ids` to both `rerank_preload_ids(...)` and
  `select_hybrid_context(...)`.

### B4. Tests for Part B (`tests/unit/test_hybrid_rerank.py`)

Add (exact code; reuse the file's `_candidate` and `_passage` helpers and
existing imports of `build_rerank_pool`, `rerank_preload_ids`,
`RERANK_POOL_SIZE`, `RERANK_MAX_PER_DOCUMENT`; import
`channel_head_pins`):

```python
def test_channel_head_pins_bypass_document_cap_and_keep_fused_order() -> None:
    """A pinned eighth chunk of a dominant document enters the pool in place."""

    document = uuid4()
    dominant = tuple(_passage(document=document, text=f"same {i}") for i in range(8))
    others = tuple(_passage(text=f"other {i}") for i in range(20))
    fused = dominant + others
    pinned = dominant[7].candidate.chunk_id
    pool = build_rerank_pool(fused, pinned_ids=(pinned,))
    ids = [item.candidate.chunk_id for item in pool]
    assert pinned in ids
    assert len(pool) <= RERANK_POOL_SIZE
    assert (
        sum(1 for item in pool if item.candidate.document_id == document)
        == RERANK_MAX_PER_DOCUMENT + 1
    )
    position = {item.candidate.chunk_id: i for i, item in enumerate(fused)}
    assert ids == sorted(ids, key=position.__getitem__)


def test_pool_without_pins_is_unchanged() -> None:
    """An empty pin set reproduces the legacy pool exactly."""

    document = uuid4()
    fused = tuple(_passage(document=document, text=f"d {i}") for i in range(8)) + tuple(
        _passage(text=f"o {i}") for i in range(20)
    )
    legacy = [item.candidate.chunk_id for item in build_rerank_pool(fused)]
    pinned = [
        item.candidate.chunk_id for item in build_rerank_pool(fused, pinned_ids=())
    ]
    assert legacy == pinned


def test_preload_ids_include_pins_and_stay_bounded() -> None:
    """Preload membership includes pins so their contexts are loaded."""

    document = uuid4()
    overflow = tuple(_candidate(document=document) for _ in range(8))
    others = tuple(_candidate() for _ in range(20))
    pinned = overflow[7].chunk_id
    preloaded = rerank_preload_ids(
        overflow + others,
        pool_size=RERANK_POOL_SIZE,
        max_per_document=RERANK_MAX_PER_DOCUMENT,
        pinned_ids=(pinned,),
    )
    assert pinned in preloaded
    assert len(preloaded) == RERANK_POOL_SIZE
    assert len(preloaded) == len(set(preloaded))


def test_channel_head_pins_only_return_authorized_ids() -> None:
    """Pins are the intersection of channel heads with fused authorized IDs."""

    a, b, c, d, e, f, x = (uuid4() for _ in range(7))
    pins = channel_head_pins(
        dense_ids=(a, b, c, d, e, f),
        bm25_ids=(x, b),
        fused_ids=(b, c, x),
    )
    assert pins == (b, c, x)
    assert channel_head_pins(dense_ids=(a,), bm25_ids=(), fused_ids=()) == ()
```

## Part C - ADR and docs

Create `docs/adr/ADR-small-corpus-long-document-and-channel-pins.md`
with sections: Status (Accepted, date), Context (paste the measured facts
from the index plan: 4 documents, 1015/632/164/3 reps, fused-rank
buckets, dense-rank facts, RRF arithmetic), Decision (Part A rule with
the two constants, Part B rule), Alternatives rejected (retune `rrf_k` or
channel weights - frozen and needs ranked-ID evidence; adaptive
per-document cap - fragile when the fused tail contains other documents;
new frozen default profile - needs a digest freeze), Consequences
(cache keys already include `retrieval_profile_id`; unscoped questions on
small corpora now use `document_quota: 12` and `query_aware` excerpts;
pins may displace up to 10 fused-order IDs from a 20-slot pool), Rollback
(set `SMALL_CORPUS_MAX_DOCUMENTS = 0` and `CHANNEL_HEAD_PIN = 0`; both
revert to today's behavior with no data change), Verification (the tests
above plus the KA50 re-run in P7). Include one `flowchart` Mermaid
diagram of `select_runtime_profile`.

Update:

- `docs/adr/ADR-hybrid-long-document-profile.md`: add a "Superseded in
  part" note linking the new ADR for the eligibility rule.
- `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md`: in the rerank-pool
  section replace "at most 5 per document" wording with the cap rule plus
  pins, and add the profile-selection rule. Keep the frozen profile
  numbers unchanged.
- `docs/README.md`: add the new ADR row with owner/status/last-reviewed.

## Commands

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/retrieval tests/unit
uv run python -m pytest tests/unit/test_long_document_profile.py tests/unit/test_source_scope.py tests/unit/test_hybrid_rerank.py tests/unit/test_hybrid_branch_slice.py tests/unit/test_private_pdf_eval.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier docs
```

Live proof (about 15 minutes including the image build): rebuild the
`api` image first (`00-rules-and-commands.md`, "Docker rebuild before any
live run"; the probe must print `P0 present` and `P1 present`). Then run
the 10-question subset `k01 k02 k04 k05 k08 k11 k14 k28 k32 k37` (all cap
drops or RRF demotions) into `.private-eval/runs/p1/`. Expected in the
stage export:
`retrieval_profile_id == "hybrid_long_document_v2"` and
`source_resolution == "unscoped"` on all 10; `drop=rerank_pool_drop` on
at most 1 of 10 (`k11`/`k28`/`k32` must show `in_pool=yes`).

## Done when

- [ ] `select_runtime_profile(..., authorized_document_count=4, representative_count=1015)`
      returns `("hybrid_long_document_v2", "small_corpus_long_document")`;
      9 documents or `representative_count <= 5` return the default.
- [ ] `resolve_retrieval_scope` with a connection and no title match runs
      `_count_authorized_corpus` once and records
      `authorized_document_count`.
- [ ] `build_rerank_pool` / `rerank_preload_ids` accept `pinned_ids`,
      pins bypass the per-document cap, pool stays <= `pool_size`, fused
      order is preserved, and empty pins reproduce legacy output.
- [ ] `retriever.py` computes pins from `dense_ids`, `bm25_ids`,
      `fused_ids` and passes them to both preload and selection.
- [ ] ADR written and linked; contract doc and README updated.
- [ ] Full unit tier, lint, types, docs pass.
- [ ] Live subset (against the rebuilt image) shows
      `hybrid_long_document_v2` on 10/10 and `in_pool=yes` on `k11`,
      `k28`, `k32`.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
fix(retrieval): route small corpora to hybrid_long_document_v2 and pin channel heads into the rerank pool (P1)
```

## Do not

- Do not edit any JSON under `retrieval/frozen/` or any digest constant.
- Do not change `rrf_k`, channel weights, `RERANK_POOL_SIZE`,
  `RERANK_MAX_PER_DOCUMENT`, or `DOCUMENT_QUOTA` constants.
- Do not apply a `version_id` filter for the small-corpus rule; the
  resolution stays `unscoped`.
- Do not let pins add an ID that is not in `fused_ids`.
