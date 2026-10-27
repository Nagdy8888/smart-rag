"""Measured counters are immutable, private, and independent of budget caps."""

from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from tests.contract.test_admin_overview import identity
from tests.contract.test_company_knowledge import db as db
from tests.contract.test_usage_cost_reporting import report


def test_measurements_exclude_allowances_and_preserve_unknown_model_tokens(
    db: psycopg.Connection,
) -> None:
    """Only observed counters enter actual token totals, regardless of pricing."""
    owner = identity(db)
    before = report(db, owner)
    measured, timeout = uuid4(), uuid4()
    db.execute(
        "INSERT INTO app.llm_usage(id,user_id,model_id,usage_kind,prompt_tokens,completion_tokens,cost_usd,timeout_after_send) VALUES (%s,%s,'unknown','answer',123,45,0.4,false),(%s,%s,'gpt-6-luna','answer',8000,2000,0.4,true)",
        (measured, owner[0], timeout, owner[0]),
    )
    db.execute("SET LOCAL ROLE app_api")
    args = (*owner, measured, 123, 45, 100)
    db.execute("SELECT app.record_usage_token_measurement(%s,%s,%s,%s,%s,%s,%s)", args)
    db.execute("SELECT app.record_usage_token_measurement(%s,%s,%s,%s,%s,%s,%s)", args)
    with pytest.raises(psycopg.errors.RaiseException):
        with db.transaction():
            db.execute(
                "SELECT app.record_usage_token_measurement(%s,%s,%s,%s,8000,2000,0)",
                (*owner, timeout),
            )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction():
            db.execute("SELECT * FROM app.usage_token_measurements")
    db.execute("RESET ROLE")
    after = report(db, owner)
    assert after.measured_prompt_tokens == (before.measured_prompt_tokens or 0) + 123
    assert (
        after.measured_completion_tokens
        == (before.measured_completion_tokens or 0) + 45
    )
    assert after.unmeasured_operations == before.unmeasured_operations + 1
    assert after.budget_accounted_usd - before.budget_accounted_usd == Decimal("0.8")


def test_measurement_owner_idempotency_and_immutability(db: psycopg.Connection) -> None:
    """A foreign caller cannot forge counters, and duplicate writes must match."""
    owner, other = identity(db), identity(db, "member")
    usage = uuid4()
    db.execute(
        "INSERT INTO app.llm_usage(id,user_id,model_id,usage_kind,prompt_tokens,completion_tokens,cost_usd) VALUES (%s,%s,'gpt-6-luna','answer',10,2,0.000002)",
        (usage, owner[0]),
    )
    db.execute("SET LOCAL ROLE app_api")
    with pytest.raises(psycopg.errors.RaiseException, match="run_forbidden"):
        with db.transaction():
            db.execute(
                "SELECT app.record_usage_token_measurement(%s,%s,%s,%s,10,2,0)",
                (*other, usage),
            )
    db.execute(
        "SELECT app.record_usage_token_measurement(%s,%s,%s,%s,10,2,0)", (*owner, usage)
    )
    with pytest.raises(
        psycopg.errors.RaiseException, match="token_measurement_conflict"
    ):
        with db.transaction():
            db.execute(
                "SELECT app.record_usage_token_measurement(%s,%s,%s,%s,10,2,1)",
                (*owner, usage),
            )
    db.execute("RESET ROLE")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        with db.transaction():
            db.execute(
                "UPDATE app.usage_token_measurements SET prompt_tokens=11 WHERE usage_id=%s",
                (usage,),
            )
