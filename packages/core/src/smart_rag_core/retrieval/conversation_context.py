"""Resolved conversational context steers ranking but never authorizes evidence."""

from __future__ import annotations

import hashlib
import json
import re

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.query_profile.variants import (
    VariantFidelityError,
    assert_variant_fidelity,
)
from smart_rag_core.retrieval.hybrid_run.profile_fields import str_list_field

_REFERENCE = re.compile(
    r"(?i)\b(?:it|its|those|these|that|them|former|latter|same|previous|earlier|above)\b"
    r"|\u0630\u0644\u0643|\u0647\u0630\u0647|\u062a\u0644\u0643|\u0627\u0644\u0633\u0627\u0628\u0642|\u0646\u0641\u0633|\u0647\u0630\u0627"
)


def contextual_ranking_query(query: str, profile: ExpectedProfile | None) -> str:
    """Use one fidelity-checked variant for a reference or multilingual question."""
    extract = extract_deterministic(query)
    if not _REFERENCE.search(query) and extract.language == "en":
        return query
    variants = str_list_field(profile, "variants")
    if len(variants) != 1 or not 0 < len(variants[0]) <= 2000:
        return query
    candidate = variants[0]
    try:
        assert_variant_fidelity(query, candidate, extract)
    except VariantFidelityError:
        return query
    if not all(number in candidate for number in re.findall(r"\b\d+\b", query)):
        return query
    return candidate


def profile_cache_query(query_normalized: str, profile: ExpectedProfile | None) -> str:
    """Include profile context so identical follow-ups cannot reuse another subject's ranks."""
    if profile is None:
        return query_normalized
    encoded = json.dumps(
        profile.model_dump(mode="json"), sort_keys=True, ensure_ascii=True
    )
    digest = hashlib.sha256(
        (query_normalized + "\0" + encoded).encode("utf8")
    ).hexdigest()
    return "profile-context:" + digest
