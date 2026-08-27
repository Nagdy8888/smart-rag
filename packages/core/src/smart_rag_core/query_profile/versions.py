"""Pinned query-profile prompt, model, and parser versions."""

from __future__ import annotations

PROFILE_PROMPT_VERSION = "query_profile_v1"
PROFILE_PROMPT_SHA256 = (
    "a5c87258e3837daa2bdbac623d90e4d022817eeff2b8d5e650763d07c2d49a7b"
)
PROFILE_MODEL_ID = "gpt-4o-mini"
ALLOWED_PROFILE_MODEL_IDS = frozenset({PROFILE_MODEL_ID})
PROFILE_MAX_OUTPUT_TOKENS = 1500
PROFILE_MODEL_VERSION = "query-profile-mock-v1"
DATE_PARSER_VERSION = "gregorian_v1"
NORMALIZER_VERSION = "arabic_norm_v1"
MAX_SUBQUESTIONS = 3
MAX_VARIANTS = 3
LOW_CONFIDENCE_HARD_FILTER = 0.7
