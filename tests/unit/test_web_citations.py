"""Unit tests for Web evidence URL policy, hashing, and span containment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_api.schemas.fastapi_security import CitationResponse
from smart_rag_api.services.query_runs import escape_run_citation
from smart_rag_api.services.sse.mapping.citations import citation_preview
from smart_rag_core.query_admission.service import RunCitationRecord
from smart_rag_core.query_answer.citations import persist_web_answer_citations
from smart_rag_core.query_answer.models import AnswerPayload, AtomicLink
from smart_rag_core.web_research.models import WebCitation, WebSourceRecord
from smart_rag_core.web_research.policy import (
    assert_span_contained,
    excerpt_sha256,
    normalize_web_url,
)


def test_normalize_web_url_rejects_loopback_and_userinfo() -> None:
    """Crawl policy rejects loopback and credentialed URLs."""

    with pytest.raises(ValueError, match="invalid_url"):
        normalize_web_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError, match="invalid_url"):
        normalize_web_url("https://user:pass@example.com/x")
    assert normalize_web_url("https://example.com/a") == "https://example.com/a"


def test_span_must_be_substring_of_excerpt() -> None:
    """Python rejects spans that are not contained in the stored excerpt."""

    citation = WebCitation(
        web_source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", span="hello"
    )
    assert_span_contained(excerpt="hello world", citation=citation)
    with pytest.raises(ValueError, match="span_not_contained"):
        assert_span_contained(excerpt="goodbye", citation=citation)


def test_excerpt_hash_is_sha256_hex() -> None:
    """Content hash is 64 hex characters of the excerpt bytes."""

    digest = excerpt_sha256("hello")
    assert len(digest) == 64
    assert digest == excerpt_sha256("hello")
    assert digest != excerpt_sha256("Hello")


def test_answer_payload_accepts_web_citations() -> None:
    """AnswerPayload stores Web citations without company chunks."""

    citation = WebCitation(
        web_source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        span="public fact",
    )
    payload = AnswerPayload(
        answer_text="A public fact.",
        web_citations=(citation,),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="A public fact.",
                web_source_ids=("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",),
            ),
        ),
    )
    assert payload.citations == ()
    assert payload.web_citations[0].span == "public fact"
    dumped = payload.model_dump()
    assert "excerpt" not in dumped
    assert "hello world" not in str(dumped)


def test_web_citation_rejects_blank_span() -> None:
    """Whitespace-only spans fail closed."""

    with pytest.raises(ValidationError):
        WebCitation(web_source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", span="   ")


def test_citation_response_schema_omits_excerpt_and_span() -> None:
    """OpenAPI CitationResponse has source_kind and never excerpt or span."""

    props = CitationResponse.model_json_schema()["properties"]
    assert "source_kind" in props
    assert "web_source_id" in props
    assert "evidence_excerpt" in props
    assert "document_title" in props
    assert "pdf_page_number" in props
    assert "paragraph_index" in props
    assert "excerpt" not in props
    assert "span" not in props
    assert "html" not in props


def test_escape_run_citation_preserves_web_metadata() -> None:
    """HTTP sanitizer keeps source_kind and web_source_id and drops no URL."""

    citation_id = uuid4()
    web_source_id = uuid4()
    escaped = escape_run_citation(
        RunCitationRecord(
            citation_id=citation_id,
            citation_index=0,
            chunk_id=None,
            provenance={
                "source_kind": "web",
                "url": "https://example.com/a",
                "title": "Water",
                "content_hash": "a" * 64,
            },
            source_unavailable=False,
            source_kind="web",
            web_source_id=web_source_id,
        )
    )
    assert escaped.source_kind == "web"
    assert escaped.web_source_id == web_source_id
    assert escaped.provenance["url"] == "https://example.com/a"
    assert "excerpt" not in escaped.provenance
    assert "span" not in escaped.provenance


def test_citation_preview_uses_web_source_ids_not_spans() -> None:
    """SSE preview lists web_source_id values and never span text."""

    source_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    event = citation_preview(
        AnswerPayload(
            answer_text="A public fact.",
            web_citations=(
                WebCitation(web_source_id=source_id, span="SECRET_SPAN_TEXT"),
            ),
        )
    )
    assert event is not None
    assert event[0] == "citation_preview"
    assert event[1]["citation_ids"] == (source_id,)
    assert "SECRET_SPAN_TEXT" not in str(event)


def test_persist_web_answer_citations_requires_matching_source() -> None:
    """Persist fails closed when the citation source was not stored."""

    citation = WebCitation(
        web_source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        span="public fact",
    )
    with pytest.raises(ValueError, match="not_found"):
        persist_web_answer_citations(
            MagicMock(),
            caller=MagicMock(),
            run_id=uuid4(),
            sources=(),
            answer=AnswerPayload(
                answer_text="A public fact.", web_citations=(citation,)
            ),
        )


def test_persist_web_answer_citations_delegates_insert() -> None:
    """Verified Web citations persist through the store helper."""

    source_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    source = WebSourceRecord(
        web_source_id=source_id,
        source_index=0,
        url="https://example.com/a",
        title="Water",
        excerpt="public fact from the web",
        content_hash=excerpt_sha256("public fact from the web"),
    )
    citation = WebCitation(web_source_id=source_id, span="public fact")
    inserted = uuid4()
    with patch(
        "smart_rag_core.web_research.store.insert_web_citation",
        return_value=inserted,
    ) as insert:
        ids = persist_web_answer_citations(
            MagicMock(),
            caller=MagicMock(),
            run_id=uuid4(),
            sources=(source,),
            answer=AnswerPayload(
                answer_text="A public fact.", web_citations=(citation,)
            ),
        )
    assert ids == (inserted,)
    insert.assert_called_once()
    assert insert.call_args.kwargs["citation_index"] == 0
    assert insert.call_args.kwargs["source"] is source
