"""Seal a private PDF evaluation dataset after named human review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.private_pdf import (
    PrivatePdfSealError,
    assert_holdout_outside_repository,
    assert_holdout_path_hidden,
    manifest_hash,
    read_private_pdf_payload,
    seal_cases,
)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.pdf_eval_cli import apply_merged_env, operator_url  # noqa: E402


def _current_chunk_ids(ingest_ids: Path) -> frozenset[UUID] | None:
    """Load live representative chunk ids for the ingested version.

    Args:
        ingest_ids: Gitignored ingest identity file.

    Returns:
        Current chunk ids, or None when identity/DB is unavailable.
    """

    if not ingest_ids.is_file():
        return None
    payload = json.loads(ingest_ids.read_text(encoding="utf-8"))
    version_id = str(payload.get("version_id", ""))
    if not version_id:
        return None
    env = apply_merged_env()
    try:
        url = operator_url(env)
    except RuntimeError:
        return None
    with psycopg.connect(url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            """
            SELECT id
            FROM app.document_chunks
            WHERE version_id = %s::uuid
              AND deleted_at IS NULL
              AND is_search_representative
            """,
            (version_id,),
        ).fetchall()
    return frozenset(UUID(str(row[0])) for row in rows)


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


def _labeled_rows(raw: object) -> list[dict[str, object]]:
    """Return labeled case mappings from a dataset payload.

    Args:
        raw: Decoded JSON.

    Returns:
        Case mappings including private fields.
    """

    payload = _as_object(raw)
    cases = payload.get("cases", ())
    if not isinstance(cases, list):
        return []
    rows: list[dict[str, object]] = []
    for item in cast(list[object], cases):
        if isinstance(item, dict):
            typed = cast(dict[Any, object], item)
            rows.append({str(key): value for key, value in typed.items()})
    return rows


def _write_labeled(
    path: Path,
    *,
    rows: list[dict[str, object]],
    extra: dict[str, object],
) -> None:
    """Write labeled JSON without printing source text.

    Args:
        path: Destination.
        rows: Labeled case mappings.
        extra: Dataset-level fields.
    """

    payload: dict[str, object] = {**extra, "cases": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Validate human approval, hide holdout, and write a Git-safe manifest.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code. Generated-only rows fail. Holdout export
        requires ``dataset_seal_verify`` access and a path outside the repo.
    """

    parser = argparse.ArgumentParser(
        description="Seal private PDF eval cases. Generated-only rows fail."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".private-eval/eval-draft/manifest.json"),
    )
    parser.add_argument(
        "--sealed-out",
        type=Path,
        default=None,
        help="Gitignored open-split labeled JSON (development+qualification).",
    )
    parser.add_argument(
        "--ids",
        type=Path,
        default=Path(".private-eval/ingest-ids.json"),
    )
    parser.add_argument(
        "--holdout-out",
        type=Path,
        default=None,
        help="Reviewer-controlled path outside the repo for holdout rows.",
    )
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args(argv)
    assert_holdout_path_hidden(args.input)
    cases = read_private_pdf_payload(args.input)
    holdout_present = any(case.split == "holdout" for case in cases)
    access = HoldoutAccess.denied()
    if args.holdout_out is not None:
        reviewer = args.reviewer.strip()
        if not reviewer or reviewer.lower() in {"model", "assistant"}:
            print("seal_rejected=PrivatePdfSealError")
            print("seal_reason=named_reviewer_required")
            return 2
        try:
            assert_holdout_outside_repository(args.holdout_out, repo=REPO)
        except PrivatePdfSealError as exc:
            print("seal_rejected=PrivatePdfSealError")
            print(f"seal_reason={exc}")
            return 2
        access = HoldoutAccess(
            allowed=True,
            purpose="dataset_seal_verify",
            actor=reviewer,
        )
    elif holdout_present:
        print("blocked=holdout_export_requires_authorized_access")
        print("holdout_opened=false")
        return 2
    try:
        # Reject unsafe custody/labels before opening any database connection.
        if any(case.generated_only or not case.human_approved for case in cases):
            raise PrivatePdfSealError("generated_labels_cannot_self_seal")
        current_ids = _current_chunk_ids(args.ids)
        sealed = seal_cases(
            cases,
            holdout_access=access,
            current_chunk_ids=current_ids,
        )
    except (PrivatePdfSealError, HoldoutSealedError) as exc:
        print(f"seal_rejected={type(exc).__name__}")
        print(f"seal_reason={exc}")
        return 2
    labeled = _labeled_rows(json.loads(args.input.read_text(encoding="utf-8")))
    by_id = {str(row.get("case_id")): row for row in labeled}
    open_rows = [
        by_id[case.case_id]
        for case in sealed
        if case.split != "holdout" and case.case_id in by_id
    ]
    holdout_rows = [
        by_id[case.case_id]
        for case in sealed
        if case.split == "holdout" and case.case_id in by_id
    ]
    open_sealed = tuple(case for case in sealed if case.split != "holdout")
    sealed_path = args.sealed_out
    if sealed_path is None and args.ids.is_file():
        digest = str(
            json.loads(args.ids.read_text(encoding="utf-8")).get("content_hash", "")
        )
        if len(digest) >= 12:
            sealed_path = Path(".private-eval") / digest[:12] / "v1" / "sealed.json"
    if sealed_path is None:
        sealed_path = Path(".private-eval/eval-draft/sealed.json")
    extra: dict[str, object] = {
        "human_sealed": True,
        "generated_only": False,
        "holdout_opened": False,
        "reviewer": args.reviewer.strip() or None,
        "review_kind": "locator_bound_owner_instruction",
    }
    _write_labeled(sealed_path, rows=open_rows, extra=extra)
    if holdout_rows:
        if args.holdout_out is None:
            print("blocked=holdout_export_requires_authorized_access")
            print("holdout_opened=false")
            return 2
        _write_labeled(
            args.holdout_out,
            rows=holdout_rows,
            extra={
                **extra,
                "split": "holdout",
                "holdout_opened": False,
                "purpose": "dataset_seal_verify",
            },
        )
    payload = {
        "manifest_sha256": manifest_hash(sealed),
        "open_manifest_sha256": manifest_hash(open_sealed),
        "case_count": len(sealed),
        "open_case_count": len(open_sealed),
        "holdout_case_count": len(holdout_rows),
        "holdout_opened": False,
        "case_ids": [case.case_id for case in sealed],
        "source_family_ids": sorted({case.source_family_id for case in sealed}),
        "split_counts": {
            "development": sum(1 for case in sealed if case.split == "development"),
            "qualification": sum(1 for case in sealed if case.split == "qualification"),
            "holdout": sum(1 for case in sealed if case.split == "holdout"),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"case_count={len(sealed)}")
    print(f"open_case_count={len(open_sealed)}")
    print(f"holdout_case_count={len(holdout_rows)}")
    print("holdout_opened=false")
    print(f"manifest_sha256={payload['manifest_sha256']}")
    print("human_sealed=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
