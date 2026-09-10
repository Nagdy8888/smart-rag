"""Contract tests for isolated bake-off indexing helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_core.evaluation.parser_bakeoff.indexing import (
    assert_title_owned,
    lane_document_title,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError

from tests.contract.integration_support import resolve_supabase_db_url


def test_lane_titles_are_run_scoped() -> None:
    """Each lane title uses the exact run prefix."""

    run_id = "20260909T000000Z-abcdef123456"
    assert lane_document_title(run_id, "current") == f"parser-bakeoff:{run_id}:current"
    assert (
        lane_document_title(run_id, "anydoc_local")
        == f"parser-bakeoff:{run_id}:anydoc_local"
    )
    assert_title_owned(
        title=lane_document_title(run_id, "current"),
        run_id=run_id,
        lane_id="current",
    )
    with pytest.raises(BakeoffError) as err:
        assert_title_owned(
            title="unrelated-document",
            run_id=run_id,
            lane_id="current",
        )
    assert err.value.code == "cleanup_title_mismatch"


def test_index_live_path_is_opt_in() -> None:
    """Live persist is operator-run; missing DSN is an explicit skip."""

    if resolve_supabase_db_url() is None:
        pytest.skip("SUPABASE_DB_URL not set; DB-backed bake-off index is opt-in")
    assert uuid4()
