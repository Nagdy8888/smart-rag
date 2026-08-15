#!/usr/bin/env python3
"""Run Phase 4 open-split ranked-ID, locator, ACL, table, and p95 eval.

Holdout labels are never loaded. Dry sidecars with null chunk UUIDs fail
closed and do not report Recall@10. Mock embeddings must not be labeled as
live QT-EVAL-006. Frozen ``hybrid_default_v1`` is not retuned here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smart_rag_core.evaluation.materialize import GoldIdSidecar, OpenSplitName
from smart_rag_core.evaluation.ranked_ids import (
    CaseRetrieveOutcome,
    EmbeddingsKind,
    evaluate_ranked_ids,
    gold_records_for_case,
    load_eval_cases,
    load_gold_id_sidecar,
    report_to_json,
    sidecar_has_unmapped_chunks,
    table_dispatch_required,
)
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings
from smart_rag_core.tables.builder import compile_table_query
from smart_rag_core.tables.executor import TableSandboxError, execute_compiled_query
from smart_rag_core.tables.plan import (
    TableAggregation,
    TableAggregationOp,
    TableQueryPlan,
)

DEFAULT_SIDECAR = (
    _ROOT
    / "tests"
    / "fixtures"
    / "evaluation"
    / "phase4"
    / "runtime"
    / "gold_id_map.json"
)
DEFAULT_PARADE_PORT = "54329"


def _load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` with ``setdefault``. Values are not logged.
    """

    path = _ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = key.strip()
        if not name:
            continue
        os.environ.setdefault(name, value.strip().strip('"').strip("'"))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse ranked-ID eval flags.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Score Phase-4-owned open-split ranked IDs. Never loads sealed "
            "labels. Fail-closes when the sidecar has unmapped chunk UUIDs."
        )
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=DEFAULT_SIDECAR,
        help="Path to gold_id_map.json (Wave 1B sidecar)",
    )
    parser.add_argument(
        "--split",
        choices=("development", "qualification", "open"),
        default="development",
        help="Open-split selector. Never includes sealed labels.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional positive cap after Phase-4 retrieve filtering",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run HybridRetriever against local Supabase and Packet 8 ParadeDB",
    )
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        default=None,
        help="Optional directory of case_id.parquet artifacts for table cases",
    )
    return parser.parse_args(argv)


def _embeddings_kind(settings: SharedSettings) -> EmbeddingsKind:
    """Return whether query embeddings are mock or OpenAI.

    Args:
        settings: Shared deployable settings.

    Returns:
        ``mock`` when ``MOCK_MODEL_MODE`` is true, otherwise ``openai``.
    """

    if settings.mock_model_mode:
        return "mock"
    return "openai"


def _closed_payload(
    *,
    split: str,
    case_count: int,
    embeddings: EmbeddingsKind,
    sidecar_unmapped: bool,
    cost: float | None = None,
) -> dict[str, object]:
    """Build fail-closed CLI JSON without reporting Recall@10.

    Args:
        split: Open-split name.
        case_count: Loaded case count.
        embeddings: Embedding adapter kind.
        sidecar_unmapped: True when gold chunk UUIDs are missing.
        cost: Optional known cost.

    Returns:
        JSON mapping with null recall fields and ``holdout_opened=false``.
    """

    from smart_rag_core.evaluation.ranked_ids import (
        QT_EVAL_002_LOCATOR_CORRECTNESS,
        QT_EVAL_006_RECALL_AT_10,
        QT_EVAL_007_EXACT_CODE_RECALL_AT_5,
        QT_EVAL_008_ALIAS_RECALL_AT_10,
        QT_LAT_001_FIRST_EVIDENCE_P95_MS,
        hardware_snapshot,
    )

    return {
        "split": split,
        "case_count": case_count,
        "recall_at_10": None,
        "exact_code_recall_at_5": None,
        "alias_recall_at_10": None,
        "locator_correctness": None,
        "first_evidence_p95_ms": None,
        "holdout_opened": False,
        "sidecar_unmapped": sidecar_unmapped,
        "embeddings": embeddings,
        "qt_eval_006_live": False,
        "cost": cost,
        "hardware": hardware_snapshot(),
        "qt_lat_001_ms": QT_LAT_001_FIRST_EVIDENCE_P95_MS,
        "qt_eval_006_threshold": QT_EVAL_006_RECALL_AT_10,
        "qt_eval_007_threshold": QT_EVAL_007_EXACT_CODE_RECALL_AT_5,
        "qt_eval_008_threshold": QT_EVAL_008_ALIAS_RECALL_AT_10,
        "qt_eval_002_threshold": QT_EVAL_002_LOCATOR_CORRECTNESS,
        "live_retrieve": False,
    }


def _print_json(payload: dict[str, object]) -> None:
    """Write one JSON object to stdout.

    Args:
        payload: Report mapping.

    Side Effects:
        Prints JSON to stdout.
    """

    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _try_packet7_table(
    case: EvaluationCase,
    sidecar: GoldIdSidecar,
    *,
    parquet_dir: Path | None,
) -> bool:
    """Run Packet 7 ``execute_compiled_query`` when a Parquet artifact exists.

    Ordinary cell lookup does not enter this path. Missing artifacts return
    False; dispatch is still recorded by ``scoring_kind``.

    Args:
        case: Phase-4-owned case.
        sidecar: Gold-id sidecar with optional table UUIDs.
        parquet_dir: Directory containing ``{case_id}.parquet`` files.

    Returns:
        True when the sandboxed executor completed.
    """

    if parquet_dir is None or not table_dispatch_required(case):
        return False
    parquet_path = parquet_dir / f"{case.case_id}.parquet"
    if not parquet_path.is_file():
        return False
    records = gold_records_for_case(sidecar, case.case_id)
    table_id = next((item.table_id for item in records if item.table_id), None)
    version_id = next((item.version_id for item in records if item.version_id), None)
    if table_id is None or version_id is None:
        return False
    digest = _sha256_file(parquet_path)
    plan = TableQueryPlan(
        table_id=table_id,
        version_id=version_id,
        aggregations=(
            TableAggregation(
                op=TableAggregationOp.SUM,
                column="amount",
                alias="total",
            ),
        ),
    )
    compiled = compile_table_query(plan, allowed_columns=frozenset({"amount"}))
    try:
        execute_compiled_query(
            compiled,
            parquet_path=parquet_path,
            expected_sha256=digest,
            row_limit=plan.row_limit,
            output_byte_limit=plan.output_byte_limit,
        )
    except (TableSandboxError, OSError, ValueError):
        return False
    return True


def _sha256_file(path: Path) -> str:
    """Return SHA-256 of a local Parquet file.

    Args:
        path: Artifact path.

    Returns:
        Hex digest.
    """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lookup_member_caller(supabase: psycopg.Connection) -> CallerContext | None:
    """Load one active member-or-better caller from canonical profiles.

    Args:
        supabase: Open ``psycopg`` connection.

    Returns:
        ``CallerContext`` or None when no profile exists.

    Side Effects:
        Reads ``app.profiles`` in a committed transaction so the connection
        is idle for later ``retrieval_transaction`` calls.
    """

    with supabase.transaction():
        supabase.execute("SET ROLE postgres")
        with supabase.cursor() as cursor:
            cursor.execute("SELECT app.current_authorization_version()")
            version_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT user_id::text, role::text
                FROM app.profiles
                WHERE disabled_at IS NULL
                ORDER BY CASE role::text
                  WHEN 'member' THEN 0
                  WHEN 'viewer' THEN 1
                  WHEN 'admin' THEN 2
                  ELSE 3
                END
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    if row is None or version_row is None:
        return None
    user_raw: object = row[0]
    role_raw: object = row[1]
    version_raw: object = version_row[0]
    return CallerContext(
        user_id=str(user_raw),
        role=UserRole(str(role_raw)),
        authorization_version=int(str(version_raw)),
        disabled=False,
    )


def _live_outcomes(
    cases: list[EvaluationCase],
    sidecar: GoldIdSidecar,
    *,
    settings: SharedSettings,
    parquet_dir: Path | None,
) -> dict[str, CaseRetrieveOutcome] | None:
    """Retrieve live Hybrid results when Compose overlay is reachable.

    Args:
        cases: Phase-4-owned open-split cases.
        sidecar: Mapped gold-id sidecar.
        settings: Shared settings for the embedding gateway.
        parquet_dir: Optional table Parquet directory.

    Returns:
        Per-case outcomes, or None when Supabase/ParadeDB cannot be opened.
    """

    import psycopg
    from smart_rag_core.gateways.embedding import create_embedding_gateway
    from smart_rag_core.retrieval.bm25 import Bm25Retriever
    from smart_rag_core.retrieval.context_loader import fetch_authorized_chunk_context
    from smart_rag_core.retrieval.dense import DenseRetriever
    from smart_rag_core.retrieval.hybrid_run import HybridRetriever
    from smart_rag_core.retrieval.terms import TermRetriever

    from tests.contract.integration_support import (
        packet8_paradedb_url,
        paradedb_host_reachable,
        resolve_supabase_db_url,
        try_connect,
    )

    supabase_url = resolve_supabase_db_url()
    parade_url = packet8_paradedb_url()
    probe = try_connect(supabase_url)
    if probe is None or parade_url is None or not paradedb_host_reachable():
        return None
    probe.close()
    gateway = create_embedding_gateway(settings)
    outcomes: dict[str, CaseRetrieveOutcome] = {}
    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        caller = _lookup_member_caller(supabase)
        if caller is None:
            return None
        retriever = HybridRetriever(
            embedding_gateway=gateway,
            supabase=supabase,
            paradedb=parade,
            supabase_dsn=supabase_url,
            dense=DenseRetriever(supabase),
            bm25=Bm25Retriever(parade),
            term=TermRetriever(supabase),
        )
        for case in cases:
            if table_dispatch_required(case):
                executed = _try_packet7_table(case, sidecar, parquet_dir=parquet_dir)
                outcomes[case.case_id] = CaseRetrieveOutcome(
                    table_executed=executed,
                    table_ok=executed,
                )
                continue
            try:
                result = retriever.retrieve(
                    query=case.query,
                    caller=caller,
                    profile=case.expected_profile,
                )
            except Exception as error:
                sys.stderr.write(
                    f"retrieve_skipped {case.case_id} {type(error).__name__}:{error}\n"
                )
                outcomes[case.case_id] = CaseRetrieveOutcome()
                continue
            evidence_ids = tuple(unit.chunk_id for unit in result.evidence)
            ranked_prefix = result.ranked_ids[:12]
            fetch_ids = evidence_ids or ranked_prefix
            contexts = ()
            if fetch_ids:
                contexts = fetch_authorized_chunk_context(
                    supabase,
                    caller=caller,
                    chunk_ids=fetch_ids[:75],
                )
            outcomes[case.case_id] = CaseRetrieveOutcome(
                result=result,
                contexts=contexts,
            )
    return outcomes


def main(argv: list[str] | None = None) -> int:
    """Score Phase-4-owned open splits and print JSON.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` when the run finished (including recorded gate misses),
        ``2`` when the sidecar is missing or unmapped (fail closed).
        Mock Recall@10 is never labeled live QT-EVAL-006.

    Side Effects:
        Prints JSON to stdout. Optional live retrieve reads local Postgres.
        Does not open sealed labels or retune ``hybrid_default_v1``.
    """

    args = _parse_args(argv)
    split: OpenSplitName = args.split
    _load_repo_env()
    settings = SharedSettings()
    embeddings = _embeddings_kind(settings)
    cases = load_eval_cases(split, limit=args.limit)
    if not args.sidecar.is_file():
        _print_json(
            _closed_payload(
                split=split,
                case_count=len(cases),
                embeddings=embeddings,
                sidecar_unmapped=True,
            )
        )
        return 2
    sidecar = load_gold_id_sidecar(args.sidecar)
    if sidecar_has_unmapped_chunks(sidecar):
        _print_json(
            _closed_payload(
                split=split,
                case_count=len(cases),
                embeddings=embeddings,
                sidecar_unmapped=True,
            )
        )
        return 2
    outcomes: dict[str, CaseRetrieveOutcome] = {}
    live_retrieve = False
    if args.live:
        live = _live_outcomes(
            cases,
            sidecar,
            settings=settings,
            parquet_dir=args.parquet_dir,
        )
        if live is None:
            _print_json(
                {
                    **_closed_payload(
                        split=split,
                        case_count=len(cases),
                        embeddings=embeddings,
                        sidecar_unmapped=False,
                    ),
                    "sidecar_unmapped": False,
                    "live_retrieve": False,
                    "live_skip_reason": (
                        "local Supabase or Packet 8 ParadeDB overlay "
                        f"(localhost:{DEFAULT_PARADE_PORT}) is unavailable"
                    ),
                }
            )
            return 2
        outcomes = live
        live_retrieve = True
    else:
        parquet_dir: Path | None = args.parquet_dir
        for case in cases:
            if table_dispatch_required(case):
                executed = _try_packet7_table(case, sidecar, parquet_dir=parquet_dir)
                outcomes[case.case_id] = CaseRetrieveOutcome(
                    table_executed=executed,
                    table_ok=executed,
                )
    report = evaluate_ranked_ids(
        cases,
        sidecar,
        outcomes,
        split=split,
        embeddings=embeddings,
        table_executor=None,
    )
    payload = report_to_json(report)
    payload["live_retrieve"] = live_retrieve
    _print_json(payload)
    if report.sidecar_unmapped:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
