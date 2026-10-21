"""Map ``answer_v4`` provider claims onto the internal answer payload.

``answer_v4`` asks the model for an ordered claim list whose citations
name source IDs only. Application code assigns link IDs, paragraph
indices, priorities, and citation ownership, so one bad citation drops
only its own claim instead of the whole answer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.versions import (
    MAX_CITATION_SPAN_CHARS,
    MAX_CLAIM_CHARS,
    MAX_CLAIM_CITATIONS,
    MAX_CONCLUSION_CHARS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_routing.models import TableEvidenceRecord

CLAIM_LINK_PREFIX = "claim-"
_CODE_CLAIM = re.compile(
    r"(?m)(?:^|\s)(?:@\w+|def\s+\w+\s*\(|class\s+\w+|import\s+\w+|from\s+\w+)"
)
_STRUCTURED_CLAIM = re.compile(
    r"(?m)^\s*(?:#{1,3}\s+|\*\*[^*\n]+\*\*\s*$|[-*]\s+|\d+\.\s+|```|\|)"
)


def normalize_claim_text(text: str) -> str:
    """Normalize whitespace while preserving code and structured prose lines.

    Unstructured wrapped prose becomes one line. Headings, lists, and native
    blocks retain their line boundaries. A multiline code claim keeps each
    non-empty line, including leading indentation, and drops blank lines
    so the paragraph delimiter never appears inside the claim.

    Args:
        text: Provider claim body.

    Returns:
        Normalized claim text, or empty when the body is blank.
    """

    flattened = " ".join(text.split())
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in normalized or (
        _CODE_CLAIM.search(normalized) is None
        and _STRUCTURED_CLAIM.search(normalized) is None
    ):
        return flattened
    cleaned: list[str] = []
    for line in normalized.split("\n"):
        body = " ".join(line.split())
        if not body:
            continue
        indent = line[: len(line) - len(line.lstrip(" \t"))].replace("\t", "    ")
        cleaned.append(f"{indent}{body}")
    return "\n".join(cleaned)


class ClaimCitation(BaseModel):
    """One provider citation inside an ``answer_v4`` claim.

    Attributes:
        source_id: Chunk or table ID copied from a delimited source record.
        span: Exact passage substring, or the copied table value.
        source_ranges: Exact table ranges. Empty for passages.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    span: str
    source_ranges: tuple[str, ...] = ()


class AnswerClaim(BaseModel):
    """One ordered provider claim with its own citations.

    Attributes:
        text: Claim statement released only after verification.
        kind: ``fact`` or one ``inference_link`` step of a chain.
        citations: Provider citations. The mapper keeps at most
            ``MAX_CLAIM_CITATIONS``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    kind: Literal["fact", "inference_link"] = "fact"
    citations: tuple[ClaimCitation, ...] = ()


class ClaimConclusion(BaseModel):
    """Optional multi-hop conclusion over numbered claims.

    Attributes:
        text: Composed conclusion. Need not appear verbatim in a source.
        claim_numbers: 1-based provider claim positions it depends on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    claim_numbers: tuple[int, ...] = ()


class AnswerClaimsPayload(BaseModel):
    """Raw ``answer_v4`` structured output before application mapping.

    Bounds are not enforced here. The mapper drops claims and citations
    beyond the caps so one oversized item cannot fail the whole answer.

    Attributes:
        claims: Ordered provider claims.
        conclusion: Optional composed conclusion.
        status: Provider-reported answer status.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[AnswerClaim, ...] = ()
    conclusion: ClaimConclusion | None = None
    status: Literal["complete", "partial", "refused"] = "complete"


@dataclass(frozen=True)
class _MappedClaim:
    """Citations and link evidence kept for one claim.

    Attributes:
        chunk_ids: Cited supplied chunk IDs in first-seen order.
        table_id: The single supplied table the claim cites, if any.
        source_ranges: Exact table ranges owned by the link.
        citations: Passage citations owned by the claim's paragraph.
        table_citations: Table citations owned by the claim's paragraph.
    """

    chunk_ids: tuple[str, ...]
    table_id: str | None
    source_ranges: tuple[str, ...]
    citations: tuple[AnswerCitation, ...]
    table_citations: tuple[AnswerCitation, ...]


def parse_provider_answer(
    raw: object,
    *,
    chunk_ids: tuple[str, ...],
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Parse one answer-provider payload into the internal answer shape.

    Payloads with a top-level ``claims`` key are ``answer_v4`` output and
    are mapped by :func:`claims_to_answer_payload`. Payloads without it
    use the internal ``AnswerPayload`` shape that the offline mock gateway
    and recorded fixtures still emit.

    Args:
        raw: Decoded provider JSON object.
        chunk_ids: Canonical chunk IDs sent in the request.
        tables: Table records sent in the request.

    Returns:
        Internal payload before invented-ID filtering and binding.

    Raises:
        AnswerError: ``answer_schema_invalid`` when the payload matches
            neither shape.
    """

    if isinstance(raw, Mapping) and "claims" in raw:
        try:
            claims = AnswerClaimsPayload.model_validate(raw)
        except ValidationError as exc:
            raise AnswerError("answer_schema_invalid") from exc
        return claims_to_answer_payload(claims, chunk_ids=chunk_ids, tables=tables)
    try:
        return AnswerPayload.model_validate(raw)
    except ValidationError as exc:
        raise AnswerError("answer_schema_invalid") from exc


def claims_to_answer_payload(
    claims: AnswerClaimsPayload,
    *,
    chunk_ids: tuple[str, ...],
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Build paragraphs, atomic links, and citations from provider claims.

    Each kept claim becomes one paragraph holding one atomic link
    ``claim-<n>``, where ``n`` is the 1-based provider position. The
    link ``priority`` is the paragraph index, so the claims-only release
    keeps provider order. A claim is dropped on its own, and its link ID
    recorded in ``refused_links``, when it is past ``MAX_VERIFIER_LINKS``,
    its text is blank or longer than ``MAX_CLAIM_CHARS``, or none of its
    citations names a supplied chunk or table. A provider ``refused``
    status keeps no claims.

    Args:
        claims: Validated ``answer_v4`` provider output.
        chunk_ids: Canonical chunk IDs sent in the request.
        tables: Table records sent in the request.

    Returns:
        Internal payload for the existing filter, binder, paragraph
        contract, verifier, and release. ``answer_text`` stays empty.
    """

    allowed_chunks = frozenset(chunk_ids)
    tables_by_id = {item.table_id: item for item in tables}
    paragraphs: list[AnswerParagraph] = []
    links: list[AtomicLink] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    refused: list[str] = []
    link_by_number: dict[int, str] = {}
    for number, claim in enumerate(claims.claims, start=1):
        link_id = f"{CLAIM_LINK_PREFIX}{number}"
        text = normalize_claim_text(claim.text)
        mapped = None
        if (
            claims.status != "refused"
            and number <= MAX_VERIFIER_LINKS
            and text
            and len(text) <= MAX_CLAIM_CHARS
        ):
            mapped = _map_claim(
                claim,
                link_id=link_id,
                paragraph_index=len(paragraphs),
                allowed_chunks=allowed_chunks,
                tables_by_id=tables_by_id,
            )
        if mapped is None:
            refused.append(link_id)
            continue
        paragraph_index = len(paragraphs)
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=text,
                link_ids=(link_id,),
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=text,
                chunk_ids=mapped.chunk_ids,
                table_id=mapped.table_id,
                source_ranges=mapped.source_ranges,
                kind=claim.kind,
                priority=paragraph_index,
            )
        )
        citations.extend(mapped.citations)
        table_citations.extend(mapped.table_citations)
        link_by_number[number] = link_id
    status = claims.status
    if not paragraphs:
        status = "refused"
    elif refused and status == "complete":
        status = "partial"
    return AnswerPayload(
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        table_citations=tuple(table_citations),
        atomic_links=tuple(links),
        composed_conclusion=_conclusion(claims.conclusion, link_by_number),
        status=status,
        refused_links=tuple(refused),
    )


def _map_claim(
    claim: AnswerClaim,
    *,
    link_id: str,
    paragraph_index: int,
    allowed_chunks: frozenset[str],
    tables_by_id: Mapping[str, TableEvidenceRecord],
) -> _MappedClaim | None:
    """Keep the claim citations that name supplied evidence.

    Passage spans are clipped to ``MAX_CITATION_SPAN_CHARS``; a prefix of
    an exact substring is still an exact substring. Table citations keep
    only ranges present on the table record and fall back to all of the
    record's ranges when the provider listed none of them. A claim cites
    at most one table because ``AtomicLink.table_id`` is singular.

    Args:
        claim: One provider claim.
        link_id: Application-assigned link ID.
        paragraph_index: Paragraph the claim becomes.
        allowed_chunks: Chunk IDs sent in the request.
        tables_by_id: Table records sent in the request.

    Returns:
        Kept evidence, or ``None`` when no citation names supplied
        evidence.
    """

    inference = claim.kind == "inference_link"
    chunk_order: list[str] = []
    table_id: str | None = None
    ranges_order: list[str] = []
    passages: list[AnswerCitation] = []
    table_rows: list[AnswerCitation] = []
    seen: set[tuple[str, str]] = set()
    for cited in claim.citations[:MAX_CLAIM_CITATIONS]:
        span = cited.span[:MAX_CITATION_SPAN_CHARS]
        key = (cited.source_id, span)
        if key in seen:
            continue
        seen.add(key)
        if cited.source_id in allowed_chunks:
            if not span.strip():
                continue
            if cited.source_id not in chunk_order:
                chunk_order.append(cited.source_id)
            passages.append(
                AnswerCitation(
                    chunk_id=cited.source_id,
                    span=span,
                    inference=inference,
                    atomic_link_id=link_id,
                    paragraph_index=paragraph_index,
                )
            )
            continue
        record = tables_by_id.get(cited.source_id)
        if record is None or table_id not in (None, record.table_id):
            continue
        allowed_ranges = set(record.source_ranges)
        ranges = tuple(
            dict.fromkeys(
                item for item in cited.source_ranges if item in allowed_ranges
            )
        ) or tuple(record.source_ranges)
        table_id = record.table_id
        ranges_order.extend(item for item in ranges if item not in ranges_order)
        table_rows.append(
            AnswerCitation(
                table_id=record.table_id,
                source_ranges=ranges,
                inference=inference,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
    if not passages and not table_rows:
        return None
    return _MappedClaim(
        chunk_ids=tuple(chunk_order),
        table_id=table_id,
        source_ranges=tuple(ranges_order),
        citations=tuple(passages),
        table_citations=tuple(table_rows),
    )


def _conclusion(
    conclusion: ClaimConclusion | None,
    link_by_number: Mapping[int, str],
) -> ComposedConclusion | None:
    """Map a provider conclusion onto kept links, or drop it.

    Args:
        conclusion: Provider conclusion, or ``None``.
        link_by_number: Kept link IDs by 1-based provider position.

    Returns:
        Composed conclusion whose every listed claim was kept, else
        ``None``.
    """

    if conclusion is None:
        return None
    text = " ".join(conclusion.text.split())
    numbers = tuple(dict.fromkeys(conclusion.claim_numbers))
    if (
        not text
        or len(text) > MAX_CONCLUSION_CHARS
        or not numbers
        or any(number not in link_by_number for number in numbers)
    ):
        return None
    return ComposedConclusion(
        text=text,
        link_ids=tuple(link_by_number[number] for number in numbers),
    )
