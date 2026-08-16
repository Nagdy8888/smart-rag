"""Resolved-path Combined fusion, naive-union ablation, and frozen quotas."""

from smart_rag_core.query_fusion.ablation import (
    decide_algorithm,
    refuse_holdout_tuning,
    run_ablation,
)
from smart_rag_core.query_fusion.assemble import (
    fuse_evidence,
    fusion_input_from_branches,
)
from smart_rag_core.query_fusion.config_hash import fusion_config_hash
from smart_rag_core.query_fusion.constants import (
    AGREEMENT_CAP,
    EDGE_SUPPORT_MULTIPLIER_CAP,
    FUSION_RRF_K,
    GRAPH_DISCOVERED_ONLY_CAP,
    GRAPH_WEIGHT,
    HOP_PENALTY,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.formulas import (
    apply_agreement_multiplier,
    assert_constant_graph_weight,
    combined_rrf_score,
    edge_support_multiplier,
    graph_passage_strength_for_path,
    path_support,
)
from smart_rag_core.query_fusion.models import (
    AblationReport,
    FusionAlgorithm,
    FusionInput,
    FusionResult,
    GraphPassage,
    GraphPathInput,
    HybridPassage,
    ScoredPassage,
)

SELECTED_FUSION_ALGORITHM = FusionAlgorithm.RESOLVED_PATH_FUSION
"""Algorithm frozen after development-fixture ablation in packet 3 tests."""

__all__ = [
    "AGREEMENT_CAP",
    "EDGE_SUPPORT_MULTIPLIER_CAP",
    "FUSION_RRF_K",
    "GRAPH_DISCOVERED_ONLY_CAP",
    "GRAPH_WEIGHT",
    "HOP_PENALTY",
    "SELECTED_FUSION_ALGORITHM",
    "AblationReport",
    "FusionAlgorithm",
    "FusionError",
    "FusionInput",
    "FusionResult",
    "GraphPassage",
    "GraphPathInput",
    "HybridPassage",
    "ScoredPassage",
    "apply_agreement_multiplier",
    "assert_constant_graph_weight",
    "combined_rrf_score",
    "decide_algorithm",
    "edge_support_multiplier",
    "fuse_evidence",
    "fusion_config_hash",
    "fusion_input_from_branches",
    "graph_passage_strength_for_path",
    "path_support",
    "refuse_holdout_tuning",
    "run_ablation",
]
