"""Unit tests for authorized source resolution and ranking-query cleanup."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.source_scope import (
    SourceResolution,
    high_confidence_source_names,
    resolve_retrieval_scope,
    strip_source_selectors,
)
from smart_rag_core.security.identity import CallerContext, UserRole


def _caller() -> CallerContext:
    """Return a member caller.

    Returns:
        Frozen identity.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def test_strip_source_selectors_keeps_fact_tokens() -> None:
    """Matched titles are removed from ranking without dropping fact codes."""

    query = "In Policy Handbook, what is INV-1001?"
    stripped = strip_source_selectors(query, ("Policy Handbook",))
    assert "Policy Handbook" not in stripped
    assert "INV-1001" in stripped
    assert stripped != query


def test_strip_source_selectors_falls_back_when_only_title_remains() -> None:
    """A title-only question keeps the original query instead of going blank."""

    query = "Policy Handbook"
    assert strip_source_selectors(query, ("Policy Handbook",)) == query


def test_low_confidence_requested_names_are_dropped() -> None:
    """Confidence below the named-source floor must not become a selector."""

    names = high_confidence_source_names(("Policy Handbook",), 0.79)
    assert names == ()
    kept = high_confidence_source_names(("Policy Handbook",), 0.80)
    assert kept == ("Policy Handbook",)


def test_contained_title_query_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A unique title inside the question can still uniquely scope retrieve."""

    version = uuid4()
    captured: dict[str, object] = {}

    def _search(*_args: object, **kwargs: object) -> tuple[tuple[object, str], ...]:
        """Capture search kwargs for the contained-title assertion.

        Returns:
            One authorized version/title pair.
        """

        captured["query_text"] = kwargs["query_text"]
        captured["sources"] = kwargs["sources"]
        return ((version, "Policy Handbook"),)

    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._search_authorized_versions",
        _search,
    )
    scope = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=(),
        whole_document=False,
        connection=SimpleNamespace(),  # type: ignore[arg-type]
        query_text="In Policy Handbook, what is INV-1001?",
        representative_count=4,
    )
    assert captured["sources"] == ()
    assert captured["query_text"] == "In Policy Handbook, what is INV-1001?"
    assert scope.resolution is SourceResolution.EXACT_ONE
    assert scope.version_id == version
    assert "Policy Handbook" in scope.selector_texts


def test_unscoped_without_connection_is_indistinguishable() -> None:
    """Missing connection cannot distinguish unauthorized from unknown titles."""

    scope = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=("Missing Handbook",),
        whole_document=False,
    )
    assert scope.resolution is SourceResolution.UNSCOPED
    assert scope.version_id is None
    assert scope.selector_texts == ()
    assert scope.candidate_profile_id == HYBRID_DEFAULT_PROFILE_ID


def test_exact_one_match_scopes_and_records_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one authorized title becomes a version scope selector."""

    version = uuid4()

    def _exact(*_args: object, **_kwargs: object) -> tuple[tuple[object, str], ...]:
        """Return one authorized version/title pair.

        Returns:
            One match.
        """

        return ((version, "Policy Handbook"),)

    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._search_authorized_versions",
        _exact,
    )
    scope = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=("Policy Handbook",),
        whole_document=False,
        connection=SimpleNamespace(),  # type: ignore[arg-type]
        representative_count=12,
    )
    assert scope.resolution is SourceResolution.EXACT_ONE
    assert scope.version_id == version
    assert scope.selector_texts == ("Policy Handbook",)


def test_ambiguous_and_empty_matches_stay_unscoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple or zero authorized matches never become a hard filter."""

    first = uuid4()
    second = uuid4()

    def _ambiguous(*_args: object, **_kwargs: object) -> tuple[tuple[object, str], ...]:
        """Return two authorized matches.

        Returns:
            Two version/title pairs.
        """

        return ((first, "Alpha"), (second, "Beta"))

    def _empty(*_args: object, **_kwargs: object) -> tuple[tuple[object, str], ...]:
        """Return no authorized matches.

        Returns:
            Empty tuple.
        """

        return ()

    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._search_authorized_versions",
        _ambiguous,
    )
    ambiguous = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=("Alpha",),
        whole_document=False,
        connection=SimpleNamespace(),  # type: ignore[arg-type]
    )
    assert ambiguous.resolution is SourceResolution.AMBIGUOUS
    assert ambiguous.version_id is None
    assert ambiguous.selector_texts == ()
    monkeypatch.setattr(
        "smart_rag_core.retrieval.source_scope._search_authorized_versions",
        _empty,
    )
    missing = resolve_retrieval_scope(
        caller=_caller(),
        requested_sources=("Secret Handbook",),
        whole_document=False,
        connection=SimpleNamespace(),  # type: ignore[arg-type]
    )
    assert missing.resolution is SourceResolution.UNSCOPED
    assert missing.version_id is None
