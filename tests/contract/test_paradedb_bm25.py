"""Contract tests for ParadeDB pg_search BM25 semantics on the pinned local image."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.contract.integration_support import (
    ensure_paradedb_arabic_normalizer,
    paradedb_psql,
    paradedb_reachable,
)

pytestmark = pytest.mark.skipif(
    not paradedb_reachable(),
    reason="docker compose paradedb service not reachable",
)

_SETUP_SQL = """
DROP TABLE IF EXISTS qual_bm25_contract CASCADE;
CREATE TABLE qual_bm25_contract (
  id text PRIMARY KEY,
  body text NOT NULL,
  lang text NOT NULL
);

INSERT INTO qual_bm25_contract (id, body, lang) VALUES
  ('en-leave', 'annual leave policy grants fifteen paid working days', 'en'),
  ('en-safety', 'warehouse safety requires a hard hat near forklifts', 'en'),
  ('en-delivery', 'purchase order PO-7781 requires delivery within thirty days', 'en'),
  ('ar-leave', 'سياسة الإجازات السنوية تمنح الموظف خمسة عشر يوما', 'ar'),
  ('ar-safety', 'إجراءات السلامة تفرض ارتداء خوذة في المستودع', 'ar');

CREATE INDEX qual_bm25_contract_idx ON qual_bm25_contract
USING bm25 (
  id,
  (body::pdb.unicode_words),
  lang
)
WITH (key_field = 'id');
"""


def _query_ids(sql: str) -> list[str]:
    """Run one ParadeDB SQL query and return the first column as string IDs.

    Args:
        sql: SQL selecting at least one column.

    Returns:
        Ordered identifier strings from the first result column.

    Raises:
        AssertionError: When psql fails or returns no rows unexpectedly.
    """

    completed = paradedb_psql(sql)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return lines


def _setup_qual_table() -> None:
    """Create the temporary BM25 qualification table and index."""

    ensure_paradedb_arabic_normalizer()
    completed = paradedb_psql(_SETUP_SQL)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.fixture(scope="module", autouse=True)
def _qual_bm25_table() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Provision one shared BM25 qualification table for the module."""

    _setup_qual_table()
    yield
    paradedb_psql("DROP TABLE IF EXISTS qual_bm25_contract CASCADE;\n")


def test_extension_versions_are_present() -> None:
    """Prove pg_search and vector extensions are installed with version strings."""

    completed = paradedb_psql(
        """
        SELECT extname, extversion
        FROM pg_extension
        WHERE extname IN ('pg_search', 'vector')
        ORDER BY extname;
        """
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    rows = {
        parts[0].strip(): parts[1].strip()
        for line in completed.stdout.splitlines()
        if "|" in line
        for parts in [line.split("|", maxsplit=1)]
    }
    assert rows.get("pg_search")
    assert rows.get("vector")


def test_bm25_score_and_rank() -> None:
    """``pdb.score(id)`` orders leave-policy rows above unrelated safety text."""

    ids = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ||| 'annual leave policy'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 3;
        """
    )
    assert ids[0] == "en-leave"
    assert "en-safety" not in ids[:1]


def test_bm25_phrase_query_when_supported() -> None:
    """Phrase operator ``###`` prefers contiguous token sequences when available."""

    ids = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ### 'paid working days'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 3;
        """
    )
    assert "en-leave" in ids


def test_bm25_boolean_conjunction() -> None:
    """Conjunction operator ``&&&`` requires all query tokens to match."""

    ids = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body &&& 'warehouse safety'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 3;
        """
    )
    assert ids[0] == "en-safety"


def test_bm25_filter_on_lang_column() -> None:
    """Postgres ``WHERE lang =`` filters BM25 results to one language bucket."""

    ids = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ||| 'annual leave' AND lang = 'en'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 3;
        """
    )
    assert ids == ["en-leave"]


def test_bm25_field_query_on_body_column() -> None:
    """Field-scoped ``body |||`` matches identifier text without lang noise."""

    ids = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ||| 'PO-7781'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 3;
        """
    )
    assert ids[0] == "en-delivery"


def test_bm25_stable_key_field_tiebreaker() -> None:
    """Tie-breaking on ``id`` keeps ordering deterministic for equal scores."""

    first = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ||| 'policy'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 5;
        """
    )
    second = _query_ids(
        """
        SELECT id
        FROM qual_bm25_contract
        WHERE body ||| 'policy'
        ORDER BY pdb.score(id) DESC, id ASC
        LIMIT 5;
        """
    )
    assert first == second
    assert first == sorted(first)


def test_index_version_mismatch_fails_closed() -> None:
    """Wrong ``app.bm25_normalization_version`` rejects queries before search."""

    ok = paradedb_psql("SELECT search.assert_arabic_normalization_version();\n")
    assert ok.returncode == 0, ok.stderr or ok.stdout

    mismatch = paradedb_psql(
        """
        SELECT set_config('app.bm25_normalization_version', 'wrong_version', false);
        SELECT search.assert_arabic_normalization_version();
        """
    )
    assert mismatch.returncode != 0
    assert (
        "normalization version mismatch" in (mismatch.stderr + mismatch.stdout).lower()
    )
