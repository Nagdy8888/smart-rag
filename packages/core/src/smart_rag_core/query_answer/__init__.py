"""Canonical answer generation, inference citations, and layered verification."""

from smart_rag_core.query_answer.assembly import (
    assemble_source_records,
    fit_source_records,
)
from smart_rag_core.query_answer.citations import (
    citation_provenance_payload,
    persist_answer_citations,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import generate_answer, mock_answer_payload
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    TableComposition,
    VerificationResult,
)
from smart_rag_core.query_answer.release import (
    bind_company_atomic_links,
    render_verified_company_answer,
)
from smart_rag_core.query_answer.tables import compose_tables
from smart_rag_core.query_answer.verifier import (
    mock_verifier_payload,
    run_verifier_batch,
    select_material_links,
)
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    MAX_VERIFIER_LINKS,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)

__all__ = [
    "ANSWER_PROMPT_SHA256",
    "ANSWER_PROMPT_VERSION",
    "MAX_VERIFIER_LINKS",
    "VERIFIER_PROMPT_SHA256",
    "VERIFIER_PROMPT_VERSION",
    "AnswerError",
    "AnswerPayload",
    "AtomicLink",
    "TableComposition",
    "VerificationResult",
    "assemble_source_records",
    "bind_company_atomic_links",
    "citation_provenance_payload",
    "compose_tables",
    "deterministic_check_answer",
    "fit_source_records",
    "generate_answer",
    "mock_answer_payload",
    "mock_verifier_payload",
    "persist_answer_citations",
    "render_verified_company_answer",
    "run_verifier_batch",
    "select_material_links",
]
