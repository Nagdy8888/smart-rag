"""Count-only gold loss stages from authorized channel IDs."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.evaluation.private_pdf.metrics import (
    GoldLossStage,
    gold_loss_stage,
    score_retrieve_case,
)

BM25_SNIPPET = "bm25 snippet must never be cited"


def test_gold_loss_stages_map_synthetic_ids() -> None:
    """Synthetic ranked/fused/channel IDs map to the four loss stages."""

    gold = uuid4()
    other = uuid4()
    absent = gold_loss_stage((gold,), dense_ids=(), bm25_ids=(), term_ids=())
    assert absent == GoldLossStage.ABSENT_ALL_CHANNELS.value
    channel = gold_loss_stage(
        (gold,),
        dense_ids=(gold,),
        fused_ids=(other,),
        selected_ids=(other,),
    )
    assert channel == GoldLossStage.CHANNEL_NOT_FUSED.value
    dropped = gold_loss_stage(
        (gold,),
        dense_ids=(gold,),
        fused_ids=(gold,),
        selected_ids=(other,),
    )
    assert dropped == GoldLossStage.FUSED_DROPPED.value
    selected = gold_loss_stage(
        (gold,),
        dense_ids=(gold,),
        fused_ids=(gold,),
        selected_ids=(gold,),
    )
    assert selected == GoldLossStage.SELECTED.value


def test_diagnostics_are_count_and_id_only() -> None:
    """Histogram keys are stage tokens; BM25 snippets never appear."""

    gold = uuid4()
    score = score_retrieve_case(
        case_id="aa" * 12,
        query_class="factual_definition",
        ranked_ids=(gold,),
        gold_ids=(gold,),
        gold_pages=(1,),
        evidence_pages=(1,),
        expected_refusal=False,
        refused=False,
        acl_leak=False,
        fused_ids=(gold,),
        selected_ids=(gold,),
        dense_ids=(gold,),
        bm25_ids=(),
        term_ids=(),
    )
    assert score.loss_stage == GoldLossStage.SELECTED.value
    assert BM25_SNIPPET not in score.loss_stage
    assert BM25_SNIPPET not in score.bm25_fallback
