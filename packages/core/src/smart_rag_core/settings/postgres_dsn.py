"""Session/direct Postgres DSN guards for LangGraph and LightRAG.

Transaction-pooler URLs (Supavisor/PgBouncer transaction mode) are rejected
using documented signals only: TCP port ``6543`` and ``pgbouncer=true``.
Session-mode pooler URLs on port ``5432`` and other direct ports remain
accepted. Error messages never echo the DSN.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

_TRANSACTION_POOLER_PORTS = frozenset({6543})
_PGBOUNCER_TRUE = frozenset({"1", "true", "yes"})


class TransactionPoolerDsnError(ValueError):
    """Raised when a session/direct integration is given a transaction-pooler DSN."""


def is_transaction_pooler_dsn(dsn: str) -> bool:
    """Return whether ``dsn`` is a known transaction-pooler Postgres URL.

    Args:
        dsn: Candidate Postgres URL. Must not be logged by callers.

    Returns:
        True when the URL uses port ``6543`` or ``pgbouncer=true``.
    """

    parsed = urlparse(dsn)
    if parsed.port in _TRANSACTION_POOLER_PORTS:
        return True
    query = parse_qs(parsed.query, keep_blank_values=True)
    for raw in query.get("pgbouncer", ()):
        if raw.casefold() in _PGBOUNCER_TRUE:
            return True
    return False


def require_session_postgres_dsn(dsn: str, *, setting_name: str) -> str:
    """Require a session/direct Postgres DSN for long-lived integrations.

    Args:
        dsn: Candidate Postgres URL. Never included in the raised message.
        setting_name: Environment variable name used in the sanitized error.

    Returns:
        The original ``dsn`` when it is not a known transaction-pooler URL.

    Raises:
        TransactionPoolerDsnError: If the URL is a transaction pooler. The
            exception message names ``setting_name`` only and omits the DSN.
    """

    if is_transaction_pooler_dsn(dsn):
        raise TransactionPoolerDsnError(
            f"{setting_name} must be a session/direct Postgres DSN; "
            "transaction pooler URLs are not supported for this integration"
        )
    return dsn
