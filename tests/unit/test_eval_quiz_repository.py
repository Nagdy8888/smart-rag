"""Sanitized quiz RPC error mapping (P06-29)."""

from __future__ import annotations

import psycopg
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    canonical_payload_hash,
    quiz_error_code,
)


def test_quiz_error_code_does_not_return_sql_text() -> None:
    """Mapped codes are short tokens, never question or SQL bodies."""

    missing = psycopg.errors.UndefinedFunction("function missing")
    table = psycopg.errors.UndefinedTable("table missing")
    holdout = psycopg.errors.RaiseException("eval_quiz:holdout_rejected")
    stale = psycopg.errors.RaiseException("eval_quiz:stale_row_version")
    assert quiz_error_code(missing) == "quiz_schema_missing"
    assert quiz_error_code(table) == "quiz_schema_missing"
    assert quiz_error_code(holdout) == "holdout_rejected"
    assert quiz_error_code(stale) == "stale_row_version"
    assert quiz_error_code(RuntimeError("other")) == "request_rejected"


def test_canonical_payload_hash_is_stable() -> None:
    """Idempotency hashes are 64 hex characters."""

    digest = canonical_payload_hash({"split": "development", "query_class": "factual_definition"})
    assert len(digest) == 64
    assert digest == canonical_payload_hash(
        {"query_class": "factual_definition", "split": "development"}
    )
