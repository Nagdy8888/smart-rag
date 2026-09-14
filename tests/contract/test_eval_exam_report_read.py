"""Additive exam report-read RPC contract (P06-32)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260913170000_eval_exam_report_read_v1.sql"
)


def test_report_read_rpcs_are_app_api_only() -> None:
    """Latest-for-split and report-case list grant EXECUTE to app_api only."""

    sql = MIGRATION.read_text(encoding="utf-8")
    assert (
        "CREATE OR REPLACE FUNCTION app.get_latest_eval_exam_report_for_split(" in sql
    )
    assert "CREATE OR REPLACE FUNCTION app.list_eval_exam_report_cases(" in sql
    assert "GRANT EXECUTE ON FUNCTION app.get_latest_eval_exam_report_for_split(" in sql
    assert "GRANT EXECUTE ON FUNCTION app.list_eval_exam_report_cases(" in sql
    assert "REVOKE ALL ON FUNCTION app.get_latest_eval_exam_report_for_split(" in sql
    assert "r.split = v_split" in sql
    assert "FROM app.eval_exam_reports AS r" in sql
    assert "ranked_ids" not in sql
    assert "expected_answer" not in sql
    assert "SET search_path = pg_catalog, app" in sql
    assert "SECURITY DEFINER" in sql
    assert "holdout_rejected" in sql
