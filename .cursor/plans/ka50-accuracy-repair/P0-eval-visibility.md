# P0 - Eval visibility: name the real drop stage

## Goal

Make `scripts/run_company_ask.py --verbose` distinguish three different
failures that today all print `drop=retrieval_miss`:

| New bucket | Meaning |
| --- | --- |
| `retrieval_miss` | gold page absent from `fused_ids` (dense+BM25+term union after RRF) |
| `rerank_pool_drop` | gold page in `fused_ids` but absent from the rerank pool |
| `selection_drop` | gold page in the rerank pool but absent from final evidence |

To do that, the rerank pool membership must be persisted on the Hybrid
branch diagnostics and exported. The pool already exists in memory as
`HybridRunResult.rerank_order` (`retriever.py` line ~507: it is
`selection.rerank_order`, which `context.py` sets to the pool's chunk ids
in every branch). It is just not copied into `HybridBranchDiagnostics`.

No product behavior changes in this packet. Only diagnostics and the eval
script.

## Read first

- `packages/core/src/smart_rag_core/query_routing/models/results.py`
  class `HybridBranchDiagnostics` (fields `dense_ids`, `bm25_ids`,
  `term_ids`, `fused_ids`, `selected_ids`, the `field_validator` list).
- `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py`
  function `hybrid_diagnostics_from_outcome`.
- `scripts/eval_ask_stage_export.py` constants `REQUIRED_FIELDS` and
  function `stage_record`.
- `scripts/run_company_ask.py` functions `classify_ask_drop`,
  `format_diagnosis_line`, `_print_verbose_diagnosis`,
  `_checkpoint_diagnosis`, `_hybrid_coverage`, `_page_in_fusion`.
- `tests/unit/test_hybrid_branch_diagnostics.py` and
  `tests/unit/test_company_ask_verbose_log.py`.
- `.private-eval/page_in_pool.py` (private helper; shows the
  chunk-id -> page_number SQL you will port).

## Steps

### 1. Add `rerank_pool_ids` to `HybridBranchDiagnostics`

In `results.py`, inside `HybridBranchDiagnostics`:

- Docstring `Attributes:` add
  `rerank_pool_ids: Chunk IDs that entered the one-shot rerank pool, in pool order, capped at 100.`
- After `selected_ids` add (exact code):

```python
    rerank_pool_ids: tuple[str, ...] = Field(default=(), max_length=100)
```

- Add `"rerank_pool_ids"` to the `@field_validator(...)` name list that
  already contains `"dense_ids"`, `"bm25_ids"`, `"term_ids"`,
  `"fused_ids"`, `"selected_ids"`.

### 2. Copy the pool into the diagnostics

In `branch_channels/hybrid.py` `hybrid_diagnostics_from_outcome`, after
the `selected_ids=` argument add (exact code):

```python
        rerank_pool_ids=_uuid_ids(getattr(outcome, "rerank_order", ()), 100)
        if outcome is not None
        else (),
```

### 3. Export it

In `scripts/eval_ask_stage_export.py`:

- Add `"rerank_pool_ids",` to `REQUIRED_FIELDS` right after
  `"selected_ids",`.
- In `stage_record`, in the returned dict, after the `"selected_ids"` entry
  add:

```python
        "rerank_pool_ids": _id_list_or_unknown(diagnostics.get("rerank_pool_ids")),
```

### 4. Map chunk ids to pages in the eval runner

In `scripts/run_company_ask.py`:

a. Add a helper next to `_hybrid_coverage` (shape):

```python
def _hybrid_diagnostic_ids(payload: object, field: str) -> tuple[str, ...]:
    """Return one ID list from the Hybrid branch's persisted diagnostics.

    Args:
        payload: Deserialized ``branch_results`` channel.
        field: ``fused_ids``, ``rerank_pool_ids``, or ``selected_ids``.

    Returns:
        String chunk ids, or empty when the branch or field is absent.
    """

    if not isinstance(payload, list):
        return ()
    for item in cast(list[object], payload):
        mapping = _json_mapping(item)
        if mapping.get("kind") != "hybrid" and mapping.get("family") not in {
            "hybrid",
            "Hybrid",
        }:
            continue
        diagnostics = _json_mapping(mapping.get("hybrid_diagnostics"))
        raw = diagnostics.get(field)
        if isinstance(raw, list):
            return tuple(str(value) for value in cast(list[object], raw))
        return ()
    return ()
```

b. Add a helper that maps chunk ids to page numbers on the operator
connection (shape; the SQL is the same one `.private-eval/page_in_pool.py`
uses):

```python
def _pages_for_chunk_ids(
    connection: psycopg.Connection,
    chunk_ids: Sequence[str],
) -> dict[str, int]:
    """Map chunk ids to ``page_number`` through the operator connection.

    Args:
        connection: Operator database connection.
        chunk_ids: Chunk id strings from stage diagnostics.

    Returns:
        Chunk id to page for rows that carry an integer page.
    """

    unique = [item for item in dict.fromkeys(chunk_ids) if item]
    if not unique:
        return {}
    rows = connection.execute(
        """
        SELECT id::text, page_number
        FROM app.document_chunks
        WHERE id = ANY(%s::uuid[])
        """,
        (unique,),
    ).fetchall()
    return {
        str(row[0]): int(row[1])
        for row in rows
        if isinstance(row[1], int) and not isinstance(row[1], bool)
    }
```

If `_checkpoint_diagnosis` runs `SET ROLE` anywhere, keep that behavior;
otherwise do not add one (the operator DSN already reads `app` tables).

c. In `_checkpoint_diagnosis`, inside the per-question loop after
`branches = _load_checkpoint_channel(..., "branch_results")`:

```python
                fused_ids = _hybrid_diagnostic_ids(branches, "fused_ids")
                pool_ids = _hybrid_diagnostic_ids(branches, "rerank_pool_ids")
                page_of = _pages_for_chunk_ids(connection, (*fused_ids, *pool_ids))
                found[question_id] = {
                    "pages": _fusion_pages(fusion),
                    "failures": _citation_failures(verification),
                    "coverage": _hybrid_coverage(branches),
                    "fused_pages": tuple(
                        page_of[item] for item in fused_ids if item in page_of
                    ),
                    "pool_pages": tuple(
                        page_of[item] for item in pool_ids if item in page_of
                    ),
                }
```

Replace the existing `found[question_id] = {...}` with this block.

d. Extend `classify_ask_drop` (exact code for the body; keep the docstring
and update its `Returns` list with the two new buckets):

```python
def classify_ask_drop(
    *,
    outcome: str,
    grounded: bool,
    gold_page_in_fusion: bool | None,
    citation_failures: tuple[str, ...],
    gold_page_in_fused: bool | None = None,
    gold_page_in_rerank_pool: bool | None = None,
) -> str:
    if outcome in {"strict_phrase", "fact_covered"} and grounded:
        return "pass"
    if outcome == "error":
        return "error"
    if outcome == "deadline":
        return "deadline"
    if outcome == "empty_retrieval" or gold_page_in_fused is False:
        return "retrieval_miss"
    if gold_page_in_fused and gold_page_in_rerank_pool is False:
        return "rerank_pool_drop"
    if gold_page_in_rerank_pool and gold_page_in_fusion is False:
        return "selection_drop"
    if gold_page_in_fused is None and gold_page_in_fusion is False:
        return "retrieval_miss"
    if citation_failures or outcome == "verifier_refusal_after_fusion":
        return "citation" if citation_failures else "verifier_refusal"
    if outcome == "wrong_phrasing":
        return "phrasing"
    if outcome == "partial":
        return "partial"
    return outcome
```

The last `retrieval_miss` line keeps today's behavior when the stage
export is unavailable, so `test_missing_gold_page_is_a_retrieval_miss`
keeps passing unchanged.

e. Thread the flags through `format_diagnosis_line` (add keyword params
`gold_page_in_fused: bool | None = None` and
`gold_page_in_rerank_pool: bool | None = None`, pass them to
`classify_ask_drop`, and append
`f"in_fused={_yes_no(gold_page_in_fused)} in_pool={_yes_no(gold_page_in_rerank_pool)} "`
to the DIAG line before `failures=`). Add a tiny `_yes_no(value: bool | None) -> str`
returning `"unknown"`, `"yes"`, or `"no"`, and use it for the existing
`in_fusion` token too.

f. In `_print_verbose_diagnosis` compute and pass:

```python
        in_fused = _page_in_fusion(gold_page, checkpoint.get("fused_pages"))
        in_pool = _page_in_fusion(gold_page, checkpoint.get("pool_pages"))
```

`_page_in_fusion` already returns `None` when the value is not a tuple.

## Tests

### `tests/unit/test_hybrid_branch_diagnostics.py`

- In the test that builds a full `HybridBranchDiagnostics`
  (`test_hybrid_diagnostics_serialization_is_deterministic` or the
  fixture it uses), add `rerank_pool_ids=(<uuid str>,)` and assert it
  round-trips.
- In `test_hybrid_diagnostics_enforce_id_caps`, add a case: 101
  `rerank_pool_ids` raises `ValidationError`.
- In `test_hybrid_diagnostics_from_none_fallback_persist` (or a new test
  `test_hybrid_diagnostics_copy_rerank_order_as_pool`), give the outcome
  stub `rerank_order=(uuid4(), uuid4())` and assert
  `diagnostics.rerank_pool_ids == tuple(str(x) for x in rerank_order)`.
- In `test_stage_record_measures_accounting_and_bm25_explicit`, assert
  `record["rerank_pool_ids"]` is a list when diagnostics carry it and
  `"unknown"` when `diagnostics is None`.

### `tests/unit/test_company_ask_verbose_log.py`

Add (exact code):

```python
def test_cap_drop_is_named_rerank_pool_drop() -> None:
    """A gold page inside fused ids but outside the pool is a pool drop."""

    from scripts.run_company_ask import classify_ask_drop

    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=False,
        )
        == "rerank_pool_drop"
    )
    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=True,
        )
        == "selection_drop"
    )
    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=False,
            gold_page_in_rerank_pool=None,
        )
        == "retrieval_miss"
    )
```

Check how the existing tests in that file import `classify_ask_drop` and
use the same import style.

## Docs

- `docs/development/phase-06/p06-68-stage-diagnostics-2026-09-21.md`:
  add `rerank_pool_ids` to the field list with one sentence on its source
  (`HybridRunResult.rerank_order`).
- `docs/evaluation/KNOWN_ANSWER_50_ROOT_CAUSES_2026-09-22.md`: under
  Issue 2 (coverage/eval blindness) add a line that the eval now emits
  `rerank_pool_drop` / `selection_drop` and link to this plan file.

## Commands

```powershell
uv run python -m pytest tests/unit/test_hybrid_branch_diagnostics.py tests/unit/test_company_ask_verbose_log.py -q
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier docs
```

Optional live proof (about 4 minutes): first rebuild the `api` image
(`00-rules-and-commands.md`, "Docker rebuild before any live run"; the
probe must print `P0 present`). Then write a 3-question gold subset to
`.private-eval/ka50-subset-p0.json` containing `k11`, `k28`, `k32` (all
three are cap drops), run the KA50 command from `00-rules-and-commands.md`
with `--gold .private-eval/ka50-subset-p0.json` and fresh `--out`,
`--answers-out`, `--progress`, `--stage-export` paths under
`.private-eval/runs/p0/`. Expect `drop=rerank_pool_drop` on all three and
`rerank_pool_ids` present in the stage export.

## Done when

- [ ] `HybridBranchDiagnostics` has `rerank_pool_ids` with the same
      validator and a 100 cap; `extra="forbid"` unchanged.
- [ ] `hybrid_diagnostics_from_outcome` copies `rerank_order` into it.
- [ ] `stage_record` returns `rerank_pool_ids` and `REQUIRED_FIELDS`
      lists it.
- [ ] `classify_ask_drop` returns `rerank_pool_drop` and `selection_drop`
      per the test above; existing verbose-log tests still pass unchanged.
- [ ] DIAG line prints `in_fused=` and `in_pool=`.
- [ ] Lint, types, docs tiers pass.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
fix(eval): export rerank_pool_ids and split retrieval_miss into pool/selection drops (P0)
```

## Do not

- Do not change `select_hybrid_context`, `build_rerank_pool`, or any
  profile in this packet.
- Do not print chunk text, gold phrases, or answer text in DIAG lines.
