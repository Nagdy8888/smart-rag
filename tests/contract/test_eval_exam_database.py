"""Hosted exam-run schema, hidden conversations, and RPC contract tests (P06-30)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260910160000_eval_exam_runs_v1.sql"


def _sql() -> str:
    """Return the reviewed exam migration text.

    Returns:
        Migration SQL.
    """

    return MIGRATION.read_text(encoding="utf-8")


def test_exam_tables_omit_private_and_ranked_payloads() -> None:
    """Result and report tables store counts only."""

    sql = _sql()
    results = sql.split("CREATE TABLE app.eval_exam_case_results", 1)[1].split(
        "CREATE TABLE app.eval_exam_reports", 1
    )[0]
    reports = sql.split("CREATE TABLE app.eval_exam_reports", 1)[1].split(
        "CREATE UNIQUE INDEX eval_exam_runs_one_active_uq", 1
    )[0]
    for block in (results, reports):
        columns = "\n".join(
            line
            for line in block.splitlines()
            if not line.strip().startswith("'")
            and "COMMENT" not in line.upper()
            and "no questions" not in line.lower()
        )
        lowered = columns.lower()
        assert "question text" not in lowered
        assert "expected_answer" not in lowered
        assert "ranked_ids" not in lowered
        assert "gold_ids" not in lowered
        assert " chunk_id " not in lowered and "chunk_id uuid" not in lowered


def test_exam_reports_holdout_stays_closed() -> None:
    """Successful reports CHECK holdout_opened false."""

    sql = _sql()
    assert "CONSTRAINT eval_exam_reports_holdout_chk CHECK (holdout_opened IS FALSE)" in sql
    assert "CONSTRAINT eval_exam_runs_holdout_chk CHECK (holdout_opened IS FALSE)" in sql
    assert "metric_version = 'production_corpus_all_required_gold_at_10_v1'" in sql
    assert "cache_mode = 'cold_bypass'" in sql


def test_one_active_and_qualification_indexes_exist() -> None:
    """Singleton active exam and qualification-once keys are schema-enforced."""

    sql = _sql()
    assert "CREATE UNIQUE INDEX eval_exam_runs_one_active_uq" in sql
    assert "WHERE status IN ('queued', 'running')" in sql
    assert "CREATE UNIQUE INDEX eval_exam_runs_qualification_key_uq" in sql
    assert "eval_exam:holdout_rejected" in sql
    assert "eval_exam:already_running" in sql
    assert "eval_exam:qualification_consumed" in sql
    assert "eval_exam:report_immutable" in sql


def test_browser_conversation_rpcs_hide_evaluation_purpose() -> None:
    """List/get/messages/title replacements require purpose=chat."""

    sql = _sql()
    assert "INSERT INTO app.conversations (creator_user_id, title, purpose)" in sql
    assert re.search(r"AND c\.purpose = 'chat'", sql) is not None
    assert "conversation_row.purpose IS DISTINCT FROM 'chat'" in sql
    assert "VALUES (caller_user_id, NULL, 'evaluation')" in sql


def test_runtime_roles_have_no_exam_table_dml() -> None:
    """app_api and app_worker receive no table DML on exam tables."""

    sql = _sql()
    assert (
        "REVOKE ALL ON TABLE app.eval_exam_runs FROM PUBLIC, anon, authenticated, app_api, app_worker;"
        in sql
    )
    assert (
        "REVOKE ALL ON TABLE app.eval_exam_case_results FROM PUBLIC, anon, authenticated, app_api, app_worker;"
        in sql
    )
    assert (
        "REVOKE ALL ON TABLE app.eval_exam_reports FROM PUBLIC, anon, authenticated, app_api, app_worker;"
        in sql
    )
    assert "GRANT EXECUTE ON FUNCTION app.enqueue_eval_exam(" in sql
    assert "GRANT SELECT ON TABLE app.conversations TO app_worker" not in sql


def test_exam_migration_is_security_definer_with_search_path() -> None:
    """Public exam RPCs are SECURITY DEFINER with a fixed search_path."""

    sql = _sql()
    assert sql.count("SECURITY DEFINER") >= 10
    assert "SET search_path = pg_catalog, app" in sql


@pytest.mark.skip(reason="Live mutation tests require a non-hosted SUPABASE_DB_URL")
def test_live_exam_enqueue_concurrency_placeholder() -> None:
    """Live one-active and qualification tests stay opt-in (ADR-cloud-only)."""

    pytest.skip("Hosted destructive exam tests are forbidden")
