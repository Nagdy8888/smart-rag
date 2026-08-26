"""Structured-table branch conversion."""

from __future__ import annotations

from smart_rag_core.query_routing.models import TableEvidenceRecord


def table_evidence(outcome: object) -> TableEvidenceRecord | None:
    """Snapshot a structured-table result. Prose arithmetic is forbidden.

    Args:
        outcome: ``TableQueryResult`` or None.

    Returns:
        Table evidence record, or None when the executor returned nothing.
    """

    if outcome is None:
        return None
    table_id = getattr(outcome, "table_id", None)
    if table_id is None:
        return None
    rows_raw = getattr(outcome, "rows", ()) or ()
    rows = tuple(dict(item) for item in rows_raw)
    return TableEvidenceRecord(
        table_id=str(table_id),
        version_id=str(getattr(outcome, "version_id", "") or ""),
        document_id=str(getattr(outcome, "document_id", "") or ""),
        source_ranges=tuple(
            str(item) for item in getattr(outcome, "source_ranges", ()) or ()
        ),
        operation=str(getattr(outcome, "operation", "table") or "table"),
        rows=rows,
        sheet=getattr(outcome, "sheet", None),
        workbook=getattr(outcome, "workbook", None),
        units=getattr(outcome, "units", None),
        from_prose=False,
    )
