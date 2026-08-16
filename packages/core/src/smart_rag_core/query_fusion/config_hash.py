"""SHA-256 of the frozen Combined fusion configuration."""

from __future__ import annotations

import hashlib
import json

from smart_rag_core.query_fusion.constants import (
    AGREEMENT_CAP,
    EDGE_SUPPORT_MULTIPLIER_CAP,
    EDGE_SUPPORT_MULTIPLIER_STEP,
    FUSION_DOCUMENT_QUOTA,
    FUSION_FINAL_EVIDENCE_MAX,
    FUSION_RRF_K,
    FUSION_SECTION_QUOTA,
    FUSION_SURVIVAL_THRESHOLD,
    GRAPH_DISCOVERED_ONLY_CAP,
    GRAPH_WEIGHT,
    HOP_PENALTY,
)
from smart_rag_core.query_fusion.models import FusionAlgorithm


def fusion_config_payload(algorithm: FusionAlgorithm) -> dict[str, object]:
    """Return the canonical frozen-constant mapping for one algorithm.

    Args:
        algorithm: Selected ranking algorithm.

    Returns:
        JSON-serializable mapping used for the configuration hash.
    """

    return {
        "algorithm": algorithm.value,
        "agreement_cap": AGREEMENT_CAP,
        "document_quota": FUSION_DOCUMENT_QUOTA,
        "edge_support_multiplier_cap": EDGE_SUPPORT_MULTIPLIER_CAP,
        "edge_support_multiplier_step": EDGE_SUPPORT_MULTIPLIER_STEP,
        "final_evidence_max": FUSION_FINAL_EVIDENCE_MAX,
        "graph_discovered_only_cap": GRAPH_DISCOVERED_ONLY_CAP,
        "graph_weight": GRAPH_WEIGHT,
        "hop_penalty": HOP_PENALTY,
        "rrf_k": FUSION_RRF_K,
        "section_quota": FUSION_SECTION_QUOTA,
        "survival_threshold": FUSION_SURVIVAL_THRESHOLD,
    }


def fusion_config_hash(algorithm: FusionAlgorithm) -> str:
    """Return the SHA-256 hex digest of the frozen fusion configuration.

    Args:
        algorithm: Selected ranking algorithm.

    Returns:
        64-character lowercase hex digest.
    """

    encoded = json.dumps(
        fusion_config_payload(algorithm),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
