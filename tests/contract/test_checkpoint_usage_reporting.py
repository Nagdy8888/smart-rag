"""Recovered usage obeys caller scope and deduplicates against the live ledger."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.observability.checkpoint_usage import CheckpointUsageSummary

from tests.contract.test_admin_overview import identity, overview
from tests.contract.test_company_knowledge import db as db


def summary(
    db: psycopg.Connection, caller: tuple[UUID, str, int], company: bool = True
) -> CheckpointUsageSummary:
    """Call only the protected runtime RPC."""
    db.execute("SET LOCAL ROLE app_api")
    row = db.execute(
        "SELECT app.summarize_checkpoint_usage(%s,%s,%s,%s)", (*caller, company)
    ).fetchone()
    db.execute("RESET ROLE")
    assert row is not None
    return CheckpointUsageSummary.model_validate(row[0])


def add_history(db: psycopg.Connection, user: UUID, run: UUID) -> None:
    """Seed a single operator-owned stored snapshot without application content."""
    db.execute(
        "INSERT INTO app.checkpoint_usage_runs VALUES(%s,%s,'snapshot',%s,1000,100,0.001,0.001,'recorded_estimate')",
        (run, user, datetime.now(UTC)),
    )


def test_ledger_and_measurement_overlap_are_not_added_twice(
    db: psycopg.Connection,
) -> None:
    """Stored costs defer to ledger rows; stored counts defer to provider measurements."""
    owner = identity(db)
    before = summary(db, owner)
    dashboard_before = overview(db, owner)
    old, live = uuid4(), uuid4()
    conversation = uuid4()
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES(%s,%s)",
        (conversation, owner[0]),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id,graph_name,status) VALUES(%s,%s,%s,'query','completed')",
        (live, conversation, owner[0]),
    )
    add_history(db, owner[0], old)
    add_history(db, owner[0], live)
    usage = uuid4()
    db.execute(
        "INSERT INTO app.llm_usage(id,user_id,run_id,model_id,usage_kind,prompt_tokens,completion_tokens,cost_usd) VALUES(%s,%s,%s,'gpt-6-luna','answer',1000,100,0.00015)",
        (usage, owner[0], live),
    )
    result = summary(db, owner)
    assert result.runs - before.runs == 2
    assert result.additional_estimated_cost_usd is not None
    assert result.additional_estimated_cost_usd - (
        before.additional_estimated_cost_usd or 0
    ) == Decimal("0.001")
    assert result.additional_prompt_tokens - before.additional_prompt_tokens == 2000
    db.execute(
        "INSERT INTO app.usage_token_measurements(usage_id,prompt_tokens,completion_tokens,cached_prompt_tokens) VALUES(%s,1000,100,0)",
        (usage,),
    )
    result = summary(db, owner)
    assert result.additional_prompt_tokens - before.additional_prompt_tokens == 1000
    dashboard = overview(db, owner)
    assert dashboard.summary.display_cost_usd is not None
    assert dashboard.summary.display_cost_usd - (
        dashboard_before.summary.display_cost_usd or 0
    ) == Decimal("0.00115")
    assert dashboard.daily[-1].display_cost_usd is not None


def test_member_scope_and_direct_table_access_are_restricted(
    db: psycopg.Connection,
) -> None:
    """Old hosted users are never reassigned to a local caller's personal totals."""
    owner = identity(db)
    member = identity(db, "member")
    before = summary(db, member, False)
    add_history(db, owner[0], uuid4())
    assert summary(db, member, False) == before
    db.execute("SET LOCAL ROLE app_api")
    with pytest.raises(psycopg.errors.RaiseException, match="forbidden"):
        with db.transaction():
            db.execute("SELECT app.summarize_checkpoint_usage(%s,%s,%s,true)", member)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction():
            db.execute("SELECT * FROM app.checkpoint_usage_runs")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction():
            db.execute(
                "SELECT app.checkpoint_usage_summary('-infinity','infinity',NULL)"
            )
    db.execute("RESET ROLE")


def test_extraction_and_recovery_are_idempotent(db: psycopg.Connection) -> None:
    """Decode stored primitive runtime data and retain one cumulative run total."""
    import ormsgpack
    from psycopg.types.json import Jsonb

    from scripts.ops.recover_checkpoint_usage import extract_usage, write_usage

    owner = identity(db)
    thread, run = str(uuid4()), uuid4()
    db.execute(
        "INSERT INTO langgraph.checkpoint_blobs(thread_id,checkpoint_ns,channel,version,type,blob) VALUES(%s,'','authorized_runtime','test','msgpack',%s)",
        (thread, ormsgpack.packb({"run_id": str(run), "user_id": str(owner[0])})),
    )
    for index, tokens in enumerate([100, 150, 0]):
        db.execute(
            "INSERT INTO langgraph.checkpoints(thread_id,checkpoint_ns,checkpoint_id,checkpoint,type,metadata) VALUES(%s,'',%s,%s,'json',%s)",
            (
                thread,
                str(index),
                Jsonb(
                    {
                        "ts": f"2026-10-26T01:00:0{index}+00:00",
                        "channel_versions": {"authorized_runtime": "test"},
                        "channel_values": {
                            "prompt_tokens": tokens,
                            "completion_tokens": 10 if tokens else 0,
                            "cost_usd": 0.001,
                        },
                    }
                ),
                Jsonb({}),
            ),
        )
    recovered = extract_usage(db)
    chosen = [row for row in recovered if row.run_id == run]
    assert len(chosen) == 1 and chosen[0].prompt_tokens == 150
    write_usage(db, recovered)
    before = summary(db, owner)
    write_usage(db, recovered)
    assert summary(db, owner) == before
    assert before.prompt_tokens >= 150


def test_unknown_only_daily_cost_is_a_gap(db: psycopg.Connection) -> None:
    """Historical runs with no costs must not become a zero-dollar chart bar."""
    owner = identity(db)
    db.execute(
        "INSERT INTO app.checkpoint_usage_runs VALUES(%s,%s,'unknown-cost',%s,100,10,NULL,NULL,'unrecorded')",
        (uuid4(), owner[0], datetime.now(UTC)),
    )
    result = overview(db, owner)
    assert result.summary.display_cost_usd is None
    assert result.daily[-1].display_cost_usd is None
