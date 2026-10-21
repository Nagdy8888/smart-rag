"""Presentation-only lexical hints for Arabic questions over bilingual evidence."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_literals import significant_query_terms
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

# These are vocabulary glosses, not answers, source IDs, filters, or retrieval
# rewrites. Arabic terms remain eligible for Arabic source records as well.
_GLOSSES = (
    (("انسان", "بشر"), ("human",)),
    (("مسوول", "ادوار", "دور"), ("responsib", "role")),
    (("تعاون", "معا"), ("collaborat",)),
    (("وكيل", "وكلاء"), ("agent",)),
    (("ذاكر",), ("memory",)),
    (("معرف",), ("knowledge",)),
    (("مراقب", "رصد"), ("monitor",)),
    (("انتاج",), ("production",)),
    (("تهديد", "هجم", "امن"), ("threat", "attack", "security")),
)
_STOP = frozenset(
    {"كيف", "ماذا", "عندما", "المستندات", "تصفها", "اشرح", "التي", "بين", "هذا", "هذه"}
)


def answer_focus_terms(query: str) -> tuple[str, ...]:
    """Return original content tokens and bounded Arabic vocabulary glosses.

    Args:
        query: Original user text; no generated rewrite or answer content.

    Returns:
        Deduplicated presentation terms. They cannot retrieve, filter, authorize,
        modify, or enlarge the already fitted evidence.
    """
    normalized = normalize_arabic_v1(query)
    arabic = tuple(
        t for t in re.findall(r"[\u0600-\u06ff]{3,}", normalized) if t not in _STOP
    )
    terms = [*significant_query_terms(query), *arabic]
    for stems, glosses in _GLOSSES:
        if any(stem in word for stem in stems for word in arabic):
            terms.extend(glosses)
    return tuple(dict.fromkeys(terms))
