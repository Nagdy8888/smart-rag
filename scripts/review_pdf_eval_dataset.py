"""Count-only status and locator-bound owner review for a private PDF draft.

Never prints questions, answers, glossary values, or excerpts. Generated
rows stay unsealed unless locators resolve on the current version and a
named reviewer is supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

import psycopg
from smart_rag_core.evaluation.private_pdf import (
    PrivatePdfQueryClass,
    assert_holdout_path_hidden,
    case_is_locator_grounded,
    read_private_pdf_payload,
)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.pdf_eval_cli import apply_merged_env, operator_url  # noqa: E402

_EXACT_DEFAULT = frozenset(
    {
        PrivatePdfQueryClass.EXACT_ACRONYM.value,
    }
)


def _as_object(payload: object) -> dict[str, object]:
    """Require a JSON object.

    Args:
        payload: Decoded JSON.

    Returns:
        Mapping.

    Raises:
        ValueError: When payload is not an object.
    """

    if not isinstance(payload, dict):
        raise ValueError("invalid_private_pdf_dataset")
    return cast(dict[str, object], payload)


def _load_chunk_pages(
    *,
    operator_dsn: str,
    version_id: str,
) -> dict[str, tuple[int, str]]:
    """Load current representative chunk pages and text. Never logged.

    Args:
        operator_dsn: Operator session URL.
        version_id: Ingested version id.

    Returns:
        Chunk id to (page, raw_text).
    """

    with psycopg.connect(operator_dsn, connect_timeout=20) as connection:
        connection = connection
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            """
            SELECT id::text, coalesce(page_number, 0), coalesce(raw_text, '')
            FROM app.document_chunks
            WHERE version_id = %s::uuid
              AND deleted_at IS NULL
              AND is_search_representative
            """,
            (version_id,),
        ).fetchall()
    mapping: dict[str, tuple[int, str]] = {}
    for row in rows:
        mapping[str(row[0])] = (int(str(row[1])), str(row[2] or ""))
    return mapping


def _locator_bound(case: dict[str, object], chunks: dict[str, tuple[int, str]]) -> bool:
    """Return whether locators and required terms are grounded in current chunks.

    Args:
        case: Draft mapping including private fields.
        chunks: Live chunk id to page/text.

    Returns:
        True when chunk ids, pages, and required terms resolve.
    """

    raw_ids = case.get("chunk_ids", ())
    if not isinstance(raw_ids, (list, tuple)) or not raw_ids:
        return False
    ids: tuple[str, ...] = tuple(
        str(item) for item in cast(list[object] | tuple[object, ...], raw_ids)
    )
    pages_raw = case.get("page_numbers", ())
    pages: tuple[int, ...]
    if isinstance(pages_raw, (list, tuple)):
        pages = tuple(
            int(str(item))
            for item in cast(list[object] | tuple[object, ...], pages_raw)
        )
    else:
        pages = ()
    question = str(case.get("question", "")).strip()
    gold_texts: list[str] = []
    for index, chunk_id in enumerate(ids):
        record = chunks.get(chunk_id)
        if record is None:
            return False
        if index < len(pages) and record[0] not in {0, pages[index]}:
            if pages[index] != record[0]:
                return False
        gold_texts.append(record[1])
    headings_raw = case.get("heading_paths", ())
    headings: tuple[str, ...] = ()
    if isinstance(headings_raw, (list, tuple)):
        headings = tuple(
            str(item) for item in cast(list[object] | tuple[object, ...], headings_raw)
        )
    terms_raw = case.get("required_terms", ())
    required: tuple[str, ...] = ()
    if isinstance(terms_raw, (list, tuple)):
        required = tuple(
            str(item) for item in cast(list[object] | tuple[object, ...], terms_raw)
        )
    return case_is_locator_grounded(
        question=question,
        required_terms=required,
        expected_refusal=bool(case.get("expected_refusal", False)),
        gold_texts=gold_texts,
        gold_headings=headings,
    )


def _apply_review(
    *,
    input_path: Path,
    ingest_ids: Path,
    reviewer: str,
) -> int:
    """Approve only locator-bound rows. Does not print source text.

    Args:
        input_path: Gitignored draft JSON.
        ingest_ids: Ingest identity.
        reviewer: Named human reviewer.

    Returns:
        ``0`` when every row is locator-bound and rewritten; ``2`` otherwise.
    """

    if not reviewer.strip() or reviewer.strip().lower() in {"model", "assistant"}:
        print("blocked=named_human_reviewer_required")
        return 2
    if not ingest_ids.is_file():
        print("blocked=ingest_ids_missing")
        return 2
    ids = json.loads(ingest_ids.read_text(encoding="utf-8"))
    version_id = str(ids.get("version_id", ""))
    if not version_id:
        print("blocked=ingest_identity_missing")
        return 2
    env = apply_merged_env()
    chunks = _load_chunk_pages(operator_dsn=operator_url(env), version_id=version_id)
    payload = _as_object(json.loads(input_path.read_text(encoding="utf-8")))
    cases_raw = payload.get("cases", ())
    if not isinstance(cases_raw, list):
        print("blocked=invalid_private_pdf_dataset")
        return 2
    updated: list[dict[str, object]] = []
    rejected = 0
    for item in cast(list[object], cases_raw):
        if not isinstance(item, dict):
            rejected += 1
            continue
        case = cast(dict[str, object], item)
        if not _locator_bound(case, chunks):
            rejected += 1
            continue
        query_class = str(case.get("query_class", ""))
        expected_profile = (
            "hybrid_default_v1"
            if query_class in _EXACT_DEFAULT
            else "hybrid_long_document_v1"
        )
        case["human_approved"] = True
        case["generated_only"] = False
        case["reviewer"] = reviewer.strip()
        case["expected_profile_id"] = expected_profile
        updated.append(case)
    print(f"locator_bound={len(updated)}")
    print(f"locator_rejected={rejected}")
    print("holdout_opened=false")
    if rejected or len(updated) < 50:
        print("blocked=locator_bound_review_incomplete")
        return 2
    payload["cases"] = updated
    payload["generated_only"] = False
    payload["human_sealed"] = False
    payload["reviewer"] = reviewer.strip()
    payload["review_kind"] = "locator_bound_owner_instruction"
    input_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("human_approved=true")
    print(f"reviewer={reviewer.strip()}")
    print("coding_model_is_not_reviewer=true")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Print seal readiness counts or apply locator-bound review.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code. Apply mode still requires a named reviewer.
    """

    parser = argparse.ArgumentParser(
        description="Private PDF draft status or locator-bound review."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--ids", type=Path, default=Path(".private-eval/ingest-ids.json")
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewer", default="")
    parser.add_argument(
        "--i-inspected-locators",
        action="store_true",
        help="Required with --apply. Confirms current-version locator inspection.",
    )
    args = parser.parse_args(argv)
    assert_holdout_path_hidden(args.input)
    if args.apply:
        if not args.i_inspected_locators:
            print("blocked=locator_inspection_flag_required")
            return 2
        return _apply_review(
            input_path=args.input,
            ingest_ids=args.ids,
            reviewer=args.reviewer,
        )
    cases = read_private_pdf_payload(args.input)
    generated = sum(1 for case in cases if case.generated_only)
    approved = sum(1 for case in cases if case.human_approved)
    reviewers = {case.reviewer for case in cases if case.reviewer}
    print(f"case_count={len(cases)}")
    print(f"generated_only={generated}")
    print(f"human_approved={approved}")
    print(f"named_reviewer_count={len(reviewers)}")
    print("human_sealed=false" if generated else "human_sealed_candidate=true")
    print("holdout_opened=false")
    print("coding_model_is_not_reviewer=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
