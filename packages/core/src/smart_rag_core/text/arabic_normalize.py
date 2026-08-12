"""Versioned Arabic search-form normalization shared by SQL and ParadeDB paths.

Raw citation text and logical offsets must never use this search form. The
Python implementation is the byte-identical twin of
``search.normalize_arabic_v1`` in the Phase 2 Supabase migration.
"""

from __future__ import annotations

import re
import unicodedata

ARABIC_NORMALIZATION_VERSION = "arabic_norm_v1"

_DIACRITICS_AND_TATWEEL = re.compile("[\u064b-\u065f\u0670\u0640\u06d6-\u06ed]")
_WHITESPACE = re.compile(r"\s+")
# Preserve hyphen so codes like PO-7781 stay contiguous for lexical match.
_PUNCT_TO_SPACE = re.compile(r"[^\w\s-]+", flags=re.UNICODE)

# Alef/hamza variants, ya/alef-maqsura, ta-marbuta, Arabic-Indic digits.
# Unicode escapes keep Ruff RUF001 from treating intentional Arabic as typos.
_TRANSLATE = str.maketrans(
    {
        "\u0623": "\u0627",  # alef with hamza above -> alef
        "\u0625": "\u0627",  # alef with hamza below -> alef
        "\u0622": "\u0627",  # alef with madda -> alef
        "\u0671": "\u0627",  # alef wasla -> alef
        "\u0624": "\u0648",  # waw with hamza -> waw
        "\u0626": "\u064a",  # yeh with hamza -> yeh
        "\u0649": "\u064a",  # alef maqsura -> yeh
        "\u0629": "\u0647",  # teh marbuta -> heh
        "\u0660": "0",
        "\u0661": "1",
        "\u0662": "2",
        "\u0663": "3",
        "\u0664": "4",
        "\u0665": "5",
        "\u0666": "6",
        "\u0667": "7",
        "\u0668": "8",
        "\u0669": "9",
    }
)


def normalize_arabic_v1(text: str) -> str:
    """Return the ``arabic_norm_v1`` search form for BM25 projection/query text.

    Args:
        text: Raw Unicode text. Empty string is allowed and returns empty.

    Returns:
        NFC-normalized, diacritic/tatweel-stripped, alef/ya/digit-folded,
        Latin-lowercased, punctuation-collapsed, whitespace-collapsed search
        text. Idempotent for already-normalized input.

    Side Effects:
        None. Does not mutate citation/raw storage forms.
    """

    if text == "":
        return ""

    value = unicodedata.normalize("NFC", text)
    value = _DIACRITICS_AND_TATWEEL.sub("", value)
    value = value.translate(_TRANSLATE)
    value = value.casefold()
    value = _PUNCT_TO_SPACE.sub(" ", value)
    value = _WHITESPACE.sub(" ", value).strip()
    return value
