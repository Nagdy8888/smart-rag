"""Exam supervisor lifespan binding (P06-31)."""

from __future__ import annotations

from types import SimpleNamespace

from smart_rag_api.services.eval_exam_supervisor import bind_eval_exam_supervisor
from smart_rag_core.settings import Environment


def test_supervisor_stays_off_when_workspace_flag_is_false() -> None:
    """Default local/test processes do not start an exam loop."""

    application = SimpleNamespace(state=SimpleNamespace())
    settings = SimpleNamespace(
        pdf_eval_workspace_enabled=False,
        app_env=Environment.TEST,
        supabase_db_url=None,
    )
    task = bind_eval_exam_supervisor(application, settings)  # type: ignore[arg-type]
    assert task is None
    assert application.state.eval_exam_supervisor is None


def test_supervisor_requires_app_api_dsn() -> None:
    """A workspace flag without a DSN cannot claim exams."""

    application = SimpleNamespace(state=SimpleNamespace())
    settings = SimpleNamespace(
        pdf_eval_workspace_enabled=True,
        app_env=Environment.TEST,
        supabase_db_url=None,
    )
    task = bind_eval_exam_supervisor(application, settings)  # type: ignore[arg-type]
    assert task is None
    assert application.state.eval_exam_supervisor is None
