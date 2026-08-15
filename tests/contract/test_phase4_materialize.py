"""Optional live Hybrid Ready persist for Phase 4 open-split materialization.

Skips cleanly when local Supabase or the Packet 8 ParadeDB overlay is down.
Does not open holdout labels.
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.materialize import (
    PersistMapping,
    build_compact_source,
    build_sidecar,
    select_phase4_retrieve_cases,
)
from smart_rag_core.settings import SharedSettings

from tests.contract.hybrid_ready_driver import (
    drive_hybrid_ready,
    list_persisted_chunk_texts,
    list_persisted_table_ids,
    parse_local_bytes,
)
from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_host_reachable,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATERIALIZE_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "materialize.py"
)


def _require_stack() -> tuple[str, str]:
    """Return Supabase and ParadeDB URLs or skip when Compose is down.

    Returns:
        ``(supabase_url, parade_url)``.
    """

    supabase_url = resolve_supabase_db_url()
    parade_url = packet8_paradedb_url()
    connection = try_connect(supabase_url)
    if connection is None or parade_url is None or not paradedb_host_reachable():
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Phase 4 materialize contract requires local Compose overlay")
        pytest.skip("local Supabase or Packet 8 ParadeDB overlay is unavailable")
    connection.close()
    return supabase_url, parade_url


def test_materialize_module_does_not_reference_holdout_loaders() -> None:
    """Contract AST guard: materialize.py stays holdout-blind."""

    dumped = ast.dump(
        ast.parse(
            MATERIALIZE_MODULE.read_text(encoding="utf-8"),
            filename=str(MATERIALIZE_MODULE),
        )
    )
    assert "load_holdout" not in dumped
    assert "HOLDOUT" not in dumped
    assert "HoldoutAccess" not in dumped


def test_open_split_markdown_reaches_hybrid_ready_with_gold_map() -> None:
    """One exact-code open-split source persists and maps synthetic gold to UUID."""

    supabase_url, parade_url = _require_stack()
    case = next(
        item
        for item in select_phase4_retrieve_cases(split="development")
        if item.query_class is QueryClass.EXACT_CODE
    )
    source = build_compact_source(case)
    parsed = parse_local_bytes(
        source.markdown_text.encode("utf-8"),
        filename=source.markdown_filename,
        format_key="markdown",
    )
    result = drive_hybrid_ready(
        supabase_url=supabase_url,
        parade_url=parade_url,
        parse_result=parsed,
        title=f"p4-eval-{case.case_id}",
        filename=source.markdown_filename,
        settings=SharedSettings(mock_model_mode=True),
        visibility=source.visibility,
    )
    assert result.hybrid_ready is True
    with psycopg.connect(supabase_url) as supabase:
        chunk_texts = list_persisted_chunk_texts(supabase, result.version_id)
        table_ids = list_persisted_table_ids(supabase, result.version_id)
        supabase.execute("SET ROLE postgres")
        with supabase.cursor() as cursor:
            cursor.execute(
                "SELECT visibility::text FROM app.documents WHERE id = %s",
                (result.document_id,),
            )
            visibility_row = cursor.fetchone()
    assert visibility_row is not None
    assert str(visibility_row[0]) == "company_visible"
    sidecar = build_sidecar(
        [case],
        persist_index={
            case.case_id: PersistMapping(
                document_id=result.document_id,
                version_id=result.version_id,
                chunk_texts=chunk_texts,
                table_ids=table_ids,
            )
        },
    )
    assert sidecar.holdout_opened is False
    gold = case.evidence_links[0].chunk_id
    record = sidecar.records[0]
    assert record.synthetic_chunk_id == gold
    assert record.chunk_id is not None
    assert isinstance(record.chunk_id, UUID)
    assert record.document_id == result.document_id


def test_acl_negative_persists_as_restricted() -> None:
    """ACL-negative gold is indexed as restricted, not company-visible."""

    supabase_url, parade_url = _require_stack()
    case = next(
        item
        for item in select_phase4_retrieve_cases(split="development")
        if item.query_class is QueryClass.ACL_NEGATIVE
    )
    source = build_compact_source(case)
    assert source.visibility == "restricted"
    parsed = parse_local_bytes(
        source.markdown_text.encode("utf-8"),
        filename=source.markdown_filename,
        format_key="markdown",
    )
    result = drive_hybrid_ready(
        supabase_url=supabase_url,
        parade_url=parade_url,
        parse_result=parsed,
        title=f"p4-eval-acl-{case.case_id}",
        filename=source.markdown_filename,
        settings=SharedSettings(mock_model_mode=True),
        visibility=source.visibility,
    )
    assert result.hybrid_ready is True
    with psycopg.connect(supabase_url) as supabase:
        supabase.execute("SET ROLE postgres")
        with supabase.cursor() as cursor:
            cursor.execute(
                "SELECT visibility::text FROM app.documents WHERE id = %s",
                (result.document_id,),
            )
            row = cursor.fetchone()
    assert row is not None
    assert str(row[0]) == "restricted"
