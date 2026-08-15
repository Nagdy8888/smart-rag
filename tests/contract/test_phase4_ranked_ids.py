"""Optional live ranked-ID wiring for Phase 4 Packet 9 Wave 2.

Skips cleanly when local Supabase, Packet 8 ParadeDB (localhost:54329), or
mapped sidecar UUIDs are missing. Does not open sealed labels.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.ranked_ids import (
    CaseRetrieveOutcome,
    EmbeddingsKind,
    evaluate_ranked_ids,
    load_eval_cases,
    load_gold_id_sidecar,
    report_to_json,
    sidecar_has_unmapped_chunks,
)
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.settings import SharedSettings

from tests.contract.hybrid_retrieval_seed import seed_hybrid_retrieval_fixture
from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_host_reachable,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RANKED_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "ranked_ids.py"
)
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_phase4_ranked_ids.py"
SIDECAR_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "evaluation"
    / "phase4"
    / "runtime"
    / "gold_id_map.json"
)


def _require_stack_and_mapped_sidecar() -> tuple[str, str]:
    """Return live URLs or skip when Compose/sidecar UUIDs are missing.

    Returns:
        ``(supabase_url, parade_url)``.
    """

    supabase_url = resolve_supabase_db_url()
    parade_url = packet8_paradedb_url()
    connection = try_connect(supabase_url)
    if connection is None or parade_url is None or not paradedb_host_reachable():
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Phase 4 ranked-ID contract requires local Compose overlay")
        pytest.skip(
            "local Supabase or Packet 8 ParadeDB overlay "
            "(localhost:54329) is unavailable"
        )
    connection.close()
    if not SIDECAR_PATH.is_file():
        pytest.skip("mapped sidecar gold_id_map.json is missing")
    sidecar = load_gold_id_sidecar(SIDECAR_PATH)
    if sidecar_has_unmapped_chunks(sidecar):
        pytest.skip("sidecar UUIDs unmapped (dry materialize); Recall@10 fail-closed")
    if not any(record.chunk_id is not None for record in sidecar.records):
        pytest.skip("mapped sidecar UUIDs missing")
    return supabase_url, parade_url


def test_ranked_ids_module_and_script_are_holdout_blind() -> None:
    """Contract AST guard: ranked-ID eval never loads sealed labels."""

    for path in (RANKED_MODULE, EVAL_SCRIPT):
        dumped = ast.dump(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )
        assert "load_holdout" not in dumped
        assert "HoldoutAccess" not in dumped
        assert "HOLDOUT" not in dumped


def test_live_hybrid_retrieve_scores_mapped_sidecar_without_live_mock_claim() -> None:
    """One mapped exact-code retrieve is scored; mock is not live QT-EVAL-006."""

    supabase_url, parade_url = _require_stack_and_mapped_sidecar()
    sidecar = load_gold_id_sidecar(SIDECAR_PATH)
    cases = load_eval_cases("development")
    mapped = next(
        (
            item
            for item in cases
            if item.query_class is QueryClass.EXACT_CODE
            and any(
                record.case_id == item.case_id and isinstance(record.chunk_id, UUID)
                for record in sidecar.records
            )
        ),
        None,
    )
    if mapped is None:
        pytest.skip("no mapped exact_code case in sidecar")
    settings = SharedSettings()
    embeddings: EmbeddingsKind = "mock" if settings.mock_model_mode else "openai"
    gateway = create_embedding_gateway(settings)
    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        seed = seed_hybrid_retrieval_fixture(supabase)
        retriever = HybridRetriever(
            embedding_gateway=gateway,
            supabase=supabase,
            paradedb=parade,
            supabase_dsn=supabase_url,
            dense=DenseRetriever(supabase),
            bm25=Bm25Retriever(parade),
            term=TermRetriever(supabase),
        )
        result = retriever.retrieve(
            query=mapped.query,
            caller=seed.member,
            profile=mapped.expected_profile,
        )
    report = evaluate_ranked_ids(
        [mapped],
        sidecar,
        {mapped.case_id: CaseRetrieveOutcome(result=result)},
        split="development",
        embeddings=embeddings,
    )
    payload = report_to_json(report)
    assert payload["holdout_opened"] is False
    assert payload["sidecar_unmapped"] is False
    assert payload["embeddings"] == embeddings
    if embeddings == "mock":
        assert payload["qt_eval_006_live"] is False
    assert "recall_at_10" in payload
    assert "first_evidence_p95_ms" in payload
    assert isinstance(result.ranked_ids, tuple)
    assert result.first_evidence_ms >= 0.0


def test_acl_restricted_gold_absent_for_member_when_mapped() -> None:
    """Restricted gold UUID must not appear for the labeled unauthorized actor."""

    supabase_url, parade_url = _require_stack_and_mapped_sidecar()
    sidecar = load_gold_id_sidecar(SIDECAR_PATH)
    cases = load_eval_cases("development")
    acl_case = next(
        (
            item
            for item in cases
            if item.query_class is QueryClass.ACL_NEGATIVE
            and any(
                record.case_id == item.case_id and record.chunk_id is not None
                for record in sidecar.records
            )
        ),
        None,
    )
    if acl_case is None:
        pytest.skip("no mapped ACL-negative case in sidecar")
    settings = SharedSettings()
    gateway = create_embedding_gateway(settings)
    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        seed = seed_hybrid_retrieval_fixture(supabase)
        retriever = HybridRetriever(
            embedding_gateway=gateway,
            supabase=supabase,
            paradedb=parade,
            supabase_dsn=supabase_url,
            dense=DenseRetriever(supabase),
            bm25=Bm25Retriever(parade),
            term=TermRetriever(supabase),
        )
        result = retriever.retrieve(
            query=acl_case.query,
            caller=seed.member,
            profile=acl_case.expected_profile,
        )
    report = evaluate_ranked_ids(
        [acl_case],
        sidecar,
        {acl_case.case_id: CaseRetrieveOutcome(result=result)},
        split="development",
        embeddings="mock" if settings.mock_model_mode else "openai",
    )
    gold_ids = {
        record.chunk_id
        for record in sidecar.records
        if record.case_id == acl_case.case_id and record.chunk_id is not None
    }
    assert gold_ids.isdisjoint(set(result.ranked_ids))
    assert report.acl_leak_count == 0
    assert report.holdout_opened is False
    assert json.dumps(report_to_json(report))
