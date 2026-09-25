# A2 - Hybrid stage timings and rerank validation sub-codes (Fix 2, step 1)

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.
This packet is one commit on `fix/answer-loss-repair`.

**Depends on:** A1 committed (ordering only; A2 uses no A1 code).
**Probe symbol:** `smart_rag_core.retrieval.rerank.RerankPayloadError`.

## Goal

Measure where the 10 s retrieve slice goes, and say why a rerank payload
was rejected. No ranking, prompt, profile, or deadline changes here.

After this packet:

1. Every Hybrid retrieve records integer wall-clock milliseconds per stage
   in `HybridRunResult.stage_timings_ms`. It is copied into
   `HybridBranchDiagnostics.stage_timings_ms: dict[str, int]` (default
   empty). The keys are `HYBRID_STAGE_TIMING_KEYS`.
2. `validate_rerank_payload` raises `RerankPayloadError(ValueError)`.
   Its `subcode` is one of `json`, `hash`, `length`, `duplicate`, or
   `unknown_id`. `reranker.py` still returns `rerank_schema_invalid` and
   puts the sub-code on `RerankUsage.invalid_subcode`. From there it
   reaches `HybridBranchDiagnostics.rerank_invalid_subcode: str = ""`.
3. `scripts/eval_ask_stage_export.py` exports both fields. Its per-run
   `bm25_degraded_explicit` becomes `False` for `fallback_reason` `none`
   or empty (today it is `True` for `none`).
4. Diagnostics stay ID-only: the keys are allow-listed names, the values
   are integers, and the sub-code is allow-listed.

Facts to keep in mind while editing (verified in the code):

- `remaining` (the value the rerank gate compares with 3.0 s) is computed
  **before** pool preload (`retriever.py` lines 386-389, then preload at
  401-407). `rerank_gate_remaining_ms` records exactly that value.
- Scope resolution runs in `adapters_hybrid.py` line 192, outside the
  retriever, so `scope_ms` is added there.
- Invalid JSON text from OpenAI fails inside the gateway before any
  payload exists (`openai_rerank.py`, `OpenAIRerankError("rerank_schema_invalid")`),
  and that path has no usage. Its sub-code stays empty. Do not change
  that path; accounting tests depend on it.

## Read first (confirm each quote; line numbers may drift a few lines)

**R1** `packages/core/src/smart_rag_core/retrieval/profiles.py` lines 52-57:

```python
EXACT_START_MIN_SLICE_SECONDS = HYBRID_DEADLINE_SECONDS
"""Exact dense starts only when the retrieve slice is at least the Hybrid
envelope. Production Ask remaining is below this after profile/embed, so
ANN starts first. P06-70 named ``deadline_budget`` after exact-from-start
exhausted the 25s Ask envelope. The ceiling is not raised."""
CHANNEL_WEIGHT_DENSE = 1.0
```

**R2** `packages/core/src/smart_rag_core/retrieval/hybrid.py`: imports at
lines 5-10 (there is no `import time`). `run_channels_parallel` at lines
254-288 is the last function in the file:

```python
def run_channels_parallel(
    jobs: dict[str, Callable[[], object]],
    *,
    deadline_seconds: float = HYBRID_DEADLINE_SECONDS,
) -> tuple[dict[str, object], tuple[str, ...], bool]:
    """Run channel callables in parallel and record timeouts separately.

    Args:
        jobs: Mapping of channel name to zero-argument callables.
        deadline_seconds: Remaining Hybrid deadline share.

    Returns:
        Completed results, timed-out names, and whether the deadline exhausted.

    Side Effects:
        Executes the callables in worker threads. Does not start answer
        generation.
    """

    if deadline_seconds <= 0:
        return {}, tuple(jobs), True
    executor = ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    try:
        futures = {executor.submit(job): name for name, job in jobs.items()}
        done, pending = wait(futures, timeout=deadline_seconds)
        timed_out = tuple(futures[item] for item in pending)
        for item in pending:
            item.cancel()
        completed: dict[str, object] = {}
        for item in done:
            completed[futures[item]] = item.result()
        return completed, timed_out, bool(timed_out)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
```

**R3** `packages/core/src/smart_rag_core/retrieval/hybrid_run/types.py`:
line 6 `from dataclasses import dataclass`. `HybridRunResult` ends at lines
170-172 (docstring) and line 192 (last field):

```python
        source_resolution: Server-derived scope token. Empty when the
            retrieve path did not attach one.
    """
```

```python
    term_ids: tuple[UUID, ...] = ()
    source_resolution: str = ""
```

**R4** `packages/core/src/smart_rag_core/retrieval/hybrid_run/budget.py`:
lines 3-5 are `from __future__ import annotations`, a blank line, and
`from collections.abc import Callable`. The file ends at line 235 with
`counted_rerank`'s `return _wrapped`.

**R5** `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py`
(527 lines). The blocks that change:

- Lines 29-41: the `assemble` import list (`compute_principal_scope_hash,`
  then `fail_closed_query,`) and `from ...hybrid_run.budget import (`
  `counted_rerank,` `)`.
- Lines 211-216, end of the `retrieve` docstring:
  `read ParadeDB and Supabase. No holdout access. No answer tokens.`
- Lines 248-249: `texts = query_texts(query, profile)` then
  `embed_response, embed_error = embed_query_texts(`.
- Line 258: `vectors = embed_response.vectors`.
- Lines 271-275: `channel_started = time.perf_counter()` then
  `run_channels_parallel(jobs, deadline_seconds=slice_seconds,)`.
- Lines 346-348: `temporal_records = self._load_temporal_records(...)`.
- Lines 382-389: `fused_ids`, `fused_at`, `context_cache`, `loader`,
  `remaining = remaining_slice_seconds(...)`.
- Lines 407-418: `contexts = loader(preload_ids) ...`, `rerank_fn: RerankFn = counted_rerank(...)`,
  and `rerank_fallback = ""`, then `rerank_top_support: float | None = None`.
- Lines 421-439: `if assembled.fused:`, `selection = select_hybrid_context(`,
  the `if selection.usage is not None:` block, and
  `locator_rows = loader(selected_ids) if selected_ids else ()`.
- Lines 524-527, end of the return:
  `dense_ids=dense_ids,` `bm25_ids=bm25_ids,` `term_ids=term_ids,` `)`.

**R6** `packages/core/src/smart_rag_core/retrieval/rerank.py`: the profiles
import at lines 17-27 (`RERANK_EXCERPT_CHARS,` then `RERANK_MAX_PER_DOCUMENT,`).
`RerankFallbackReason` ends at line 49 with `PROVIDER_ERROR = "rerank_provider_error"`.
`RerankUsage` at lines 96-112 ends:

```python
        model_calls: ``0`` or ``1``. Hidden retries are forbidden.
    """

    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    model_calls: int
```

`validate_rerank_payload` lines 651-697: the `Raises:` block says
`ValueError: If status, IDs, ranks, or support violate the contract.`.
There are nine `raise ValueError(...)` lines (660-683 and 696-697), with
these messages: `rerank_support_out_of_bounds`, `rerank_support_invalid`,
`rerank_rank_invalid`, `rerank_incomplete`, `rerank_schema_invalid`,
`rerank_input_hash_mismatch`, `rerank_ranking_length`,
`rerank_unknown_or_missing_id`, `rerank_duplicate_id`, the combined
`if row.rank > len(candidate_ids) or row.rank in seen_ranks:` check
(`rerank_rank_invalid`), and `rerank_id_set_mismatch`.

**R7** `packages/core/src/smart_rag_core/retrieval/reranker.py`: the
imports at lines 10-17, and `except ValueError:` at line 90, which
returns `RerankUsage(... model_calls=response.model_calls,)` with
`RerankFallbackReason.SCHEMA_INVALID`.

**R8** `packages/core/src/smart_rag_core/query_routing/models/results.py`:
- Line 16: `from smart_rag_core.query_routing.models.plan import BranchKind, CorrectionKind`.
- Line 72: `effective_route: Executed branch family, never ``runs.route_family``.`
- Line 95: `effective_route: str = Field(min_length=1, max_length=64)`.
- Lines 119-124: the end of `ids_are_uuid_strings`
  (`UUID(item)`, `return value`), then `class BranchResult(BaseModel):`.

**R9** `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py`:
- Line 30: `from smart_rag_core.retrieval.profiles import RETRIEVAL_SLICE_SECONDS`.
- Lines 234-236, end of `hybrid_diagnostics_from_outcome`:
  `support_confidence=getattr(coverage, "support_confidence", None),`
  `effective_route=effective_route,` `)`.
- Lines 263-267: the end of `_uuid_ids`, then `def chunk_loader(`.
  `cast` is already imported (line 5).

**R10** `apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py`:
- Lines 3-6: `from __future__ import annotations`, a blank line,
  `from collections.abc import Callable`, and
  `from dataclasses import dataclass, replace`.
- Lines 184-188, the `retrieve` docstring `Side Effects:` block ending
  `preload, parent expansion, and locator reload.`
- Line 192: `scope = self._resolve_scope(caller, typed_profile, query=query)`.
- Lines 207-208: `retrieval_profile = load_frozen_profile(profile_id)`
  then `gateway = self._model_gateway`.
- Line 268: `return replace(result, source_resolution=resolution)`.

**R11** `scripts/eval_ask_stage_export.py`:
- Line 18: `from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer`.
- Lines 122-123: `if record["bm25_degraded_explicit"] is not True:` and
  `bm25_explicit = False`.
- Line 232: `fallback = str(diagnostics.get("fallback_reason") or "").strip() or "unknown"`.
- Lines 243-252: from `bm25_named = fallback.casefold().startswith("bm25")`
  to the final `bm25_explicit = "unknown"`. The last `else` cannot run,
  because an empty fallback is already `"unknown"` at line 232.
- Lines 281-283: `"bm25_degraded_explicit": bm25_explicit,`,
  `"retrieval_empty": retrieval_empty,`, and `}`.
- Line 286: `def _int_or_unknown(value: object) -> int | str:`.

**R12** `tests/unit/test_hybrid_branch_diagnostics.py` line 225
`assert ok["bm25_degraded_explicit"] is True`, in
`test_stage_record_measures_accounting_and_bm25_explicit`. Its
diagnostics have `"fallback_reason": "none"`. That assertion encodes the
bug; step 11 is the only existing assertion this packet changes.

## Steps (exact code)

### 1. `profiles.py`: allow-lists

Insert between the R1 docstring and `CHANNEL_WEIGHT_DENSE = 1.0`:

```python
RERANK_INVALID_SUBCODES = frozenset(
    {"json", "hash", "length", "duplicate", "unknown_id"}
)
"""ID-free ``RerankPayloadError.subcode`` values persisted in diagnostics."""
HYBRID_STAGE_TIMING_KEYS = frozenset(
    {
        "scope_ms",
        "embed_ms",
        "channels_ms",
        "channel_dense_ms",
        "channel_bm25_ms",
        "channel_term_ms",
        "assemble_ms",
        "temporal_load_ms",
        "pool_preload_ms",
        "rerank_gate_remaining_ms",
        "rerank_call_ms",
        "selection_ms",
        "locator_reload_ms",
        "retrieve_total_ms",
    }
)
"""Allowed ``stage_timings_ms`` keys on Hybrid diagnostics (integer ms)."""
```

### 2. `rerank.py`: `RerankPayloadError`, usage sub-code, raises

a) In the R6 profiles import, add `RERANK_INVALID_SUBCODES,` directly
after `RERANK_EXCERPT_CHARS,`.

b) Insert after `PROVIDER_ERROR = "rerank_provider_error"` (the end of
`RerankFallbackReason`), keeping two blank lines before the next class:

```python
class RerankPayloadError(ValueError):
    """Rerank payload failed application validation.

    ``str(error)`` stays the specific message (for example
    ``rerank_input_hash_mismatch``), so existing ``ValueError`` handlers
    and ``match=`` tests keep working. ``subcode`` is the coarse, ID-free
    class that diagnostics persist.

    Attributes:
        subcode: One of ``RERANK_INVALID_SUBCODES``: ``json`` (shape, type,
            or bounds), ``hash`` (echoed digest differs), ``length`` (row
            count differs), ``duplicate`` (repeated ID or rank), or
            ``unknown_id`` (ID not supplied, or supplied set not covered).
    """

    def __init__(self, message: str, *, subcode: str) -> None:
        """Build the error.

        Args:
            message: Specific validation message; becomes ``str(error)``.
            subcode: Coarse sub-code from ``RERANK_INVALID_SUBCODES``.

        Raises:
            ValueError: ``rerank_subcode_invalid`` when ``subcode`` is not
                allow-listed.
        """

        if subcode not in RERANK_INVALID_SUBCODES:
            raise ValueError("rerank_subcode_invalid")
        super().__init__(message)
        self.subcode = subcode
```

c) Replace the R6 `RerankUsage` tail with:

```python
        model_calls: ``0`` or ``1``. Hidden retries are forbidden.
        invalid_subcode: ``RerankPayloadError.subcode`` when the payload
            failed application validation, else empty.
    """

    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    model_calls: int
    invalid_subcode: str = ""
```

d) In `validate_rerank_payload`, replace the `Raises:` entry with:

```python
    Raises:
        RerankPayloadError: If status, IDs, ranks, or support violate the
            contract. ``str(error)`` is the specific reason and
            ``subcode`` is its coarse class.
```

Then replace each raise as follows. Keep `from error` where the line has
it now, and keep every other line unchanged.

| Current line | New line |
| --- | --- |
| `raise ValueError("rerank_support_out_of_bounds") from error` | `raise RerankPayloadError("rerank_support_out_of_bounds", subcode="json") from error` |
| `raise ValueError("rerank_support_invalid") from error` | `raise RerankPayloadError("rerank_support_invalid", subcode="json") from error` |
| `raise ValueError("rerank_rank_invalid") from error` | `raise RerankPayloadError("rerank_rank_invalid", subcode="json") from error` |
| `raise ValueError("rerank_incomplete") from error` | `raise RerankPayloadError("rerank_incomplete", subcode="json") from error` |
| `raise ValueError("rerank_schema_invalid") from error` | `raise RerankPayloadError("rerank_schema_invalid", subcode="json") from error` |
| `raise ValueError("rerank_input_hash_mismatch")` | `raise RerankPayloadError("rerank_input_hash_mismatch", subcode="hash")` |
| `raise ValueError("rerank_ranking_length")` | `raise RerankPayloadError("rerank_ranking_length", subcode="length")` |
| `raise ValueError("rerank_unknown_or_missing_id")` | `raise RerankPayloadError("rerank_unknown_or_missing_id", subcode="unknown_id")` |
| `raise ValueError("rerank_duplicate_id")` | `raise RerankPayloadError("rerank_duplicate_id", subcode="duplicate")` |
| `raise ValueError("rerank_id_set_mismatch")` | `raise RerankPayloadError("rerank_id_set_mismatch", subcode="unknown_id")` |

Replace the combined rank check

```python
        if row.rank > len(candidate_ids) or row.rank in seen_ranks:
            raise ValueError("rerank_rank_invalid")
```

with

```python
        if row.rank > len(candidate_ids):
            raise RerankPayloadError("rerank_rank_invalid", subcode="json")
        if row.rank in seen_ranks:
            raise RerankPayloadError("rerank_rank_invalid", subcode="duplicate")
```

After the edit, `rg -n "raise ValueError" packages/core/src/smart_rag_core/retrieval/rerank.py`
must not list any line inside `validate_rerank_payload`. The only new
`raise ValueError` is in `RerankPayloadError.__init__`.

### 3. `reranker.py`: carry the sub-code

a) In the R7 import list add `RerankPayloadError,` directly after
`RerankPassage,`.

b) Replace `    except ValueError:` (line 90) and the `RerankUsage(...)`
inside it with:

```python
    except ValueError as error:
        subcode = error.subcode if isinstance(error, RerankPayloadError) else "json"
        return (
            (),
            RerankUsage(
                request_id=response.request_id,
                model=RERANK_MODEL_ID,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model_calls=response.model_calls,
                invalid_subcode=subcode,
            ),
            RerankFallbackReason.SCHEMA_INVALID,
        )
```

c) In the `rerank_pool` docstring `Returns:` block, add this sentence
after `rankings tuple is empty so the caller keeps fused RRF order.`:
`Schema-invalid usage carries ``invalid_subcode``.`

### 4. `hybrid.py`: per-channel durations

a) Add `import time` as the first stdlib import, directly after
`from __future__ import annotations` and its blank line, and before
`from collections import defaultdict`.

b) Replace the whole R2 function with the code below, and append
`_timed_call` after it at the end of the file:

```python
def run_channels_parallel(
    jobs: dict[str, Callable[[], object]],
    *,
    deadline_seconds: float = HYBRID_DEADLINE_SECONDS,
    durations_ms: dict[str, int] | None = None,
) -> tuple[dict[str, object], tuple[str, ...], bool]:
    """Run channel callables in parallel and record timeouts separately.

    Args:
        jobs: Mapping of channel name to zero-argument callables.
        deadline_seconds: Remaining Hybrid deadline share.
        durations_ms: Optional sink. Receives the in-thread wall time in
            integer milliseconds of every job that finished before the
            deadline. Timed-out jobs get no entry.

    Returns:
        Completed results, timed-out names, and whether the deadline exhausted.

    Side Effects:
        Executes the callables in worker threads. Does not start answer
        generation. Writes ``durations_ms`` when given.
    """

    if deadline_seconds <= 0:
        return {}, tuple(jobs), True
    executor = ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    try:
        futures = {
            executor.submit(_timed_call, job): name for name, job in jobs.items()
        }
        done, pending = wait(futures, timeout=deadline_seconds)
        timed_out = tuple(futures[item] for item in pending)
        for item in pending:
            item.cancel()
        completed: dict[str, object] = {}
        for item in done:
            value, elapsed = item.result()
            completed[futures[item]] = value
            if durations_ms is not None:
                durations_ms[futures[item]] = elapsed
        return completed, timed_out, bool(timed_out)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _timed_call(job: Callable[[], object]) -> tuple[object, int]:
    """Run one channel job and measure it inside its worker thread.

    Args:
        job: Zero-argument channel callable.

    Returns:
        The job result and its non-negative wall time in integer
        milliseconds.

    Raises:
        Exception: Whatever ``job`` raises, unchanged. ``item.result()``
            re-raises it in the caller exactly as before.
    """

    started = time.perf_counter()
    value = job()
    return value, int(max(0.0, time.perf_counter() - started) * 1000.0)
```

### 5. `types.py`: result fields

a) Line 6 becomes `from dataclasses import dataclass, field`.

b) Replace the R3 docstring tail with:

```python
        source_resolution: Server-derived scope token. Empty when the
            retrieve path did not attach one.
        stage_timings_ms: ID-free wall-clock milliseconds per retrieve
            stage, keyed by ``HYBRID_STAGE_TIMING_KEYS``. Empty on cache
            hits and fail-closed returns. ``rerank_call_ms`` exists only
            when the rerank callback ran; a timed-out channel has no
            ``channel_*_ms`` key. Treat as read-only.
        rerank_invalid_subcode: ``RerankPayloadError.subcode`` when the
            rerank payload failed validation, else empty.
    """
```

c) Replace the R3 field tail with:

```python
    term_ids: tuple[UUID, ...] = ()
    source_resolution: str = ""
    stage_timings_ms: dict[str, int] = field(default_factory=dict[str, int])
    rerank_invalid_subcode: str = ""
```

### 6. `budget.py`: `timed_rerank`

a) Insert `import time` between `from __future__ import annotations`
(plus its blank line) and `from collections.abc import Callable`.

b) Append at the end of the file (after `return _wrapped`, with two
blank lines):

```python
def timed_rerank(inner: RerankFn, sink: list[int]) -> RerankFn:
    """Wrap a rerank callback and record its wall time.

    Args:
        inner: Rerank callback, usually the ``counted_rerank`` wrapper.
        sink: List that receives one non-negative integer millisecond
            value per invocation, including invocations that raise.

    Returns:
        Callback with the same contract as ``inner``.

    Side Effects:
        Appends to ``sink``. Adds no model call, retry, or budget debit.
    """

    def _timed(
        query: str,
        pool: tuple[RerankPassage, ...],
        remaining_deadline_seconds: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Invoke ``inner`` once and record its duration.

        Args:
            query: Original user query.
            pool: Authorized rerank pool.
            remaining_deadline_seconds: Remaining Hybrid deadline share.

        Returns:
            The unchanged ``inner`` triple.
        """

        started = time.perf_counter()
        try:
            return inner(query, pool, remaining_deadline_seconds)
        finally:
            sink.append(int(max(0.0, time.perf_counter() - started) * 1000.0))

    return _timed
```

### 7. `retriever.py`: measure the stages

Make these edits in order. Each "after" is an exact insertion.

a) In the assemble import list, add `elapsed_ms,` after
`compute_principal_scope_hash,`. In the budget import, add
`timed_rerank,` after `counted_rerank,`.

b) After `read ParadeDB and Supabase. No holdout access. No answer tokens.`
add the docstring line
`            Records ID-free per-stage wall times in ``stage_timings_ms``.`

c) Between `texts = query_texts(query, profile)` and
`embed_response, embed_error = embed_query_texts(` insert:

```python
        embed_started = time.perf_counter()
```

d) After `vectors = embed_response.vectors` insert:

```python
        timings: dict[str, int] = {"embed_ms": int(elapsed_ms(embed_started))}
```

e) Replace

```python
        channel_started = time.perf_counter()
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
        )
```

with

```python
        channel_started = time.perf_counter()
        channel_ms: dict[str, int] = {}
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
            durations_ms=channel_ms,
        )
        post_channel_started = time.perf_counter()
        timings["channels_ms"] = int(elapsed_ms(channel_started))
        for name in ("dense", "bm25", "term"):
            if name in channel_ms:
                timings[f"channel_{name}_ms"] = channel_ms[name]
```

f) Replace

```python
        temporal_records = self._load_temporal_records(
            flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
```

with

```python
        temporal_started = time.perf_counter()
        temporal_records = self._load_temporal_records(
            flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
        timings["temporal_load_ms"] = int(elapsed_ms(temporal_started))
```

g) After `fused_at = time.perf_counter() if fused_ids else None` insert:

```python
        timings["assemble_ms"] = max(
            0, int(elapsed_ms(post_channel_started)) - timings["temporal_load_ms"]
        )
```

h) After the `remaining = remaining_slice_seconds(...)` call (its
closing `)` line) insert:

```python
        timings["rerank_gate_remaining_ms"] = int(remaining * 1000)
        preload_started = time.perf_counter()
```

i) Replace

```python
        contexts = loader(preload_ids) if preload_ids else ()
        rerank_fn: RerankFn = counted_rerank(
            self._rerank or identity_rerank,
            self.query_budget,
            count_gateway=self._rerank is not None,
        )
```

with

```python
        contexts = loader(preload_ids) if preload_ids else ()
        timings["pool_preload_ms"] = int(elapsed_ms(preload_started))
        rerank_call_ms: list[int] = []
        rerank_fn: RerankFn = timed_rerank(
            counted_rerank(
                self._rerank or identity_rerank,
                self.query_budget,
                count_gateway=self._rerank is not None,
            ),
            rerank_call_ms,
        )
```

j) After `rerank_fallback = ""` insert `        rerank_invalid_subcode = ""`.

k) Between `if assembled.fused:` and `selection = select_hybrid_context(`
insert `            selection_started = time.perf_counter()`.

l) Replace

```python
            if selection.usage is not None:
                rerank_calls = selection.usage.model_calls
```

with

```python
            timings["selection_ms"] = int(elapsed_ms(selection_started))
            if rerank_call_ms:
                timings["rerank_call_ms"] = rerank_call_ms[0]
            if selection.usage is not None:
                rerank_calls = selection.usage.model_calls
                rerank_invalid_subcode = selection.usage.invalid_subcode
```

m) Replace
`            locator_rows = loader(selected_ids) if selected_ids else ()` with

```python
            locator_started = time.perf_counter()
            locator_rows = loader(selected_ids) if selected_ids else ()
            timings["locator_reload_ms"] = int(elapsed_ms(locator_started))
```

n) Replace the return tail

```python
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            term_ids=term_ids,
        )
```

with

```python
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            term_ids=term_ids,
            stage_timings_ms={
                **timings,
                "retrieve_total_ms": int(elapsed_ms(started)),
            },
            rerank_invalid_subcode=rerank_invalid_subcode,
        )
```

Then `(Get-Content packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py).Count`
must print a number below 600 (the architecture cap). Expect about 560.

### 8. `adapters_hybrid.py`: `scope_ms`

a) Insert `import time` between `from __future__ import annotations`
(plus its blank line) and `from collections.abc import Callable`.

b) In the `retrieve` docstring, after
`preload, parent expansion, and locator reload.` add:
`            Adds ``scope_ms`` (scope resolution plus frozen-profile load) to ``stage_timings_ms``.`

c) Directly before `scope = self._resolve_scope(caller, typed_profile, query=query)`
insert `        scope_started = time.perf_counter()`.

d) Directly after `retrieval_profile = load_frozen_profile(profile_id)`
insert:

```python
        scope_ms = int(max(0.0, time.perf_counter() - scope_started) * 1000.0)
```

e) Replace `        return replace(result, source_resolution=resolution)` with:

```python
        return replace(
            result,
            source_resolution=resolution,
            stage_timings_ms={**result.stage_timings_ms, "scope_ms": scope_ms},
        )
```

### 9. `results.py`: diagnostics fields

a) After the R8 `plan` import line add:

```python
from smart_rag_core.retrieval.profiles import (
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
)
```

b) After the docstring line
`        effective_route: Executed branch family, never ``runs.route_family``.`
add:

```python
        stage_timings_ms: ID-free wall-clock milliseconds per retrieve
            stage. Keys come from ``HYBRID_STAGE_TIMING_KEYS``; values are
            non-negative integers. Empty for older checkpoints.
        rerank_invalid_subcode: Rerank validation sub-code (``json``,
            ``hash``, ``length``, ``duplicate``, ``unknown_id``) when
            ``rerank_fallback`` is ``rerank_schema_invalid``, else empty.
```

c) After `    effective_route: str = Field(min_length=1, max_length=64)` add:

```python
    stage_timings_ms: dict[str, int] = Field(default_factory=dict[str, int])
    rerank_invalid_subcode: str = Field(default="", max_length=16)
```

d) After `ids_are_uuid_strings` (after its `return value`, before the two
blank lines and `class BranchResult`) add:

```python

    @field_validator("stage_timings_ms")
    @classmethod
    def timings_are_known_non_negative(
        cls, value: dict[str, int]
    ) -> dict[str, int]:
        """Reject unknown stage names and negative durations.

        Args:
            value: Stage name to integer milliseconds.

        Returns:
            The same mapping when every key is allow-listed and every
            value is at least zero.

        Raises:
            ValueError: ``stage_timing_key_invalid`` or
                ``stage_timing_negative``.
        """

        for key, item in value.items():
            if key not in HYBRID_STAGE_TIMING_KEYS:
                raise ValueError("stage_timing_key_invalid")
            if item < 0:
                raise ValueError("stage_timing_negative")
        return value

    @field_validator("rerank_invalid_subcode")
    @classmethod
    def subcode_is_known(cls, value: str) -> str:
        """Reject free-text rerank validation sub-codes.

        Args:
            value: Empty or one ``RERANK_INVALID_SUBCODES`` value.

        Returns:
            The same string.

        Raises:
            ValueError: ``rerank_subcode_invalid``.
        """

        if value and value not in RERANK_INVALID_SUBCODES:
            raise ValueError("rerank_subcode_invalid")
        return value
```

### 10. `branch_channels/hybrid.py`: builder

a) Replace line 30 with:

```python
from smart_rag_core.retrieval.profiles import (
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
    RETRIEVAL_SLICE_SECONDS,
)
```

b) Replace the R9 builder tail with:

```python
        support_confidence=getattr(coverage, "support_confidence", None),
        effective_route=effective_route,
        stage_timings_ms=_stage_timings(getattr(outcome, "stage_timings_ms", None)),
        rerank_invalid_subcode=_invalid_subcode(
            getattr(outcome, "rerank_invalid_subcode", "")
        ),
    )
```

c) Insert before `def chunk_loader(` (after `_uuid_ids`):

```python
def _stage_timings(value: object) -> dict[str, int]:
    """Keep allow-listed, non-negative integer stage timings.

    Args:
        value: ``stage_timings_ms`` from the retrieve outcome, or anything.

    Returns:
        A new dict with only known keys and non-negative ``int`` values.
        Booleans, floats, strings, and unknown keys are dropped, so a bad
        value never fails the branch.
    """

    if not isinstance(value, dict):
        return {}
    kept: dict[str, int] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str) or key not in HYBRID_STAGE_TIMING_KEYS:
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            continue
        kept[key] = item
    return kept


def _invalid_subcode(value: object) -> str:
    """Return an allow-listed rerank validation sub-code or empty.

    Args:
        value: ``rerank_invalid_subcode`` from the retrieve outcome.

    Returns:
        The value when it is in ``RERANK_INVALID_SUBCODES``, else ``""``.
    """

    if isinstance(value, str) and value in RERANK_INVALID_SUBCODES:
        return value
    return ""
```

### 11. `scripts/eval_ask_stage_export.py`: export and flag fix

a) After the R11 `langgraph` import add:
`from smart_rag_core.retrieval.profiles import RERANK_INVALID_SUBCODES`.

b) Replace lines 122-123 with:

```python
            if not bm25_record_keeps_aggregate(record):
                bm25_explicit = False
```

c) Replace line 232 with:

```python
    raw_fallback = str(diagnostics.get("fallback_reason") or "").strip()
    fallback = raw_fallback or "unknown"
```

d) Replace lines 243-252 (the ten lines from `bm25_named = ...` to the
last `bm25_explicit = "unknown"`) with:

```python
    bm25_explicit = bm25_explicit_flag(raw_fallback)
```

e) Replace the R11 dict tail with:

```python
        "bm25_degraded_explicit": bm25_explicit,
        "retrieval_empty": retrieval_empty,
        "stage_timings_ms": _timings_or_unknown(diagnostics.get("stage_timings_ms")),
        "rerank_invalid_subcode": _subcode_or_unknown(
            diagnostics.get("rerank_invalid_subcode")
        ),
    }
```

Do **not** add the two new names to `REQUIRED_FIELDS`. Older checkpoints
lack them, and they must not count as unknown required fields.

f) Insert directly before `def _int_or_unknown(value: object) -> int | str:`:

```python
def bm25_explicit_flag(raw_fallback: str) -> bool | str:
    """Classify whether one run's retrieve fallback names a BM25 outage.

    Args:
        raw_fallback: Stripped ``fallback_reason`` from diagnostics; may be
            empty.

    Returns:
        ``False`` for no degradation (``none`` or empty) and for reasons
        that can hide a BM25 outage (``term_unavailable``,
        ``dense_unavailable``). ``"unknown"`` for the literal ``unknown``.
        ``True`` for every other named reason.
    """

    if raw_fallback in {"", "none", "term_unavailable", "dense_unavailable"}:
        return False
    if raw_fallback == "unknown":
        return "unknown"
    return True


def bm25_record_keeps_aggregate(record: Mapping[str, object]) -> bool:
    """Return whether one run keeps the aggregate BM25-explicit flag true.

    A run whose ``fallback_reason`` is ``none`` had no outage to name, so
    its per-run ``False`` does not lower the promotion aggregate. Any
    other run must carry ``bm25_degraded_explicit is True``.

    Args:
        record: One ``stage_record`` result.

    Returns:
        True when the aggregate may stay true for this run.
    """

    if record.get("fallback_reason") == "none":
        return True
    return record.get("bm25_degraded_explicit") is True


def _timings_or_unknown(value: object) -> dict[str, int] | str:
    """Return non-negative integer stage timings or ``unknown``.

    Args:
        value: JSON value of ``stage_timings_ms``.

    Returns:
        String-keyed integer milliseconds, or ``unknown`` when missing or
        malformed.
    """

    if not isinstance(value, dict):
        return "unknown"
    timings: dict[str, int] = {}
    for key, item in cast(dict[object, object], value).items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            return "unknown"
        timings[str(key)] = item
    return timings


def _subcode_or_unknown(value: object) -> str:
    """Return the rerank validation sub-code, empty, or ``unknown``.

    Args:
        value: JSON value of ``rerank_invalid_subcode``.

    Returns:
        The string when it is empty or allow-listed, else ``unknown``.
    """

    if not isinstance(value, str):
        return "unknown"
    if value and value not in RERANK_INVALID_SUBCODES:
        return "unknown"
    return value
```

g) `tests/unit/test_hybrid_branch_diagnostics.py` line 225: change
`assert ok["bm25_degraded_explicit"] is True` to
`assert ok["bm25_degraded_explicit"] is False`. Change nothing else in
that file.

## Tests: `tests/unit/test_hybrid_stage_timings.py` (new file, exact code)

```python
"""Hybrid stage timings, rerank validation sub-codes, and export flags (A2)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.gateways.model import RerankModelRequest, RerankModelResponse
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branch_channels.hybrid import (
    hybrid_diagnostics_from_outcome,
)
from smart_rag_core.query_routing.models import HybridBranchDiagnostics
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid import run_channels_parallel
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import (
    HYBRID_DEFAULT_PROFILE_ID,
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankPayloadError,
    RerankRanking,
    RerankUsage,
    rerank_input_hash,
    validate_rerank_payload,
)
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole

from scripts.eval_ask_stage_export import (
    bm25_explicit_flag,
    bm25_record_keeps_aggregate,
    stage_record,
)

_RerankTriple = tuple[
    tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason
]
_ALWAYS = frozenset(
    {
        "embed_ms",
        "channels_ms",
        "assemble_ms",
        "temporal_load_ms",
        "pool_preload_ms",
        "rerank_gate_remaining_ms",
        "selection_ms",
        "locator_reload_ms",
        "retrieve_total_ms",
    }
)


def _caller() -> CallerContext:
    """Build an active member caller.

    Returns:
        Server-derived caller context.
    """

    return CallerContext(
        user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
    )


def _candidate(rank: int = 1) -> RetrievalCandidate:
    """Build one authorized candidate in its own document.

    Args:
        rank: Channel rank.

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


def _retriever(
    rows: dict[UUID, ChunkContext], triple: _RerankTriple | None = None
) -> HybridRetriever:
    """Build a retriever with mock embeddings and an injected rerank.

    Args:
        rows: Authorized context rows by chunk id.
        triple: Fixed rerank result. ``None`` returns identity rankings.

    Returns:
        Retriever that uses no database.
    """

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows for the requested IDs.

        Args:
            ids: Requested chunk IDs.

        Returns:
            Matching rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def rerank(
        _query: str, pool: tuple[RerankPassage, ...], _deadline: float
    ) -> _RerankTriple:
        """Return the fixed triple, or identity rankings with one call.

        Args:
            _query: Unused.
            pool: Authorized pool.
            _deadline: Unused.

        Returns:
            Rerank triple.
        """

        if triple is not None:
            return triple
        rankings = tuple(
            RerankRanking(chunk_id=item.candidate.chunk_id, rank=index, support=0.5)
            for index, item in enumerate(pool, start=1)
        )
        usage = RerankUsage(
            request_id="t",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return rankings, usage, RerankFallbackReason.NONE

    return HybridRetriever(
        embedding_gateway=EmbeddingGateway(MockEmbeddingAdapter(fixture_id="hybrid-run")),
        load_context=load,
        rerank=rerank,
    )


def _is_ms(value: object) -> bool:
    """Return whether a timing value is a non-negative int (not bool).

    Args:
        value: Timing value.

    Returns:
        True for a non-negative integer.
    """

    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def test_retrieve_records_non_negative_stage_timings() -> None:
    """Every measured stage is a known key with non-negative integer ms."""

    dense, bm25, term = _candidate(), _candidate(), _candidate()
    rows = {
        dense.chunk_id: _context(dense, "annual leave accrues monthly"),
        bm25.chunk_id: _context(bm25, "leave carry over rules"),
        term.chunk_id: _context(term, "leave policy definitions"),
    }
    result = _retriever(rows).retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={
            "dense": lambda: (dense,),
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=(bm25,)),
            "term": lambda: (term,),
        },
    )
    timings = result.stage_timings_ms
    assert set(timings) >= _ALWAYS
    assert {"channel_dense_ms", "channel_bm25_ms", "channel_term_ms"} <= set(timings)
    assert "rerank_call_ms" in timings
    assert "scope_ms" not in timings
    assert set(timings) <= HYBRID_STAGE_TIMING_KEYS
    assert all(_is_ms(value) for value in timings.values())
    assert result.rerank_invalid_subcode == ""


def test_timed_out_channel_and_gate_skip_have_no_duration() -> None:
    """A timed-out channel has no key; a gate skip records no rerank call."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }

    def hang() -> object:
        """Outlive the tiny test slice.

        Returns:
            An empty BM25 result after the slice has expired.
        """

        time.sleep(0.25)
        return Bm25RetrievalResult(scanned_ids=(), candidates=())

    result = _retriever(rows).retrieve(
        query="annual leave policy",
        caller=_caller(),
        deadline_seconds=0.05,
        channel_jobs={"dense": lambda: (first, second), "bm25": hang},
    )
    timings = result.stage_timings_ms
    assert result.deadline_exhausted is True
    assert "channel_dense_ms" in timings
    assert "channel_bm25_ms" not in timings
    assert "rerank_call_ms" not in timings
    assert timings["rerank_gate_remaining_ms"] <= 50
    assert result.rerank_fallback == RerankFallbackReason.TIMEOUT.value


def test_schema_invalid_subcode_reaches_the_result() -> None:
    """The sub-code rides on rerank usage into the retrieve result."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }
    usage = RerankUsage(
        request_id="r",
        model="gpt-4o-mini",
        input_tokens=3,
        output_tokens=2,
        model_calls=1,
        invalid_subcode="hash",
    )
    triple: _RerankTriple = ((), usage, RerankFallbackReason.SCHEMA_INVALID)
    result = _retriever(rows, triple).retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={"dense": lambda: (first, second)},
    )
    assert result.rerank_fallback == RerankFallbackReason.SCHEMA_INVALID.value
    assert result.rerank_invalid_subcode == "hash"
    assert "rerank_call_ms" in result.stage_timings_ms


def test_rerank_pool_records_json_subcode_without_retry() -> None:
    """A parsed payload with the wrong shape is schema-invalid with ``json``."""

    calls: list[str] = []

    class _Gateway:
        """Return one payload that lacks the ranking fields."""

        async def generate_rerank(
            self, request: RerankModelRequest
        ) -> RerankModelResponse:
            """Record the call and return a shape-invalid payload.

            Args:
                request: Structured rerank request.

            Returns:
                Response whose payload has only ``status``.
            """

            calls.append(request.prompt_version)
            return RerankModelResponse(
                mode="mock",
                payload={"status": "complete"},
                request_id="fake-rerank",
                input_tokens=5,
                output_tokens=2,
            )

    pool = (
        RerankPassage(candidate=_candidate(1), raw_text="alpha", excerpt="alpha"),
        RerankPassage(candidate=_candidate(2), raw_text="beta", excerpt="beta"),
    )
    rankings, usage, reason = rerank_pool(
        "q",
        pool,
        8.0,
        gateway=_Gateway(),  # type: ignore[arg-type]
        prompt_text="rank",
    )
    assert len(calls) == 1
    assert rankings == ()
    assert reason is RerankFallbackReason.SCHEMA_INVALID
    assert usage is not None
    assert usage.invalid_subcode == "json"
    assert usage.output_tokens == 2


def test_v1_validation_errors_carry_one_subcode_each() -> None:
    """Each rerank_v1 check raises RerankPayloadError with its sub-code."""

    first, second = uuid4(), uuid4()
    digest = rerank_input_hash(
        query="q",
        candidate_ids=(str(first), str(second)),
        excerpts=("a", "b"),
        prompt_sha256="0" * 64,
    )
    good: list[dict[str, object]] = [
        {"chunk_id": str(first), "rank": 1, "support": 0.9},
        {"chunk_id": str(second), "rank": 2, "support": 0.1},
    ]
    extra: dict[str, object] = {"chunk_id": str(uuid4()), "rank": 3, "support": 0.0}
    cases: list[tuple[object, str, str]] = [
        ({"status": "complete"}, "rerank_schema_invalid", "json"),
        (
            {"status": "complete", "input_hash": "f" * 64, "rankings": good},
            "rerank_input_hash_mismatch",
            "hash",
        ),
        (
            {"status": "complete", "input_hash": digest, "rankings": [*good, extra]},
            "rerank_ranking_length",
            "length",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [good[0], {**good[0], "rank": 2}],
            },
            "rerank_duplicate_id",
            "duplicate",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [good[0], {**good[1], "rank": 1}],
            },
            "rerank_rank_invalid",
            "duplicate",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [{**good[0], "chunk_id": str(uuid4())}, good[1]],
            },
            "rerank_unknown_or_missing_id",
            "unknown_id",
        ),
    ]
    for payload, message, subcode in cases:
        with pytest.raises(RerankPayloadError) as caught:
            validate_rerank_payload(
                payload, candidate_ids=(first, second), input_hash=digest
            )
        assert str(caught.value) == message
        assert caught.value.subcode == subcode
    assert issubclass(RerankPayloadError, ValueError)
    assert frozenset({"json", "hash", "length", "duplicate", "unknown_id"}) == (
        RERANK_INVALID_SUBCODES
    )
    with pytest.raises(ValueError, match="rerank_subcode_invalid"):
        RerankPayloadError("x", subcode="other")


def test_diagnostics_keep_known_timings_and_reject_bad_ones() -> None:
    """The builder drops bad values; the model rejects them outright."""

    chunk = str(uuid4())
    outcome = SimpleNamespace(
        source_resolution="unscoped",
        retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        rerank_fallback="rerank_schema_invalid",
        rerank_call_count=1,
        embedding_call_count=1,
        first_evidence_ms=4.0,
        dense_ids=(chunk,),
        fused_ids=(chunk,),
        selected_ids=(chunk,),
        stage_timings_ms={
            "embed_ms": 120,
            "channels_ms": 2400,
            "not_a_stage_ms": 5,
            "selection_ms": -1,
            "rerank_call_ms": True,
        },
        rerank_invalid_subcode="length",
    )
    row = hybrid_diagnostics_from_outcome(
        outcome, effective_route=Phase6RouteFamily.HYBRID.value, fallback_reason="none"
    )
    assert row is not None
    assert row.stage_timings_ms == {"embed_ms": 120, "channels_ms": 2400}
    assert row.rerank_invalid_subcode == "length"
    bare = hybrid_diagnostics_from_outcome(
        SimpleNamespace(
            source_resolution="unscoped",
            retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
            rerank_invalid_subcode="free text",
        ),
        effective_route=Phase6RouteFamily.HYBRID.value,
        fallback_reason="none",
    )
    assert bare is not None
    assert bare.rerank_invalid_subcode == ""
    assert bare.stage_timings_ms == {}
    base = row.model_dump()
    for bad in (
        {"stage_timings_ms": {"query_text": 1}},
        {"stage_timings_ms": {"embed_ms": -3}},
        {"rerank_invalid_subcode": "other"},
    ):
        with pytest.raises(ValidationError):
            HybridBranchDiagnostics.model_validate({**base, **bad})


def test_stage_record_exports_new_fields_and_fixed_bm25_flag() -> None:
    """Export copies the fields; ``none`` and empty are not explicit BM25."""

    chunk = str(uuid4())
    diagnostics: dict[str, object] = {
        "source_resolution": "unscoped",
        "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "fallback_reason": "none",
        "rerank_fallback": "rerank_schema_invalid",
        "rerank_call_count": 1,
        "embedding_call_count": 1,
        "dense_ids": [chunk],
        "bm25_ids": [chunk],
        "term_ids": [chunk],
        "fused_ids": [chunk],
        "selected_ids": [chunk],
        "rerank_pool_ids": [chunk],
        "effective_route": "hybrid",
        "stage_timings_ms": {"embed_ms": 110, "rerank_call_ms": 4200},
        "rerank_invalid_subcode": "duplicate",
    }
    record = stage_record(diagnostics, {"embedding", "rerank"})
    assert record["stage_timings_ms"] == {"embed_ms": 110, "rerank_call_ms": 4200}
    assert record["rerank_invalid_subcode"] == "duplicate"
    assert record["bm25_degraded_explicit"] is False
    legacy = stage_record(
        {
            key: value
            for key, value in diagnostics.items()
            if key not in {"stage_timings_ms", "rerank_invalid_subcode"}
        },
        {"embedding", "rerank"},
    )
    assert legacy["stage_timings_ms"] == "unknown"
    assert legacy["rerank_invalid_subcode"] == "unknown"
    empty = stage_record({**diagnostics, "fallback_reason": ""}, {"embedding"})
    assert empty["fallback_reason"] == "unknown"
    assert empty["bm25_degraded_explicit"] is False
    assert bm25_explicit_flag("none") is False
    assert bm25_explicit_flag("") is False
    assert bm25_explicit_flag("term_unavailable") is False
    assert bm25_explicit_flag("bm25_unavailable") is True
    assert bm25_explicit_flag("timeout") is True
    assert bm25_explicit_flag("unknown") == "unknown"
    assert bm25_record_keeps_aggregate(record) is True
    masked = {"fallback_reason": "term_unavailable", "bm25_degraded_explicit": False}
    named = {"fallback_reason": "bm25_unavailable", "bm25_degraded_explicit": True}
    unknown = {"fallback_reason": "unknown", "bm25_degraded_explicit": "unknown"}
    assert bm25_record_keeps_aggregate(masked) is False
    assert bm25_record_keeps_aggregate(named) is True
    assert bm25_record_keeps_aggregate(unknown) is False


def test_run_channels_parallel_measures_only_finished_channels() -> None:
    """Finished channels get a duration; timed-out channels get none."""

    def slow() -> object:
        """Outlive the deadline.

        Returns:
            An empty tuple after the deadline.
        """

        time.sleep(0.25)
        return ()

    durations: dict[str, int] = {}
    completed, timed_out, exhausted = run_channels_parallel(
        {"dense": lambda: ("d",), "bm25": slow},
        deadline_seconds=0.05,
        durations_ms=durations,
    )
    assert completed == {"dense": ("d",)}
    assert timed_out == ("bm25",)
    assert exhausted is True
    assert set(durations) == {"dense"}
    assert durations["dense"] >= 0
```

`scope_ms` has no unit test: no unit test builds `ProcessHybridRetriever`
(it needs a DSN). The live export below proves it.

## Private script: `.private-eval/a2_timing_summary.py` (new, not tracked)

`.private-eval/` is gitignored. Confirm it with
`git check-ignore .private-eval/a2_timing_summary.py`, which must print
the path. Exact code:

```python
"""Summarize Hybrid stage timings from one private stage export (A2).

Usage: python .private-eval/a2_timing_summary.py <stages.json>

Prints aggregates only: n, p50, p90, and max per timing key, the derived
post-channel sum, rerank outcome counts, and schema-invalid sub-code
counts. Never prints questions, answers, or chunk IDs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

KEYS = (
    "scope_ms",
    "embed_ms",
    "channels_ms",
    "channel_dense_ms",
    "channel_bm25_ms",
    "channel_term_ms",
    "assemble_ms",
    "temporal_load_ms",
    "pool_preload_ms",
    "rerank_gate_remaining_ms",
    "rerank_call_ms",
    "selection_ms",
    "locator_reload_ms",
    "retrieve_total_ms",
)
POST_CHANNEL_PARTS = ("assemble_ms", "temporal_load_ms", "pool_preload_ms")


def percentile_row(name: str, values: list[int]) -> str:
    """Format one Markdown row of n, p50 (lower median), p90 (nearest rank), max.

    Args:
        name: Timing key.
        values: Integer milliseconds.

    Returns:
        One Markdown table row. Empty input prints dashes.
    """

    if not values:
        return f"| `{name}` | 0 | - | - | - |"
    ordered = sorted(values)
    count = len(ordered)
    p50 = ordered[(count - 1) // 2]
    p90 = ordered[min(count - 1, int(0.9 * count))]
    return f"| `{name}` | {count} | {p50} | {p90} | {ordered[-1]} |"


def main(argv: list[str]) -> int:
    """Print the timing table and outcome counts for one stages.json.

    Args:
        argv: ``[stages_json_path]``.

    Returns:
        0 on success, 2 on bad usage.
    """

    if len(argv) != 1:
        print("usage: a2_timing_summary.py <stages.json>")
        return 2
    runs = json.loads(Path(argv[0]).read_text(encoding="utf-8")).get("runs", {})
    series: dict[str, list[int]] = {key: [] for key in KEYS}
    post_channel: list[int] = []
    outcomes: Counter[str] = Counter()
    subcodes: Counter[str] = Counter()
    missing = 0
    for record in runs.values():
        timings = record.get("stage_timings_ms")
        if not isinstance(timings, dict):
            missing += 1
            timings = {}
        for key in KEYS:
            value = timings.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                series[key].append(value)
        if all(isinstance(timings.get(part), int) for part in POST_CHANNEL_PARTS):
            post_channel.append(sum(int(timings[part]) for part in POST_CHANNEL_PARTS))
        outcome = str(record.get("rerank_fallback") or "unknown")
        if outcome == "rerank_timeout":
            source = "provider" if "rerank_call_ms" in timings else "gate"
            outcome = f"rerank_timeout ({source})"
        outcomes[outcome] += 1
        if record.get("rerank_fallback") == "rerank_schema_invalid":
            subcodes[str(record.get("rerank_invalid_subcode") or "(empty)")] += 1
    print("| Key | n | p50 ms | p90 ms | max ms |")
    print("| --- | --- | --- | --- | --- |")
    for key in KEYS:
        print(percentile_row(key, series[key]))
    print(percentile_row("post_channel_ms", post_channel))
    print()
    print("Rerank outcomes:", ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())))
    codes = ", ".join(f"{k}={v}" for k, v in sorted(subcodes.items())) or "none"
    print("Schema-invalid sub-codes:", codes)
    print(f"Runs without stage_timings_ms: {missing} of {len(runs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

`(empty)` in the sub-code line means the provider text was not JSON (the
gateway path with no usage).

## Commands (run in this order; all must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/retrieval/profiles.py packages/core/src/smart_rag_core/retrieval/rerank.py packages/core/src/smart_rag_core/retrieval/reranker.py packages/core/src/smart_rag_core/retrieval/hybrid.py packages/core/src/smart_rag_core/retrieval/hybrid_run/budget.py packages/core/src/smart_rag_core/retrieval/hybrid_run/types.py packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py packages/core/src/smart_rag_core/query_routing/models/results.py packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py scripts/eval_ask_stage_export.py tests/unit/test_hybrid_stage_timings.py tests/unit/test_hybrid_branch_diagnostics.py
uv run python -m ruff check --select I --fix packages/core/src/smart_rag_core/retrieval packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py scripts/eval_ask_stage_export.py tests/unit/test_hybrid_stage_timings.py
uv run python -m pytest tests/unit/test_hybrid_stage_timings.py -q
uv run python -m pytest tests/unit/test_hybrid_branch_diagnostics.py tests/unit/test_hybrid_rerank.py tests/unit/test_openai_rerank.py tests/unit/test_hybrid_run.py tests/unit/test_hybrid_fusion.py tests/unit/test_graph_mapping_hybrid.py -q
uv run python -m pytest tests/contract/test_architecture_budgets.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
```

Expected: the new file passes 8 tests. If an existing rerank test fails
because it expects a plain `ValueError` type, that is not expected
(`RerankPayloadError` is a `ValueError`); stop and report (rule 13).

## Live measurement (about 20 minutes including the image build)

Run this before writing the doc numbers. The doc goes into the same
commit.

1. Rebuild and probe (see **Docker rebuild** in the rules file). `A1` and
   `A2` must print `present`.
2. Subset gold `a01`..`a10` and the run:

   ```powershell
   New-Item -ItemType Directory -Force .private-eval/runs/a2-timings | Out-Null
   $ids = @("a01","a02","a03","a04","a05","a06","a07","a08","a09","a10")
   $gold = Get-Content .private-eval/answer50-v1.json -Raw | ConvertFrom-Json
   $gold | Where-Object { $ids -contains $_.id } | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 .private-eval/runs/a2-timings/gold.json
   uv run python scripts/run_company_ask.py `
     --gold .private-eval/runs/a2-timings/gold.json `
     --out .private-eval/runs/a2-timings/summary.json `
     --credentials .private-eval/eval-credentials.json `
     --progress .private-eval/runs/a2-timings/progress.json `
     --answers-out .private-eval/runs/a2-timings/answers.json `
     --stage-export .private-eval/runs/a2-timings/stages.json `
     --verbose
   ```

3. Summarize (aggregates only):

   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   .venv\Scripts\python.exe .private-eval/a2_timing_summary.py .private-eval/runs/a2-timings/stages.json
   ```

   `Runs without stage_timings_ms` must be `0 of 10`. Otherwise the image
   is stale or the export is broken; stop and report. `scope_ms` must have
   n = 10.

## Docs

1. New `docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md`, exact text.
   Replace every `<...>` with the measured value or today's date in the
   form YYYY-MM-DD. `rg -n "<paste|<date|<n>" docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md`
   must print nothing before you commit.

   ````markdown
   ---
   title: Hybrid stage timings (answer-loss repair)
   owner: engineering-lead
   status: draft
   last-reviewed: <date>
   audience: engineering, reviewers
   ---

   # Hybrid stage timings (2026-09)

   Aggregate retrieve-stage durations for the answer-loss repair
   ([ADR-retrieved-answer-loss-repair.md](../adr/ADR-retrieved-answer-loss-repair.md),
   Fix 2 step 1). Field contract:
   [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md#stage-timings-and-rerank-sub-codes).
   The motivating misses are in
   [ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md](./ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md).
   This file holds aggregates only: no question text, answer text, chunk
   IDs, or document text.

   ## Method

   - Ten private answer-only questions (`a01` to `a10`) on the rebuilt
     laptop Compose `api` image, <date>. 10 s retrieve slice, 3 s rerank
     reserve, `rerank_v1`.
   - Source: the private stage export (`stages.json`), summarized by a
     private script. Values are integer milliseconds.
   - p50 is the lower median. p90 is nearest-rank
     (`sorted[min(n - 1, int(0.9 * n))]`), so with n = 10 it equals the
     maximum.
   - `rerank_call_ms` exists only when the rerank callback ran. A
     `rerank_timeout` without it is the remaining-slice gate; with it,
     the provider call ran out of time.
   - `post_channel_ms` is the per-run sum of `assemble_ms`,
     `temporal_load_ms`, and `pool_preload_ms`. It is the time between
     the end of the channels and the rerank gate's budget use.

   ```mermaid
   flowchart LR
     scope["scope_ms"] --> embed["embed_ms"]
     embed --> channels["channels_ms: dense, bm25, term in parallel"]
     channels --> assemble["assemble_ms and temporal_load_ms"]
     assemble --> preload["pool_preload_ms"]
     preload --> selection["selection_ms: gate, rerank_call_ms, MMR, parents"]
     selection --> locators["locator_reload_ms"]
   ```

   ## Results (after A2, before A3)

   <paste the table printed by the summary script>

   Rerank outcomes: <paste>. Schema-invalid sub-codes: <paste>.

   ## Reading

   <two to four sentences, numbers only: which stage takes most of the
   slice, how often the gate skipped rerank, and the post_channel_ms p90>

   ## Limits

   - Ten questions from one book on one laptop stack against hosted
     Supabase. With n = 10, p90 is the maximum.
   - Channel durations are measured inside each worker thread;
     `channels_ms` is the wall time of the parallel wait.
   - `scope_ms` covers scope resolution plus frozen-profile load.
   - `rerank_gate_remaining_ms` is measured before pool preload, which
     is exactly the value the gate compares.

   ## Verification

   ```powershell
   uv run python -m pytest tests/unit/test_hybrid_stage_timings.py -q
   ```
   ````

2. `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md`: insert this section
   directly before `## Claim hygiene (Packet 9 metrics)`, and set front
   matter `last-reviewed` to today:

   ```markdown
   ## Stage timings and rerank sub-codes

   `HybridBranchDiagnostics` carries two ID-free fields.
   `stage_timings_ms` maps stage names to non-negative integer
   milliseconds. Allowed keys are `HYBRID_STAGE_TIMING_KEYS` in
   `retrieval/profiles.py`: `scope_ms`, `embed_ms`, `channels_ms`,
   `channel_dense_ms`, `channel_bm25_ms`, `channel_term_ms`,
   `assemble_ms`, `temporal_load_ms`, `pool_preload_ms`,
   `rerank_gate_remaining_ms`, `rerank_call_ms`, `selection_ms`,
   `locator_reload_ms`, and `retrieve_total_ms`. A channel that timed out
   has no `channel_*_ms` key. `rerank_call_ms` exists only when the
   rerank callback ran, so a `rerank_timeout` without it means the
   remaining-slice gate skipped the call. `rerank_gate_remaining_ms` is
   the remaining slice that the gate compared with
   `RERANK_RESERVED_SECONDS`; it is measured before pool preload. Cache
   hits and fail-closed returns carry only `scope_ms`.

   `rerank_invalid_subcode` is `json`, `hash`, `length`, `duplicate`, or
   `unknown_id` when `rerank_fallback` is `rerank_schema_invalid` and the
   payload failed application validation (`RerankPayloadError`). It is
   empty otherwise, including when the provider text was not JSON (the
   gateway fails before a payload exists). The diagnostics builder drops
   unknown keys, negative values, and unknown sub-codes instead of
   failing the branch.

   `scripts/eval_ask_stage_export.py` writes both fields per run
   (`unknown` for older checkpoints). Its per-run
   `bm25_degraded_explicit` is `False` when `fallback_reason` is `none`
   or empty, and runs with `none` do not lower the aggregate flag.
   Measured values:
   [HYBRID_STAGE_TIMINGS_2026-09.md](../evaluation/HYBRID_STAGE_TIMINGS_2026-09.md).
   ```

3. `docs/README.md`: set front matter `last-reviewed` to today. Set the
   fourth column of the `retrieval/HYBRID_RETRIEVAL_CONTRACT.md` row to
   today. Add this row directly after the
   `evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md` row:

   ```markdown
   | [evaluation/HYBRID_STAGE_TIMINGS_2026-09.md](./evaluation/HYBRID_STAGE_TIMINGS_2026-09.md) | engineering-lead | draft | <date> | eng, reviewers |
   ```

Then run `uv run python scripts/check.py --tier docs` (about 6 minutes).
It must exit 0.

## Done when

- [ ] `RerankPayloadError`, `RerankUsage.invalid_subcode`, both profile
      allow-lists, `timed_rerank`, `durations_ms`, and the retriever,
      adapter, diagnostics, builder, and export edits are made exactly
      as above.
- [ ] `tests/unit/test_hybrid_stage_timings.py` passes 8 tests. The
      listed existing test files pass with only the one R12 assertion
      changed.
- [ ] `retriever.py` is below 600 lines; `test_architecture_budgets.py` passes.
- [ ] `unit`, `lint`, `types`, `format`, and `docs` tiers exit 0.
- [ ] Rebuilt image, probe prints `A1 present` and `A2 present`.
- [ ] The a01..a10 run exported `stage_timings_ms` on 10 of 10 runs.
- [ ] The timings doc has the measured table, outcome counts, and sub-code
      counts, with no placeholders; the contract section and README row
      exist.
- [ ] Commit pushed; `gh pr checks --watch --fail-fast` exits 0.

## Commit

Follow **At the end of every code packet (A1 to A9)** in the rules file.
Message:

```text
feat(retrieval): record Hybrid stage timings and rerank validation sub-codes (A2)
```

Files to `git add`, one by one (16 paths):

```text
packages/core/src/smart_rag_core/retrieval/profiles.py
packages/core/src/smart_rag_core/retrieval/rerank.py
packages/core/src/smart_rag_core/retrieval/reranker.py
packages/core/src/smart_rag_core/retrieval/hybrid.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/budget.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/types.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py
apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py
packages/core/src/smart_rag_core/query_routing/models/results.py
packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py
scripts/eval_ask_stage_export.py
tests/unit/test_hybrid_stage_timings.py
tests/unit/test_hybrid_branch_diagnostics.py
docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md
docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md
docs/README.md
```

## Do not

- Do not change the slice, the 3 s reserve, the pool, pins, the prompt,
  the schema, or any profile. A3 to A5 do that.
- Do not add a retry, a second rerank call, or a repair call.
- Do not change the gateway's invalid-JSON path or its usage accounting.
- Do not put chunk IDs, text, or free-form strings in `stage_timings_ms`
  or `rerank_invalid_subcode`; only allow-listed names and integers.
- Do not add the new export fields to `REQUIRED_FIELDS`.
- Do not put per-question timings or IDs in the tracked doc; aggregates only.
- Do not commit `.private-eval/` files.
