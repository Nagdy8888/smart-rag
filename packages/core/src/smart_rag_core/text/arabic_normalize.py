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
_TRANSLATE = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ؤ": "و",
        "ئ": "ي",
        "ى": "ي",
        "ة": "ه",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
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
