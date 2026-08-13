# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Deterministic HTML main-content and boilerplate cleaning."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from smart_rag_core.ingestion.parser.types import HtmlLocator, RemovalDiagnostic

_BOILERPLATE_TAGS = frozenset({"nav", "footer", "aside", "script", "style", "noscript"})
_BOILERPLATE_CLASS_KEYWORDS = (
    "cookie",
    "banner",
    "sidebar",
    "menu",
    "navigation",
    "advert",
    "ad-",
)


def extract_main_content(
    html: str,
    *,
    source_url: str | None = None,
) -> tuple[BeautifulSoup, tuple[RemovalDiagnostic, ...]]:
    """Remove navigation/cookie/sidebar boilerplate using deterministic rules.

    Args:
        html: Raw HTML snapshot bytes decoded as UTF-8 with replacement.
        source_url: Optional crawl URL for locator provenance.

    Returns:
        Parsed soup limited to main/article/body content and removal diagnostics.
    """

    soup = BeautifulSoup(html, "lxml")
    removals: list[RemovalDiagnostic] = []
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag):
            continue
        if _is_boilerplate(tag):
            preview = tag.get_text(" ", strip=True)[:120]
            removals.append(
                RemovalDiagnostic(
                    reason="html_boilerplate",
                    text_preview=preview,
                    locator=HtmlLocator(
                        dom_path=_dom_path(tag),
                        element_index=0,
                        source_url=source_url,
                        removed_boilerplate=True,
                    ),
                )
            )
            tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main, tuple(removals)


def _is_boilerplate(tag: Tag) -> bool:
    """Return whether a tag matches boilerplate heuristics."""

    if tag.name in _BOILERPLATE_TAGS:
        return True
    class_text = " ".join(tag.get("class", [])).lower()
    id_text = str(tag.get("id", "")).lower()
    haystack = f"{class_text} {id_text}"
    return any(keyword in haystack for keyword in _BOILERPLATE_CLASS_KEYWORDS)


def _dom_path(tag: Tag) -> tuple[str, ...]:
    """Build a simple DOM path for diagnostics."""

    parts: list[str] = []
    current: Tag | None = tag
    while current is not None and current.name:
        parts.append(current.name)
        current = current.parent if isinstance(current.parent, Tag) else None
    parts.reverse()
    return tuple(parts)
