"""Unit tests for HTTP sanitization of ingestion job last_error text."""

from __future__ import annotations

import pytest
from smart_rag_api.services.ingestion_error_text import sanitize_ingestion_last_error
from smart_rag_api.services.keyset import parse_created_at_id_cursor
from smart_rag_core.query_admission.exceptions import QueryAdmissionError


def test_sanitize_ingestion_last_error_strips_secrets_and_traces() -> None:
    """Stack traces, connection URIs, and overlong text are not returned."""

    assert sanitize_ingestion_last_error(None) is None
    assert sanitize_ingestion_last_error("timeout contacting parser") == (
        "timeout contacting parser"
    )
    assert (
        sanitize_ingestion_last_error(
            "Traceback (most recent call last):\n  File",
            category="transient",
        )
        == "transient"
    )
    assert (
        sanitize_ingestion_last_error("postgresql://user:secret@db/app")
        == "ingestion_error"
    )
    assert (
        sanitize_ingestion_last_error("sk-abcdefghijklmnopqrstuvwxyz")
        == "ingestion_error"
    )
    assert len(sanitize_ingestion_last_error("x" * 500) or "") <= 64


def test_parse_created_at_id_cursor_rejects_half_values() -> None:
    """Keyset cursors must be ``created_at,id`` or empty."""

    assert parse_created_at_id_cursor(None) == (None, None)
    with pytest.raises(QueryAdmissionError, match="invalid_cursor"):
        parse_created_at_id_cursor("not-a-cursor")
    with pytest.raises(QueryAdmissionError, match="invalid_cursor"):
        parse_created_at_id_cursor("2026-08-19T00:00:00+00:00,not-uuid")
