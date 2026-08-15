"""Holdout-blind Phase 4 open-split Hybrid Ready eval-corpus materializer.

Packet 9 Wave 1B builds compact sources and a sidecar map from synthetic gold
ids (``p4-chk-*`` / ``p4-tbl-*``) to real canonical UUIDs. This module never
loads sealed holdout labels. Live Hybrid Ready persist is supplied by the
caller; unit tests exercise filtering, compact sources, and sidecar schema
without Docker or OpenAI.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.classes import (
    QueryClass,
    RuntimeOwner,
    class_runtime_owner,
)
from smart_rag_core.evaluation.loader import (
    load_development_cases,
    load_open_splits,
    load_qualification_cases,
)
from smart_rag_core.evaluation.schema import (
    DatasetSplit,
    EvaluationCase,
    ProfileField,
)

SIDECAR_SCHEMA_VERSION = "phase4-gold-id-map-v1"
GOLD_CHUNK_MARKER = "gold_chunk_id="
GOLD_TABLE_MARKER = "gold_table_id="
_OPEN_SPLITS = frozenset({DatasetSplit.DEVELOPMENT, DatasetSplit.QUALIFICATION})
_DEFERRED_QUERY_CLASSES = frozenset(
    {
        QueryClass.RELATIONSHIP,
        QueryClass.MULTI_HOP,
        QueryClass.GRAPH_MAPPING,
        QueryClass.PROMPT_INJECTION,
    }
)
DocumentVisibility = Literal["company_visible", "restricted"]
OpenSplitName = Literal["open", "development", "qualification"]


@dataclass(frozen=True, slots=True)
class PersistMapping:
    """Live Hybrid Ready persist results used to fill sidecar UUIDs.

    Attributes:
        document_id: Real ``app.documents.id``.
        version_id: Real ``app.document_versions.id``.
        chunk_texts: Persisted chunk id and raw-text pairs.
        table_ids: Persisted ``app.document_tables.id`` values.
    """

    document_id: UUID
    version_id: UUID
    chunk_texts: tuple[tuple[UUID, str], ...] = ()
    table_ids: tuple[UUID, ...] = ()


class CompactEvalSource(BaseModel):
    """Compact markdown (and optional CSV) for one Phase-4-owned eval case.

    Attributes:
        case_id: Immutable evaluation case identifier.
        split: Open split name that produced the case.
        query_class: Canonical query class.
        markdown_text: Compact markdown/text containing gold codes and answers.
        markdown_filename: Suggested markdown filename.
        table_csv: CSV body when the case is tabular aggregation; otherwise none.
        table_filename: Suggested CSV filename when ``table_csv`` is set.
        visibility: Canonical document visibility for Hybrid Ready persist.
        labeled_actor_id: Actor snapshot from the case label.
        restricted_actor: Whether the labeled actor is ACL-restricted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: str
    query_class: str
    markdown_text: str
    markdown_filename: str
    table_csv: str | None = None
    table_filename: str | None = None
    visibility: DocumentVisibility
    labeled_actor_id: str
    restricted_actor: bool


class GoldIdRecord(BaseModel):
    """One synthetic gold identifier mapped to optional real canonical UUIDs.

    Attributes:
        case_id: Evaluation case identifier.
        split: Open split name.
        query_class: Canonical query class.
        synthetic_chunk_id: Generator gold chunk id such as ``p4-chk-0251``.
        synthetic_table_id: Generator gold table id such as ``p4-tbl-0260``.
        synthetic_source_id: Generator source id.
        synthetic_version_id: Generator version id.
        chunk_id: Real ``app.document_chunks.id`` after persist.
        table_id: Real ``app.document_tables.id`` after persist.
        document_id: Real ``app.documents.id`` after persist.
        version_id: Real ``app.document_versions.id`` after persist.
        visibility: Persist visibility; restricted gold is never company-visible.
        labeled_actor_id: Actor from the case label.
        restricted_actor: Whether the labeled actor is restricted.
        visible_to_actor: Whether the gold link is visible to that actor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: str
    query_class: str
    synthetic_chunk_id: str | None = None
    synthetic_table_id: str | None = None
    synthetic_source_id: str | None = None
    synthetic_version_id: str | None = None
    chunk_id: UUID | None = None
    table_id: UUID | None = None
    document_id: UUID | None = None
    version_id: UUID | None = None
    visibility: DocumentVisibility
    labeled_actor_id: str
    restricted_actor: bool
    visible_to_actor: bool = True


class GoldIdSidecar(BaseModel):
    """Sidecar gold-id map written beside compact sources, never into manifests.

    Attributes:
        schema_version: Frozen sidecar schema identifier.
        holdout_opened: Always false; this materializer cannot open holdout.
        runtime_owner: Always ``phase_4``.
        splits: Open splits that contributed cases.
        case_count: Number of distinct cases in ``records``.
        records: Synthetic-to-real identifier rows.
        sidecar_sha256: SHA-256 of the canonical JSON without this field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase4-gold-id-map-v1"] = SIDECAR_SCHEMA_VERSION
    holdout_opened: Literal[False] = False
    runtime_owner: Literal["phase_4"] = "phase_4"
    splits: tuple[str, ...]
    case_count: int = Field(ge=0)
    records: tuple[GoldIdRecord, ...]
    sidecar_sha256: str | None = None


def select_phase4_retrieve_cases(
    *,
    split: OpenSplitName = "open",
    cases: Sequence[EvaluationCase] | None = None,
    limit: int | None = None,
) -> list[EvaluationCase]:
    """Return Phase-4-owned open-split cases eligible for Hybrid retrieve eval.

    Loads development, qualification, or both via the holdout-blind loaders.
    Relationship, multi-hop, graph-mapping, and prompt-injection classes are
    excluded even if a caller injects them.

    Args:
        split: ``open`` (development+qualification), ``development``, or
            ``qualification``.
        cases: Optional preloaded cases. When omitted, open-split loaders run.
        limit: Optional maximum case count after filtering and id sort.

    Returns:
        Filtered cases ordered by ``case_id``.

    Raises:
        ValueError: If ``limit`` is not positive.
    """

    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer")
    if cases is not None:
        loaded = list(cases)
    elif split == "development":
        loaded = load_development_cases()
    elif split == "qualification":
        loaded = load_qualification_cases()
    else:
        loaded = load_open_splits()
    selected = [case for case in loaded if _is_phase4_retrieve_case(case)]
    selected.sort(key=lambda item: item.case_id)
    if limit is not None:
        return selected[:limit]
    return selected


def document_visibility_for_case(case: EvaluationCase) -> DocumentVisibility:
    """Return canonical visibility for one labeled case.

    ACL-negative labels and restricted actors persist as ``restricted`` so gold
    is never indexed as globally public.

    Args:
        case: Open-split evaluation case.

    Returns:
        ``restricted`` or ``company_visible``.
    """

    if case.query_class is QueryClass.ACL_NEGATIVE:
        return "restricted"
    if case.acl_actor.restricted:
        return "restricted"
    if any(not link.visible_to_actor for link in case.evidence_links):
        return "restricted"
    return "company_visible"


def build_compact_source(case: EvaluationCase) -> CompactEvalSource:
    """Build a compact markdown source, plus CSV when the case is tabular.

    The body includes gold codes, aliases, acceptable answers, Arabic query
    text when present, and synthetic gold-id markers for sidecar matching.

    Args:
        case: Phase-4-owned open-split case.

    Returns:
        Frozen compact source. Does not write files.
    """

    visibility = document_visibility_for_case(case)
    lines = [
        "# Overview",
        "",
        f"Case {case.case_id} class {case.query_class.value}.",
        f"Family {case.source_family_id}.",
        f"Query: {case.query}",
        "",
    ]
    for code in _field_strings(case.expected_profile.codes):
        lines.append(f"Identifier code {code} is documented in this overview.")
    for alias in _field_strings(case.expected_profile.approved_aliases):
        lines.append(f"Approved alias {alias} refers to the same identifier.")
    for answer in case.acceptable_answers:
        lines.append(f"Acceptable answer: {answer}")
    for link in case.evidence_links:
        if link.chunk_id:
            lines.append(f"{GOLD_CHUNK_MARKER}{link.chunk_id}")
            page = link.locator.get("page", "1")
            section = link.locator.get("section", "Overview")
            lines.append(f"Locator page {page} section {section}.")
        if link.table_id:
            lines.append(f"{GOLD_TABLE_MARKER}{link.table_id}")
            sheet = link.locator.get("sheet", "Summary")
            cell_range = link.locator.get("range", "B2:B20")
            lines.append(f"Table sheet {sheet} range {cell_range}.")
    markdown = "\n".join(lines).rstrip() + "\n"
    table_csv: str | None = None
    table_filename: str | None = None
    if case.query_class is QueryClass.TABULAR_AGGREGATION:
        table_csv = _tabular_csv(case)
        table_filename = f"{case.case_id}.csv"
    return CompactEvalSource(
        case_id=case.case_id,
        split=case.split.value,
        query_class=case.query_class.value,
        markdown_text=markdown,
        markdown_filename=f"{case.case_id}.md",
        table_csv=table_csv,
        table_filename=table_filename,
        visibility=visibility,
        labeled_actor_id=case.acl_actor.actor_id,
        restricted_actor=case.acl_actor.restricted,
    )


def write_compact_sources(
    cases: Sequence[EvaluationCase],
    output_dir: Path,
) -> list[CompactEvalSource]:
    """Write compact markdown and tabular CSV files under ``output_dir/sources``.

    Args:
        cases: Filtered Phase-4-owned cases.
        output_dir: Caller-supplied directory. Must not be the sealed
            ``manifests`` folder.

    Returns:
        Compact sources in the same order as ``cases``.

    Raises:
        ValueError: If ``output_dir`` targets sealed dataset manifests.

    Side Effects:
        Creates ``sources/*.md`` and ``sources/*.csv`` for tabular cases.
    """

    _reject_sealed_manifest_dir(output_dir)
    source_dir = output_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    written: list[CompactEvalSource] = []
    for case in cases:
        source = build_compact_source(case)
        (source_dir / source.markdown_filename).write_text(
            source.markdown_text, encoding="utf-8"
        )
        if source.table_csv is not None and source.table_filename is not None:
            (source_dir / source.table_filename).write_text(
                source.table_csv, encoding="utf-8"
            )
        written.append(source)
    return written


def map_gold_ids(
    case: EvaluationCase,
    *,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    chunk_texts: Sequence[tuple[UUID, str]] = (),
    table_ids: Sequence[UUID] = (),
) -> tuple[GoldIdRecord, ...]:
    """Map synthetic gold ids on one case to optional real persist UUIDs.

    Args:
        case: Phase-4-owned case whose evidence links carry synthetic ids.
        document_id: Real document UUID after Hybrid Ready persist.
        version_id: Real version UUID after persist.
        chunk_texts: Real chunk id and raw text pairs used for marker match.
        table_ids: Real table UUIDs for the persisted version.

    Returns:
        One record per evidence link, or a single empty-evidence record.
    """

    visibility = document_visibility_for_case(case)
    actor_id = case.acl_actor.actor_id
    restricted = case.acl_actor.restricted
    if not case.evidence_links:
        return (
            GoldIdRecord(
                case_id=case.case_id,
                split=case.split.value,
                query_class=case.query_class.value,
                document_id=document_id,
                version_id=version_id,
                table_id=table_ids[0] if table_ids else None,
                visibility=visibility,
                labeled_actor_id=actor_id,
                restricted_actor=restricted,
                visible_to_actor=True,
            ),
        )
    records: list[GoldIdRecord] = []
    for link in case.evidence_links:
        chunk_id = (
            _match_marked_id(link.chunk_id, chunk_texts, GOLD_CHUNK_MARKER)
            if link.chunk_id
            else None
        )
        table_id = table_ids[0] if link.table_id and table_ids else None
        records.append(
            GoldIdRecord(
                case_id=case.case_id,
                split=case.split.value,
                query_class=case.query_class.value,
                synthetic_chunk_id=link.chunk_id,
                synthetic_table_id=link.table_id,
                synthetic_source_id=link.source_id,
                synthetic_version_id=link.version_id,
                chunk_id=chunk_id,
                table_id=table_id,
                document_id=document_id,
                version_id=version_id,
                visibility=visibility,
                labeled_actor_id=actor_id,
                restricted_actor=restricted,
                visible_to_actor=link.visible_to_actor,
            )
        )
    return tuple(records)


def build_sidecar(
    cases: Sequence[EvaluationCase],
    *,
    persist_index: dict[str, PersistMapping] | None = None,
) -> GoldIdSidecar:
    """Assemble a holdout-closed sidecar for the supplied open-split cases.

    Args:
        cases: Filtered Phase-4-owned cases.
        persist_index: Optional mapping of case id to live persist results.

    Returns:
        Sidecar model with ``holdout_opened=False`` and a content digest.
    """

    records: list[GoldIdRecord] = []
    splits: list[str] = []
    seen_splits: set[str] = set()
    for case in cases:
        document_id = None
        version_id = None
        chunk_texts: Sequence[tuple[UUID, str]] = ()
        table_ids: Sequence[UUID] = ()
        if persist_index is not None and case.case_id in persist_index:
            mapping = persist_index[case.case_id]
            document_id = mapping.document_id
            version_id = mapping.version_id
            chunk_texts = mapping.chunk_texts
            table_ids = mapping.table_ids
        records.extend(
            map_gold_ids(
                case,
                document_id=document_id,
                version_id=version_id,
                chunk_texts=chunk_texts,
                table_ids=table_ids,
            )
        )
        if case.split.value not in seen_splits:
            seen_splits.add(case.split.value)
            splits.append(case.split.value)
    sidecar = GoldIdSidecar(
        splits=tuple(splits),
        case_count=len({case.case_id for case in cases}),
        records=tuple(records),
    )
    digest = sidecar_sha256(sidecar)
    return sidecar.model_copy(update={"sidecar_sha256": digest})


def sidecar_sha256(sidecar: GoldIdSidecar) -> str:
    """Return SHA-256 of canonical sidecar JSON excluding the digest field.

    Args:
        sidecar: Sidecar model, possibly with ``sidecar_sha256`` already set.

    Returns:
        Hex digest of sorted JSON without ``sidecar_sha256``.
    """

    payload = sidecar.model_dump(mode="json", exclude={"sidecar_sha256"})
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_sidecar(sidecar: GoldIdSidecar, output_dir: Path) -> Path:
    """Write ``gold_id_map.json`` under ``output_dir``.

    Args:
        sidecar: Completed sidecar including digest.
        output_dir: Caller-supplied directory. Must not be sealed manifests.

    Returns:
        Path of the written JSON file.

    Raises:
        ValueError: If ``output_dir`` targets sealed dataset manifests.

    Side Effects:
        Overwrites ``gold_id_map.json`` in ``output_dir``.
    """

    _reject_sealed_manifest_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "gold_id_map.json"
    payload = sidecar.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def materialize_phase4_eval_corpus(
    *,
    output_dir: Path,
    split: OpenSplitName = "open",
    limit: int | None = None,
    persist_index: dict[str, PersistMapping] | None = None,
) -> GoldIdSidecar:
    """Filter open splits, write compact sources, and write the sidecar map.

    Args:
        output_dir: Destination for ``sources/`` and ``gold_id_map.json``.
        split: Open-split selector passed to ``select_phase4_retrieve_cases``.
        limit: Optional case cap for smoke runs.
        persist_index: Optional live persist results keyed by case id.

    Returns:
        Written sidecar model.

    Side Effects:
        Writes compact sources and ``gold_id_map.json``. Does not mutate sealed
        dataset manifests and does not open holdout labels.
    """

    cases = select_phase4_retrieve_cases(split=split, limit=limit)
    write_compact_sources(cases, output_dir)
    sidecar = build_sidecar(cases, persist_index=persist_index)
    write_sidecar(sidecar, output_dir)
    return sidecar


def _is_phase4_retrieve_case(case: EvaluationCase) -> bool:
    """Return whether a case may be materialized for Phase 4 retrieve eval.

    Args:
        case: Candidate evaluation case.

    Returns:
        True when the case is an open-split Phase-4-owned retrieve class.
    """

    if case.split not in _OPEN_SPLITS:
        return False
    if case.runtime_owner is not RuntimeOwner.PHASE_4:
        return False
    if class_runtime_owner(case.query_class) is not RuntimeOwner.PHASE_4:
        return False
    return case.query_class not in _DEFERRED_QUERY_CLASSES


def _field_strings(field: ProfileField) -> list[str]:
    """Extract string values from one labeled profile field.

    Args:
        field: Codes, aliases, or similar list-or-string field.

    Returns:
        Non-empty string values.
    """

    value = field.value
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _tabular_csv(case: EvaluationCase) -> str:
    """Build a compact Summary-sheet CSV containing gold codes and amounts.

    Args:
        case: Tabular aggregation case.

    Returns:
        UTF-8 CSV text with a header row and gold markers.
    """

    codes = _field_strings(case.expected_profile.codes)
    code = codes[0] if codes else case.case_id
    table_id = next(
        (link.table_id for link in case.evidence_links if link.table_id), ""
    )
    project = ""
    for token in case.query.split():
        if token.startswith("PRJ-"):
            project = token
            break
    rows = [
        "sheet,gold_table_id,project,code,amount",
        f"Summary,{table_id},{project},{code},10",
        f"Summary,{table_id},{project},{code},15",
        f"Summary,{table_id},{project},{code},20",
    ]
    return "\n".join(rows) + "\n"


def _match_marked_id(
    synthetic_id: str,
    chunk_texts: Sequence[tuple[UUID, str]],
    marker_prefix: str,
) -> UUID | None:
    """Return the real chunk UUID whose text contains a synthetic gold marker.

    Args:
        synthetic_id: Generator gold id.
        chunk_texts: Persisted chunk id and raw text pairs.
        marker_prefix: ``gold_chunk_id=`` or ``gold_table_id=``.

    Returns:
        Matching chunk UUID, the sole chunk when only one exists, or ``None``.
    """

    needle = f"{marker_prefix}{synthetic_id}"
    matches = [
        chunk_id
        for chunk_id, text in chunk_texts
        if needle in text or synthetic_id in text
    ]
    if matches:
        return matches[0]
    if len(chunk_texts) == 1:
        return chunk_texts[0][0]
    return None


def _reject_sealed_manifest_dir(output_dir: Path) -> None:
    """Refuse to write into the sealed dataset manifest directory.

    Args:
        output_dir: Caller-supplied destination.

    Raises:
        ValueError: If the path is the frozen ``manifests`` directory.
    """

    resolved = output_dir.resolve()
    if resolved.name == "manifests":
        raise ValueError("refusing to mutate sealed dataset manifests")
