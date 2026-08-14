"""Canonical Phase 4 query-class identifiers and minimum corpus counts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class QueryClass(StrEnum):
    """Labeled query class for the Phase 4 evaluation corpus."""

    EXACT_CODE = "exact_code"
    ALIAS = "alias"
    TYPO = "typo"
    SEMANTIC_FACTUAL = "semantic_factual"
    ARABIC_MIXED = "arabic_mixed"
    SELECTIVE_METADATA_FILTER = "selective_metadata_filter"
    LATEST_AS_OF = "latest_as_of"
    MULTI_PART = "multi_part"
    RELATIONSHIP = "relationship"
    MULTI_HOP = "multi_hop"
    BROAD_SYNTHESIS = "broad_synthesis"
    TABULAR_AGGREGATION = "tabular_aggregation"
    INSUFFICIENT_REFUSAL = "insufficient_refusal"
    GRAPH_MAPPING = "graph_mapping"
    ACL_NEGATIVE = "acl_negative"
    PROFILE_FIDELITY = "profile_fidelity"
    NEGATION = "negation"
    DOCUMENT_SUMMARY = "document_summary"
    MIXED_LOCALE_TEMPORAL = "mixed_locale_temporal"
    MEDIA_LIMITATION = "media_limitation"
    PROMPT_INJECTION = "prompt_injection"


class RuntimeOwner(StrEnum):
    """Phase that may execute the labeled case at runtime."""

    PHASE_4 = "phase_4"
    PHASE_5 = "phase_5"
    PHASE_5_AND_6 = "phase_5_and_6"
    PHASE_6 = "phase_6"
    PHASE_8 = "phase_8"


CLASS_MINIMUMS: dict[QueryClass, int] = {
    QueryClass.EXACT_CODE: 25,
    QueryClass.ALIAS: 20,
    QueryClass.TYPO: 15,
    QueryClass.SEMANTIC_FACTUAL: 35,
    QueryClass.ARABIC_MIXED: 20,
    QueryClass.SELECTIVE_METADATA_FILTER: 15,
    QueryClass.LATEST_AS_OF: 15,
    QueryClass.MULTI_PART: 20,
    QueryClass.RELATIONSHIP: 30,
    QueryClass.MULTI_HOP: 30,
    QueryClass.BROAD_SYNTHESIS: 15,
    QueryClass.TABULAR_AGGREGATION: 20,
    QueryClass.INSUFFICIENT_REFUSAL: 20,
    QueryClass.GRAPH_MAPPING: 20,
    QueryClass.ACL_NEGATIVE: 20,
    QueryClass.PROFILE_FIDELITY: 20,
    QueryClass.NEGATION: 10,
    QueryClass.DOCUMENT_SUMMARY: 10,
    QueryClass.MIXED_LOCALE_TEMPORAL: 10,
    QueryClass.MEDIA_LIMITATION: 5,
    QueryClass.PROMPT_INJECTION: 30,
}

TOTAL_MINIMUM_CASES = 405


class ClassCountRow(BaseModel):
    """One class count used in split and corpus reports.

    Attributes:
        query_class: Canonical class identifier.
        minimum: Signed minimum from the Phase 4 corpus matrix.
        actual: Observed labeled count.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    query_class: QueryClass
    minimum: int = Field(ge=1)
    actual: int = Field(ge=0)


def class_runtime_owner(query_class: QueryClass) -> RuntimeOwner:
    """Return the phase that may execute a labeled class.

    Args:
        query_class: Canonical evaluation class.

    Returns:
        Owning runtime phase. Labels still exist in Phase 4 for deferred
        classes; executing them cannot pass Phase 4.
    """

    deferred = {
        QueryClass.RELATIONSHIP: RuntimeOwner.PHASE_5_AND_6,
        QueryClass.MULTI_HOP: RuntimeOwner.PHASE_5_AND_6,
        QueryClass.GRAPH_MAPPING: RuntimeOwner.PHASE_5,
        QueryClass.PROMPT_INJECTION: RuntimeOwner.PHASE_6,
    }
    return deferred.get(query_class, RuntimeOwner.PHASE_4)
