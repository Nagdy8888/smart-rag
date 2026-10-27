"""Cost projections preserve accounting and never turn timeouts into token bills."""

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.gateways.cost_reporting import CostReporting

from tests.contract.test_admin_overview import identity, overview
from tests.contract.test_company_knowledge import db as db


def report(
    db: psycopg.Connection, caller: tuple[UUID, str, int], company: bool = True
) -> CostReporting:
    """Call the protected aggregate as the runtime role."""
    db.execute("SET LOCAL ROLE app_api")
    row = db.execute(
        "SELECT app.summarize_usage_cost_reporting(%s,%s,%s,%s)", (*caller, company)
    ).fetchone()
    db.execute("RESET ROLE")
    assert row is not None
    return CostReporting.model_validate(row[0])


def test_historical_reconstruction_preserves_ledger_and_excludes_caps(
    db: psycopg.Connection,
) -> None:
    """Reconstruct usable Luna tokens; leave timeout/synthetic/unknown calls unresolved."""
    owner = identity(db)
    before = report(db, owner)
    rows = [
        ("gpt-6-luna", "answer", 1000, 100, "0.4", False),
        ("gpt-6-luna", "answer", 8000, 2000, "0.4", True),
        ("gpt-6-luna", "rerank", 12000, 2000, "0.2", False),
        ("unknown", "profile", 1, 1, "0.08", False),
        ("text-embedding-3-large", "embedding", 1000, 0, "0.00013", False),
    ]
    for model, kind, input_tokens, output_tokens, cost, timeout in rows:
        db.execute(
            "INSERT INTO app.llm_usage(user_id,model_id,usage_kind,prompt_tokens,completion_tokens,cost_usd,timeout_after_send) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                owner[0],
                model,
                kind,
                input_tokens,
                output_tokens,
                Decimal(cost),
                timeout,
            ),
        )
    result = report(db, owner)
    assert result.estimated_cost_usd is not None
    assert result.estimated_cost_usd - (before.estimated_cost_usd or 0) == Decimal(
        "0.00028"
    )
    assert result.safety_allowance_usd - before.safety_allowance_usd == Decimal("0.68")
    assert result.unresolved_operations - before.unresolved_operations == 3
    assert result.reconstructed_operations - before.reconstructed_operations == 2
    assert result.budget_accounted_usd - before.budget_accounted_usd == Decimal(
        "1.08013"
    )
    dashboard = overview(db, owner)
    assert dashboard.summary.cost_reporting is not None
    assert dashboard.summary.cost_reporting.unresolved_operations >= 3


def test_explicit_provenance_is_immutable_private_and_idempotent(
    db: psycopg.Connection,
) -> None:
    """Only the usage owner may append provenance; the source ledger stays unchanged."""
    owner = identity(db)
    member = identity(db, "member")
    usage = uuid4()
    db.execute(
        "INSERT INTO app.llm_usage(id,user_id,model_id,usage_kind,prompt_tokens,completion_tokens,cost_usd) VALUES (%s,%s,'unknown','answer',1,1,0.023)",
        (usage, owner[0]),
    )
    before = report(db, owner)
    db.execute("SET LOCAL ROLE app_api")
    args = (*owner, usage, "supplied_cost_estimate", Decimal("0.023"))
    db.execute("SELECT app.record_usage_cost_basis(%s,%s,%s,%s,%s,%s)", args)
    db.execute("SELECT app.record_usage_cost_basis(%s,%s,%s,%s,%s,%s)", args)
    with pytest.raises(psycopg.errors.RaiseException, match="cost_basis_conflict"):
        with db.transaction():
            db.execute(
                "SELECT app.record_usage_cost_basis(%s,%s,%s,%s,%s,%s)",
                (*owner, usage, "standard_token_estimate", Decimal("0.01")),
            )
    with pytest.raises(psycopg.errors.RaiseException, match="run_forbidden"):
        with db.transaction():
            db.execute(
                "SELECT app.record_usage_cost_basis(%s,%s,%s,%s,%s,%s)",
                (*member, usage, "supplied_cost_estimate", Decimal("0.023")),
            )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction():
            db.execute("SELECT * FROM app.usage_cost_basis")
    db.execute("RESET ROLE")
    after = report(db, owner)
    assert after.budget_accounted_usd == before.budget_accounted_usd
    assert after.estimated_cost_usd == (before.estimated_cost_usd or 0) + Decimal(
        "0.023"
    )
    assert after.unresolved_operations == before.unresolved_operations - 1
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        with db.transaction():
            db.execute(
                "UPDATE app.usage_cost_basis SET estimated_cost_usd=0 WHERE usage_id=%s",
                (usage,),
            )
    mine = report(db, member, False)
    assert mine.budget_accounted_usd == 0
    with pytest.raises(psycopg.errors.RaiseException, match="forbidden"):
        with db.transaction():
            report(db, member)
