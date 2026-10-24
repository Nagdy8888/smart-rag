"""Authorization and integrity boundaries for on-demand table artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest
from smart_rag_api.services import tables_http
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tables.plan import TableQueryPlan
from smart_rag_core.tables.resolver import TableResolveError
from smart_rag_core.tables.service import StructuredTableError


def test_materialization_requires_authorization_and_matching_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No download before authorization; corrupt objects never reach DuckDB."""
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    caller = CallerContext(
        user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
    )
    plan = TableQueryPlan.model_validate(
        {
            "table_id": uuid4(),
            "version_id": uuid4(),
            "aggregations": [{"op": "count", "alias": "rows"}],
        }
    )
    download = MagicMock(return_value=b"immutable-parquet")
    monkeypatch.setattr(tables_http, "download_object", download)
    monkeypatch.setattr(tables_http, "load_privileged_storage_settings", MagicMock())
    cursor.fetchone.return_value = None
    with pytest.raises(TableResolveError):
        tables_http.materialize_table_artifact(
            cast(psycopg.Connection, connection),
            caller=caller,
            plan=plan,
            root=tmp_path,
        )
    download.assert_not_called()
    cursor.fetchone.return_value = {
        "parquet_bucket": "table-artifacts",
        "parquet_path": "server-key",
        "provenance": {"content_hash_sha256": "0" * 64},
    }
    with pytest.raises(StructuredTableError):
        tables_http.materialize_table_artifact(
            cast(psycopg.Connection, connection),
            caller=caller,
            plan=plan,
            root=tmp_path,
        )
    assert not list(tmp_path.iterdir())
    digest = hashlib.sha256(b"immutable-parquet").hexdigest()
    cursor.fetchone.return_value = {
        "parquet_bucket": "table-artifacts",
        "parquet_path": "server-key",
        "provenance": {"content_hash_sha256": digest},
    }
    tables_http.materialize_table_artifact(
        cast(psycopg.Connection, connection), caller=caller, plan=plan, root=tmp_path
    )
    assert (tmp_path / f"{digest}.parquet").read_bytes() == b"immutable-parquet"
    assert download.call_args.kwargs["max_bytes"] == 32 * 1024 * 1024
