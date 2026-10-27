"""Anonymous dashboard aggregate and private-task boundaries on real Postgres."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from smart_rag_api.schemas.overview import OverviewResponse

from tests.contract.test_company_knowledge import db as db
from tests.contract.test_rls_matrix import rls_auth_version, rls_insert_profile


def identity(db: psycopg.Connection, role: str = "owner") -> tuple[UUID, str, int]:
    """Seed an active caller in the rollback-only fixture."""
    user = uuid4()
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=user, role=role)
        version = rls_auth_version(cursor)
    return (user, role, version)


def overview(
    db: psycopg.Connection, caller: tuple[UUID, str, int], days: int = 7
) -> OverviewResponse:
    """Read via the exact runtime role and validate the response schema."""
    with db.cursor() as cursor:
        version = rls_auth_version(cursor)
    caller = (caller[0], caller[1], version)
    db.execute("SET LOCAL ROLE app_api")
    row = db.execute(
        "SELECT app.admin_overview(%s,%s,%s,%s)", (*caller, days)
    ).fetchone()
    db.execute("RESET ROLE")
    assert row is not None
    return OverviewResponse.model_validate(row[0])


def test_aggregate_counts_dates_cost_and_unknowns(db: psycopg.Connection) -> None:
    """Separate runs from usage rows, exclude deleted/other graphs, preserve tiny cost."""
    owner = identity(db)
    employee = identity(db, "member")
    before = overview(db, owner)
    conversation = uuid4()
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id,title) VALUES (%s,%s,'DO NOT EXPOSE')",
        (conversation, employee[0]),
    )
    now = datetime.now(UTC)
    created = now - timedelta(hours=1)
    runs: list[UUID] = []
    for _index, (status, outcome, seconds) in enumerate(
        [
            ("completed", "supported", 10),
            ("completed", "partial", 30),
            ("completed", None, 20),
            ("failed", None, 5),
            ("cancelled", None, 5),
        ]
    ):
        run = uuid4()
        runs.append(run)
        db.execute(
            "INSERT INTO app.runs(id,conversation_id,creator_user_id,graph_name,status,created_at,completed_at,knowledge_result) VALUES (%s,%s,%s,'query',%s,%s,%s,%s)",
            (
                run,
                conversation,
                employee[0],
                status,
                created,
                created + timedelta(seconds=seconds),
                Jsonb({"outcome": outcome, "limitations": []}) if outcome else None,
            ),
        )
    for cost in ["0.000001", "0.000002"]:
        db.execute(
            "INSERT INTO app.llm_usage(run_id,user_id,model_id,usage_kind,cost_usd) VALUES (%s,%s,'test','answer',%s)",
            (runs[0], employee[0], Decimal(cost)),
        )
    db.execute(
        "INSERT INTO app.runs(conversation_id,creator_user_id,graph_name,created_at,status) VALUES (%s,%s,'ingest',%s,'completed'),(%s,%s,'query',%s,'completed')",
        (
            conversation,
            employee[0],
            created,
            conversation,
            employee[0],
            now - timedelta(days=100),
        ),
    )
    result = overview(db, owner)
    assert result.summary.questions == before.summary.questions + 5
    assert result.summary.measured == before.summary.measured + 2
    assert result.summary.not_measured == before.summary.not_measured + 1
    assert result.summary.latency_samples == before.summary.latency_samples + 3
    if before.summary.latency_samples == 0:
        assert result.summary.median_response_seconds == 20
    assert Decimal(result.summary.cost_usd) - Decimal(
        before.summary.cost_usd
    ) == Decimal("0.000003")
    assert len(result.daily) == 7
    assert sum(day.questions for day in result.daily) == result.summary.questions
    assert "DO NOT EXPOSE" not in str(result) and str(employee[0]) not in str(result)
    db.execute(
        "UPDATE app.conversations SET deleted_at=now() WHERE id=%s", (conversation,)
    )
    deleted = overview(db, owner)
    assert deleted.summary.questions == before.summary.questions
    assert deleted.summary.cost_usd == result.summary.cost_usd


def test_full_backlog_counts_and_current_authority(db: psycopg.Connection) -> None:
    """Full counts exceed pagination; only current versions and undeleted sources count."""
    owner = identity(db)
    before = overview(db, owner)
    for _ in range(105):
        db.execute("INSERT INTO app.documents(title) VALUES ('Unowned fixture')")
    result = overview(db, owner)
    assert (
        result.attention_counts.get("missing_owner", 0)
        == before.attention_counts.get("missing_owner", 0) + 105
    )
    assert len(result.attention_items) == 5
    doc, old, current = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO app.documents(id,title,knowledge_owner_user_id) VALUES (%s,'Current fixture',%s)",
        (doc, owner[0]),
    )
    db.execute(
        "INSERT INTO app.document_versions(id,document_id,version_number,authority_status) VALUES (%s,%s,1,'approved'),(%s,%s,2,'draft')",
        (old, doc, current, doc),
    )
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s", (current, doc)
    )
    latest = overview(db, owner)
    assert latest.authority.get("draft", 0) == result.authority.get("draft", 0) + 1
    assert latest.authority.get("approved", 0) == result.authority.get("approved", 0)
    db.execute("UPDATE app.documents SET deleted_at=now() WHERE id=%s", (doc,))
    assert overview(db, owner).authority == result.authority


def test_private_feedback_and_conflict_priority(db: psycopg.Connection) -> None:
    """Workspace totals grant no review access; sharing admits only safe task metadata."""
    owner = identity(db)
    employee = identity(db, "member")
    before = overview(db, owner)
    conversation, run, feedback = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, employee[0]),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id,graph_name,status,knowledge_result) VALUES (%s,%s,%s,'query','completed',%s)",
        (
            run,
            conversation,
            employee[0],
            Jsonb({"outcome": "conflicting_evidence", "limitations": []}),
        ),
    )
    db.execute(
        "INSERT INTO app.user_feedback(id,run_id,user_id,rating,tag,comment) VALUES (%s,%s,%s,1,'outdated answer','SECRET FEEDBACK')",
        (feedback, run, employee[0]),
    )
    private = overview(db, owner)
    assert private.attention_counts == before.attention_counts
    db.execute(
        "UPDATE app.user_feedback SET share_with_reviewers=true WHERE id=%s",
        (feedback,),
    )
    shared = overview(db, owner)
    assert (
        shared.attention_counts.get("feedback", 0)
        == before.attention_counts.get("feedback", 0) + 1
    )
    assert shared.attention_items[0].kind == "conflicting_evidence"
    assert "SECRET FEEDBACK" not in str(shared)
    db.execute(
        "UPDATE app.user_feedback SET share_with_reviewers=false WHERE id=%s",
        (feedback,),
    )
    assert overview(db, owner).attention_counts == before.attention_counts


def test_authorization_invalid_period_and_unknown_metrics(
    db: psycopg.Connection,
) -> None:
    """Spoofed roles, members, stale membership, and unexpected periods are denied."""
    owner = identity(db)
    member = identity(db, "member")
    for caller, days, error in [
        (member, 7, "forbidden"),
        ((member[0], "owner", member[2]), 7, "authorization_rejected"),
        (owner, 8, "invalid_period"),
    ]:
        with pytest.raises(psycopg.errors.RaiseException, match=error):
            with db.transaction():
                overview(db, caller, days)
    db.execute("SET LOCAL ROLE app_api")
    privilege = db.execute(
        "SELECT has_function_privilege('authenticated','app.admin_overview(uuid,text,bigint,integer)','EXECUTE')"
    ).fetchone()
    db.execute("RESET ROLE")
    assert privilege is not None and privilege[0] is False
    result = overview(db, owner, 90)
    assert len(result.daily) == 90
    assert (
        result.summary.median_response_seconds is None
        or result.summary.latency_samples > 0
    )


def test_utc_boundaries_and_invalid_latency(db: psycopg.Connection) -> None:
    """UTC windows exclude just-before/future rows and invalid timing samples."""
    owner = identity(db)
    before = overview(db, owner)
    conversation = uuid4()
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, owner[0]),
    )
    start = before.period_start
    for created, completed in [
        (start, start + timedelta(seconds=15)),
        (start - timedelta(microseconds=1), start),
        (datetime.now(UTC) + timedelta(days=1), None),
        (start + timedelta(seconds=2), start),
        (start + timedelta(seconds=3), None),
    ]:
        db.execute(
            "INSERT INTO app.runs(conversation_id,creator_user_id,graph_name,status,created_at,completed_at) VALUES (%s,%s,'query','completed',%s,%s)",
            (conversation, owner[0], created, completed),
        )
    after = overview(db, owner)
    assert after.summary.questions == before.summary.questions + 3
    assert after.daily[0].questions == before.daily[0].questions + 3
    assert after.summary.latency_samples == before.summary.latency_samples + 1
    db.execute("SET LOCAL ROLE app_api")
    with pytest.raises(psycopg.errors.RaiseException, match="authorization_rejected"):
        with db.transaction():
            db.execute(
                "SELECT app.admin_overview(%s,%s,%s,7)",
                (owner[0], owner[1], owner[2] + 100),
            )
    db.execute("RESET ROLE")
