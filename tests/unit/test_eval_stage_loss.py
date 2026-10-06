"""Unit tests for the stage-loss classifier in ``scripts/eval_stage_loss.py``."""

from __future__ import annotations

from scripts.eval_stage_loss import (
    DraftView,
    StageIds,
    classify_fact,
    collapse,
    link_prefix,
    removal_cause,
    stage_ids,
    view_from_payloads,
)

A = "00000000-0000-4000-8000-00000000000a"
B = "00000000-0000-4000-8000-00000000000b"
C = "00000000-0000-4000-8000-00000000000c"
TEXT = {
    A: collapse("The router\nselects the planner tool."),
    B: collapse("Other text."),
    C: collapse("More."),
}
CORPUS = frozenset(TEXT)
PHRASE = ["selects the planner tool"]


def _ids(candidates: set[str], pool: set[str], selected: set[str]) -> StageIds:
    """Build monotonic stage ids for a test.

    Args:
        candidates: Candidate ids.
        pool: Pool ids.
        selected: Selected ids.

    Returns:
        Stage ids with later stages folded into earlier ones.
    """

    return StageIds(
        candidates=frozenset(candidates | pool | selected),
        pool=frozenset(pool | selected),
        selected=frozenset(selected),
    )


def _classify(answer: str, ids: StageIds, view: DraftView | None) -> str:
    """Classify the shared phrase.

    Args:
        answer: Released answer text.
        ids: Stage ids.
        view: Draft view or None.

    Returns:
        Stage name.
    """

    return classify_fact(
        PHRASE,
        answer_text=answer,
        view=view,
        ids=ids,
        text_by_id=TEXT,
        corpus_ids=CORPUS,
    )


def test_ok_uses_scorer_normalization() -> None:
    """HTML entities and case do not hide a released fact."""

    assert (
        _classify(
            "It Selects the planner tool &amp; more.", _ids(set(), set(), set()), None
        )
        == "ok"
    )


def test_ingestion_when_no_chunk_holds_fact() -> None:
    """A fact absent from every stored chunk is an ingestion loss."""

    result = classify_fact(
        ["absent phrase here"],
        answer_text="",
        view=None,
        ids=_ids({A}, {A}, {A}),
        text_by_id=TEXT,
        corpus_ids=CORPUS,
    )
    assert result == "1_ingestion"


def test_stage_order() -> None:
    """Each stage is reported only when every earlier stage held the fact."""

    draft_without = DraftView(draft_text="unrelated", draft_link_ids=("claim-1",))
    draft_with = DraftView(
        draft_text="it selects the planner tool", draft_link_ids=("claim-1",)
    )
    assert _classify("", _ids({B}, set(), set()), None) == "2_retrieval"
    assert _classify("", _ids({A}, {B}, set()), None) == "3_fusion_pool"
    assert _classify("", _ids(set(), {A}, {B}), None) == "4_rerank_select"
    assert _classify("", _ids(set(), set(), {A}), None) == "5_unknown_no_checkpoint"
    assert _classify("", _ids(set(), set(), {A}), draft_without) == "5a_draft_missing"
    assert (
        _classify("", _ids(set(), set(), {A}), draft_with) == "5b_removed_after_draft"
    )


def test_stage_ids_ignore_unknown_strings() -> None:
    """``"unknown"`` fields and non-UUID items are ignored."""

    ids = stage_ids(
        {"dense_ids": "unknown", "fused_ids": [A, "w"], "selected_ids": [B]}
    )
    assert ids.selected == frozenset({B})
    assert ids.pool == frozenset({A, B})
    assert ids.candidates == frozenset({A, B})


def test_link_prefix() -> None:
    """Numeric suffixes are removed; other ids stay."""

    assert link_prefix("claim-2") == "claim"
    assert link_prefix("query-literal-extractive-1") == "query-literal-extractive"
    assert link_prefix("p1") == "p1"


def test_removal_causes() -> None:
    """New link families, refusals, and trims are told apart."""

    assert (
        removal_cause(DraftView("", ("claim-1",), ("salvage-1",), "complete"))
        == "salvage_overwrite"
    )
    assert (
        removal_cause(DraftView("", ("claim-1",), (), "refused"))
        == "refused_after_draft"
    )
    assert (
        removal_cause(DraftView("", ("claim-1", "claim-2"), ("claim-2",), "complete"))
        == "trimmed_or_rewritten"
    )


def test_view_from_payloads() -> None:
    """Draft claims are part of the draft text; a missing draft gives None."""

    assert view_from_payloads(None, {"status": "complete"}) is None
    view = view_from_payloads(
        {"answer_text": "x", "atomic_links": [{"link_id": "claim-1", "claim": "y"}]},
        {"status": "refused", "atomic_links": []},
    )
    assert view is not None
    assert view.draft_text == "x\ny"
    assert view.draft_link_ids == ("claim-1",)
    assert view.final_status == "refused"
