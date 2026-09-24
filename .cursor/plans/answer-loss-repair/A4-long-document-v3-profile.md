# A4: frozen `hybrid_long_document_v3` (dense pin 12, dense-first fallback)

## Goal

Add a new immutable profile `hybrid_long_document_v3`. It is `hybrid_long_document_v2`
plus two fields whose defaults keep the old behavior:

- `dense_head_pin` (default 5, v3 value 12): the first 12 authorized dense IDs are
  pinned into the rerank pool. The BM25 pin stays `CHANNEL_HEAD_PIN` (5). Pins still
  cannot add an ID outside `fused_ids`.
- `fallback_order` (`rrf` or `dense_first`, v3 value `dense_first`): when rerank does
  not complete (reserve gate skipped it, or the call returned a reason other than
  `none`), pool members found by dense search come first in dense-rank order, then
  the rest in fused order. A partial `rerank_v2` ranking counts as completed; only its
  server-appended tail uses the fallback order (ADR Fix 2 step 3 "append ... in
  fallback order"). MMR, quotas, parents, and trim then run unchanged.

Exact-one and small-corpus long-document routes select v3. v2 stays pinned, loadable,
and in `runtime_profile_ids()` as the rollback. `hybrid_default_v1` and v2 bytes and
digests do not change.

Probe symbol: `smart_rag_core.retrieval.frozen_profile.LONG_DOCUMENT_V3_PROFILE_ID`.

## Depends on

A3 committed (and therefore A2). Several edits below target text that A2 or A3 wrote.
Apply each A4 edit to the post-A3 file; the post-A3 target text is quoted. Line
numbers below are pre-A2 numbers; A2/A3 shift some of them, so match by content.

## Read first

**R1** `packages/core/src/smart_rag_core/retrieval/frozen_profile.py` lines 19-32:

```python
LONG_DOCUMENT_PROFILE_ID = "hybrid_long_document_v2"
PRIOR_LONG_DOCUMENT_PROFILE_ID = "hybrid_long_document_v1"
CANDIDATE_PROFILE_PATH = PROFILE_DIR / f"{LONG_DOCUMENT_PROFILE_ID}.json"
PRIOR_LONG_DOCUMENT_PROFILE_PATH = (
    PROFILE_DIR / f"{PRIOR_LONG_DOCUMENT_PROFILE_ID}.json"
)
COVERAGE_SCORE_BASELINE = 0.65
FROZEN_HYBRID_PROFILE_SHA256 = (
    "37343b15449600a4e756e7f72b9282cf709713019e033fe470a9b91fa21f0ec0"
)
FROZEN_LONG_DOCUMENT_PROFILE_SHA256 = (
    "1b356c0de0972ee42758f1ef9f0a7a47b283ec779f97fbe9af8f04e490dffd7a"
)
"""Pinned after P06-62 development ablations. Not the unfrozen v1 digest."""
```

Lines 63-64 (last Attributes entry) and 85-89 (last fields):

```python
        dense_mode_when_version_scoped: ``exact`` for a resolved version on
            the long-document candidate; default profile stays ``ann``.
```

```python
    rerank_max_per_document: int = Field(default=5, ge=1)
    excerpt_chars: int = Field(default=400, ge=1)
    mmr_candidate_depth: int = Field(default=20, ge=1)
    excerpt_strategy: Literal["prefix", "query_aware"] = "prefix"
    dense_mode_when_version_scoped: Literal["ann", "exact"] = "ann"
```

Lines 116-127 (`runtime_profile_ids`) and 160-175 (end of `load_frozen_profile`):

```python
def runtime_profile_ids() -> frozenset[str]:
    """Return profile ids that retrieve may cache and execute.

    Returns:
        Default plus the pinned long-document id when enabled.
    """

    ids = {HYBRID_DEFAULT_PROFILE_ID}
    if long_document_runtime_enabled():
        ids.add(LONG_DOCUMENT_PROFILE_ID)
    return frozenset(ids)
```

```python
    if profile_id == LONG_DOCUMENT_PROFILE_ID:
        pin = FROZEN_LONG_DOCUMENT_PROFILE_SHA256
        if not pin:
            raise UnknownRetrievalProfileError(profile_id)
        raw = json.loads(CANDIDATE_PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise FrozenProfileMutationError("frozen profile is not an object")
        payload = cast(dict[str, Any], raw)
        digest = canonical_profile_digest(payload)
        if digest != pin:
            raise FrozenProfileMutationError("frozen profile hash mismatch")
        profile = FrozenHybridProfile.model_validate(payload)
        if profile.profile_id != LONG_DOCUMENT_PROFILE_ID:
            raise FrozenProfileMutationError("profile_id mismatch")
        return profile
    raise UnknownRetrievalProfileError(profile_id)
```

Lines 132-137 (the `load_frozen_profile` Args entry):

```python
        profile_id: Requested runtime profile. ``hybrid_default_v1`` is
            always allow-listed. ``hybrid_long_document_v2`` is executable
            after P06-62 pins its digest. ``hybrid_long_document_v1``
            stays unfrozen. ``hybrid_packet5_v1`` is documented rollback,
            not a second live default.
```

`load_evaluation_profile` (lines 178-204) accepts only default and v2. Leave it.

**R2** `packages/core/src/smart_rag_core/retrieval/source_scope.py` lines 13-16, 85-87,
102-103, 204-206:

```python
from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_PROFILE_ID,
    long_document_runtime_enabled,
)
```

```python
    if scoped_long:
        return LONG_DOCUMENT_PROFILE_ID, "long_document_eligible"
    return LONG_DOCUMENT_PROFILE_ID, "small_corpus_long_document"
```

```python
        candidate_profile_id: Frozen default, or ``hybrid_long_document_v2``
            when exact-one, representative_count > 5, and the v2 pin exists.
```

```python
    document exceeds the legacy per-document cap uses
    ``hybrid_long_document_v2`` without applying a version filter.
```

**R3** `packages/core/src/smart_rag_core/retrieval/rerank.py` lines 232-263
(`channel_head_pins`; `CHANNEL_HEAD_PIN = 5` is line 31):

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

**R4** `packages/core/src/smart_rag_core/retrieval/context.py`. Signature end (line
180) is `    pinned_ids: Sequence[UUID] = (),` then `) -> ContextSelection:`. Args end
(lines 196-197):

```python
        pinned_ids: Channel-head IDs that bypass the per-document pool cap.
            Must already be authorized fused IDs.
```

Reserve gate (lines 287-307, unchanged by A3):

```python
    if remaining_deadline_seconds < RERANK_RESERVED_SECONDS:
        mmr_selected, dropped = apply_mmr(
            pool,
            query=query,
            lambda_mult=mmr_lambda,
            document_quota=document_quota,
            section_quota=section_quota,
            limit=evidence_max,
            candidate_depth=mmr_depth,
        )
        expanded, parent_ids = expand_parents(mmr_selected, load_context, pool=pool)
        trimmed = trim_token_budget(expanded, budget=token_budget, limit=evidence_max)
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in pool),
            fallback_reason=RerankFallbackReason.TIMEOUT,
            mmr_dropped=dropped,
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=False,
        )
```

Post-A3 rerank block (written by A3 step 10):

```python
    rankings, usage, reason = rerank(query, pool, remaining_deadline_seconds)
    ordered = pool
    fallback = reason
    ranked_count = 0
    appended_count = 0
    if reason is RerankFallbackReason.NONE:
        ordered = apply_rankings(pool, rankings)
        appended_count = sum(1 for item in rankings if item.appended)
        ranked_count = len(rankings) - appended_count
```

`apply_rankings` ends at line 166 (`    return tuple(by_id[item.chunk_id] for item in rankings)`).
A3's validator emits ranked rows first, then appended rows, so appended rows are a suffix.

**R5** `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py` (unchanged by
A2/A3; match by content). The `from smart_rag_core.retrieval.rerank import (` block
(about lines 85-89) contains `RerankFallbackReason,`, `channel_head_pins,`,
`rerank_preload_ids,`. Pool block (pre-A2 lines 390-400):

```python
        if self._retrieval_profile is not None:
            pool_size = self._retrieval_profile.rerank_pool_size
            max_per_document = self._retrieval_profile.rerank_max_per_document
        else:
            pool_size = RERANK_POOL_SIZE
            max_per_document = RERANK_MAX_PER_DOCUMENT
        pinned_ids = channel_head_pins(
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            fused_ids=fused_ids,
        )
```

The `select_hybrid_context(` call ends with:

```python
                retrieval_profile=selection_profile,
                pinned_ids=pinned_ids,
            )
```

**R6** `packages/core/src/smart_rag_core/evaluation/private_pdf/exam_fingerprint.py`
line 10 `from smart_rag_core.retrieval.frozen_profile import FROZEN_HYBRID_PROFILE_SHA256`
and lines 50-51 inside `components`:

```python
        "profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "profile_sha256": FROZEN_HYBRID_PROFILE_SHA256,
```

**R7** Tests that encode "routes to v2":
`tests/unit/test_long_document_profile.py` lines 76-107 (`test_exact_one_long_document_selects_v2`,
`test_small_corpus_long_document_selects_v2`; `LONG_DOCUMENT_PROFILE_ID` at lines 85, 90,
106); `tests/unit/test_source_scope.py` line 9 import and line 253
`    assert scope.candidate_profile_id == LONG_DOCUMENT_PROFILE_ID`;
`tests/unit/test_private_pdf_eval.py` line 672 `    assert profile_id == LONG_DOCUMENT_PROFILE_ID`
(the import at line 37 stays; lines 342-343 still use it for v2).

Known and left alone (report only): `scripts/pdf_eval_runtime.py` lines 138-139, 162,
604 and the other `scripts/eval_pdf_*.py` harnesses still pin v2.

## Steps

### 1. New frozen file

Create `packages/core/src/smart_rag_core/retrieval/frozen/hybrid_long_document_v3.json`
with exactly this content (LF endings, trailing newline):

```json
{
  "profile_id": "hybrid_long_document_v3",
  "rollback_profile_id": "hybrid_long_document_v2",
  "schema_version": "hybrid-frozen-profile-v1",
  "rrf_k": 60,
  "channel_weights": {
    "dense": 1.0,
    "bm25": 1.0,
    "term": 1.0
  },
  "unequal_channel_weights_selected": false,
  "coverage_score_baseline": 0.65,
  "false_supported_loss_weight": 2.0,
  "unnecessary_refusal_loss_weight": 1.0,
  "mmr_lambda": 0.7,
  "document_quota": 12,
  "section_quota": 2,
  "rerank_pool_size": 20,
  "final_evidence_max": 12,
  "final_token_budget": 6000,
  "rerank_max_per_document": 20,
  "excerpt_chars": 800,
  "mmr_candidate_depth": 20,
  "excerpt_strategy": "query_aware",
  "dense_mode_when_version_scoped": "exact",
  "dense_head_pin": 12,
  "fallback_order": "dense_first",
  "coverage_thresholds": {
    "exact_code": 0.65,
    "alias": 0.65,
    "typo": 0.65,
    "semantic_factual": 0.65,
    "arabic_mixed": 0.65,
    "selective_metadata_filter": 0.65,
    "latest_as_of": 0.65,
    "multi_part": 0.65,
    "relationship": 0.65,
    "multi_hop": 0.65,
    "broad_synthesis": 0.65,
    "tabular_aggregation": 0.65,
    "insufficient_refusal": 0.65,
    "graph_mapping": 0.65,
    "acl_negative": 0.65,
    "profile_fidelity": 0.65,
    "negation": 0.65,
    "document_summary": 0.65,
    "mixed_locale_temporal": 0.65,
    "media_limitation": 0.65,
    "prompt_injection": 0.65
  }
}
```

Pin check (must print `9906823616660f79d9a4d40d936f811961e127e095acd7d389b3e0d23f51d6c8`):

```powershell
uv run python -c "import json,pathlib; from smart_rag_core.retrieval.frozen_profile import canonical_profile_digest as d; print(d(json.loads(pathlib.Path('packages/core/src/smart_rag_core/retrieval/frozen/hybrid_long_document_v3.json').read_text(encoding='utf-8'))))"
```

If it prints anything else, fix the JSON to match the block above; never change the pin.

### 2. `frozen_profile.py`

a) After the R1 `PRIOR_LONG_DOCUMENT_PROFILE_PATH = (...)` block insert:

```python
LONG_DOCUMENT_V3_PROFILE_ID = "hybrid_long_document_v3"
LONG_DOCUMENT_V3_PROFILE_PATH = PROFILE_DIR / f"{LONG_DOCUMENT_V3_PROFILE_ID}.json"
```

b) After the line
`"""Pinned after P06-62 development ablations. Not the unfrozen v1 digest."""` insert:

```python
FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256 = (
    "9906823616660f79d9a4d40d936f811961e127e095acd7d389b3e0d23f51d6c8"
)
"""Pinned in answer-loss repair A4. Rollback is ``hybrid_long_document_v2``."""
```

c) After the R1 Attributes entry `dense_mode_when_version_scoped: ...` (two lines) add:

```python
        dense_head_pin: Dense channel-head IDs pinned into the rerank pool.
            Default 5 equals ``CHANNEL_HEAD_PIN``; the BM25 pin stays 5.
        fallback_order: Pool order when rerank does not complete. ``rrf``
            keeps fused order; ``dense_first`` puts dense hits first in
            dense-rank order, then the rest in fused order.
```

d) After `    dense_mode_when_version_scoped: Literal["ann", "exact"] = "ann"` add:

```python
    dense_head_pin: int = Field(default=5, ge=0, le=20)
    fallback_order: Literal["rrf", "dense_first"] = "rrf"
```

e) Replace the whole R1 `runtime_profile_ids` function with:

```python
def runtime_profile_ids() -> frozenset[str]:
    """Return profile ids that retrieve may cache and execute.

    Returns:
        Default, plus the pinned long-document ids when enabled: v2 (the
        rollback) and v3 (the routed profile).
    """

    ids = {HYBRID_DEFAULT_PROFILE_ID}
    if long_document_runtime_enabled():
        ids.add(LONG_DOCUMENT_PROFILE_ID)
    if FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256:
        ids.add(LONG_DOCUMENT_V3_PROFILE_ID)
    return frozenset(ids)
```

f) In the R1 Args entry, replace `            not a second live default.` with:

```python
            not a second live default. ``hybrid_long_document_v3`` is
            executable after answer-loss repair A4 pins its digest.
```

g) Replace the R1 block from `    if profile_id == LONG_DOCUMENT_PROFILE_ID:` through
`    raise UnknownRetrievalProfileError(profile_id)` (end of `load_frozen_profile`) with:

```python
    if profile_id == LONG_DOCUMENT_PROFILE_ID:
        return _load_pinned_profile(
            profile_id, CANDIDATE_PROFILE_PATH, FROZEN_LONG_DOCUMENT_PROFILE_SHA256
        )
    if profile_id == LONG_DOCUMENT_V3_PROFILE_ID:
        return _load_pinned_profile(
            profile_id,
            LONG_DOCUMENT_V3_PROFILE_PATH,
            FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256,
        )
    raise UnknownRetrievalProfileError(profile_id)


def _load_pinned_profile(profile_id: str, path: Path, pin: str) -> FrozenHybridProfile:
    """Load one pinned long-document profile or fail closed.

    Args:
        profile_id: Requested id. Must equal the file's ``profile_id``.
        path: Frozen JSON artifact.
        pin: Expected canonical digest. Empty means not executable.

    Returns:
        Validated frozen profile.

    Raises:
        UnknownRetrievalProfileError: Empty pin.
        FrozenProfileMutationError: Not an object, hash mismatch, or id mismatch.
        FileNotFoundError: Artifact is missing.
    """

    if not pin:
        raise UnknownRetrievalProfileError(profile_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise FrozenProfileMutationError("frozen profile is not an object")
    payload = cast(dict[str, Any], raw)
    if canonical_profile_digest(payload) != pin:
        raise FrozenProfileMutationError("frozen profile hash mismatch")
    profile = FrozenHybridProfile.model_validate(payload)
    if profile.profile_id != profile_id:
        raise FrozenProfileMutationError("profile_id mismatch")
    return profile
```

### 3. `source_scope.py`

a) Replace the R2 import with:

```python
from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_V3_PROFILE_ID,
    long_document_runtime_enabled,
)
```

b) Replace the R2 return lines with:

```python
    if scoped_long:
        return LONG_DOCUMENT_V3_PROFILE_ID, "long_document_eligible"
    return LONG_DOCUMENT_V3_PROFILE_ID, "small_corpus_long_document"
```

c) Replace the R2 `candidate_profile_id` docstring lines with:

```python
        candidate_profile_id: Frozen default, or ``hybrid_long_document_v3``
            when the exact-one or small-corpus long-document rule applies.
```

d) In the R2 `resolve` docstring replace `    ``hybrid_long_document_v2`` without applying a version filter.`
with `    ``hybrid_long_document_v3`` without applying a version filter.`

If `LONG_DOCUMENT_PROFILE_ID` is still used anywhere else in `source_scope.py`, stop (rule 2).

### 4. `rerank.py`: `channel_head_pins`

Replace the whole R3 function with:

```python
def channel_head_pins(
    *,
    dense_ids: Sequence[UUID],
    bm25_ids: Sequence[UUID],
    fused_ids: Sequence[UUID],
    head: int = CHANNEL_HEAD_PIN,
    dense_head: int | None = None,
) -> tuple[UUID, ...]:
    """Return the channel-head IDs that must enter the rerank pool.

    RRF with ``rrf_k=60`` ranks any chunk returned by two channels above a
    chunk returned by one channel at rank 1. Pinning the first authorized
    IDs of each channel keeps single-channel top hits visible to the
    reranker without changing fusion weights.

    Args:
        dense_ids: Dense IDs in channel-rank order.
        bm25_ids: BM25 IDs in channel-rank order.
        fused_ids: Authorized fused IDs. Pins outside this set are dropped,
            so pins can never add an ID the ACL recheck removed.
        head: BM25 pin count, and the dense pin count when ``dense_head``
            is ``None``.
        dense_head: Dense pin count from the frozen profile
            (``dense_head_pin``). ``None`` uses ``head``.

    Returns:
        Distinct pins, dense first then BM25, each within ``fused_ids``.
    """

    authorized = set(fused_ids)
    dense_limit = head if dense_head is None else dense_head
    pins: list[UUID] = []
    for channel, limit in ((dense_ids, dense_limit), (bm25_ids, head)):
        for chunk_id in tuple(channel)[: max(0, limit)]:
            if chunk_id in authorized and chunk_id not in pins:
                pins.append(chunk_id)
    return tuple(pins)
```

### 5. `context.py`: dense-first fallback

a) Insert after `apply_rankings` (after its `return` line and before
`def select_hybrid_context(`), with two blank lines around it:

```python
def fallback_pool_order(
    pool: tuple[RerankPassage, ...],
    *,
    retrieval_profile: FrozenHybridProfile | None,
    dense_ids: Sequence[UUID],
) -> tuple[RerankPassage, ...]:
    """Order the pool used when rerank did not complete.

    ``rrf`` (every profile before ``hybrid_long_document_v3`` and the
    default constants) keeps fused order. ``dense_first`` moves passages
    the dense channel returned to the front in dense-rank order and keeps
    the rest in fused order. MMR, quotas, parent expansion, and token trim
    then run unchanged on the returned order.

    Args:
        pool: Passages in fused order.
        retrieval_profile: Frozen profile, or ``None`` for default constants.
        dense_ids: Dense IDs in channel-rank order. IDs outside ``pool`` are
            ignored, so this never adds a passage.

    Returns:
        The same passages, reordered. Never adds or drops a passage.
    """

    if retrieval_profile is None or retrieval_profile.fallback_order != "dense_first":
        return pool
    dense_rank: dict[UUID, int] = {}
    for index, chunk_id in enumerate(dense_ids):
        dense_rank.setdefault(chunk_id, index)
    dense = sorted(
        (item for item in pool if item.candidate.chunk_id in dense_rank),
        key=lambda item: dense_rank[item.candidate.chunk_id],
    )
    rest = [item for item in pool if item.candidate.chunk_id not in dense_rank]
    return (*dense, *rest)
```

b) In the `select_hybrid_context` signature, after `    pinned_ids: Sequence[UUID] = (),`
add `    dense_ids: Sequence[UUID] = (),`. After the R4 `pinned_ids` Args entry add:

```python
        dense_ids: Dense IDs in channel-rank order. Used only by the
            ``dense_first`` fallback order when rerank did not complete.
```

c) Replace the R4 reserve-gate block with:

```python
    if remaining_deadline_seconds < RERANK_RESERVED_SECONDS:
        fallback_pool = fallback_pool_order(
            pool, retrieval_profile=retrieval_profile, dense_ids=dense_ids
        )
        mmr_selected, dropped = apply_mmr(
            fallback_pool,
            query=query,
            lambda_mult=mmr_lambda,
            document_quota=document_quota,
            section_quota=section_quota,
            limit=evidence_max,
            candidate_depth=mmr_depth,
        )
        expanded, parent_ids = expand_parents(mmr_selected, load_context, pool=pool)
        trimmed = trim_token_budget(expanded, budget=token_budget, limit=evidence_max)
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in fallback_pool),
            fallback_reason=RerankFallbackReason.TIMEOUT,
            mmr_dropped=dropped,
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=False,
        )
```

d) Replace the post-A3 `if reason is RerankFallbackReason.NONE:` block (R4, last four
lines) with:

```python
    if reason is RerankFallbackReason.NONE:
        ordered = apply_rankings(pool, rankings)
        appended_count = sum(1 for item in rankings if item.appended)
        ranked_count = len(rankings) - appended_count
        if appended_count:
            ordered = ordered[:ranked_count] + fallback_pool_order(
                ordered[ranked_count:],
                retrieval_profile=retrieval_profile,
                dense_ids=dense_ids,
            )
    else:
        ordered = fallback_pool_order(
            pool, retrieval_profile=retrieval_profile, dense_ids=dense_ids
        )
```

The insufficient-candidates and skip-trivial paths stay unchanged.

### 6. `retriever.py`: thread the dense pin and dense IDs

a) In the `from smart_rag_core.retrieval.rerank import (` block add `CHANNEL_HEAD_PIN,`
as the first name.

b) Replace the R5 pool block with:

```python
        if self._retrieval_profile is not None:
            pool_size = self._retrieval_profile.rerank_pool_size
            max_per_document = self._retrieval_profile.rerank_max_per_document
            dense_head = self._retrieval_profile.dense_head_pin
        else:
            pool_size = RERANK_POOL_SIZE
            max_per_document = RERANK_MAX_PER_DOCUMENT
            dense_head = CHANNEL_HEAD_PIN
        pinned_ids = channel_head_pins(
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            fused_ids=fused_ids,
            dense_head=dense_head,
        )
```

c) In the `select_hybrid_context(` call, after `                pinned_ids=pinned_ids,`
add `                dense_ids=dense_ids,`.

Then `(Get-Content packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py).Count`
must print a number below 600. If not, stop (architecture cap).

### 7. `exam_fingerprint.py`

a) Replace line 10 with:

```python
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256,
    LONG_DOCUMENT_V3_PROFILE_ID,
)
```

b) After `        "profile_sha256": FROZEN_HYBRID_PROFILE_SHA256,` add:

```python
        "long_document_profile_id": LONG_DOCUMENT_V3_PROFILE_ID,
        "long_document_profile_sha256": FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256,
```

This changes the exam fingerprint digest on purpose (ADR Consequences: the v3 digest
appears in eval fingerprints). No test pins the digest value.

### 8. Existing tests (rule 5: only these assertion changes)

a) `tests/unit/test_long_document_profile.py`: add `LONG_DOCUMENT_V3_PROFILE_ID,` to the
`frozen_profile` import after `LONG_DOCUMENT_PROFILE_ID,`. Rename
`test_exact_one_long_document_selects_v2` to `test_exact_one_long_document_selects_v3`
and `test_small_corpus_long_document_selects_v2` to
`test_small_corpus_long_document_selects_v3`. In their docstrings replace `use v2.` with
`use v3.`. In those two functions only, replace every `LONG_DOCUMENT_PROFILE_ID` with
`LONG_DOCUMENT_V3_PROFILE_ID` (three places: the two `profile_id ==` asserts and
`retrieval_profile_id=`). Leave every other test in the file unchanged.

b) `tests/unit/test_source_scope.py`: line 9 becomes
`from smart_rag_core.retrieval.frozen_profile import LONG_DOCUMENT_V3_PROFILE_ID`, and
line 253 becomes `    assert scope.candidate_profile_id == LONG_DOCUMENT_V3_PROFILE_ID`.

c) `tests/unit/test_private_pdf_eval.py`: add `LONG_DOCUMENT_V3_PROFILE_ID,` to the
`frozen_profile` import after `LONG_DOCUMENT_PROFILE_ID,` (line 37), and line 672 becomes
`    assert profile_id == LONG_DOCUMENT_V3_PROFILE_ID`. Keep lines 342-343.

If any other existing test fails because it expects `hybrid_long_document_v2` from
routing, stop and report it (rule 13). Do not edit it.

## Tests

Create `tests/unit/test_long_document_v3_profile.py`:

```python
"""``hybrid_long_document_v3``: pin, dense head pin, and dense-first fallback."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_core.retrieval.context import fallback_pool_order, select_hybrid_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.frozen_profile import (
    CANDIDATE_PROFILE_PATH,
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256,
    FROZEN_PROFILE_PATH,
    LONG_DOCUMENT_PROFILE_ID,
    LONG_DOCUMENT_V3_PROFILE_ID,
    LONG_DOCUMENT_V3_PROFILE_PATH,
    FrozenHybridProfile,
    canonical_profile_digest,
    load_frozen_profile,
    runtime_profile_ids,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.rerank import (
    CHANNEL_HEAD_PIN,
    ContextSelection,
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    channel_head_pins,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

_V2_DIGEST = "1b356c0de0972ee42758f1ef9f0a7a47b283ec779f97fbe9af8f04e490dffd7a"
_V3_DIGEST = "9906823616660f79d9a4d40d936f811961e127e095acd7d389b3e0d23f51d6c8"
_Triple = tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]
_RerankFn = Callable[[str, tuple[RerankPassage, ...], float], _Triple]


def _digest(path: Path) -> str:
    """Return the canonical digest of one frozen JSON file.

    Args:
        path: Frozen profile path.

    Returns:
        SHA-256 hex of canonical JSON.
    """

    return canonical_profile_digest(json.loads(path.read_text(encoding="utf-8")))


def _candidate(rank: int) -> RetrievalCandidate:
    """Build one authorized candidate in its own document and version.

    Args:
        rank: Fused rank.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0,
    )


def _context(candidate: RetrievalCandidate, text: str) -> ChunkContext:
    """Build the authorized context row for one candidate.

    Args:
        candidate: Candidate identity.
        text: Canonical text.

    Returns:
        Frozen context row.
    """

    return ChunkContext(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=1,
        section_path=(),
        token_count=max(1, len(text.split())),
        raw_text=text,
        is_search_representative=True,
    )


def _fused(
    count: int,
) -> tuple[tuple[RetrievalCandidate, ...], tuple[ChunkContext, ...]]:
    """Build fused candidates with distinct texts.

    Args:
        count: Number of candidates.

    Returns:
        Fused candidates and their context rows.
    """

    fused = tuple(_candidate(rank) for rank in range(1, count + 1))
    rows = tuple(
        _context(item, f"passage {index} topic{index}") for index, item in enumerate(fused)
    )
    return fused, rows


def _no_parents(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
    """Return no parent rows.

    Args:
        ids: Requested parent IDs.

    Returns:
        Empty tuple.
    """

    del ids
    return ()


def _must_not_run(query: str, pool: tuple[RerankPassage, ...], remaining: float) -> _Triple:
    """Fail when the reserve gate should have skipped rerank.

    Args:
        query: Unused.
        pool: Unused.
        remaining: Unused.

    Raises:
        AssertionError: Always.
    """

    del query, pool, remaining
    raise AssertionError("rerank must not run")


def _failed(query: str, pool: tuple[RerankPassage, ...], remaining: float) -> _Triple:
    """Return a provider failure.

    Args:
        query: Unused.
        pool: Unused.
        remaining: Unused.

    Returns:
        Empty rankings with ``rerank_provider_error``.
    """

    del query, pool, remaining
    return (), None, RerankFallbackReason.PROVIDER_ERROR


def _select(
    fused: tuple[RetrievalCandidate, ...],
    rows: tuple[ChunkContext, ...],
    *,
    retrieval_profile: FrozenHybridProfile | None,
    rerank: _RerankFn,
    remaining: float,
    dense_ids: tuple[UUID, ...],
) -> ContextSelection:
    """Run context selection without a database.

    Args:
        fused: Fused candidates.
        rows: Context rows.
        retrieval_profile: Frozen profile or ``None``.
        rerank: Rerank closure.
        remaining: Remaining slice seconds.
        dense_ids: Dense IDs in rank order.

    Returns:
        The context selection.
    """

    return select_hybrid_context(
        query="policy question",
        profile=None,
        fused=fused,
        contexts=rows,
        channel_hits={},
        rerank=rerank,
        load_context=_no_parents,
        remaining_deadline_seconds=remaining,
        retrieval_profile=retrieval_profile,
        dense_ids=dense_ids,
    )


def test_v3_pin_matches_file_and_new_fields() -> None:
    """The v3 file matches its pin and carries dense pin 12 and dense-first."""

    assert FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256 == _V3_DIGEST
    assert _digest(LONG_DOCUMENT_V3_PROFILE_PATH) == _V3_DIGEST
    profile = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    assert profile.profile_id == LONG_DOCUMENT_V3_PROFILE_ID
    assert profile.rollback_profile_id == LONG_DOCUMENT_PROFILE_ID
    assert profile.dense_head_pin == 12
    assert profile.fallback_order == "dense_first"
    assert profile.rerank_max_per_document == 20
    assert profile.document_quota == 12
    assert profile.final_token_budget == 6000
    assert {LONG_DOCUMENT_V3_PROFILE_ID, LONG_DOCUMENT_PROFILE_ID} <= runtime_profile_ids()


def test_default_and_v2_bytes_and_behavior_are_unchanged() -> None:
    """Old digests hold and the new fields default to the old behavior."""

    assert _digest(FROZEN_PROFILE_PATH) == FROZEN_HYBRID_PROFILE_SHA256
    assert _digest(CANDIDATE_PROFILE_PATH) == FROZEN_LONG_DOCUMENT_PROFILE_SHA256
    assert FROZEN_LONG_DOCUMENT_PROFILE_SHA256 == _V2_DIGEST
    for profile_id in (HYBRID_DEFAULT_PROFILE_ID, LONG_DOCUMENT_PROFILE_ID):
        profile = load_frozen_profile(profile_id)
        assert profile.dense_head_pin == CHANNEL_HEAD_PIN
        assert profile.fallback_order == "rrf"


def test_dense_head_pin_twelve_keeps_bm25_at_five() -> None:
    """The dense pin follows the profile; BM25 stays five; ACL bound holds."""

    dense = tuple(uuid4() for _ in range(15))
    bm25 = tuple(uuid4() for _ in range(8))
    fused = dense + bm25
    pins = channel_head_pins(dense_ids=dense, bm25_ids=bm25, fused_ids=fused, dense_head=12)
    assert pins == dense[:12] + bm25[:CHANNEL_HEAD_PIN]
    default = channel_head_pins(dense_ids=dense, bm25_ids=bm25, fused_ids=fused)
    assert default == dense[:CHANNEL_HEAD_PIN] + bm25[:CHANNEL_HEAD_PIN]
    bounded = channel_head_pins(
        dense_ids=dense, bm25_ids=(), fused_ids=dense[:3], dense_head=12
    )
    assert bounded == dense[:3]


def test_dense_first_moves_dense_rank_one_from_fused_rank_eleven() -> None:
    """Gate skip and failed rerank both put dense rank 1 (fused 11) first."""

    fused, rows = _fused(12)
    dense_ids = (fused[10].chunk_id, fused[2].chunk_id)
    expected = dense_ids + tuple(
        item.chunk_id for index, item in enumerate(fused) if index not in {2, 10}
    )
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    gated = _select(
        fused, rows, retrieval_profile=v3, rerank=_must_not_run, remaining=1.0,
        dense_ids=dense_ids,
    )
    assert gated.fallback_reason is RerankFallbackReason.TIMEOUT
    assert gated.rerank_order == expected
    assert gated.passages[0].candidate.chunk_id == fused[10].chunk_id
    failed = _select(
        fused, rows, retrieval_profile=v3, rerank=_failed, remaining=9.0,
        dense_ids=dense_ids,
    )
    assert failed.fallback_reason is RerankFallbackReason.PROVIDER_ERROR
    assert failed.rerank_order == expected


def test_rrf_fallback_order_is_unchanged_for_v2_and_default() -> None:
    """Profiles without ``dense_first`` keep fused order on fallback."""

    fused, rows = _fused(12)
    fused_order = tuple(item.chunk_id for item in fused)
    v2 = load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    for profile in (v2, None):
        selection = _select(
            fused, rows, retrieval_profile=profile, rerank=_must_not_run,
            remaining=1.0, dense_ids=(fused[10].chunk_id,),
        )
        assert selection.rerank_order == fused_order


def test_fallback_pool_order_never_adds_or_drops() -> None:
    """Unknown and repeated dense IDs are ignored; membership is unchanged."""

    pool = tuple(
        RerankPassage(
            candidate=_candidate(rank),
            raw_text=f"p{rank}",
            section_path=(),
            parent_chunk_id=None,
            token_count=1,
            channels=frozenset({"dense"}),
            excerpt=f"p{rank}",
        )
        for rank in range(1, 5)
    )
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    last = pool[3].candidate.chunk_id
    ordered = fallback_pool_order(
        pool, retrieval_profile=v3, dense_ids=(uuid4(), last, last)
    )
    assert ordered == (pool[3], pool[0], pool[1], pool[2])
    assert fallback_pool_order(pool, retrieval_profile=v3, dense_ids=()) == pool


def test_partial_ranking_keeps_head_and_orders_tail_by_fallback() -> None:
    """A partial rerank is completed; only its appended tail is reordered."""

    fused, rows = _fused(6)
    dense_ids = (fused[4].chunk_id,)

    def partial(query: str, pool: tuple[RerankPassage, ...], remaining: float) -> _Triple:
        """Rank one candidate and append the rest in pool order.

        Args:
            query: Unused.
            pool: Authorized pool.
            remaining: Unused.

        Returns:
            Partial rankings with ``none``.
        """

        del query, remaining
        head = pool[1]
        rest = [item for item in pool if item is not head]
        rankings = [RerankRanking(chunk_id=head.candidate.chunk_id, rank=1, support=0.9)]
        rankings.extend(
            RerankRanking(
                chunk_id=item.candidate.chunk_id, rank=index, support=0.0, appended=True
            )
            for index, item in enumerate(rest, start=2)
        )
        usage = RerankUsage(
            request_id="t",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return tuple(rankings), usage, RerankFallbackReason.NONE

    ids = [item.chunk_id for item in fused]
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    dense_tail = _select(
        fused, rows, retrieval_profile=v3, rerank=partial, remaining=9.0,
        dense_ids=dense_ids,
    )
    assert dense_tail.fallback_reason is RerankFallbackReason.NONE
    assert dense_tail.rerank_order == (ids[1], ids[4], ids[0], ids[2], ids[3], ids[5])
    assert dense_tail.rerank_ranked_count == 1
    assert dense_tail.rerank_appended_count == 5
    v2 = load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    fused_tail = _select(
        fused, rows, retrieval_profile=v2, rerank=partial, remaining=9.0,
        dense_ids=dense_ids,
    )
    assert fused_tail.rerank_order == (ids[1], ids[0], ids[2], ids[3], ids[4], ids[5])
```

Routing is covered by the two renamed tests in step 8a plus `test_source_scope.py`.

## Commands (run in this order; all must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/retrieval/frozen_profile.py packages/core/src/smart_rag_core/retrieval/source_scope.py packages/core/src/smart_rag_core/retrieval/rerank.py packages/core/src/smart_rag_core/retrieval/context.py packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py packages/core/src/smart_rag_core/evaluation/private_pdf/exam_fingerprint.py tests/unit/test_long_document_v3_profile.py tests/unit/test_long_document_profile.py tests/unit/test_source_scope.py tests/unit/test_private_pdf_eval.py
uv run python -m ruff check --select I --fix packages/core/src/smart_rag_core/retrieval packages/core/src/smart_rag_core/evaluation/private_pdf/exam_fingerprint.py tests/unit/test_long_document_v3_profile.py tests/unit/test_long_document_profile.py tests/unit/test_source_scope.py tests/unit/test_private_pdf_eval.py
uv run python -m pytest tests/unit/test_long_document_v3_profile.py tests/unit/test_long_document_profile.py tests/unit/test_source_scope.py tests/unit/test_private_pdf_eval.py tests/unit/test_hybrid_rerank.py tests/unit/test_pdf_hybrid_overlay.py tests/unit/test_eval_exam_runner.py tests/unit/test_phase4_freeze.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier contract
uv run python scripts/check.py --tier docs
```

`--tier contract` runs the 600-line architecture cap. If `test_phase4_freeze` fails,
stop and report; do not regenerate `PHASE4_FREEZE.md` in this packet.

## Docs

1. `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` (front matter `last-reviewed`: today):
   - In "## Long-document runtime profile (P06-62)", replace the two lines
     `` `hybrid_long_document_v2` is the measured immutable long-document `` and
     `profile. Runtime retrieve loads it after an exact-one authorized` with
     `` `hybrid_long_document_v3` is the runtime long-document profile (answer-loss `` and
     `repair A4). Runtime retrieve loads it after an exact-one authorized`.
   - After that section's last line `` (`deadline_budget`). `` insert a blank line and:

     ```markdown
     `hybrid_long_document_v3` copies `hybrid_long_document_v2` and adds two
     fields. `dense_head_pin` 12 pins the first 12 authorized dense IDs into
     the rerank pool; the BM25 pin stays `CHANNEL_HEAD_PIN` (5), and pins still
     cannot add an ID outside the fused list. `fallback_order` `dense_first`
     applies only when rerank does not complete (the reserve gate skipped it,
     or the call returned a fallback reason other than `none`): pool members
     found by dense search come first in dense-rank order, then the rest in
     fused order. A partial `rerank_v2` ranking counts as completed; only its
     appended tail uses that order. MMR, quotas, parent expansion, the 12-unit
     cap, and the 6000-token budget are unchanged. Both fields default to the
     old behavior (`5`, `rrf`), so `hybrid_default_v1` and
     `hybrid_long_document_v2` bytes and digests are unchanged. Canonical
     SHA-256 `9906823616660f79d9a4d40d936f811961e127e095acd7d389b3e0d23f51d6c8`
     (`FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256`). Rollback: route to
     `hybrid_long_document_v2`, which stays pinned and loadable. For v3 this
     replaces the rule "falls back to deterministic RRF", approved in
     [ADR-retrieved-answer-loss-repair.md](../adr/ADR-retrieved-answer-loss-repair.md).
     ```

   - In the Packet 5 flowchart replace
     `  valid -->|no| rrf["Keep fused RRF order. Typed fallback"]` with
     `  valid -->|no| rrf["Fused RRF order, or dense-first on v3. Typed fallback"]`.
   - In the paragraph A3 added after the `Counterfactuals:` line, replace
     `appends unranked candidates in fused order with` with
     `` appends unranked candidates in fallback order (fused, or dense-first under `hybrid_long_document_v3`) with ``.
   - In the pins paragraph, replace
     `` corpus selects `hybrid_long_document_v2` instead, whose own frozen cap is `` with
     `` corpus selects `hybrid_long_document_v3` instead, whose own frozen cap is ``, and
     `20 and whose document quota is 12. See` with
     `20, whose document quota is 12, and whose dense pin is 12. See`.
2. `docs/adr/ADR-small-corpus-long-document-and-channel-pins.md` (front matter
   `last-reviewed`: today). After the Status line
   `pool. It does not change any frozen JSON or digest.` insert a blank line and:

   ```markdown
   **Superseded in part (answer-loss repair A4).** Decisions 1 and 2 now
   select `hybrid_long_document_v3` instead of `hybrid_long_document_v2`, and
   v3 pins 12 dense heads instead of 5 (decision 3; the BM25 pin stays 5).
   The eligibility rules and the 8-document limit are unchanged. v2 stays
   pinned as the rollback. See
   [ADR-retrieved-answer-loss-repair.md](./ADR-retrieved-answer-loss-repair.md)
   Fix 2 step 5.
   ```

3. `docs/README.md`: front matter `last-reviewed` today; fourth column today in the rows
   for `retrieval/HYBRID_RETRIEVAL_CONTRACT.md` and
   `adr/ADR-small-corpus-long-document-and-channel-pins.md`. No new doc, no new row.

No freeze doc needs a digest row: `PHASE4_FREEZE.md` and `HYBRID_TUNING.md` list only the
`hybrid_default_v1` digest, and the digest lists in `ADR-ask-evidence-budget-repair.md`
and `PDF_HYBRID_EVALUATION.md` are historical. Do not edit them.

## Live proof (about 25 minutes including the image build)

1. Rebuild and probe exactly as 00-rules says (Docker command, `health/ready` shows
   `query_ready`, probe entry `'A4'` prints `present`). Rule 12: no earlier run counts.
2. Edit the private, untracked `.private-eval/answer50_stage_trace.py` (never `git add`
   it). Read the whole file first, then: add `import sys`; change `main()` to
   `main(argv: list[str]) -> int` and use `Path(argv[0])`, `Path(argv[1])`,
   `Path(argv[2])` for the gold, answers, and summary paths when given, else the
   existing defaults; in the two loops that assume all 50 IDs exist (around lines 79-89
   and 118-127) skip IDs absent from the answers or summary instead of failing; the
   entry point becomes `raise SystemExit(main(sys.argv[1:]))`. If the file does not
   have that shape, stop and report.
3. Build the subset gold with the 00-rules PowerShell `$ids` filter for
   `a03 a11 a12 a24 a25 a32 a40 a48 a22 a26`, then run the 00-rules live-run template
   with output directory `.private-eval/runs/a4-profile/`.
4. Run `.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py <subset gold> <answers-out file> <summary file>`
   with `$env:PYTHONIOENCODING="utf-8"`.
5. Report per ID: `retrieval_profile_id` from the stage export, `rerank_fallback`, and
   whether the fact chunk is in `selected_ids`. Print IDs and booleans only; no question,
   gold, or answer text (00-rules).

Stop rule: any of the 10 records without `retrieval_profile_id` `hybrid_long_document_v3`
means stop and report. Do not commit.

## Done when

- [ ] `hybrid_long_document_v3.json` exists and the pin command prints the v3 digest.
- [ ] `hybrid_default_v1.json`, `hybrid_long_document_v1.json`, `hybrid_long_document_v2.json`
      and every existing `*_SHA256` value are byte-identical to before
      (`git diff --stat -- packages/core/src/smart_rag_core/retrieval/frozen` shows only the new file).
- [ ] Exact-one and small-corpus routes return `hybrid_long_document_v3`; v2 still loads.
- [ ] v3 pins 12 dense heads and 5 BM25 heads; default and v2 pin 5 and 5.
- [ ] Dense-first applies on gate skip, on a failed rerank, and to a partial tail only;
      `rrf` profiles keep fused order.
- [ ] `retriever.py` is below 600 lines.
- [ ] All commands exit 0; docs updated; live proof shows v3 on 10/10.

## Commit

Follow 00-rules "At the end of every code packet (A1 to A9)". Message:

```text
feat(retrieval): hybrid_long_document_v3 with dense pin 12 and dense-first fallback (A4)

New frozen profile hybrid_long_document_v3 (canonical SHA-256 9906823616660f79...).
dense_head_pin 12 threads through channel_head_pins; BM25 stays 5.
fallback_order dense_first orders the pool by dense rank when rerank does not
complete, and orders the appended tail of a partial rerank_v2 ranking.
Exact-one and small-corpus routes select v3; v2 stays pinned as rollback.
Exam fingerprint includes the v3 id and digest.
```

Files to `git add`, one by one (14 paths):

```text
packages/core/src/smart_rag_core/retrieval/frozen/hybrid_long_document_v3.json
packages/core/src/smart_rag_core/retrieval/frozen_profile.py
packages/core/src/smart_rag_core/retrieval/source_scope.py
packages/core/src/smart_rag_core/retrieval/rerank.py
packages/core/src/smart_rag_core/retrieval/context.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py
packages/core/src/smart_rag_core/evaluation/private_pdf/exam_fingerprint.py
tests/unit/test_long_document_v3_profile.py
tests/unit/test_long_document_profile.py
tests/unit/test_source_scope.py
tests/unit/test_private_pdf_eval.py
docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md
docs/adr/ADR-small-corpus-long-document-and-channel-pins.md
docs/README.md
```

If `git status --short` shows any other changed file, stop and explain it before committing.

## Do not

- Do not edit `hybrid_default_v1.json`, `hybrid_long_document_v1.json`,
  `hybrid_long_document_v2.json`, or any existing `*_SHA256` value.
- Do not change `CHANNEL_HEAD_PIN`, `SMALL_CORPUS_MAX_DOCUMENTS`, `rrf_k`, weights,
  quotas, the pool size, or `load_evaluation_profile`.
- Do not apply dense-first on the insufficient-candidates or skip-trivial paths, or to
  the ranked head of a partial ranking.
- Do not edit `scripts/pdf_eval_runtime.py` or the `scripts/eval_pdf_*.py` harnesses.
- Do not put private questions, gold phrases, answer text, or raw PDF text in a tracked
  file; never print `OPERATOR_SUPABASE_DB_URL`.
- No SQL migrations. Never `git add -A`, `git add .`, `--no-verify`, `--force`, `--admin`.
