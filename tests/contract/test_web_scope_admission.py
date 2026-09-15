"""SQL admission v3 CHECK and web_research envelope alignment."""

from __future__ import annotations

from decimal import Decimal

import psycopg
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def test_sql_web_research_envelope_matches_python(
    db_connection: psycopg.Connection,
) -> None:
    """``query_route_envelope('web_research')`` matches Python ceilings."""

    expected = envelope_for_family(Phase6RouteFamily.WEB_RESEARCH)
    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT deadline_seconds, model_call_ceiling, tool_ceiling,
                   envelope_usd, recursion_limit, correction_ceiling
            FROM app.query_route_envelope(%s)
            """,
            (Phase6RouteFamily.WEB_RESEARCH.value,),
        ).fetchone()
    assert row is not None
    assert int(row[0]) == expected.deadline_seconds
    assert int(row[1]) == expected.model_call_ceiling
    assert int(row[2]) == expected.tool_ceiling
    assert Decimal(str(row[3])) == expected.envelope_usd
    assert int(row[4]) == expected.recursion_limit
    assert int(row[5]) == expected.correction_ceiling


def test_requested_search_scope_check_includes_web(
    db_connection: psycopg.Connection,
) -> None:
    """Additive CHECK lists auto, company, general, and web."""

    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'runs_requested_search_scope_chk'
            """
        ).fetchone()
    assert row is not None
    definition = str(row[0])
    assert "web" in definition
    assert "company_documents" in definition
    assert "general_knowledge" in definition


def test_admit_query_run_v2_remains_callable(
    db_connection: psycopg.Connection,
) -> None:
    """Old deployments can still resolve v2 after v3 is installed."""

    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT COUNT(*)
            FROM pg_proc
            WHERE proname IN ('admit_query_run_v2', 'admit_query_run_v3')
            """
        ).fetchone()
    assert row is not None
    assert int(row[0]) >= 2
