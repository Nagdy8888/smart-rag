"""Compose StructuredTable evidence as a separate type with Hybrid/Combined."""

from __future__ import annotations

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import TableComposition
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    TableEvidenceRecord,
)


def compose_tables(
    branch_results: tuple[BranchResult, ...],
    *,
    from_prose: bool = False,
) -> TableComposition:
    """Collect sandbox table results. Never compute totals from prose.

    Args:
        branch_results: Packet 2/3 branch outcomes.
        from_prose: Forbidden flag used by the negative test.

    Returns:
        Table composition with exact cell/range provenance.

    Raises:
        AnswerError: If ``from_prose`` is true or a record lacks ranges.
    """

    if from_prose:
        raise AnswerError("table_arithmetic_from_prose")
    records: list[TableEvidenceRecord] = []
    for branch in branch_results:
        if branch.kind is not BranchKind.STRUCTURED_TABLE:
            continue
        item = branch.table_evidence
        if item is None:
            continue
        if item.from_prose:
            raise AnswerError("table_arithmetic_from_prose")
        if not item.source_ranges:
            raise AnswerError("table_provenance_missing")
        records.append(item)
    return TableComposition(records=tuple(records), from_prose=False)
