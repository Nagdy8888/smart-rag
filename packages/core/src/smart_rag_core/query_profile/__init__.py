"""Typed query profiling: deterministic extract, one optional model call, eval."""

from smart_rag_core.query_profile.fewshots import (
    FewShotManifestError,
    load_fewshot_manifest,
)
from smart_rag_core.query_profile.models import (
    ModelInferredProfile,
    ProfileFallbackReason,
    QueryProfileResult,
)
from smart_rag_core.query_profile.phase6_map import (
    PHASE6_EXTENSION_FAMILIES,
    QUERY_TYPE_BASE_FAMILY,
    Phase6FamilyMapResult,
    Phase6Limitation,
    Phase6RouteFamily,
    map_query_type_to_phase6_family,
)
from smart_rag_core.query_profile.profiler import profile_query, profile_query_sync
from smart_rag_core.query_profile.runner import evaluate_open_splits
from smart_rag_core.query_profile.versions import (
    PROFILE_MODEL_VERSION,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)

__all__ = [
    "PHASE6_EXTENSION_FAMILIES",
    "PROFILE_MODEL_VERSION",
    "PROFILE_PROMPT_SHA256",
    "PROFILE_PROMPT_VERSION",
    "QUERY_TYPE_BASE_FAMILY",
    "FewShotManifestError",
    "ModelInferredProfile",
    "Phase6FamilyMapResult",
    "Phase6Limitation",
    "Phase6RouteFamily",
    "ProfileFallbackReason",
    "QueryProfileResult",
    "evaluate_open_splits",
    "load_fewshot_manifest",
    "map_query_type_to_phase6_family",
    "profile_query",
    "profile_query_sync",
]
