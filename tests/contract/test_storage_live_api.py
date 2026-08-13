"""Live local Supabase Storage byte-lifecycle contract."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from psycopg import sql
from smart_rag_api.storage_admin.objects import delete_object
from smart_rag_api.storage_admin.settings import PrivilegedStorageSettings

from tests.contract.integration_support import (
    local_supabase_status,
    resolve_supabase_db_url,
    try_connect,
)


def test_storage_admin_delete_removes_actual_provider_bytes() -> None:
    """Upload/read/delete one local object and prove bytes plus metadata vanish."""

    status = local_supabase_status()
    api_url = status["API_URL"].rstrip("/")
    admin_secret = status["SERVICE_ROLE_KEY"]
    object_path = f"live-cleanup/{uuid.uuid4()}.txt"
    object_url = f"{api_url}/storage/v1/object/documents-quarantine/{object_path}"
    headers = {
        "Authorization": f"Bearer {admin_secret}",
        "apikey": admin_secret,
        "Content-Type": "text/plain",
        "x-upsert": "false",
    }
    payload = b"phase-2-live-storage-byte-proof"
    upload = httpx.post(
        object_url,
        headers=headers,
        content=payload,
        timeout=10.0,
    )
    upload.raise_for_status()

    read_back = httpx.get(
        object_url,
        headers={
            "Authorization": f"Bearer {admin_secret}",
            "apikey": admin_secret,
        },
        timeout=10.0,
    )
    read_back.raise_for_status()
    assert read_back.content == payload

    settings = PrivilegedStorageSettings.model_validate(
        {
            "SUPABASE_URL": api_url,
            "SUPABASE_STORAGE_ADMIN_SECRET": admin_secret,
        }
    )
    delete_object(
        settings,
        bucket="documents-quarantine",
        object_path=object_path,
    )
    delete_object(
        settings,
        bucket="documents-quarantine",
        object_path=object_path,
    )

    absent = httpx.get(
        object_url,
        headers={
            "Authorization": f"Bearer {admin_secret}",
            "apikey": admin_secret,
        },
        timeout=10.0,
    )
    assert absent.status_code in {400, 404}

    postgres_url = resolve_supabase_db_url()
    connection = try_connect(postgres_url)
    if connection is None:
        pytest.fail(f"Local Supabase Postgres unreachable at {postgres_url}")
    with connection:
        metadata_row = connection.execute(
            """
            SELECT count(*)::integer
            FROM storage.objects
            WHERE bucket_id = 'documents-quarantine'
              AND name = %s
            """,
            (object_path,),
        ).fetchone()
    connection.close()
    assert metadata_row == (0,)


def test_runtime_roles_cannot_mutate_storage_metadata_directly() -> None:
    """API/worker roles cannot substitute SQL metadata DML for Storage API calls."""

    postgres_url = resolve_supabase_db_url()
    connection = try_connect(postgres_url)
    if connection is None:
        pytest.fail(f"Local Supabase Postgres unreachable at {postgres_url}")
    connection.autocommit = False
    with connection.cursor() as cursor:
        for role in ("app_api", "app_worker"):
            cursor.execute("SAVEPOINT role_check")
            cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    """
                    DELETE FROM storage.objects
                    WHERE bucket_id = 'documents-quarantine'
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT role_check")
            cursor.execute("RELEASE SAVEPOINT role_check")
    connection.rollback()
    connection.close()
