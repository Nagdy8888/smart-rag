"""Derive a presentation language from the original question, never sources."""

from __future__ import annotations

import re
from typing import Literal


def requested_answer_language(query: str) -> Literal["ar", "en"]:
    """Honor an explicit language request, then the dominant question script.

    Args:
        query: Original bounded user question, not a retrieval rewrite.

    Returns:
        Arabic or English for prose; verbatim artifacts retain their language.
    """
    if re.search(
        r"(?i)(?:answer|respond|explain)\s+in\s+English|بالإنجليزية|بالانجليزية", query
    ):
        return "en"
    if re.search(
        r"(?i)(?:answer|respond|explain)\s+in\s+Arabic|بالعربية|باللغة العربية", query
    ):
        return "ar"
    arabic = len(re.findall(r"[\u0620-\u064a\u066e-\u06d3]", query))
    latin = len(re.findall(r"[A-Za-z]", query))
    return "ar" if arabic > latin else "en"
