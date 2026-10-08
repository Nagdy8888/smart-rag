"""Debug Table 10-2 extract heading cut."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg


def main() -> None:
    """Print why Table 10-2 salvage truncates before Langfuse."""

    env: dict[str, str] = {}
    for line in Path(".env.compose").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    with psycopg.connect(env["OPERATOR_SUPABASE_DB_URL"]) as conn:
        text = conn.execute(
            """
            SELECT raw_text
            FROM app.document_chunks
            WHERE deleted_at IS NULL
              AND page_number = 252
              AND chunk_index = 501
            """
        ).fetchone()[0]
    match = re.search(r"(?i)Table\s+10-2\.", text)
    print("titled_at", match.start() if match else None)
    if match is None:
        idx = text.casefold().find("table 10-2")
        print("any_at", idx, repr(text[idx : idx + 40] if idx >= 0 else None))
        return
    start = match.start()
    rest = text[start : start + 1200]
    print("--- lines ---")
    for index, line in enumerate(rest.splitlines()):
        heading = bool(re.fullmatch(r"[A-Z][A-Za-z0-9 ,/&-]{8,80}", line))
        print(f"{index:02d} heading={heading} {line!r}")
    heading_match = re.search(
        r"(?m)^(?:[A-Z][A-Za-z0-9 ,/&-]{8,80})$",
        rest[40:] if len(rest) > 40 else "",
    )
    if heading_match is None:
        print("no heading cut")
    else:
        print(
            "heading_cut",
            repr(heading_match.group(0)),
            "rel",
            heading_match.start(),
            "abs_end",
            start + 40 + heading_match.start(),
        )
    langfuse_at = text.find("Langfuse", start)
    print(
        "langfuse_offset_from_title", langfuse_at - start if langfuse_at >= 0 else None
    )


if __name__ == "__main__":
    main()
