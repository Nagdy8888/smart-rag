"""Unit tests for overlay Hybrid ranking, coverage, glossary, and eval gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_agents.prompts import eval_pdf_judge_prompt_text
from smart_rag_agents.prompts.registry import prompt_text
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.retrieval.context import select_hybrid_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    LONG_DOCUMENT_PROFILE_ID,
    UnknownRetrievalProfileError,
    canonical_profile_digest,
    load_evaluation_profile,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.hybrid_run.channels import cap_unique_across_variants
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    apply_mmr,
    excerpt_text,
)
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseMode,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)
from smart_rag_core.security.identity import CallerContext, UserRole

from scripts.ops.draft_pdf_glossary import (
    build_glossary_import_entries,
    collect_glossary_candidates,
    draft_glossary_rows,
)


def _caller() -> CallerContext:
    """Build a server-derived caller.

    Returns:
        Frozen member caller.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _candidate(*, document: UUID, rank: int = 1) -> RetrievalCandidate:
    """Build one authorized candidate on a shared document.

    Args:
        document: Shared document id.
        rank: Channel rank.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=document,
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0 / rank,
    )


def test_default_frozen_profile_hash_is_unchanged() -> None:
    """``hybrid_default_v1`` bytes stay pinned until Packet 16 freeze."""

    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    assert profile.profile_id == HYBRID_DEFAULT_PROFILE_ID
    on_disk = Path(
        "packages/core/src/smart_rag_core/retrieval/frozen/hybrid_default_v1.json"
    )
    payload = json.loads(on_disk.read_text(encoding="utf-8"))
    assert canonical_profile_digest(payload) == FROZEN_HYBRID_PROFILE_SHA256
    assert profile.document_quota == 2
    assert profile.rerank_max_per_document == 5
    assert profile.excerpt_strategy == "prefix"


def test_query_aware_excerpt_includes_phrase_after_character_400() -> None:
    """Query-aware windows include a hit after the 400-character prefix."""

    prefix = "x" * 420
    raw = f"{prefix} annual leave policy remainder"
    excerpt = excerpt_text(
        raw,
        limit=80,
        query="leave policy",
        strategy="query_aware",
    )
    assert "leave" in excerpt.lower()
    assert excerpt != raw[:80]


def test_rank_mmr_keeps_zero_lexical_overlap_paraphrase() -> None:
    """Rank relevance survives zero query-token overlap."""

    document = uuid4()
    strong = RerankPassage(
        candidate=_candidate(document=document, rank=1),
        raw_text="synonym-only paraphrase without query tokens",
        excerpt="zzzz yyyy",
        token_count=6,
        channels=frozenset({"dense"}),
    )
    weak = RerankPassage(
        candidate=_candidate(document=document, rank=2),
        raw_text="leave policy leave policy",
        excerpt="leave policy leave policy",
        token_count=4,
        channels=frozenset({"bm25"}),
    )
    selected, _dropped = apply_mmr(
        (strong, weak),
        query="annual vacation entitlement",
        document_quota=2,
        limit=2,
    )
    assert selected[0].candidate.chunk_id == strong.candidate.chunk_id


def test_long_document_profile_can_select_more_than_two_children() -> None:
    """The evaluation candidate relaxes the two-passage document quota."""

    document = uuid4()
    fused = tuple(_candidate(document=document, rank=index) for index in range(1, 8))
    contexts = tuple(
        ChunkContext(
            chunk_id=item.chunk_id,
            document_id=document,
            version_id=item.version_id,
            parent_chunk_id=None,
            chunk_index=index,
            page_number=index,
            section_path=(f"Section-{index}",),
            token_count=8,
            raw_text=f"passage {index} unique body text",
            is_search_representative=True,
        )
        for index, item in enumerate(fused, start=1)
    )
    hits = {item.chunk_id: frozenset({"dense"}) for item in fused}
    profile = next(
        case.expected_profile
        for case in load_open_splits()
        if case.query_class is QueryClass.SEMANTIC_FACTUAL
    )

    def _rerank(
        _query: str,
        pool: tuple[RerankPassage, ...],
        _deadline: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Preserve fused order as a real rerank payload.

        Args:
            _query: Unused query.
            pool: Rerank pool.
            _deadline: Unused deadline.

        Returns:
            Identity rankings with one usage object.
        """

        rankings = tuple(
            RerankRanking(chunk_id=item.candidate.chunk_id, rank=index, support=0.8)
            for index, item in enumerate(pool, start=1)
        )
        usage = RerankUsage(
            request_id="overlay",
            model="mock",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return rankings, usage, RerankFallbackReason.NONE

    default = select_hybrid_context(
        query="summarize the document",
        profile=profile,
        fused=fused,
        contexts=contexts,
        channel_hits=hits,
        rerank=_rerank,
        load_context=lambda _ids: (),
        remaining_deadline_seconds=8.0,
        retrieval_profile=load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID),
    )
    default_from_doc = [
        item for item in default.passages if item.candidate.document_id == document
    ]
    assert len(default_from_doc) <= 2
    long_profile = load_evaluation_profile(LONG_DOCUMENT_PROFILE_ID)
    long = select_hybrid_context(
        query="summarize the document",
        profile=profile,
        fused=fused,
        contexts=contexts,
        channel_hits=hits,
        rerank=_rerank,
        load_context=lambda _ids: (),
        remaining_deadline_seconds=8.0,
        retrieval_profile=long_profile,
    )
    long_from_doc = [
        item for item in long.passages if item.candidate.document_id == document
    ]
    assert len(long_from_doc) > 2
    assert long_profile.document_quota == 12
    try:
        load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
        raise AssertionError("unfrozen long document must stay runtime-denied")
    except UnknownRetrievalProfileError:
        pass


def test_ranked_ids_are_post_selection_not_fused() -> None:
    """``ranked_ids`` is the post-MMR order; fused occupancy is ``fused_ids``."""

    document = uuid4()
    dense_hits = tuple(
        _candidate(document=document, rank=index) for index in range(1, 8)
    )
    contexts = {
        item.chunk_id: ChunkContext(
            chunk_id=item.chunk_id,
            document_id=document,
            version_id=item.version_id,
            parent_chunk_id=None,
            chunk_index=index,
            page_number=index,
            section_path=("Leave",),
            token_count=6,
            raw_text=f"canonical {index}",
            is_search_representative=True,
        )
        for index, item in enumerate(dense_hits, start=1)
    }

    class _Dense:
        """Fake dense retriever returning many same-document hits."""

        def retrieve(self, **_kwargs: object) -> DenseRetrievalResult:
            """Return the dense list.

            Returns:
                Dense result.
            """

            return DenseRetrievalResult(
                mode=DenseMode.ANN,
                candidates=dense_hits,
                authorized_count=len(dense_hits),
            )

    class _Bm25:
        """Empty BM25 channel."""

        def retrieve(self, **_kwargs: object) -> Bm25RetrievalResult:
            """Return an empty BM25 result.

            Returns:
                Empty BM25 result.
            """

            return Bm25RetrievalResult(scanned_ids=(), candidates=())

    class _Term:
        """Empty term channel."""

        def retrieve(self, **_kwargs: object) -> TermRetrievalResult:
            """Return an empty term result.

            Returns:
                Empty term result.
            """

            return TermRetrievalResult(
                candidates=(),
                query_normalized="annual leave policy",
                empty_channel=True,
            )

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        dense=_Dense(),
        bm25=_Bm25(),
        term=_Term(),
        load_context=lambda ids: tuple(
            contexts[item] for item in ids if item in contexts
        ),
        retrieval_profile=load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID),
    )
    result = retriever.retrieve(query="annual leave policy", caller=_caller())
    fused = {item.chunk_id for item in dense_hits}
    assert set(result.fused_ids) == fused
    assert len(result.ranked_ids) < len(result.fused_ids)
    assert set(result.ranked_ids).issubset(fused)


def test_global_unique_cap_does_not_multiply_by_variant_count() -> None:
    """A 75 unique cap applies across variants, not per list."""

    document = uuid4()
    variants = tuple(
        tuple(_candidate(document=document, rank=index) for index in range(1, 40))
        for _ in range(3)
    )
    capped = cap_unique_across_variants(variants, 75)
    unique = {item.chunk_id for variant in capped for item in variant}
    assert len(unique) <= 75


def test_glossary_draft_is_deterministic_and_hash_only(tmp_path: Path) -> None:
    """Glossary drafts store hashes and locators, never auto-approve."""

    path = tmp_path / "glossary.md"
    path.write_text(
        "# Retrieval Architecture\n\n"
        "Retrieval-Augmented Generation (RAG) is defined here.\n"
        "See ISO-27001 for the control identifier.\n",
        encoding="utf-8",
    )
    first = draft_glossary_rows(path)
    second = draft_glossary_rows(path)
    assert first == second
    assert first
    for row in first:
        assert "canonical" not in row
        assert "term" not in row
        assert "normalized_hash" in row
        assert "locator" in row


def test_glossary_import_entries_skip_ambiguous_aliases() -> None:
    """The same alias bound to two canonicals is left unapproved."""

    entries = build_glossary_import_entries(
        (
            {
                "kind": "acronym",
                "locator": "p1",
                "canonical_term": "First Expansion",
                "alias": "XYZ",
                "normalized_hash": "a" * 64,
            },
            {
                "kind": "acronym",
                "locator": "p2",
                "canonical_term": "Second Expansion",
                "alias": "XYZ",
                "normalized_hash": "b" * 64,
            },
        )
    )
    assert entries == ()


def test_glossary_import_entries_keep_supported_acronym(tmp_path: Path) -> None:
    """A locator-backed acronym becomes a company-scope import entry."""

    path = tmp_path / "glossary.md"
    path.write_text(
        "Retrieval-Augmented Generation (RAG) is defined here.\n",
        encoding="utf-8",
    )
    candidates = collect_glossary_candidates(path)
    entries = build_glossary_import_entries(candidates)
    assert entries
    for entry in entries:
        assert entry["effective_scope"] == "company"
        assert entry["entry_type"] == "acronym"
        assert entry["aliases"]
        assert "canonical_term" in entry


def test_glossary_draft_skips_empty_pdf_page_breaks(tmp_path: Path) -> None:
    """PDF page-break elements with no text do not crash the draft."""

    from tests.fixtures.parser import build_pdf_text_fixture

    payload, _digest = build_pdf_text_fixture()
    path = tmp_path / "glossary.pdf"
    path.write_bytes(payload)
    rows = draft_glossary_rows(path)
    for row in rows:
        assert "canonical" not in row
        assert "term" not in row


def test_eval_pdf_scripts_fail_closed_without_operator_gates() -> None:
    """Live PDF eval stays blocked; holdout is never opened."""

    hybrid_path = Path("scripts/eval_pdf_hybrid.py")
    agent_path = Path("scripts/eval_pdf_agent.py")
    hybrid_spec = importlib.util.spec_from_file_location("eval_pdf_hybrid", hybrid_path)
    agent_spec = importlib.util.spec_from_file_location("eval_pdf_agent", agent_path)
    assert hybrid_spec is not None and hybrid_spec.loader is not None
    assert agent_spec is not None and agent_spec.loader is not None
    hybrid_mod = importlib.util.module_from_spec(hybrid_spec)
    agent_mod = importlib.util.module_from_spec(agent_spec)
    hybrid_spec.loader.exec_module(hybrid_mod)
    agent_spec.loader.exec_module(agent_mod)
    assert hybrid_mod.main(["--split", "holdout"]) == 2
    assert agent_mod.main(["--split", "development"]) == 2
    judge = eval_pdf_judge_prompt_text()
    assert "untrusted" in judge.lower()
    assert "eval_judge_v1" not in judge
    assert prompt_text("eval_pdf_judge_v1")
