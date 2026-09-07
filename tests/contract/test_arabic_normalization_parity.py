"""Contract tests for byte-identical ``arabic_norm_v1`` across core, SQL, and ParadeDB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

import pytest
from smart_rag_core.text import normalize_arabic_v1

from tests.contract.integration_support import (
    ensure_paradedb_arabic_normalizer,
    paradedb_psql,
    paradedb_reachable,
    require_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "arabic_normalization" / "arabic_norm_v1.json"
)


class _ArabicNormCase(TypedDict):
    """One Arabic normalization fixture row."""

    id: str
    raw: str
    search: str
    tags: list[str]


def _load_cases() -> list[_ArabicNormCase]:
    """Load Arabic normalization fixture cases.

    Returns:
        Parsed fixture case mappings.
    """

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert isinstance(cases, list)
    return cast(list[_ArabicNormCase], cases)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_python_normalization_matches_fixture(case: _ArabicNormCase) -> None:
    """Core ``normalize_arabic_v1`` returns the frozen search form and is idempotent."""

    raw = str(case["raw"])
    expected = str(case["search"])
    once = normalize_arabic_v1(raw)
    twice = normalize_arabic_v1(once)
    assert once == expected, f"case {case['id']}: got {once!r}, want {expected!r}"
    assert twice == once, f"case {case['id']}: normalization is not idempotent"


def test_sql_normalization_matches_fixture_when_db_reachable() -> None:
    """Supabase ``search.normalize_arabic_v1`` matches Python for every fixture case."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Supabase Postgres unreachable at {url}")

    with connection:
        with connection.cursor() as cursor:
            for case in _load_cases():
                raw = str(case["raw"])
                expected = str(case["search"])
                cursor.execute(
                    "SELECT search.normalize_arabic_v1(%s)",
                    (raw,),
                )
                row = cursor.fetchone()
                assert row is not None
                sql_value = row[0]
                python_value = normalize_arabic_v1(raw)
                assert sql_value == expected
                assert sql_value.encode("utf-8") == python_value.encode("utf-8")


@pytest.mark.skipif(not paradedb_reachable(), reason="ParadeDB container not reachable")
def test_paradedb_normalization_matches_fixture() -> None:
    """ParadeDB ``search.normalize_arabic_v1`` matches Python byte-for-byte."""

    ensure_paradedb_arabic_normalizer()
    for case in _load_cases():
        raw = str(case["raw"])
        expected = str(case["search"])
        escaped = raw.replace("'", "''")
        completed = paradedb_psql(f"SELECT search.normalize_arabic_v1('{escaped}');\n")
        assert completed.returncode == 0, completed.stderr or completed.stdout
        sql_value = completed.stdout.strip()
        python_value = normalize_arabic_v1(raw)
        assert sql_value == expected
        assert sql_value.encode("utf-8") == python_value.encode("utf-8")
