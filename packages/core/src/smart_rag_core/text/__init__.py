"""Shared text transforms used across deployables."""

from smart_rag_core.text.arabic_normalize import (
    ARABIC_NORMALIZATION_VERSION,
    normalize_arabic_v1,
)

__all__ = [
    "ARABIC_NORMALIZATION_VERSION",
    "normalize_arabic_v1",
]
