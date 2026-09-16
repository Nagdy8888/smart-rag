"""Delimited untrusted source records for one answer generation."""

from __future__ import annotations

from dataclasses import dataclass

from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

_RECORD_SEPARATOR = "\n\n"
_TABLE_PRIORITY_ROUTES = frozenset({"structured_table", "composite"})
INPUT_BOUND_REFUSAL_TEXT = (
    "The available company evidence could not fit safely within this "
    "run's answer limit. Narrow the question and try again."
)
DEADLINE_RESERVE_REFUSAL_TEXT = (
    "This run ran out of time before a company answer could be generated. "
    "Narrow the question and try again."
)


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
    return _RECORD_SEPARATOR.join(blocks)


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


@dataclass(frozen=True)
class SourceAssemblyFit:
    """Deterministic fitted source records under the model input bound.

    Attributes:
        records: Joined delimited records for the model request.
        fusion: Fitted fusion subset. The original fusion object is unchanged.
        tables: Fitted table subset.
        included_chunk_ids: Passage IDs retained in fusion order.
        included_table_ids: Table IDs retained in table order.
        dropped_chunk_ids: Passage IDs omitted as duplicates or budget.
        dropped_table_ids: Table IDs omitted as budget.
        duplicate_drop_count: Later exact-normalized duplicate count.
        source_records_chars: Character length of ``records``.
        query_chars: Character length of the user query.
        max_input_chars: Bound used for this fit.
        trim_reason: ``answer_context_trimmed``, ``input_bound_exceeded``,
            or empty when every block was retained.
    """

    records: str
    fusion: FusionResult
    tables: tuple[TableEvidenceRecord, ...]
    included_chunk_ids: tuple[str, ...]
    included_table_ids: tuple[str, ...]
    dropped_chunk_ids: tuple[str, ...]
    dropped_table_ids: tuple[str, ...]
    duplicate_drop_count: int
    source_records_chars: int
    query_chars: int
    max_input_chars: int
    trim_reason: str

    def diagnostics(self) -> dict[str, object]:
        """Return checkpoint-safe fit metadata without source text.

        Returns:
            ID and count fields only.
        """

        return {
            "included_chunk_ids": list(self.included_chunk_ids),
            "included_table_ids": list(self.included_table_ids),
            "dropped_chunk_ids": list(self.dropped_chunk_ids),
            "dropped_table_ids": list(self.dropped_table_ids),
            "duplicate_drop_count": self.duplicate_drop_count,
            "source_records_chars": self.source_records_chars,
            "query_chars": self.query_chars,
            "max_input_chars": self.max_input_chars,
            "trim_reason": self.trim_reason,
        }


def company_input_bound_payload() -> AnswerPayload:
    """Return the canonical company refusal when no evidence block fits.

    Returns:
        Refused company payload with a non-empty limitation.
    """

    return AnswerPayload(
        answer_text=INPUT_BOUND_REFUSAL_TEXT,
        status="refused",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def company_deadline_reserve_payload() -> AnswerPayload:
    """Return the canonical company refusal when the eight-second reserve is gone.

    Returns:
        Partial company payload with a non-empty limitation.
    """

    return AnswerPayload(
        answer_text=DEADLINE_RESERVE_REFUSAL_TEXT,
        status="partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def _joined_len(blocks: list[str]) -> int:
    """Return character length of delimiter-joined blocks.

    Args:
        blocks: Complete delimited records.

    Returns:
        Joined length, or 0 when empty.
    """

    if not blocks:
        return 0
    return sum(len(item) for item in blocks) + len(_RECORD_SEPARATOR) * (
        len(blocks) - 1
    )


def fit_source_records(
    *,
    user_query: str,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    max_input_chars: int,
    route: str | None = None,
) -> SourceAssemblyFit:
    """Fit whole source records under the existing model input bound.

    This function performs no model calls, database reads, or token
    estimation. It never mutates ``fusion`` or ``tables``.

    Args:
        user_query: Original user text counted against the bound.
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.
        max_input_chars: ``QueryGraphDeps.model_input_max_chars``.
        route: Server-derived effective route. StructuredTable/Composite
            reserve table blocks before optional lower-ranked prose.

    Returns:
        Fitted records, a new fusion/table subset, and ID-only diagnostics.
    """

    query_chars = len(user_query)
    bound = max_input_chars if max_input_chars >= 1 else 0
    selected_route = route if route is not None else fusion.effective_route
    table_first = selected_route in _TABLE_PRIORITY_ROUTES
    retained_passages: list[ScoredPassage] = []
    retained_tables: list[TableEvidenceRecord] = []
    dropped_chunks: list[str] = []
    dropped_tables: list[str] = []
    blocks: list[str] = []
    seen_digests: set[str] = set()
    duplicate_drop_count = 0
    budget_dropped = False

    def _can_add(block: str) -> bool:
        """Return whether one complete block still fits with the query.

        Args:
            block: One delimited passage or table record.

        Returns:
            True when ``len(query + joined_records)`` stays in bound.
        """

        trial_len = query_chars + _joined_len([*blocks, block])
        return bound >= 1 and trial_len <= bound

    def _take_tables() -> None:
        """Retain whole table blocks in original order while they fit."""

        nonlocal budget_dropped
        for record in tables:
            block = delimit_table(record)
            if _can_add(block):
                blocks.append(block)
                retained_tables.append(record)
            else:
                dropped_tables.append(record.table_id)
                budget_dropped = True

    def _take_passages() -> None:
        """Retain fusion-order passages, dropping exact duplicates later."""

        nonlocal duplicate_drop_count, budget_dropped
        for passage in fusion.evidence:
            digest = content_hash(passage.citation_text)
            if digest in seen_digests:
                dropped_chunks.append(passage.chunk_id)
                duplicate_drop_count += 1
                continue
            block = delimit_passage(passage)
            if _can_add(block):
                blocks.append(block)
                retained_passages.append(passage)
                seen_digests.add(digest)
            else:
                dropped_chunks.append(passage.chunk_id)
                budget_dropped = True

    if table_first:
        _take_tables()
        _take_passages()
    else:
        _take_passages()
        _take_tables()

    had_evidence = bool(fusion.evidence) or bool(tables)
    if had_evidence and not retained_passages and not retained_tables:
        trim_reason = "input_bound_exceeded"
    elif budget_dropped or duplicate_drop_count:
        trim_reason = "answer_context_trimmed"
    else:
        trim_reason = ""

    fitted_fusion = fusion.model_copy(update={"evidence": tuple(retained_passages)})
    fitted_tables = tuple(retained_tables)
    records = assemble_source_records(fitted_fusion, fitted_tables)
    return SourceAssemblyFit(
        records=records,
        fusion=fitted_fusion,
        tables=fitted_tables,
        included_chunk_ids=tuple(item.chunk_id for item in retained_passages),
        included_table_ids=tuple(item.table_id for item in retained_tables),
        dropped_chunk_ids=tuple(dropped_chunks),
        dropped_table_ids=tuple(dropped_tables),
        duplicate_drop_count=duplicate_drop_count,
        source_records_chars=len(records),
        query_chars=query_chars,
        max_input_chars=max_input_chars,
        trim_reason=trim_reason,
    )
