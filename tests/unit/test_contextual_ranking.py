"""Conversational ranking uses resolved references without replacing initial retrieval."""

from smart_rag_core.evaluation.schema import ExpectedProfile, FieldProvenance, det
from smart_rag_core.query_profile.profiler import profile_query_sync
from smart_rag_core.retrieval.conversation_context import (
    contextual_ranking_query,
    profile_cache_query,
)
from smart_rag_core.retrieval.hybrid_run.assemble import query_texts


def _profile(query: str, variant: str) -> ExpectedProfile:
    """Create a profile with one already inferred conversational variant."""
    return profile_query_sync(query).profile.model_copy(
        update={
            "variants": det([variant], provenance=FieldProvenance.MODEL_INFERRED),
        }
    )


def test_followup_ranking_resolves_the_subject_and_keeps_original_embedding() -> None:
    """The vague original remains the first candidate-search query."""
    query = "Why is that a problem when queries are frequent?"
    resolved = "Why is the lack of indexing in object storage a problem when queries are frequent?"
    profile = _profile(query, resolved)
    assert contextual_ranking_query(query, profile) == resolved
    assert query_texts(query, profile) == (query, resolved)
    assert profile.original_query == query


def test_standalone_question_does_not_adopt_an_unrelated_variant() -> None:
    """Ordinary lexical and exact-identifier ranking retains the user's wording."""
    query = "Explain PostgreSQL indexing."
    assert (
        contextual_ranking_query(query, _profile(query, "Explain a different system."))
        == query
    )


def test_changed_protected_identifier_cannot_steer_ranking() -> None:
    """A resolved reference cannot silently replace an explicit invoice code."""
    query = "How does that affect INV-SR-1001?"
    assert (
        contextual_ranking_query(
            query, _profile(query, "How does indexing affect INV-SR-2002?")
        )
        == query
    )


def test_context_variants_do_not_share_the_same_rank_cache_key() -> None:
    """Identical follow-up wording can refer to different subjects in different chats."""
    query = "Explain that again."
    first = _profile(query, "Explain object storage again.")
    second = _profile(query, "Explain memory again.")
    assert profile_cache_query(query, first) != profile_cache_query(query, second)
    assert profile_cache_query(query, first) == profile_cache_query(query, first)
    assert len(profile_cache_query(query, first)) <= 2000
