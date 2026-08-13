"""Canonical schema fingerprint helpers for destructive reset verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import LiteralString, TypeAlias

import psycopg
from psycopg import sql

FingerprintScalar: TypeAlias = str | int | bool | None
FingerprintRow: TypeAlias = list[FingerprintScalar]
SchemaFingerprint: TypeAlias = dict[str, list[FingerprintRow]]
FingerprintQuery: TypeAlias = tuple[LiteralString, tuple[object, ...]]

APPLICATION_SCHEMAS = (
    "app",
    "auth",
    "langgraph",
    "lightrag",
    "private",
    "public",
    "search",
    "storage",
)
APPLICATION_ROLES = (
    "app_api",
    "app_audit_writer",
    "app_checkpointer",
    "app_lightrag",
    "app_worker",
)
PRIVATE_SCHEMAS = ("app", "langgraph", "lightrag", "private")
BROWSER_ROLES = ("anon", "authenticated")

FINGERPRINT_QUERIES: Mapping[str, FingerprintQuery] = {
    "roles": (
        """
        SELECT
            rolname,
            rolsuper,
            rolinherit,
            rolcreaterole,
            rolcreatedb,
            rolcanlogin,
            rolreplication,
            rolbypassrls,
            COALESCE(to_jsonb(rolconfig)::text, 'null')
        FROM pg_roles
        WHERE rolname LIKE 'app\\_%' ESCAPE '\\'
        ORDER BY rolname
        """,
        (),
    ),
    "extensions": (
        """
        SELECT
            extension.extname,
            extension.extversion,
            namespace.nspname
        FROM pg_extension AS extension
        JOIN pg_namespace AS namespace
          ON namespace.oid = extension.extnamespace
        ORDER BY extension.extname
        """,
        (),
    ),
    "tables": (
        """
        SELECT
            namespace.nspname,
            relation.relname,
            relation.relkind::text,
            pg_get_userbyid(relation.relowner),
            relation.relrowsecurity,
            relation.relforcerowsecurity
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(%s)
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
        ORDER BY namespace.nspname, relation.relname, relation.relkind
        """,
        (list(APPLICATION_SCHEMAS),),
    ),
    "columns": (
        """
        SELECT
            columns.table_schema,
            columns.table_name,
            columns.ordinal_position,
            columns.column_name,
            columns.data_type,
            columns.udt_schema,
            columns.udt_name,
            columns.is_nullable,
            COALESCE(columns.column_default, ''),
            columns.is_identity,
            columns.identity_generation,
            columns.is_generated,
            COALESCE(columns.generation_expression, '')
        FROM information_schema.columns AS columns
        WHERE columns.table_schema = ANY(%s)
        ORDER BY
            columns.table_schema,
            columns.table_name,
            columns.ordinal_position
        """,
        (list(APPLICATION_SCHEMAS),),
    ),
    "constraints": (
        """
        SELECT
            namespace.nspname,
            relation.relname,
            constraint_record.conname,
            constraint_record.contype::text,
            pg_get_constraintdef(constraint_record.oid, true)
        FROM pg_constraint AS constraint_record
        JOIN pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(%s)
        ORDER BY
            namespace.nspname,
            relation.relname,
            constraint_record.conname
        """,
        (list(APPLICATION_SCHEMAS),),
    ),
    "enums": (
        """
        SELECT
            namespace.nspname,
            type_record.typname,
            enum_record.enumsortorder::text,
            enum_record.enumlabel
        FROM pg_type AS type_record
        JOIN pg_namespace AS namespace
          ON namespace.oid = type_record.typnamespace
        JOIN pg_enum AS enum_record
          ON enum_record.enumtypid = type_record.oid
        WHERE namespace.nspname = ANY(%s)
        ORDER BY
            namespace.nspname,
            type_record.typname,
            enum_record.enumsortorder
        """,
        (list(APPLICATION_SCHEMAS),),
    ),
    "private_schema_exposure": (
        """
        SELECT
            browser_role.rolname,
            private_schema.schema_name,
            has_schema_privilege(
                browser_role.rolname,
                private_schema.schema_name,
                'USAGE'
            ),
            has_schema_privilege(
                browser_role.rolname,
                private_schema.schema_name,
                'CREATE'
            )
        FROM pg_roles AS browser_role
        CROSS JOIN (
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = ANY(%s)
        ) AS private_schema
        WHERE browser_role.rolname = ANY(%s)
        ORDER BY browser_role.rolname, private_schema.schema_name
        """,
        (list(PRIVATE_SCHEMAS), list(BROWSER_ROLES)),
    ),
}


class SchemaInventoryError(RuntimeError):
    """Raised when required Phase 2 schema inventory is missing or exposed."""


def _normalize_scalar(value: object) -> FingerprintScalar:
    """Convert one database value to a stable JSON scalar.

    Args:
        value: Scalar returned by psycopg.

    Returns:
        A JSON-compatible scalar with non-primitive values represented by their
        deterministic PostgreSQL text form.
    """

    if value is None or isinstance(value, str | int | bool):
        return value
    return str(value)


def _fetch_rows(
    connection: psycopg.Connection[tuple[object, ...]],
    query_spec: FingerprintQuery,
) -> list[FingerprintRow]:
    """Execute one inventory query and normalize its ordered rows.

    Args:
        connection: Open PostgreSQL connection.
        query_spec: Static schema-inventory SQL with an explicit ``ORDER BY``
            plus bound catalog filter parameters.

    Returns:
        Ordered, JSON-compatible fingerprint rows.
    """

    query, parameters = query_spec
    with connection.cursor() as cursor:
        if parameters:
            cursor.execute(sql.SQL(query), parameters)
        else:
            cursor.execute(sql.SQL(query))
        return [
            [_normalize_scalar(value) for value in row] for row in cursor.fetchall()
        ]


def capture_schema_fingerprint(
    connection: psycopg.Connection[tuple[object, ...]],
) -> SchemaFingerprint:
    """Capture the authoritative schema state required by the reset gate.

    Args:
        connection: Open PostgreSQL connection to the reset local database.

    Returns:
        Ordered role, extension, relation, column, constraint, enum, and private
        schema exposure inventories.

    Side Effects:
        Executes read-only catalog queries in the current transaction.
    """

    return {
        name: _fetch_rows(connection, query)
        for name, query in FINGERPRINT_QUERIES.items()
    }


def serialize_schema_fingerprint(fingerprint: SchemaFingerprint) -> str:
    """Serialize a schema fingerprint with stable ordering and separators.

    Args:
        fingerprint: Catalog inventory returned by
            :func:`capture_schema_fingerprint`.

    Returns:
        Canonical UTF-8 JSON text suitable for equality and digest checks.
    """

    return json.dumps(
        fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def schema_fingerprint_sha256(fingerprint: SchemaFingerprint) -> str:
    """Return the SHA-256 digest of a canonical schema fingerprint.

    Args:
        fingerprint: Catalog inventory returned by
            :func:`capture_schema_fingerprint`.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """

    serialized = serialize_schema_fingerprint(fingerprint).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def normalize_generated_types(source: str) -> str:
    """Normalize generated TypeScript only for cross-platform comparison.

    Args:
        source: Raw Supabase CLI generated output.

    Returns:
        Text with LF line endings and exactly one final newline.
    """

    return source.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def assert_required_inventory(fingerprint: SchemaFingerprint) -> None:
    """Fail when a reset fingerprint omits required Phase 2 schema state.

    Args:
        fingerprint: Catalog inventory returned by
            :func:`capture_schema_fingerprint`.

    Raises:
        SchemaInventoryError: If a required inventory is empty, an application
            role is missing, pgvector is absent, or a browser role can
            use/create in a private schema.
    """

    for inventory in ("extensions", "tables", "columns", "constraints"):
        if not fingerprint[inventory]:
            raise SchemaInventoryError(f"{inventory} inventory is empty")

    role_names = {str(row[0]) for row in fingerprint["roles"]}
    if role_names != set(APPLICATION_ROLES):
        raise SchemaInventoryError(
            "Application role inventory differs from the required role set"
        )

    extension_names = {str(row[0]) for row in fingerprint["extensions"]}
    if "vector" not in extension_names:
        raise SchemaInventoryError("pgvector extension is absent")

    exposure_rows = fingerprint["private_schema_exposure"]
    expected_exposure_count = len(BROWSER_ROLES) * len(PRIVATE_SCHEMAS)
    if len(exposure_rows) != expected_exposure_count:
        raise SchemaInventoryError("Private-schema exposure inventory is incomplete")
    if not all(row[2:] == [False, False] for row in exposure_rows):
        raise SchemaInventoryError(
            "A browser role has USAGE or CREATE on a private schema"
        )


def fingerprints_match(first: SchemaFingerprint, second: SchemaFingerprint) -> bool:
    """Return whether two reset fingerprints are byte-equivalent canonically.

    Args:
        first: Inventory captured after the first clean reset.
        second: Inventory captured after the second clean reset.

    Returns:
        ``True`` only when canonical serialized inventories match.
    """

    return serialize_schema_fingerprint(first) == serialize_schema_fingerprint(second)


def generated_types_match(first: str, second: str) -> bool:
    """Return whether generated TypeScript outputs match cross-platform.

    Args:
        first: First generated TypeScript output.
        second: Second generated TypeScript output.

    Returns:
        ``True`` when line-ending-normalized generated outputs are identical.
    """

    return normalize_generated_types(first) == normalize_generated_types(second)


def inventory_counts(fingerprint: SchemaFingerprint) -> Sequence[tuple[str, int]]:
    """Return stable inventory counts for evidence output.

    Args:
        fingerprint: Catalog inventory returned by
            :func:`capture_schema_fingerprint`.

    Returns:
        Alphabetically ordered ``(inventory, row_count)`` pairs.
    """

    return tuple((name, len(rows)) for name, rows in sorted(fingerprint.items()))
