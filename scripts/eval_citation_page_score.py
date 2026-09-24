"""Score answers for a fact plus a persisted citation on the gold page.

Reads a private gold file (JSON array of objects with ``id`` and integer
``page``), the runner answers mapping (question id to a row with
``run_id``), and the runner summary (``outcomes`` rows with
``question_id`` and ``strict_pass``). Loads persisted citation pages for
those runs from ``app.citations`` joined to ``app.document_chunks`` for one
document. Output and stdout hold ids, page numbers, booleans, and counts
only.

Usage::

    uv run python scripts/eval_citation_page_score.py --gold G --answers A --summary S --document-id D --out O
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.eval_ask_stage_export import operator_url  # noqa: E402

_CITATION_PAGES_SQL: LiteralString = """
SELECT c.run_id::text, dc.page_number
FROM app.citations AS c
JOIN app.document_chunks AS dc ON dc.id = c.chunk_id
WHERE c.run_id = ANY(%s::uuid[])
  AND dc.document_id = %s::uuid
"""


def score_rows(
    *,
    gold_pages: Mapping[str, int],
    run_ids: Mapping[str, str],
    strict: Mapping[str, bool],
    citation_pages: Mapping[str, Sequence[int]],
) -> dict[str, object]:
    """Score each gold question against its run's cited pages.

    Args:
        gold_pages: Question id to gold page.
        run_ids: Question id to run id. A missing id means no run.
        strict: Question id to the runner's ``strict_pass``.
        citation_pages: Run id to cited page numbers on the scored document.

    Returns:
        ``questions``: one row per gold id in sorted order with ``id``,
        ``gold_page``, ``pages``, ``strict``, ``cited_gold`` (gold page
        cited), and ``cited_near`` (a page exactly one away cited and the
        gold page not cited). ``totals``: ``questions``, ``cited_gold``,
        ``fact_and_gold_page`` (strict and cited_gold), ``fact_near_page``
        (strict and cited_near), and ``fact_other_page`` (strict, neither).
    """

    questions: list[dict[str, object]] = []
    totals = {
        "questions": 0,
        "cited_gold": 0,
        "fact_and_gold_page": 0,
        "fact_near_page": 0,
        "fact_other_page": 0,
    }
    for question_id in sorted(gold_pages):
        gold = gold_pages[question_id]
        run_id = run_ids.get(question_id, "")
        pages = sorted(set(citation_pages.get(run_id, ()))) if run_id else []
        passed = strict.get(question_id, False) is True
        cited_gold = gold in pages
        cited_near = not cited_gold and any(abs(page - gold) == 1 for page in pages)
        questions.append(
            {
                "id": question_id,
                "gold_page": gold,
                "pages": pages,
                "strict": passed,
                "cited_gold": cited_gold,
                "cited_near": cited_near,
            }
        )
        totals["questions"] += 1
        if cited_gold:
            totals["cited_gold"] += 1
        if passed and cited_gold:
            totals["fact_and_gold_page"] += 1
        elif passed and cited_near:
            totals["fact_near_page"] += 1
        elif passed:
            totals["fact_other_page"] += 1
    return {"questions": questions, "totals": totals}


def _mapping(value: object) -> dict[str, object]:
    """Return ``value`` as a string-keyed dict, else an empty dict.

    Args:
        value: Any JSON value.

    Returns:
        String-keyed shallow copy.
    """

    if not isinstance(value, Mapping):
        return {}
    typed = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _is_uuid(value: str) -> bool:
    """Return whether ``value`` parses as a UUID.

    Args:
        value: Candidate id.

    Returns:
        True for a UUID string.
    """

    try:
        UUID(value)
    except ValueError:
        return False
    return True


def gold_pages_from(raw: object) -> dict[str, int]:
    """Read ``id`` to integer ``page`` from a gold JSON array.

    Args:
        raw: Parsed gold file.

    Returns:
        Gold pages. Items without an integer page are skipped.
    """

    pages: dict[str, int] = {}
    if not isinstance(raw, list):
        return pages
    for item in cast(list[object], raw):
        row = _mapping(item)
        page = row.get("page")
        if isinstance(page, int) and not isinstance(page, bool):
            pages[str(row.get("id"))] = page
    return pages


def run_ids_from(raw: object) -> dict[str, str]:
    """Read question id to UUID ``run_id`` from runner answers.

    Args:
        raw: Parsed answers mapping.

    Returns:
        Run ids. Rows without a UUID ``run_id`` are skipped.
    """

    ids: dict[str, str] = {}
    for question_id, value in _mapping(raw).items():
        run_id = str(_mapping(value).get("run_id") or "").strip()
        if _is_uuid(run_id):
            ids[question_id] = run_id
    return ids


def strict_from(raw: object) -> dict[str, bool]:
    """Read question id to ``strict_pass`` from a runner summary.

    Args:
        raw: Parsed summary with an ``outcomes`` list.

    Returns:
        Strict flags. Only ``True`` counts as a pass.
    """

    flags: dict[str, bool] = {}
    outcomes = _mapping(raw).get("outcomes")
    if not isinstance(outcomes, list):
        return flags
    for item in cast(list[object], outcomes):
        row = _mapping(item)
        flags[str(row.get("question_id"))] = row.get("strict_pass") is True
    return flags


def load_citation_pages(
    url: str, run_ids: Sequence[str], document_id: str
) -> dict[str, list[int]]:
    """Load cited page numbers per run for one document.

    Args:
        url: Operator DSN.
        run_ids: UUID run ids.
        document_id: Scored document UUID.

    Returns:
        Run id to page numbers (unsorted, may repeat).

    Side Effects:
        One read-only SELECT as the operator role.
    """

    pages: dict[str, list[int]] = {}
    if not run_ids:
        return pages
    with psycopg.connect(url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            _CITATION_PAGES_SQL, (list(run_ids), document_id)
        ).fetchall()
    for row in rows:
        page: object = row[1]
        if isinstance(page, int) and not isinstance(page, bool):
            pages.setdefault(str(row[0]), []).append(page)
    return pages


def main(argv: list[str] | None = None) -> int:
    """Write a private citation-page score and print its totals.

    Args:
        argv: Optional CLI arguments without the program name.

    Returns:
        0 on success; 2 for a non-private output, a bad document id, or a
        missing operator URL.
    """

    parser = argparse.ArgumentParser(description="Fact plus gold-page score.")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    out = cast(Path, args.out)
    document_id = cast(str, args.document_id)
    if ".private-eval" not in {part.casefold() for part in out.resolve().parts}:
        print("blocked=out_not_private")
        return 2
    if not _is_uuid(document_id):
        print("blocked=document_id_not_uuid")
        return 2
    try:
        url = operator_url()
    except RuntimeError as error:
        print(f"blocked={error}")
        return 2
    gold_pages = gold_pages_from(
        json.loads(cast(Path, args.gold).read_text(encoding="utf-8"))
    )
    run_ids = run_ids_from(
        json.loads(cast(Path, args.answers).read_text(encoding="utf-8"))
    )
    strict = strict_from(
        json.loads(cast(Path, args.summary).read_text(encoding="utf-8"))
    )
    citation_pages = load_citation_pages(
        url, sorted(set(run_ids.values())), document_id
    )
    result = score_rows(
        gold_pages=gold_pages,
        run_ids=run_ids,
        strict=strict,
        citation_pages=citation_pages,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for key, value in _mapping(result["totals"]).items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
