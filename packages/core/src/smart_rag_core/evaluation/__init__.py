"""Phase 4 evaluation dataset contracts: schema, splits, holdout, and labels."""

from smart_rag_core.evaluation.calibration import load_tuning_cases
from smart_rag_core.evaluation.classes import (
    CLASS_MINIMUMS,
    TOTAL_MINIMUM_CASES,
    QueryClass,
)
from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.loader import (
    load_cases,
    load_development_cases,
    load_open_splits,
    load_qualification_cases,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
)
from smart_rag_core.evaluation.validation import validate_corpus

__all__ = [
    "CLASS_MINIMUMS",
    "DATASET_SCHEMA_VERSION",
    "LABEL_REVISION",
    "TOTAL_MINIMUM_CASES",
    "DatasetSplit",
    "EvaluationCase",
    "HoldoutAccess",
    "HoldoutSealedError",
    "QueryClass",
    "generate_corpus",
    "load_cases",
    "load_development_cases",
    "load_open_splits",
    "load_qualification_cases",
    "load_tuning_cases",
    "validate_corpus",
]
