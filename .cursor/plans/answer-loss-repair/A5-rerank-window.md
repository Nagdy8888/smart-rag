# A5: protect the rerank window (channel-phase deadline)

## Goal

Channels finish early enough that assembly, temporal load, and pool preload still
leave `RERANK_RESERVED_SECONDS` (3.0) for the rerank call (ADR Fix 2 step 4). The
channel phase gets:

```text
channel_deadline = min(slice, max(CHANNEL_MIN_SECONDS,
                                  slice - RERANK_RESERVED_SECONDS - CHANNEL_PHASE_RESERVE_SECONDS))
```

A channel still running at that point is handled exactly like today's channel timeout
(`run_channels_parallel` returns it in `timed_out`). Nothing else changes: the slice,
the 25 s Hybrid deadline, and the 50 s run deadline stay.

Probe symbol: `smart_rag_core.retrieval.profiles.CHANNEL_PHASE_RESERVE_SECONDS`.

## Depends on

A4 committed, and the A2 measurements in
`docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md` ("## Results (after A2, before A3)").

## Step 0: STOP GATE (do this before editing anything)

Open the plan index `.cursor/plans/answer_loss_repair_9c24e1a0.plan.md` and find
decision **D5**. On 2026-09-24 the user approved D5 **as a rule**:
`CHANNEL_PHASE_RESERVE_SECONDS` is the value computed in item 2 below from the A2
measurements, and `CHANNEL_MIN_SECONDS` is 2.0, unless item 5 below triggers. If
D5 in the index does not say "approved as a rule" (or records a number), edit no
file and stop.

Compute and report these items (they are the evidence for the value):

1. The A2 rows for `channels_ms`, `channel_dense_ms`, `assemble_ms`,
   `temporal_load_ms`, `pool_preload_ms`, and `post_channel_ms`, copied from the
   A2 results table (n, p50, p90, max).
2. The candidate value: p90 of `post_channel_ms` (per-run
   `assemble_ms + temporal_load_ms + pool_preload_ms`), rounded up to the next 0.5 s
   (`ceil(p90_ms / 500) * 0.5`).
3. The resulting deadline at the full slice: `max(2.0, 10.0 - 3.0 - value)` seconds
   (`RETRIEVAL_SLICE_SECONDS` 10, `RERANK_RESERVED_SECONDS` 3.0). Note that the
   branch clamp can hand retrieve less than 10 s.
4. p90 of `channels_ms` and p90 of `channel_dense_ms` from the same table.
5. If `deadline * 1000` is below p90 `channel_dense_ms`, say so explicitly: the cut
   would time out dense on more than 10% of runs. In that case stop even if D5 is
   approved, and report.

If item 5 did not trigger, edit the D5 **Answer** line in the plan index to
`approved as a rule; computed value <value> s from A2 (p90 post_channel_ms <p90> ms), CHANNEL_MIN_SECONDS 2.0`
and continue. Below, `<D5_RESERVE>` is the only placeholder; replace it with that
computed value (for example `1.5`). Nothing else in this packet is a placeholder.
Add the plan index to this packet's `git add` list.

## Read first

**R1** `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py`
lines 106-109 (the slice retrieve receives):

```python
        deadline_seconds = max(
            2.0, min(remaining - ANSWER_STAGE_MIN_SECONDS, RETRIEVAL_SLICE_SECONDS)
        )
```

**R2** `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py`, the
channel call after A2 (match by content):

```python
        channel_started = time.perf_counter()
        channel_ms: dict[str, int] = {}
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
            durations_ms=channel_ms,
        )
```

`remaining = remaining_slice_seconds(slice_seconds=slice_seconds, slice_started=channel_started)`
runs after assembly and before pool preload. It imports `remaining_slice_seconds`
(and, after A2, `elapsed_ms`) from the assemble module.

**R3** `packages/core/src/smart_rag_core/retrieval/context.py` reserve gate:

```python
    from smart_rag_core.retrieval.profiles import RERANK_RESERVED_SECONDS

    if remaining_deadline_seconds < RERANK_RESERVED_SECONDS:
```

**R4** `run_channels_parallel` (in `smart_rag_core.retrieval.hybrid`, after A2) waits
`deadline_seconds`, cancels pending futures, and returns
`(completed, timed_out, bool(timed_out))`. A late channel is therefore already the
"today's timeout" path; A5 only shortens the wait.

**R5** The assemble module (`packages/core/src/smart_rag_core/retrieval/hybrid_run/assemble.py`;
confirm with Glob `**/hybrid_run/assemble.py`, stop if absent). Its profiles import is
at lines 20-23:

```python
from smart_rag_core.retrieval.profiles import (
    MAX_NORMALIZED_QUERY_CHARS,
    RetrievalFallbackReason,
)
```

`fused_first_evidence_ms` is the last function in the file.

**R6** `.private-eval/latency_probe.py` (private, untracked) `TOTAL` block:

```python
    if totals:
        values = sorted(t for _, t, _ in totals)
        print(
            "TOTAL", len(values), f"{statistics.mean(values):.1f}",
            f"{statistics.median(values):.1f}", f"{max(values):.1f}",
        )
```

## Steps

### 1. `profiles.py`

In `packages/core/src/smart_rag_core/retrieval/profiles.py`, directly after the
`RERANK_RESERVED_SECONDS` assignment (and its docstring line, if it has one) insert:

```python
CHANNEL_PHASE_RESERVE_SECONDS = <D5_RESERVE>
"""Post-channel work (assemble, temporal load, pool preload) kept free before the
rerank reserve. p90 of A2 ``post_channel_ms`` rounded up to 0.5 s; approved in D5."""
CHANNEL_MIN_SECONDS = 2.0
"""Floor for the channel-phase deadline. Equals the Hybrid branch slice floor."""
```

If `RERANK_RESERVED_SECONDS` is not defined in `profiles.py`, stop (rule 2).

### 2. Assemble module: `channel_phase_deadline_seconds`

a) Replace the R5 import with:

```python
from smart_rag_core.retrieval.profiles import (
    CHANNEL_MIN_SECONDS,
    CHANNEL_PHASE_RESERVE_SECONDS,
    MAX_NORMALIZED_QUERY_CHARS,
    RERANK_RESERVED_SECONDS,
    RetrievalFallbackReason,
)
```

b) Append at the end of the file (two blank lines before it):

```python
def channel_phase_deadline_seconds(slice_seconds: float) -> float:
    """Return how long channels may run inside one retrieve slice.

    The channel phase ends early enough that post-channel work
    (``CHANNEL_PHASE_RESERVE_SECONDS``) plus the rerank reserve
    (``RERANK_RESERVED_SECONDS``) still fit in the slice. The result is at
    least ``CHANNEL_MIN_SECONDS`` and never more than the slice itself.

    Args:
        slice_seconds: Retrieve slice in seconds (already clamped by the
            Hybrid branch).

    Returns:
        Channel wait in seconds. A channel still running then is reported as
        timed out by ``run_channels_parallel``.
    """

    reserved = RERANK_RESERVED_SECONDS + CHANNEL_PHASE_RESERVE_SECONDS
    return min(slice_seconds, max(CHANNEL_MIN_SECONDS, slice_seconds - reserved))
```

### 3. `retriever.py`

a) Add `channel_phase_deadline_seconds,` to the assemble import list, after
`compute_principal_scope_hash,` (ruff `--select I --fix` will reorder).

b) In the R2 block replace `            deadline_seconds=slice_seconds,` with
`            deadline_seconds=channel_phase_deadline_seconds(slice_seconds),`.

c) In the class docstring's `Deadline:` section, add as its last line (same indent as
the section text):
`Channels wait only ``channel_phase_deadline_seconds(slice)`` so rerank keeps its reserve.`

Then `(Get-Content packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py).Count`
must print a number below 600.

### 4. Private `latency_probe.py` p90 (never `git add` it)

Replace the R6 block with:

```python
    if totals:
        values = sorted(t for _, t, _ in totals)
        p90 = values[min(len(values) - 1, int(0.9 * len(values)))]
        print(
            "TOTAL", len(values), f"{statistics.mean(values):.1f}",
            f"{statistics.median(values):.1f}", f"{max(values):.1f}",
            f"p90={p90:.1f}",
        )
```

## Tests

Create `tests/unit/test_channel_phase_window.py`:

```python
"""Channel-phase deadline keeps the rerank reserve (answer-loss repair A5)."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.hybrid_run.assemble import channel_phase_deadline_seconds
from smart_rag_core.retrieval.profiles import (
    CHANNEL_MIN_SECONDS,
    CHANNEL_PHASE_RESERVE_SECONDS,
    RERANK_RESERVED_SECONDS,
    RETRIEVAL_SLICE_SECONDS,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole

_Triple = tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]


def _candidate(rank: int) -> RetrievalCandidate:
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


def test_channel_deadline_subtracts_both_reserves() -> None:
    """At the full slice the channel phase ends before both reserves."""

    expected = max(
        CHANNEL_MIN_SECONDS,
        RETRIEVAL_SLICE_SECONDS - RERANK_RESERVED_SECONDS - CHANNEL_PHASE_RESERVE_SECONDS,
    )
    assert channel_phase_deadline_seconds(RETRIEVAL_SLICE_SECONDS) == expected
    assert CHANNEL_PHASE_RESERVE_SECONDS > 0
    assert expected < RETRIEVAL_SLICE_SECONDS - RERANK_RESERVED_SECONDS


def test_channel_deadline_floor_and_slice_cap() -> None:
    """Short slices get the floor, but never more than the slice itself."""

    assert channel_phase_deadline_seconds(4.0) == CHANNEL_MIN_SECONDS
    assert channel_phase_deadline_seconds(1.0) == 1.0
    assert channel_phase_deadline_seconds(0.0) == 0.0


def test_late_channel_times_out_and_rerank_keeps_its_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake clock jumps by the channel wait; rerank still gets 3 seconds."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }
    now = [1000.0]
    waits: list[float] = []
    remaining_seen: list[float] = []

    def clock() -> float:
        """Return the fake monotonic time.

        Returns:
            Seconds.
        """

        return now[0]

    def fake_parallel(
        jobs: dict[str, Callable[[], object]],
        *,
        deadline_seconds: float,
        durations_ms: dict[str, int] | None = None,
    ) -> tuple[dict[str, object], tuple[str, ...], bool]:
        """Finish dense, let BM25 run past the channel deadline.

        Args:
            jobs: Channel jobs.
            deadline_seconds: Channel wait under test.
            durations_ms: Unused sink.

        Returns:
            Dense completed, BM25 timed out, deadline exhausted.
        """

        del durations_ms
        waits.append(deadline_seconds)
        now[0] += deadline_seconds
        return {"dense": jobs["dense"]()}, ("bm25",), True

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows for the requested IDs.

        Args:
            ids: Requested chunk IDs.

        Returns:
            Matching rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def rerank(_query: str, pool: tuple[RerankPassage, ...], remaining: float) -> _Triple:
        """Record the remaining seconds and return identity rankings.

        Args:
            _query: Unused.
            pool: Authorized pool.
            remaining: Remaining slice seconds at the rerank call.

        Returns:
            Identity rankings with ``none``.
        """

        remaining_seen.append(remaining)
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

    monkeypatch.setattr(time, "perf_counter", clock)
    monkeypatch.setattr(
        "smart_rag_core.retrieval.hybrid_run.retriever.run_channels_parallel",
        fake_parallel,
    )
    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(MockEmbeddingAdapter(fixture_id="hybrid-run")),
        load_context=load,
        rerank=rerank,
    )
    result = retriever.retrieve(
        query="annual leave policy",
        caller=CallerContext(
            user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
        ),
        deadline_seconds=RETRIEVAL_SLICE_SECONDS,
        channel_jobs={
            "dense": lambda: (first, second),
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=()),
        },
    )
    assert waits == [channel_phase_deadline_seconds(RETRIEVAL_SLICE_SECONDS)]
    assert result.deadline_exhausted is True
    assert remaining_seen and remaining_seen[0] >= RERANK_RESERVED_SECONDS
    assert result.rerank_fallback == RerankFallbackReason.NONE.value
```

If the last test fails because `remaining_seen` is empty or below 3.0, check whether a
module calls `perf_counter` imported by name (so the fake clock does not reach it).
Stop and report; do not change production code to suit the test.

## Commands (run in this order; all must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/retrieval/profiles.py packages/core/src/smart_rag_core/retrieval/hybrid_run/assemble.py packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py tests/unit/test_channel_phase_window.py
uv run python -m ruff check --select I --fix packages/core/src/smart_rag_core/retrieval tests/unit/test_channel_phase_window.py
uv run python -m pytest tests/unit/test_channel_phase_window.py tests/unit/test_hybrid_stage_timings.py tests/unit/test_hybrid_run.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier contract
uv run python scripts/check.py --tier docs
```

## Live proof (about 45 minutes including the image build)

1. Rebuild and probe exactly as 00-rules says; probe entry `'A5'` must print `present`.
2. Run the 00-rules live-run template on the full gold `.private-eval/answer50-v1.json`
   with output directory `.private-eval/runs/a5-window/`.
3. Run `.private-eval/a2_timing_summary.py` on this run's stage export exactly as in
   A2's live step. Keep its table and its "Rerank outcomes:" counts.
4. Run-total p90:

   ```powershell
   $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH=".private-eval"
   .venv\Scripts\python.exe .private-eval/latency_probe.py stages <this run's --answers-out file>
   ```

   Read `p90=` on the `TOTAL` line. The script reads `OPERATOR_SUPABASE_DB_URL` from
   `.env`/`.env.compose`; never print it.

Acceptance: rerank completed (`rerank_fallback` `none`, including partial rankings)
on at least 45 of 50, and run-total p90 at most 45 s. If p90 > 45 s, or completed is
below 45, report the numbers and stop. Do not commit.

## Docs

1. `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` (front matter `last-reviewed`: today).
   After the v3 paragraph that A4 added to "## Long-document runtime profile (P06-62)"
   (it ends with `[ADR-retrieved-answer-loss-repair.md](../adr/ADR-retrieved-answer-loss-repair.md).`),
   insert a blank line and (fill the two numbers from D5):

   ```markdown
   Channel-phase window (answer-loss repair A5): channels wait only
   `min(slice, max(CHANNEL_MIN_SECONDS, slice - RERANK_RESERVED_SECONDS - CHANNEL_PHASE_RESERVE_SECONDS))`
   with `CHANNEL_MIN_SECONDS` 2.0 and `CHANNEL_PHASE_RESERVE_SECONDS` <D5_RESERVE>
   (p90 of measured post-channel work, approved as decision D5). A channel still
   running then is a channel timeout, as before. The slice, the 25 s Hybrid
   deadline, and the 50 s run deadline are unchanged. Cutting a channel early can
   cost recall; see [HYBRID_STAGE_TIMINGS_2026-09.md](../evaluation/HYBRID_STAGE_TIMINGS_2026-09.md).
   ```

2. `docs/adr/ADR-ask-evidence-budget-repair.md` (front matter `last-reviewed`: today).
   Before `## Alternatives rejected` insert:

   ```markdown
   ## Amendment (answer-loss repair A5)

   The retrieve slice and `RERANK_RESERVED_SECONDS` (3) stay. Inside the
   slice, channels now stop at
   `max(CHANNEL_MIN_SECONDS, slice - RERANK_RESERVED_SECONDS - CHANNEL_PHASE_RESERVE_SECONDS)`
   (capped at the slice), so assembly, temporal load, and pool preload no
   longer consume the rerank reserve. Values: `CHANNEL_MIN_SECONDS` 2.0,
   `CHANNEL_PHASE_RESERVE_SECONDS` <D5_RESERVE>. Rollback: set
   `CHANNEL_PHASE_RESERVE_SECONDS` to 0 and pass the whole slice to channels.
   See [ADR-retrieved-answer-loss-repair.md](./ADR-retrieved-answer-loss-repair.md) Fix 2 step 4.
   ```

3. `docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md` (front matter `last-reviewed`:
   today). After the "## Results (after A2, before A3)" section, add
   `## Results after A5 (full 50)` with: the `a2_timing_summary.py` table for
   `.private-eval/runs/a5-window/` (same columns), the "Rerank outcomes:" counts, and
   one line `Run-total p90: <n> s (latency_probe TOTAL p90).` Numbers, key names, and
   counts only; no question IDs with text, no answers.
4. `docs/README.md`: front matter `last-reviewed` today; fourth column today in the rows
   for `retrieval/HYBRID_RETRIEVAL_CONTRACT.md`, `adr/ADR-ask-evidence-budget-repair.md`,
   and `evaluation/HYBRID_STAGE_TIMINGS_2026-09.md`.

## Done when

- [ ] D5 is recorded as approved with the numbers used; no placeholder remains
      (`rg "<D5_RESERVE>" packages docs tests` prints nothing).
- [ ] The channel wait uses `channel_phase_deadline_seconds`; tests prove the formula,
      the floor and cap, and a late channel with rerank still getting at least 3.0 s.
- [ ] `retriever.py` below 600 lines; all commands exit 0.
- [ ] Live: completed on at least 45/50 and run-total p90 at most 45 s, recorded in the
      timings doc.

## Commit

Follow 00-rules "At the end of every code packet (A1 to A9)". Message:

```text
feat(retrieval): protect the rerank window with a channel-phase deadline (A5)

Channels wait max(CHANNEL_MIN_SECONDS, slice - RERANK_RESERVED_SECONDS -
CHANNEL_PHASE_RESERVE_SECONDS), capped at the slice. A late channel is a normal
channel timeout. Values approved as decision D5 from the A2 measurements.
Full-50 rerun: rerank completed on <n>/50, run-total p90 <n> s.
```

Files to `git add`, one by one (8 paths):

```text
packages/core/src/smart_rag_core/retrieval/profiles.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/assemble.py
packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py
tests/unit/test_channel_phase_window.py
docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md
docs/adr/ADR-ask-evidence-budget-repair.md
docs/evaluation/HYBRID_STAGE_TIMINGS_2026-09.md
docs/README.md
```

If `git status --short` shows any other changed file, stop and explain it before committing.

## Do not

- Do not start without D5 approval, and do not invent or tune the reserve value.
- Do not change `RETRIEVAL_SLICE_SECONDS`, `RERANK_RESERVED_SECONDS`,
  `HYBRID_DEADLINE_SECONDS`, the branch clamp, or the run deadline.
- Do not add retries or a second rerank call; do not change rerank, pool, or profile code.
- Do not `git add` anything under `.private-eval/`. No private text in tracked files;
  never print `OPERATOR_SUPABASE_DB_URL`.
- No SQL migrations. Never `git add -A`, `git add .`, `--no-verify`, `--force`, `--admin`.
