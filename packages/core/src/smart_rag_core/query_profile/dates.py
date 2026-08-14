"""Gregorian date parser ``gregorian_v1``.

Hijri calendar values are never authoritative ``effective_at`` dates in v1.
Zero-padded first slash tokens are day-month-year; otherwise month-day-year
is preferred so mixed ``01/06/2024 versus 6/1/2024`` fixtures resolve to one
ISO day.
"""

from __future__ import annotations

import calendar
import re

from smart_rag_core.query_profile.versions import DATE_PARSER_VERSION

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _choose_slash_date(first_token: str, second_token: str, year: int) -> str | None:
    """Select one Gregorian day from a slash date using ``gregorian_v1`` rules.

    A zero-padded first token is read as day-month-year. Otherwise month-day-year
    is preferred. If the preferred reading is invalid, the alternate is used
    when it is the only valid civil day.

    Args:
        first_token: Text before the first slash.
        second_token: Text between slashes.
        year: Four-digit year.

    Returns:
        One ISO date, or ``None`` when both readings are valid without a pad
        hint and they disagree.
    """

    first = int(first_token)
    second = int(second_token)
    mdy = _iso(year, first, second) if _valid_gregorian(year, first, second) else None
    dmy = _iso(year, second, first) if _valid_gregorian(year, second, first) else None
    if mdy is not None and mdy == dmy:
        return mdy
    prefer_dmy = len(first_token) == 2 and first_token.startswith("0")
    if prefer_dmy:
        return dmy or mdy
    if mdy is not None and dmy is None:
        return mdy
    if dmy is not None and mdy is None:
        return dmy
    return mdy



def _valid_gregorian(year: int, month: int, day: int) -> bool:
    """Return whether the civil Gregorian triple is a real calendar day.

    Args:
        year: Civil year.
        month: Month number.
        day: Day of month.

    Returns:
        True when the date exists.
    """

    if month < 1 or month > 12 or day < 1:
        return False
    return day <= calendar.monthrange(year, month)[1]


def _iso(year: int, month: int, day: int) -> str:
    """Format a validated Gregorian day as ISO-8601.

    Args:
        year: Civil year.
        month: Month number.
        day: Day of month.

    Returns:
        ``YYYY-MM-DD``.
    """

    return f"{year:04d}-{month:02d}-{day:02d}"


def _append_unique(ordered: list[str], seen: set[str], value: str) -> None:
    """Append ``value`` once to the first-seen date list.

    Args:
        ordered: Output ISO dates.
        seen: Dates already recorded.
        value: Candidate ISO date.
    """

    if value not in seen:
        seen.add(value)
        ordered.append(value)


def parse_gregorian_v1(text: str) -> tuple[str, ...]:
    """Extract authoritative Gregorian ISO dates from query text.

    Args:
        text: Original query. Hijri month names are ignored.

    Returns:
        Deduplicated ISO dates in first-seen order. Parser version is
        ``gregorian_v1``.

    Side Effects:
        None.
    """

    if DATE_PARSER_VERSION != "gregorian_v1":
        raise RuntimeError("unexpected date parser version")
    ordered: list[str] = []
    seen: set[str] = set()
    for match in _ISO.finditer(text):
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if _valid_gregorian(year, month, day):
            _append_unique(ordered, seen, _iso(year, month, day))
    for match in _SLASH.finditer(text):
        chosen = _choose_slash_date(match.group(1), match.group(2), int(match.group(3)))
        if chosen is not None:
            _append_unique(ordered, seen, chosen)
    return tuple(ordered)
