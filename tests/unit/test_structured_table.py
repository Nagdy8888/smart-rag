"""Unit tests for Packet 7 structured-table plans, sandbox, and refusals."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import duckdb
import pyarrow as pa
import pytest
from pydantic import ValidationError
from smart_rag_core.ingestion.tables.limits import (
    DUCKDB_VERSION_PIN as INGESTION_DUCKDB_PIN,
)
from smart_rag_core.ingestion.tables.limits import (
    PYARROW_VERSION_PIN as INGESTION_ARROW_PIN,
)
from smart_rag_core.ingestion.tables.manifest import ColumnManifest
from smart_rag_core.ingestion.tables.parquet_io import write_parquet_artifact
from smart_rag_core.ingestion.tables.schema import PROVENANCE_COLUMN, ROW_INDEX_COLUMN
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tables.builder import TableQueryCompileError, compile_table_query
from smart_rag_core.tables.executor import (
    TableSandboxError,
    execute_compiled_query,
    stripped_worker_env,
)
from smart_rag_core.tables.limits import DUCKDB_VERSION_PIN, PYARROW_VERSION_PIN
from smart_rag_core.tables.plan import (
    TableAggregation,
    TableAggregationOp,
    TableComparison,
    TableOrder,
    TablePredicate,
    TablePredicateOperator,
    TableQueryPlan,
    TableSortDirection,
)
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import MemoryTableResolver, TableResolveError
from smart_rag_core.tables.sandbox_worker import SandboxWorkerError, run_worker_payload
from smart_rag_core.tables.service import (
    should_bind_structured_table,
    structured_table_query,
)
from smart_rag_core.tables.types import AuthorizedTable, CompiledTableQuery

DOCUMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TABLE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
VERSION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def _caller() -> CallerContext:
    """Return a non-disabled member caller.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _column(
    name: str,
    *,
    column_type: str = "integer",
    unit: str | None = None,
    ordinal: int | None = None,
    original_header: str | None = None,
    currency: str | None = None,
    hidden: bool = False,
) -> ColumnManifest:
    """Build one manifest column.

    Args:
        name: Internal id.
        column_type: Logical type.
        unit: Optional unit.
        ordinal: Header ordinal.
        original_header: Display header.
        currency: Optional currency code.
        hidden: Hidden-sheet flag.

    Returns:
        Column manifest.
    """

    return ColumnManifest(
        column_name=name,
        original_header=original_header or name,
        header_ordinal=ordinal if ordinal is not None else 0,
        column_type=column_type,
        unit=unit,
        currency=currency,
        hidden=hidden,
    )


def _prov(cell: str) -> str:
    """Return fixture provenance JSON for one cell.

    Args:
        cell: A1-style cell reference.

    Returns:
        Canonical provenance JSON.
    """

    return json.dumps(
        {
            "sheet": "Summary",
            "range": cell,
            "cells": [
                {
                    "format": "xlsx",
                    "sheet_name": "Summary",
                    "cell_ref": cell,
                    "row": 2,
                    "col": 2,
                }
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _write_sales(path: Path) -> str:
    """Write a three-row sales Parquet fixture.

    Args:
        path: Destination file.

    Returns:
        SHA-256 of the bytes.
    """

    payload, _schema = write_parquet_artifact(
        columns=[("dept", pa.string()), ("amount", pa.int64())],
        rows=[
            {
                "dept": "ops",
                "amount": 10,
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: _prov("B2"),
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "ops",
                "amount": 15,
                ROW_INDEX_COLUMN: 1,
                PROVENANCE_COLUMN: _prov("B3"),
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "hr",
                "amount": 7,
                ROW_INDEX_COLUMN: 2,
                PROVENANCE_COLUMN: _prov("B4"),
                "__schema_version": "table_parquet_v1",
            },
        ],
    )
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _authorized(path: Path, digest: str, **overrides: object) -> AuthorizedTable:
    """Build an authorized table around one fixture file.

    Args:
        path: Local Parquet.
        digest: Content hash.
        **overrides: Attribute replacements.

    Returns:
        Authorized table.
    """

    payload: dict[str, object] = {
        "table_id": TABLE_ID,
        "document_id": DOCUMENT_ID,
        "version_id": VERSION_ID,
        "table_name": "sales",
        "sheet_name": "Summary",
        "workbook_name": "budget.xlsx",
        "columns": (
            _column("dept", column_type="string", ordinal=0),
            _column("amount", ordinal=1),
        ),
        "parquet_sha256": digest,
        "local_parquet_path": path,
        "source_format": "xlsx",
    }
    payload.update(overrides)
    return AuthorizedTable(**payload)  # type: ignore[arg-type]


def _sum_plan() -> TableQueryPlan:
    """Return a SUM plan over amount.

    Returns:
        Validated plan.
    """

    return TableQueryPlan(
        table_id=TABLE_ID,
        version_id=VERSION_ID,
        aggregations=(
            TableAggregation(op=TableAggregationOp.SUM, column="amount", alias="total"),
        ),
    )


def test_pins_match_ingestion_and_runtime() -> None:
    """Packet 7 pins match Phase 3 artifacts and the installed DuckDB."""

    assert DUCKDB_VERSION_PIN == INGESTION_DUCKDB_PIN == "1.2.1"
    assert PYARROW_VERSION_PIN == INGESTION_ARROW_PIN == "19.0.1"
    assert duckdb.__version__ == DUCKDB_VERSION_PIN


def test_plan_rejects_sql_path_and_extra_fields() -> None:
    """Plans cannot carry SQL, paths, or unknown fields."""

    with pytest.raises(ValidationError):
        TableQueryPlan.model_validate(
            {
                "table_id": str(TABLE_ID),
                "version_id": str(VERSION_ID),
                "aggregations": [{"op": "sum", "column": "amount", "alias": "total"}],
                "sql": "SELECT 1",
            }
        )
    with pytest.raises(ValidationError):
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            predicates=(
                TablePredicate(
                    column="amount",
                    operator=TablePredicateOperator.EQ,
                    value="../secrets.parquet",
                ),
            ),
        )
    with pytest.raises(ValidationError):
        TableQueryPlan(table_id=TABLE_ID, version_id=VERSION_ID)


def test_should_bind_only_for_calculation_hints() -> None:
    """Ordinary lookup stays Hybrid; calculation hints bind the table path."""

    assert not should_bind_structured_table(table_intent=True, operation_hints=())
    assert should_bind_structured_table(table_intent=True, operation_hints=("sum",))
    assert not should_bind_structured_table(
        table_intent=False, operation_hints=("sum",)
    )


def test_sum_group_filter_and_comparison(tmp_path: Path) -> None:
    """Sum/group/filter/comparison match exact integer expected values."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    caller = _caller()
    summed = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            aggregations=(
                TableAggregation(
                    op=TableAggregationOp.SUM, column="amount", alias="total"
                ),
            ),
            predicates=(
                TablePredicate(
                    column="dept", operator=TablePredicateOperator.EQ, value="ops"
                ),
            ),
        ),
        caller=caller,
        resolver=resolver,
    )
    assert summed.rows[0]["total"] in {25, "25"}
    assert summed.input_row_count == 2
    assert summed.sheet == "Summary"
    assert "budget.xlsx!Summary!B2" in summed.source_ranges
    grouped = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            group_by=("dept",),
            aggregations=(
                TableAggregation(
                    op=TableAggregationOp.SUM, column="amount", alias="total"
                ),
            ),
        ),
        caller=caller,
        resolver=resolver,
    )
    totals = {row["dept"]: int(row["total"]) for row in grouped.rows}
    assert totals == {"ops": 25, "hr": 7}
    compared = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            comparison=TableComparison(
                aggregation=TableAggregationOp.SUM,
                column="amount",
                left=(
                    TablePredicate(
                        column="dept",
                        operator=TablePredicateOperator.EQ,
                        value="ops",
                    ),
                ),
                right=(
                    TablePredicate(
                        column="dept",
                        operator=TablePredicateOperator.EQ,
                        value="hr",
                    ),
                ),
            ),
        ),
        caller=caller,
        resolver=resolver,
    )
    assert int(compared.rows[0]["left_value"]) == 25
    assert int(compared.rows[0]["right_value"]) == 7


def test_count_average_min_max_and_sort(tmp_path: Path) -> None:
    """Count/average/min/max/sort return deterministic values."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    result = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            aggregations=(
                TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                TableAggregation(
                    op=TableAggregationOp.MIN, column="amount", alias="lo"
                ),
                TableAggregation(
                    op=TableAggregationOp.MAX, column="amount", alias="hi"
                ),
                TableAggregation(
                    op=TableAggregationOp.AVERAGE, column="amount", alias="avg_amount"
                ),
            ),
        ),
        caller=_caller(),
        resolver=resolver,
    )
    row = result.rows[0]
    assert int(row["n"]) == 3
    assert int(row["lo"]) == 7
    assert int(row["hi"]) == 15
    assert float(row["avg_amount"]) == pytest.approx(10.666, rel=1e-2)
    ordered = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            columns=("dept", "amount"),
            order_by=(TableOrder(column="amount", direction=TableSortDirection.DESC),),
        ),
        caller=_caller(),
        resolver=resolver,
    )
    assert [int(item["amount"]) for item in ordered.rows] == [15, 10, 7]


def test_decimal_null_date_and_arabic(tmp_path: Path) -> None:
    """Decimals, nulls, UTC dates, and Arabic values stay exact."""

    parquet = tmp_path / "mixed.parquet"
    payload, _schema = write_parquet_artifact(
        columns=[
            ("dept", pa.string()),
            ("amount", pa.decimal128(10, 2)),
            ("booked_on", pa.date32()),
        ],
        rows=[
            {
                "dept": "عمليات",
                "amount": Decimal("10.50"),
                "booked_on": date(2026, 1, 2),
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: _prov("C2"),
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "عمليات",
                "amount": None,
                "booked_on": date(2026, 1, 3),
                ROW_INDEX_COLUMN: 1,
                PROVENANCE_COLUMN: _prov("C3"),
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "hr",
                "amount": Decimal("1.25"),
                "booked_on": date(2026, 8, 14),
                ROW_INDEX_COLUMN: 2,
                PROVENANCE_COLUMN: _prov("C4"),
                "__schema_version": "table_parquet_v1",
            },
        ],
    )
    parquet.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    table = _authorized(
        parquet,
        digest,
        columns=(
            _column("dept", column_type="string", ordinal=0),
            _column("amount", column_type="decimal", ordinal=1),
            _column("booked_on", column_type="date", ordinal=2),
        ),
    )
    resolver = MemoryTableResolver({(TABLE_ID, VERSION_ID): table})
    summed = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            aggregations=(
                TableAggregation(
                    op=TableAggregationOp.SUM, column="amount", alias="total"
                ),
            ),
            predicates=(
                TablePredicate(
                    column="dept",
                    operator=TablePredicateOperator.EQ,
                    value="عمليات",
                ),
            ),
        ),
        caller=_caller(),
        resolver=resolver,
    )
    assert Decimal(str(summed.rows[0]["total"])) == Decimal("10.50")
    dated = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            aggregations=(TableAggregation(op=TableAggregationOp.COUNT, alias="n"),),
            predicates=(
                TablePredicate(
                    column="booked_on",
                    operator=TablePredicateOperator.EQ,
                    value="2026-08-14",
                ),
            ),
        ),
        caller=_caller(),
        resolver=resolver,
    )
    assert int(dated.rows[0]["n"]) == 1


def test_idor_and_disabled_caller(tmp_path: Path) -> None:
    """Unknown table ids and disabled callers return no artifact."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    with pytest.raises(TableResolveError):
        structured_table_query(
            TableQueryPlan(
                table_id=uuid4(),
                version_id=VERSION_ID,
                aggregations=(
                    TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                ),
            ),
            caller=_caller(),
            resolver=resolver,
        )
    disabled = CallerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
        disabled=True,
    )
    with pytest.raises(TableResolveError):
        structured_table_query(
            TableQueryPlan(
                table_id=TABLE_ID,
                version_id=VERSION_ID,
                aggregations=(
                    TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                ),
            ),
            caller=disabled,
            resolver=resolver,
        )


def test_wrong_version_is_unauthorized(tmp_path: Path) -> None:
    """A non-current version id cannot resolve the artifact."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    with pytest.raises(TableResolveError):
        structured_table_query(
            TableQueryPlan(
                table_id=TABLE_ID,
                version_id=uuid4(),
                aggregations=(
                    TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                ),
            ),
            caller=_caller(),
            resolver=resolver,
        )


def test_hidden_sheet_and_formula_and_mixed_units_refuse(tmp_path: Path) -> None:
    """Hidden sheets, formula columns, and mixed units refuse."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    hidden = _authorized(parquet, digest, hidden_sheet=True)
    with pytest.raises(TableQueryRefusal, match="hidden_sheet_policy"):
        structured_table_query(
            _sum_plan(),
            caller=_caller(),
            resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): hidden}),
        )
    formula = _authorized(parquet, digest, formula_columns=("amount",))
    with pytest.raises(TableQueryRefusal, match="missing_formula_cache"):
        structured_table_query(
            _sum_plan(),
            caller=_caller(),
            resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): formula}),
        )
    mixed = _authorized(
        parquet,
        digest,
        columns=(
            _column("dept", column_type="string", ordinal=0),
            _column("amount", unit="USD", ordinal=1),
            ColumnManifest(
                column_name="eur_amount",
                original_header="eur_amount",
                header_ordinal=2,
                column_type="integer",
                currency="EUR",
            ),
        ),
    )
    with pytest.raises(TableQueryRefusal, match="mixed_units_or_currency"):
        structured_table_query(
            TableQueryPlan(
                table_id=TABLE_ID,
                version_id=VERSION_ID,
                aggregations=(
                    TableAggregation(
                        op=TableAggregationOp.SUM, column="amount", alias="usd"
                    ),
                    TableAggregation(
                        op=TableAggregationOp.SUM, column="eur_amount", alias="eur"
                    ),
                ),
            ),
            caller=_caller(),
            resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): mixed}),
        )


def test_duplicate_header_reference_refuses(tmp_path: Path) -> None:
    """Ambiguous original headers cannot be used as column ids."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    table = _authorized(
        parquet,
        digest,
        columns=(
            _column(
                "amount_a",
                ordinal=0,
                original_header="Amount",
            ),
            _column(
                "amount_b",
                ordinal=1,
                original_header="Amount",
            ),
        ),
    )
    with pytest.raises(TableQueryRefusal, match="duplicate_header_reference"):
        structured_table_query(
            TableQueryPlan(
                table_id=TABLE_ID,
                version_id=VERSION_ID,
                aggregations=(
                    TableAggregation(
                        op=TableAggregationOp.SUM, column="Amount", alias="total"
                    ),
                ),
            ),
            caller=_caller(),
            resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): table}),
        )


def test_non_finite_result_refuses(tmp_path: Path) -> None:
    """Infinity cannot be returned as a calculated total."""

    parquet = tmp_path / "inf.parquet"
    payload, _schema = write_parquet_artifact(
        columns=[("amount", pa.float64())],
        rows=[
            {
                "amount": math.inf,
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: _prov("B2"),
                "__schema_version": "table_parquet_v1",
            }
        ],
    )
    parquet.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    table = _authorized(
        parquet,
        digest,
        columns=(_column("amount", column_type="float", ordinal=0),),
    )
    with pytest.raises(TableSandboxError, match="non_finite_result"):
        structured_table_query(
            _sum_plan(),
            caller=_caller(),
            resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): table}),
        )


def test_compile_rejects_unknown_column() -> None:
    """Unknown internal ids cannot be compiled into SQL."""

    plan = TableQueryPlan(
        table_id=TABLE_ID,
        version_id=VERSION_ID,
        aggregations=(
            TableAggregation(op=TableAggregationOp.SUM, column="nope", alias="total"),
        ),
    )
    with pytest.raises(TableQueryCompileError):
        compile_table_query(plan, allowed_columns=frozenset({"amount"}))


def test_worker_rejects_blocked_sql_path_hash_and_http(tmp_path: Path) -> None:
    """The worker refuses ATTACH, COPY, HTTP, swapped path, and bad hash."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    other = tmp_path / "other.parquet"
    other.write_bytes(parquet.read_bytes())
    base = {
        "parquet_path": parquet.as_posix(),
        "expected_path": parquet.as_posix(),
        "expected_sha256": digest,
        "params": [],
        "count_sql": "SELECT COUNT(*) FROM allowed_table",
        "count_params": [],
        "provenance_sql": "",
        "provenance_params": [],
        "row_limit": 10,
        "output_byte_limit": 1000,
    }
    with pytest.raises(SandboxWorkerError, match="blocked_sql"):
        run_worker_payload({**base, "sql": "ATTACH 'x.db' AS db"})
    with pytest.raises(SandboxWorkerError, match="blocked_sql"):
        run_worker_payload({**base, "sql": "COPY allowed_table TO 'out.csv'"})
    with pytest.raises(SandboxWorkerError, match="blocked_sql"):
        run_worker_payload(
            {
                **base,
                "sql": "SELECT * FROM read_parquet('https://example.com/x.parquet')",
            }
        )
    with pytest.raises(SandboxWorkerError, match="artifact_path_mismatch"):
        run_worker_payload(
            {
                **base,
                "parquet_path": other.as_posix(),
                "sql": "SELECT COUNT(*) FROM allowed_table",
            }
        )
    with pytest.raises(SandboxWorkerError, match="artifact_hash_mismatch"):
        run_worker_payload(
            {
                **base,
                "expected_sha256": "00" * 32,
                "sql": "SELECT COUNT(*) FROM allowed_table",
            }
        )


def test_worker_blocks_local_read_parquet_escape(tmp_path: Path) -> None:
    """enable_external_access=false blocks read_parquet of another file."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    other = tmp_path / "secrets.parquet"
    other.write_bytes(parquet.read_bytes())
    other_literal = other.as_posix().replace("'", "''")
    with pytest.raises(Exception, match=r"Permission|file system|blocked"):
        run_worker_payload(
            {
                "parquet_path": parquet.as_posix(),
                "expected_path": parquet.as_posix(),
                "expected_sha256": digest,
                "sql": (
                    f"SELECT * FROM read_parquet('{other_literal}')"  # noqa: S608
                ),
                "params": [],
                "count_sql": "SELECT COUNT(*) FROM allowed_table",
                "count_params": [],
                "row_limit": 10,
                "output_byte_limit": 1000,
            }
        )


def test_catalog_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    """A replaced Parquet file cannot satisfy the catalog hash."""

    parquet = tmp_path / "sales.parquet"
    _write_sales(parquet)
    table = _authorized(parquet, "11" * 32)
    resolver = MemoryTableResolver({(TABLE_ID, VERSION_ID): table})
    with pytest.raises(TableSandboxError, match="artifact_hash_mismatch"):
        structured_table_query(_sum_plan(), caller=_caller(), resolver=resolver)


def test_worker_output_row_limit_fails_closed(tmp_path: Path) -> None:
    """The worker rejects more rows than the declared output cap."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    with pytest.raises(SandboxWorkerError, match="output_row_limit"):
        run_worker_payload(
            {
                "parquet_path": parquet.as_posix(),
                "expected_path": parquet.as_posix(),
                "expected_sha256": digest,
                "sql": 'SELECT "dept", "amount" FROM allowed_table',
                "params": [],
                "count_sql": "SELECT COUNT(*) FROM allowed_table",
                "count_params": [],
                "row_limit": 1,
                "output_byte_limit": 10000,
            }
        )


def test_output_byte_limit_fails_closed(tmp_path: Path) -> None:
    """Returning more rows than the plan cap fails closed."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    with pytest.raises(TableSandboxError, match="output_byte_limit"):
        structured_table_query(
            TableQueryPlan(
                table_id=TABLE_ID,
                version_id=VERSION_ID,
                columns=("dept", "amount"),
                order_by=(
                    TableOrder(column="amount", direction=TableSortDirection.ASC),
                ),
                output_byte_limit=8,
            ),
            caller=_caller(),
            resolver=resolver,
        )


def test_process_not_reused_after_violation(tmp_path: Path) -> None:
    """A later allowed query still works after a blocked worker attempt."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    with pytest.raises(SandboxWorkerError):
        run_worker_payload(
            {
                "parquet_path": parquet.as_posix(),
                "expected_path": parquet.as_posix(),
                "expected_sha256": digest,
                "sql": "INSTALL httpfs",
                "params": [],
                "count_sql": "SELECT COUNT(*) FROM allowed_table",
                "count_params": [],
                "row_limit": 10,
                "output_byte_limit": 1000,
            }
        )
    resolver = MemoryTableResolver(
        {(TABLE_ID, VERSION_ID): _authorized(parquet, digest)}
    )
    result = structured_table_query(_sum_plan(), caller=_caller(), resolver=resolver)
    assert int(result.rows[0]["total"]) == 32
    second = structured_table_query(_sum_plan(), caller=_caller(), resolver=resolver)
    assert second.artifact_sha256 == digest


def test_deadline_terminate_then_kill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The parent interrupts then kills a hung worker."""

    class FakeProc:
        """Stand-in process that never returns from communicate."""

        def __init__(self) -> None:
            """Record terminate/kill calls."""

            self.terminated = False
            self.killed = False
            self.returncode: int | None = None

        def communicate(
            self, _data: str, timeout: float | None = None
        ) -> tuple[str, str]:
            """Raise the process deadline.

            Args:
                _data: Unused stdin.
                timeout: Deadline seconds.

            Returns:
                Never returns.

            Raises:
                TimeoutExpired: Always.
            """

            raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0)

        def terminate(self) -> None:
            """Record SIGTERM-equivalent."""

            self.terminated = True

        def kill(self) -> None:
            """Record kill."""

            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            """Hang until killed.

            Args:
                timeout: Wait seconds.

            Returns:
                Exit code after kill.

            Raises:
                TimeoutExpired: Before kill.
            """

            if not self.killed:
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0)
            self.returncode = -9
            return -9

    fake = FakeProc()

    def _fake_popen(*args: object, **kwargs: object) -> FakeProc:
        """Return the hung process stand-in.

        Args:
            *args: Ignored Popen args.
            **kwargs: Ignored Popen kwargs.

        Returns:
            The prebuilt fake process.
        """

        return fake

    monkeypatch.setattr(
        "smart_rag_core.tables.executor.subprocess.Popen",
        _fake_popen,
    )
    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    compiled = CompiledTableQuery(
        sql="SELECT 1",
        params=(),
        count_sql="SELECT 1",
        count_params=(),
        provenance_sql="SELECT 1",
        provenance_params=(),
    )
    with pytest.raises(TableSandboxError, match="statement_deadline"):
        execute_compiled_query(
            compiled,
            parquet_path=parquet,
            expected_sha256=digest,
            row_limit=1,
            output_byte_limit=100,
            deadline_seconds=0.05,
            kill_grace_seconds=0.01,
        )
    assert fake.terminated is True
    assert fake.killed is True


def test_symlink_escape_fails_closed(tmp_path: Path) -> None:
    """A symlink to a different file cannot satisfy the expected path."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    other = tmp_path / "other.parquet"
    other.write_bytes(b"not-the-artifact")
    link = tmp_path / "link.parquet"
    try:
        link.symlink_to(other)
    except OSError:
        pytest.skip("symlink creation requires privileges on this host")
    with pytest.raises(SandboxWorkerError, match="artifact_path_mismatch"):
        run_worker_payload(
            {
                "parquet_path": link.as_posix(),
                "expected_path": parquet.as_posix(),
                "expected_sha256": digest,
                "sql": "SELECT COUNT(*) FROM allowed_table",
                "params": [],
                "count_sql": "SELECT COUNT(*) FROM allowed_table",
                "count_params": [],
                "row_limit": 10,
                "output_byte_limit": 1000,
            }
        )


def test_worker_env_strips_secrets() -> None:
    """Sandbox environment cannot inherit API keys or JWTs."""

    env = stripped_worker_env(
        {
            "PATH": "/bin",
            "OPENAI_API_KEY": "sk-test",
            "SUPABASE_SERVICE_ROLE_KEY": "secret",
            "LANGSMITH_API_KEY": "ls-test",
            "PYTHONPATH": "/app",
        }
    )
    assert "OPENAI_API_KEY" not in env
    assert "SUPABASE_SERVICE_ROLE_KEY" not in env
    assert "LANGSMITH_API_KEY" not in env
    assert env["PYTHONPATH"] == "/app"
    assert env["SMART_RAG_TABLE_SANDBOX"] == "1"


def test_timestamp_stays_utc(tmp_path: Path) -> None:
    """Timestamp filters use the worker UTC session, not the host zone."""

    parquet = tmp_path / "ts.parquet"
    instant = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    payload, _schema = write_parquet_artifact(
        columns=[("amount", pa.int64()), ("seen_at", pa.timestamp("us", tz="UTC"))],
        rows=[
            {
                "amount": 4,
                "seen_at": instant,
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: _prov("D2"),
                "__schema_version": "table_parquet_v1",
            }
        ],
    )
    parquet.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    table = _authorized(
        parquet,
        digest,
        columns=(
            _column("amount", ordinal=0),
            _column("seen_at", column_type="timestamp", ordinal=1),
        ),
    )
    result = structured_table_query(
        TableQueryPlan(
            table_id=TABLE_ID,
            version_id=VERSION_ID,
            aggregations=(
                TableAggregation(
                    op=TableAggregationOp.SUM, column="amount", alias="total"
                ),
            ),
            predicates=(
                TablePredicate(
                    column="seen_at",
                    operator=TablePredicateOperator.EQ,
                    value="2026-08-14 12:00:00+00",
                ),
            ),
        ),
        caller=_caller(),
        resolver=MemoryTableResolver({(TABLE_ID, VERSION_ID): table}),
    )
    assert int(result.rows[0]["total"]) == 4
    assert "timezone:UTC" in result.diagnostics
