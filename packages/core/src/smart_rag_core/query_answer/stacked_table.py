"""Display-only conversion of repeated bold field/value records into Markdown."""

from __future__ import annotations

import re


def repair_missing_row_header(text: str) -> str:
    """Add an empty row-label header only when every data row proves one extra column."""
    lines = text.splitlines()
    for index in range(len(lines) - 2):
        if not lines[index].strip().startswith("|"):
            continue
        header = re.split(r"(?<!\\)\|", lines[index].strip().strip("|"))
        separator = re.split(r"(?<!\\)\|", lines[index + 1].strip().strip("|"))
        if (
            len(header) < 2
            or len(separator) != len(header)
            or not all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in separator)
        ):
            continue
        data: list[list[str]] = []
        for line in lines[index + 2 :]:
            if not line.strip().startswith("|"):
                break
            data.append(re.split(r"(?<!\\)\|", line.strip().strip("|")))
        if data and all(len(row) == len(header) + 1 for row in data):
            lines[index] = "| |" + lines[index].strip()[1:]
            lines[index + 1] = "| --- |" + lines[index + 1].strip()[1:]
            return "\n".join(lines)
    return text


def stacked_records_to_table(text: str) -> str | None:
    """Convert only complete repeated records; never guess missing cells or reorder values."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) % 2:
        return None
    pairs: list[tuple[str, str]] = []
    for offset in range(0, len(lines), 2):
        label = re.fullmatch(r"\*\*([^*\n]{1,60})\*\*:?", lines[offset])
        if label is None or lines[offset + 1].startswith("**"):
            return None
        pairs.append((label[1], lines[offset + 1]))
    first = pairs[0][0]
    width = next((i for i, pair in enumerate(pairs[1:], 1) if pair[0] == first), 0)
    if not 2 <= width <= 8 or len(pairs) % width or len(pairs) // width < 2:
        return None
    headers = [key for key, _ in pairs[:width]]
    if len(set(headers)) != width:
        return None
    rows: list[list[str]] = []
    for offset in range(0, len(pairs), width):
        record = pairs[offset : offset + width]
        if [key for key, _ in record] != headers:
            return None
        rows.append([value.replace("|", "\\|") for _, value in record])
    return "\n".join(
        "| " + " | ".join(row) + " |" for row in (headers, ["---"] * width, *rows)
    )
