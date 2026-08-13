"""Owner bootstrap helper using the race-safe SQL RPC."""

from __future__ import annotations

import uuid

import psycopg


class OwnerBootstrapError(Exception):
    """Raised when owner bootstrap preconditions are not met."""


def bootstrap_owner(postgres_url: str, user_id: uuid.UUID) -> bool:
    """Attempt one-time owner bootstrap for a newly signed-up user.

    Args:
        postgres_url: Postgres URL able to execute ``app.bootstrap_owner``.
        user_id: Authenticated subject requesting bootstrap.

    Returns:
        ``True`` when this call became the first owner; ``False`` when an owner
        already exists.

    Raises:
        OwnerBootstrapError: On database errors.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor() as cursor:
                cursor.execute("SELECT app.bootstrap_owner(%s)", (user_id,))
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        raise OwnerBootstrapError("bootstrap_owner rpc failed") from exc

    if row is None:
        return False
    return bool(row[0])
