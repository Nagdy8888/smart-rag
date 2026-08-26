"""SQL route-envelope contract alignment with Python ceilings."""

from __future__ import annotations

from decimal import Decimal

import psycopg
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def test_sql_envelopes_match_python_table(db_connection: psycopg.Connection) -> None:
    """SQL ``query_route_envelope`` stays aligned with ``ceilings.py``."""

    with db_connection.cursor() as cursor:
        for family in Phase6RouteFamily:
            expected = envelope_for_family(family)
            row = cursor.execute(
                """
                SELECT deadline_seconds, model_call_ceiling, tool_ceiling,
                       envelope_usd, recursion_limit
                FROM app.query_route_envelope(%s)
                """,
                (family.value,),
            ).fetchone()
            assert row is not None
            assert int(row[0]) == expected.deadline_seconds
            assert int(row[1]) == expected.model_call_ceiling
            assert int(row[2]) == expected.tool_ceiling
            assert Decimal(str(row[3])) == expected.envelope_usd
            assert int(row[4]) == expected.recursion_limit
