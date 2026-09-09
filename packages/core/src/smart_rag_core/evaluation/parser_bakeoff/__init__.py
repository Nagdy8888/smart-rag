"""Public contracts for the isolated PDF parser bake-off."""

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_LANE,
    ANYDOC_PACKAGE_VERSION,
    CURRENT_LANE,
    SCHEMA_VERSION,
    SELECTED_PDF_RELATIVE,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    ChunkSummary,
    Classification,
    CleanupReceipt,
    ComparisonReport,
    GoldMap,
    LaneIngestIds,
    NeutralCaseSet,
)

__all__ = [
    "ANYDOC_LANE",
    "ANYDOC_PACKAGE_VERSION",
    "CURRENT_LANE",
    "SCHEMA_VERSION",
    "SELECTED_PDF_RELATIVE",
    "BakeoffError",
    "BakeoffManifest",
    "ChunkSummary",
    "Classification",
    "CleanupReceipt",
    "ComparisonReport",
    "GoldMap",
    "LaneId",
    "LaneIngestIds",
    "NeutralCaseSet",
]
