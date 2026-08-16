"""Delimited untrusted source records for one answer generation."""

from __future__ import annotations

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.models import TableEvidenceRecord


def delimit_passage(passage: ScoredPassage) -> str:
    """Return one instruction-safe canonical passage record.

    Args:
        passage: Authorized current canonical evidence unit.

    Returns:
        Delimited record. Embedded instructions stay inside the record.
    """

    text = passage.citation_text.replace("\x00", "")
    return (
        f'<<untrusted-source id="{passage.chunk_id}" kind="canonical-passage"'
        f' document="{passage.document_id}" version="{passage.version_id}">>\n'
        f"{text}\n"
        "</untrusted-source>"
    )


def delimit_table(record: TableEvidenceRecord) -> str:
    """Return one instruction-safe deterministic table record.

    Args:
        record: Sandbox table result with exact ranges.

    Returns:
        Delimited record containing provenance and row values.

    Raises:
        AnswerError: If the record was produced from prose arithmetic.
    """

    if record.from_prose:
        raise AnswerError("table_arithmetic_from_prose")
    ranges = ",".join(record.source_ranges)
    rows = "; ".join(str(item) for item in record.rows)
    return (
        f'<<untrusted-source id="{record.table_id}" kind="structured-table"'
        f' document="{record.document_id}" version="{record.version_id}"'
        f' ranges="{ranges}" operation="{record.operation}">>\n'
        f"{rows}\n"
        "</untrusted-source>"
    )


def assemble_source_records(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> str:
    """Join delimited Hybrid/Combined passages and table values.

    Graph prose and BM25 snippets cannot appear because ``FusionResult``
    only carries canonical passages.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.

    Returns:
        Prompt body of delimited untrusted records.
    """

    blocks = [delimit_passage(item) for item in fusion.evidence]
    blocks.extend(delimit_table(item) for item in tables)
    return "\n\n".join(blocks)


def allowed_chunk_ids(fusion: FusionResult) -> frozenset[str]:
    """Return canonical chunk IDs the answer may cite.

    Args:
        fusion: Combined or Hybrid-effective evidence.

    Returns:
        Allowed citation IDs.
    """

    return frozenset(item.chunk_id for item in fusion.evidence)


def allowed_table_ids(tables: tuple[TableEvidenceRecord, ...]) -> frozenset[str]:
    """Return table IDs the answer may cite.

    Args:
        tables: Deterministic table snapshots.

    Returns:
        Allowed table IDs.
    """

    return frozenset(item.table_id for item in tables)
