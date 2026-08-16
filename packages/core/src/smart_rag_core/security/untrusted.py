"""Escape untrusted source, OCR, crawl, and citation text for JSON APIs.

The API never returns ``text/html`` for untrusted content. JSON string
values are HTML-escaped so a raw ``<script>`` cannot appear in responses.
Frontend XSS encoding remains packet 8.
"""

from __future__ import annotations

import html


def isolate_untrusted_text(value: str) -> str:
    """HTML-escape one untrusted string for JSON responses.

    Args:
        value: Source, title, comment, or citation text.

    Returns:
        Escaped plain text. Angle brackets become entities.
    """

    return html.escape(value, quote=True)
