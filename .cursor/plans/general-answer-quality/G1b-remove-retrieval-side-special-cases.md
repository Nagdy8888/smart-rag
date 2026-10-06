# G1b - Remove question-specific retrieval promotions and seed terms

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.

**Depends on:** G1a committed, pushed, green, and kept by its stop rule.
**Live run:** yes (dev40). **Target:** hygiene. The gold-literal guard
must exit 0 (no `--report-only`). **Stop rule:** revert if dev40 strict
passes drop by more than 3 against the G1a run, or if
`2_retrieval + 3_fusion_pool + 4_rerank_select` together grow by more
than 3 facts.

## Goal

`retrieval/rerank.py` and `retrieval/context.py` pin passages into the
final evidence with regexes built from earlier gold answers ("expose
mode", "ADAS", chunking window, tool description, host literal, IDE
product, protocol, listed literals), and `hybrid_seed_terms` appends
answer-side words to BM25 seeds. Delete all of it. Keep two generic
promotions: the passage holding `def <name>(` for a name the user typed,
and the passage holding a `Table N-M` caption the user typed. Seeds may
only contain identifiers that literally appear in the query.

## Read first (confirm each exists)

- `packages/core/src/smart_rag_core/retrieval/context.py` lines 12-36
  (the `from smart_rag_core.retrieval.rerank import (` block), lines
  46-104 (`def _promote_query_anchor_passages(`), and the fused-reload
  block near line 174
  (`if not literal_anchor_ask(query) or not fused:` and
  `if literal_gold_already_loaded(query, passages):`).
- `packages/core/src/smart_rag_core/retrieval/rerank.py`:
  `_CODE_DEF_ASK = re.compile(` (its alternatives include
  `r"|\b[A-Z][A-Za-z0-9]*(?:Config|State|OpenAI)\s*\("`),
  `_PASCAL_TYPE_FROM_QUERY = re.compile(` (two alternatives),
  `_CODE_ID_STOP = frozenset(`, `_PASCAL_TYPE_STOP = frozenset(`,
  `_CONSTRUCTOR_KWARG_FROM_QUERY`, `def named_pascal_type_ids(`,
  `def named_code_definition_ids(` (with a `wiring = wiring_code_ask(query)`
  block and a hard-coded name set), `def code_definition_gold_pattern(`,
  `def wiring_code_gold_pattern(`, `def constructor_code_gold_pattern(`,
  `def class_def_code_gold_pattern(`, `def listed_literal_groups(`,
  `def hybrid_seed_terms(`, `def named_table_captions(`,
  `def literal_anchor_ask(`, `def literal_gold_already_loaded(`,
  `def promote_named_code_definition_passages(`,
  `def promote_named_table_passages(`, and the ten other
  `def promote_*_passages(` functions.
- Callers of `hybrid_seed_terms`:
  `packages/core/src/smart_rag_core/retrieval/hybrid_run/jobs.py` lines
  ~142-144 and ~230-234, and
  `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py`
  line ~355. They stay unchanged.
- `tests/unit/test_hybrid_rerank.py` lines ~800-990 (tests importing
  `promote_helper_naming_passages`, `promote_tool_description_passages`,
  `promote_chunking_window_passages`).

## Step 1 - `context.py`

Replace the `from smart_rag_core.retrieval.rerank import (` block with
exactly:

```python
from smart_rag_core.retrieval.rerank import (
    ContextSelection,
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    apply_mmr,
    build_rerank_pool,
    literal_anchor_ask,
    literal_gold_already_loaded,
    promote_named_code_definition_passages,
    promote_named_table_passages,
    should_skip_trivial_exact,
    trim_token_budget,
)
```

If the original block imports a name not in this list and not in the
deleted list of Step 2, keep that name (report it).

Replace the whole `_promote_query_anchor_passages` function with exactly:

```python
def _promote_query_anchor_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
    fused: tuple[RerankPassage, ...] | None = None,
) -> tuple[RerankPassage, ...]:
    """Pin the code-definition or table-caption passage the query names.

    Only identifiers and ``Table N-M`` captions typed in the query can pin a
    passage, so the promotion works the same way for any document.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.
        fused: Optional full fused passage list. When set, a named block may
            be promoted from a fused chunk that missed the rerank pool.

    Returns:
        Trimmed passages after at most two additive promotions.
    """

    search = fused if fused is not None else pool
    promoted = promote_named_code_definition_passages(
        trimmed, query=query, pool=search, limit=limit
    )
    return promote_named_table_passages(
        promoted, query=query, pool=search, limit=limit
    )
```

Leave the fused-reload block near line 174 as it is; its two helpers are
simplified in Step 3.

## Step 2 - Delete question-specific rerank functions

In `packages/core/src/smart_rag_core/retrieval/rerank.py` delete these
whole functions:

```text
promote_helper_naming_passages
promote_expose_mode_passages
promote_adas_model_passages
promote_chunking_window_passages
promote_tool_description_passages
promote_method_label_passages
promote_host_literal_passages
promote_ide_product_passages
promote_protocol_aspire_passages
promote_listed_literal_passages
listed_literal_groups
listed_literal_gold_pattern
wiring_code_ask
wiring_code_gold_pattern
constructor_code_gold_pattern
class_def_code_gold_pattern
```

If a name does not exist, note it under **Deviations** and continue.

## Step 3 - Replace the kept helpers (exact code)

### 3a. `hybrid_seed_terms`

```python
def hybrid_seed_terms(query: str) -> tuple[str, ...]:
    """Return BM25 and exact-term seeds copied from identifiers in the query.

    Every returned term occurs in ``query`` (case-insensitive). The function
    never adds document-side words, so seeding behaves the same for any
    corpus.

    Args:
        query: Original user query. Untrusted.

    Returns:
        Deduplicated seed terms in first-seen order.
    """

    lowered_query = query.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for token in (*named_code_definition_ids(query), *named_pascal_type_ids(query)):
        text = token.strip()
        key = text.casefold()
        if not text or key in seen or key not in lowered_query:
            continue
        seen.add(key)
        found.append(text)
    return tuple(found)
```

### 3b. `literal_anchor_ask`

```python
def literal_anchor_ask(query: str) -> bool:
    """Return whether the query asks to reproduce named code or a named table.

    Used to load fused-outside-pool contexts before promotion so a named
    ``def`` block or ``Table N-M`` body stays reachable after the rerank pool
    drops it.

    Args:
        query: Original user query. Untrusted.

    Returns:
        True for code-reproduce or table-reproduce asks.
    """

    return bool(_CODE_DEF_ASK.search(query) or _TABLE_REPRO_ASK.search(query))
```

### 3c. `literal_gold_already_loaded`

```python
def literal_gold_already_loaded(
    query: str,
    passages: Sequence[RerankPassage],
) -> bool:
    """Return whether loaded passages already hold the named block.

    Table asks require a titled caption plus rows, not a prose intro that
    only mentions ``Table N-M``.

    Args:
        query: Original user query. Untrusted.
        passages: Passages already loaded for the rerank pool.

    Returns:
        True when no fused reload is needed for promotion.
    """

    code_gold = code_definition_gold_pattern(named_code_definition_ids(query))
    if code_gold is not None and _CODE_DEF_ASK.search(query):
        if any(code_gold.search(item.raw_text or "") for item in passages):
            return True
    captions = named_table_captions(query)
    table_gold = table_caption_gold_pattern(captions)
    if table_gold is not None and _TABLE_REPRO_ASK.search(query):
        if any(
            table_gold.search(item.raw_text or "")
            and _table_body_rank(item.raw_text or "", captions) >= 12
            for item in passages
        ):
            return True
    return False
```

### 3d. `promote_named_code_definition_passages`

```python
def promote_named_code_definition_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin the passage that holds ``def <name>(`` for a name the query types.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool or fused passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one definition passage first.
    """

    if not _CODE_DEF_ASK.search(query):
        return trimmed
    gold = code_definition_gold_pattern(named_code_definition_ids(query))
    if gold is None:
        return trimmed
    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_CODE_DEF_ASK,
        gold_pattern=gold,
        prefer_early_match=True,
    )
```

### 3e. `named_code_definition_ids` (shape)

Keep the function. Delete the line `wiring = wiring_code_ask(query)` and
the whole `if wiring and token.casefold() in { ... }: continue` block
with its comment. Delete `or token.casefold() in _CODE_ID_STOP` from the
skip condition (so it reads `if not token:` / `continue`). Remove the
docstring sentences about wiring asks and PascalCase constructors. Keep
the remaining loop exactly.

### 3f. `named_pascal_type_ids` and its regex (exact edits)

Replace the `_PASCAL_TYPE_FROM_QUERY` definition (and the two comment
lines above it) with:

```python
_PASCAL_TYPE_FROM_QUERY = re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]+)+)\b")
```

In `named_pascal_type_ids`, replace
`token = (match.group(1) or match.group(2) or "").strip()` with
`token = (match.group(1) or "").strip()` (the regex now has one group;
`group(2)` would raise `IndexError`).

Replace the `_PASCAL_TYPE_STOP` definition with:

```python
_PASCAL_TYPE_STOP = frozenset({"typeddict", "python", "markdown"})
```

Delete the `_CODE_ID_STOP` definition.

### 3g. `_CODE_DEF_ASK` (exact edit)

Delete only this alternative line from `_CODE_DEF_ASK`:

```python
    r"|\b[A-Z][A-Za-z0-9]*(?:Config|State|OpenAI)\s*\("
```

Keep the other alternatives.

## Step 4 - Orphan sweep and guard loop

```powershell
.venv\Scripts\python.exe .private-eval/unused_private_names.py packages/core/src/smart_rag_core/retrieval/rerank.py
.venv\Scripts\python.exe .private-eval/unused_private_names.py packages/core/src/smart_rag_core/retrieval/context.py
.venv\Scripts\python.exe .private-eval/unused_private_names.py packages/core/src/smart_rag_core/query_answer/generate_grounded.py
```

Delete every printed name; repeat until all three print nothing. Then:

```powershell
uv run python scripts/check_gold_literals.py
```

For every remaining `hit packages/...:<line>`, open the line and apply
the G1a Step 5 rule (delete a specific-word alternative/constant and its
only code path; leave a generic syntax rule and record why). Repeat until
the guard prints `failing_files=0` and exits 0.

Then list the remaining module-level regex constants and justify each:

```powershell
Select-String -Path packages/core/src/smart_rag_core/retrieval/rerank.py,packages/core/src/smart_rag_core/query_answer/generate_grounded.py,packages/core/src/smart_rag_core/query_answer/format_shape.py -Pattern '^_[A-Z0-9_]+ = re\.compile' | ForEach-Object { "$($_.Filename):$($_.LineNumber) $($_.Line.Split('=')[0].Trim())" }
```

In the report, write one line per constant:
`<file>:<line> <NAME> generic: <what syntax it matches>`. A constant you
cannot describe without naming a topic, product, person, or term from
one document is question-specific: delete it and its only code path,
then rerun the guard and tests.

## Step 5 - Tests

### 5a. Deletion procedure

```powershell
rg -l "promote_(helper_naming|expose_mode|adas_model|chunking_window|tool_description|method_label|host_literal|ide_product|protocol_aspire|listed_literal)_passages|listed_literal_groups|listed_literal_gold_pattern|wiring_code_ask|wiring_code_gold_pattern|constructor_code_gold_pattern|class_def_code_gold_pattern|_CODE_ID_STOP" tests
```

Apply the G1a Step 8 procedure to each listed file (remove imports of
deleted names; delete tests that call them; delete tests named for
wiring, constructors, class plus def, listed literals, `fresh30`,
`remain5`, or a question id; keep and do not edit every other test;
`git rm` an emptied file). For `hybrid_seed_terms` tests: delete any test
that expects a seed term that does not appear in its own query string;
keep the others.

### 5b. New invariant test (exact code)

Create `tests/unit/test_hybrid_seed_terms_query_only.py`:

```python
"""``hybrid_seed_terms`` returns only identifiers the user typed."""

from __future__ import annotations

import pytest
from smart_rag_core.retrieval.rerank import hybrid_seed_terms, literal_anchor_ask

QUERIES = (
    "Reproduce the parse_invoice function as a fenced Python code block.",
    "Show def load_rows(path) and the RowCache class as fenced Python code.",
    "Reproduce Table 3-2 (Storage options) as a Markdown pipe table.",
    "What does the document say about retry budgets?",
    "Reproduce the ChatClient constructor call as a fenced code block.",
)


@pytest.mark.parametrize("query", QUERIES)
def test_every_seed_term_occurs_in_the_query(query: str) -> None:
    """No seed term is invented from document-side vocabulary."""

    lowered = query.casefold()
    for term in hybrid_seed_terms(query):
        assert term.casefold() in lowered


def test_code_identifier_is_seeded() -> None:
    """A snake_case identifier in a code ask is seeded."""

    assert "parse_invoice" in hybrid_seed_terms(QUERIES[0])


def test_plain_question_has_no_seeds() -> None:
    """A prose question gets no seed terms."""

    assert hybrid_seed_terms(QUERIES[3]) == ()


def test_literal_anchor_ask_is_code_or_table_only() -> None:
    """Only code-reproduce and table-reproduce asks trigger fused reloads."""

    assert literal_anchor_ask(QUERIES[0])
    assert literal_anchor_ask(QUERIES[2])
    assert not literal_anchor_ask(QUERIES[3])
```

```powershell
uv run python -m pytest tests/unit/test_hybrid_seed_terms_query_only.py tests/unit/test_hybrid_rerank.py tests/unit/test_code_table_literal_salvage.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
```

If a kept test fails, stop and report it; do not edit it. If a test in
the new file fails, print the helper output for its query (for example
`uv run python -c "from smart_rag_core.retrieval.rerank import named_code_definition_ids as f; print(f('<query>'))"`)
and report it; do not change the new test to make it pass.

## Step 6 - Lint, types, docs

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/retrieval/rerank.py packages/core/src/smart_rag_core/retrieval/context.py packages/core/src/smart_rag_core/query_answer/generate_grounded.py tests/unit/test_hybrid_seed_terms_query_only.py
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check_gold_literals.py
```

Docs:

- `rg -n "promote_(helper|expose|adas|chunking|tool_description|method_label|host_literal|ide_product|protocol|listed)|listed_literal|wiring_code" docs` -
  update or delete each sentence that describes a deleted promotion.
- `docs/retrieval/` page that documents context selection (find it with
  `rg -l "_promote_query_anchor_passages|query-anchor" docs/retrieval`):
  state that only named code-definition and named table-caption
  promotions remain, and that seed terms are query-only.
- ADR `## Decision` item 1: add "Retrieval side done in G1b on <TODAY>."
- `docs/README.md`: update the date cells of every doc you edited.

## Step 7 - Commit, rebuild, dev40, stop rule

```powershell
git status --short
git add packages/core/src/smart_rag_core/retrieval/rerank.py packages/core/src/smart_rag_core/retrieval/context.py
git add packages/core/src/smart_rag_core/query_answer/generate_grounded.py tests/unit/test_hybrid_seed_terms_query_only.py
git add <each edited test file and doc, one by one>
git commit -m "fix(retrieval): remove question-specific promotions and seed terms (G1b)"
git push
gh pr checks --watch --fail-fast
```

Rebuild, probe (`G1a present`, `G1b present`), run dev40 with
`$run = "dev40-g1b"`, stage report, compare with `dev40-g1a`. Apply the
stop rule at the top of this packet. Fill `## After G1b` in the evidence
doc (counts only), commit `docs(eval): G1b dev40 results`, push, green.

## Done when

- [ ] Only `promote_named_code_definition_passages` and
      `promote_named_table_passages` remain as promotions; the 16 listed
      functions are deleted.
- [ ] `hybrid_seed_terms` returns query substrings only (new test passes).
- [ ] Orphan sweep prints nothing for the three files.
- [ ] `uv run python scripts/check_gold_literals.py` exits 0.
- [ ] Every remaining regex constant has a one-line "generic" reason in
      the report.
- [ ] Unit, contract, lint, types exit 0; deleted tests listed.
- [ ] Image rebuilt; probe `G1b present`; dev40 ran; stop-rule decision
      recorded; evidence doc updated; PR checks green.

## Commit messages

```text
fix(retrieval): remove question-specific promotions and seed terms (G1b)
docs(eval): G1b dev40 results
```

## Do not

- Do not change rerank pool size, fusion weights, MMR, quotas, or the
  rerank prompt in this packet.
- Do not add any new promotion or seed rule.
- Do not run the holdout.
