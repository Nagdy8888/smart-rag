"""Pinned Hybrid rerank prompt and model versions."""

from __future__ import annotations

from smart_rag_core.models.env_pins import RERANK_MODEL_ID

RERANK_PROMPT_VERSION = "rerank_v2"
RERANK_PROMPT_SHA256 = (
    "995a87d869b3330aac0b5e2d64b764a32cc8542c7d85d9182118945ce9560cab"
)
RERANK_V1_PROMPT_SHA256 = (
    "4767049107cfe6e8591c84d3b1d202393dfd2564383e6c5bfa0bd5fece8f1925"
)
"""Immutable ``rerank_v1.md`` digest, kept for replay and pin tests."""
RERANK_LABEL_PREFIX = "c"
"""``rerank_v2`` candidate labels are ``c01`` to ``c20`` in pool order."""
RERANK_MODEL_VERSION = RERANK_MODEL_ID
