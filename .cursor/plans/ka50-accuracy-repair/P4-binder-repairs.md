# P4 - Binder repairs before the paragraph contract

## Goal

`bind_company_atomic_links` (`query_answer/bind.py`) already repairs the
model's payload deterministically: it synthesizes paragraphs from links,
fills missing `atomic_link_id`, and replaces non-verbatim spans with exact
excerpts. The paragraph contract (`paragraphs.py::apply_paragraph_contract`)
then fails closed on bookkeeping mismatches:

- `citation_link_mismatch` when a citation's `atomic_link_id` is set but
  is not one of its paragraph's `link_ids`, or when the citation's
  `chunk_id` is not in that link's `chunk_ids`.
- `paragraph_unmapped` when, after those drops, a paragraph has no
  surviving citation.

Two KA50 answers (`k07`, `k12`) refused with `paragraph_unmapped` while
the gold page was in the evidence and the spans were verbatim. These are
model bookkeeping slips, not evidence failures: the span is still checked
verbatim against an authorized passage afterwards.

Three deterministic repairs, all evidence-preserving:

1. **Leaf retarget.** If the cited chunk's text strictly contains another
   evidence chunk's text and the span sits inside that smaller chunk,
   cite the smaller chunk (page-precise and avoids `leaf_ambiguous` in
   P3). Only when exactly one such leaf exists.
2. **Link id repair.** A citation whose `atomic_link_id` is not in its
   paragraph's `link_ids` takes the paragraph's first link id (today only
   an empty id is filled).
3. **Link chunk repair.** Each atomic link's `chunk_ids` is extended with
   the chunk ids of citations that point to it (cap 12).

Depends on P3 for `SkippedCitation` semantics only in the sense that
retargeting reduces skips; code-wise it is independent.

## Read first

- `packages/core/src/smart_rag_core/query_answer/bind.py` whole file
  (`bind_company_atomic_links`, `_align_citation_spans`,
  `_citation_with_link_id`, `_links_from_paragraphs`).
- `packages/core/src/smart_rag_core/query_answer/paragraphs.py`
  `_mapped_passage_ok` (line ~406) and the loop around lines 160-190, to
  confirm the failure codes above.
- `packages/core/src/smart_rag_core/query_answer/models.py`
  `AnswerCitation`, `AtomicLink` (check `chunk_ids` max length),
  `AnswerParagraph`.
- `packages/core/src/smart_rag_core/query_fusion/models.py`
  `ScoredPassage` (`chunk_id`, `citation_text`).
- `tests/unit/test_answer_verifier.py` (`_mcp_fusion`, imports from
  `tests.support.answer_verifier`: `verifier_fusion`, `verifier_passage`).

## Steps

### 1. Leaf retarget inside `_align_citation_spans`

Add a helper (exact code):

```python
def _leaf_in_evidence(
    chunk_id: str,
    span: str,
    passages: dict[str, ScoredPassage],
) -> str | None:
    """Return the one evidence chunk nested in ``chunk_id`` that holds ``span``.

    Parent passages concatenate their children. When the model cites the
    parent and the span sits inside exactly one child that is also in
    evidence, the child is the page-precise citation target and the
    database leaf rule will accept it.

    Args:
        chunk_id: Cited chunk id.
        span: Verbatim span contained in the cited chunk's text.
        passages: Fusion evidence by chunk id.

    Returns:
        Child chunk id, or None when zero or several children qualify.
    """

    parent_text = passages[chunk_id].citation_text
    if not span or not parent_text:
        return None
    leaves = [
        other_id
        for other_id, other in passages.items()
        if other_id != chunk_id
        and other.citation_text
        and len(other.citation_text) < len(parent_text)
        and other.citation_text in parent_text
        and span in other.citation_text
    ]
    if len(leaves) != 1:
        return None
    return leaves[0]
```

Import `ScoredPassage` from `smart_rag_core.query_fusion.models` if not
already imported (check the module's existing type for `passages`).

In `_align_citation_spans`, replace the loop body with (exact code):

```python
    for citation in payload.citations:
        chunk_id = citation.chunk_id
        if chunk_id is None or chunk_id not in passages:
            aligned.append(citation)
            continue
        text = passages[chunk_id].citation_text
        span = citation.span
        if not (span and span in text):
            replacement = exact_source_span(text)
            if not replacement:
                aligned.append(citation)
                continue
            span = replacement
        leaf = _leaf_in_evidence(chunk_id, span, passages)
        update: dict[str, object] = {"span": span}
        if leaf is not None:
            update["chunk_id"] = leaf
        aligned.append(citation.model_copy(update=update))
```

If `AnswerCitation.chunk_id` is typed `UUID`, convert with the same type
the dict keys use; match the existing code's key type exactly.

### 2. Link id repair in `_citation_with_link_id`

Replace the function body (exact code; keep the docstring, update the
`Returns` text to "The citation, or a copy whose ``atomic_link_id`` is the
paragraph's first link id when it was missing or not one of the
paragraph's links."):

```python
    paragraph = next(
        (
            item
            for item in paragraphs
            if item.paragraph_index == citation.paragraph_index
        ),
        None,
    )
    if paragraph is None or not paragraph.link_ids:
        return citation
    if citation.atomic_link_id and citation.atomic_link_id in paragraph.link_ids:
        return citation
    return citation.model_copy(update={"atomic_link_id": paragraph.link_ids[0]})
```

### 3. Link chunk repair

Add (exact code):

```python
def _repair_link_chunk_ids(payload: AnswerPayload) -> AnswerPayload:
    """Extend each link's ``chunk_ids`` with the chunks its citations cite.

    The paragraph contract rejects a citation whose chunk is not listed on
    its link. Citations are the stronger signal because their spans are
    checked verbatim against authorized passages; links are bookkeeping.

    Args:
        payload: Company answer after link-id binding and span alignment.

    Returns:
        Payload whose links list every cited chunk, capped at 12 per link.
        Unchanged when nothing was missing.
    """

    cited: dict[str, list[str]] = {}
    for citation in payload.citations:
        if not citation.atomic_link_id or not citation.chunk_id:
            continue
        bucket = cited.setdefault(citation.atomic_link_id, [])
        if citation.chunk_id not in bucket:
            bucket.append(citation.chunk_id)
    changed = False
    links: list[AtomicLink] = []
    for link in payload.atomic_links:
        missing = [
            chunk_id
            for chunk_id in cited.get(link.link_id, [])
            if chunk_id not in link.chunk_ids
        ]
        if not missing:
            links.append(link)
            continue
        changed = True
        merged = (*link.chunk_ids, *missing)[:12]
        links.append(link.model_copy(update={"chunk_ids": merged}))
    if not changed:
        return payload
    return payload.model_copy(update={"atomic_links": tuple(links)})
```

Confirm `12` matches the `chunk_ids` cap on `AtomicLink`; if the model
uses a named constant, import and use it.

In `bind_company_atomic_links`, change the tail:

```python
    if fusion is None:
        return _repair_link_chunk_ids(working)
    return _repair_link_chunk_ids(_align_citation_spans(working, fusion))
```

Update the function docstring: list the three repairs and state that
none of them can add a chunk id that is not already cited by a citation
the paragraph contract will check verbatim.

## Tests (`tests/unit/test_answer_verifier.py`)

Add (exact code; adapt `verifier_passage` argument names to the helper's
signature in `tests/support/answer_verifier.py`):

```python
def test_binder_retargets_parent_citation_to_unique_leaf() -> None:
    """A span inside exactly one nested evidence chunk cites that chunk."""

    child_text = "Refund period is 30 days from purchase."
    parent_text = f"Intro paragraph. {child_text} Shipping is refunded too."
    fusion = verifier_fusion(
        verifier_passage(1, text=parent_text),
        verifier_passage(2, text=child_text),
    )
    parent_id = fusion.evidence[0].chunk_id
    child_id = fusion.evidence[1].chunk_id
    payload = AnswerPayload(
        answer_text="Refunds take 30 days.",
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text="Refunds take 30 days.", link_ids=("l1",)),
        ),
        citations=(
            AnswerCitation(chunk_id=parent_id, span=child_text, paragraph_index=0, atomic_link_id="l1"),
        ),
        atomic_links=(
            AtomicLink(link_id="l1", claim="Refunds take 30 days.", chunk_ids=(parent_id,)),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations[0].chunk_id == child_id
    assert child_id in bound.atomic_links[0].chunk_ids
    checked, failures = deterministic_check_answer(
        bound, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert "citation_link_mismatch" not in failures
    assert "paragraph_unmapped" not in failures
    assert "unauthorized_or_missing_passage" not in failures
    assert checked.status != "refused"


def test_binder_repairs_link_id_and_link_chunks() -> None:
    """A wrong atomic_link_id and a missing link chunk are repaired, not refused."""

    text = "Refund period is 30 days from purchase."
    fusion = verifier_fusion(verifier_passage(1, text=text))
    chunk_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="Refunds take 30 days.",
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text="Refunds take 30 days.", link_ids=("l1",)),
        ),
        citations=(
            AnswerCitation(chunk_id=chunk_id, span=text, paragraph_index=0, atomic_link_id="wrong"),
        ),
        atomic_links=(
            AtomicLink(link_id="l1", claim="Refunds take 30 days.", chunk_ids=()),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations[0].atomic_link_id == "l1"
    assert bound.atomic_links[0].chunk_ids == (chunk_id,)
    _, failures = deterministic_check_answer(
        bound, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert "citation_link_mismatch" not in failures
    assert "paragraph_unmapped" not in failures


def test_binder_does_not_retarget_when_two_leaves_match() -> None:
    """A repeated sentence in two nested chunks keeps the parent citation."""

    repeated = "Refund period is 30 days from purchase."
    parent_text = f"{repeated} Some more text. {repeated}"
    fusion = verifier_fusion(
        verifier_passage(1, text=parent_text),
        verifier_passage(2, text=repeated),
        verifier_passage(3, text=f"{repeated} Some more text."),
    )
    parent_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="Refunds take 30 days.",
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text="Refunds take 30 days.", link_ids=("l1",)),
        ),
        citations=(
            AnswerCitation(chunk_id=parent_id, span=repeated, paragraph_index=0, atomic_link_id="l1"),
        ),
        atomic_links=(
            AtomicLink(link_id="l1", claim="Refunds take 30 days.", chunk_ids=(parent_id,)),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations[0].chunk_id == parent_id
```

If `AtomicLink.chunk_ids` requires at least one id, build the second test
with `chunk_ids=(other_id,)` for an unrelated evidence chunk instead of
`()` and assert `chunk_id in bound.atomic_links[0].chunk_ids`.

All existing tests in this file must still pass unchanged, in particular
`test_wrong_mcp_expansion_in_link_is_rejected_despite_mock_verifier`,
`test_free_prose_mcp_expansion_cannot_stay_verified`, and
`test_citation_span_and_table_range_mismatch_fail`. If one fails, the
repair is too broad; do not edit that test - narrow the repair.

## Docs

- The agent/answer doc that describes deterministic binding (search
  `docs/agent` and `docs/development/phase-06` for
  `bind_company_atomic_links` or `paragraph_unmapped`): add the three
  repairs and the rule that repairs never widen evidence.
- `docs/evaluation/KNOWN_ANSWER_50_ROOT_CAUSES_2026-09-22.md`: under the
  verifier/citation issue, link this packet and the tests.

## Commands

```powershell
uv run python -m pytest tests/unit/test_answer_verifier.py tests/unit/test_answer_paragraph_citations.py tests/unit/test_query_node_bindings.py tests/unit/test_pdf_agent_citation_scores.py -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier docs
```

Optional live proof: rebuild the `api` image first
(`00-rules-and-commands.md`, "Docker rebuild before any live run"; probe
must print `P4 present`), then run the KA50 subset `k07 k12` into
`.private-eval/runs/p4/`; expected `failures=-` (no `paragraph_unmapped`)
on the DIAG lines.

## Done when

- [ ] Parent citation with a unique nested leaf in evidence is retargeted;
      ambiguous leaves are left alone.
- [ ] Wrong `atomic_link_id` is replaced by the paragraph's first link id.
- [ ] Links list every chunk their citations cite (cap 12).
- [ ] The three new tests pass; every existing test in
      `test_answer_verifier.py` passes unchanged.
- [ ] Unit, lint, types, docs tiers pass.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
fix(bind): retarget parent citations to in-evidence leaves and repair link bookkeeping (P4)
```

## Do not

- Do not change `apply_paragraph_contract` or `_mapped_passage_ok`
  failure codes; repairs happen before the contract, never inside it.
- Do not add a chunk id to a link unless a citation with a verbatim span
  already cites that chunk.
- Do not retarget when the span appears in zero or several nested chunks.
