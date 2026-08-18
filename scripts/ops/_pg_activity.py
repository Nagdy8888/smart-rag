"""Show waiting Postgres sessions without query text that may include secrets."""

from __future__ import annotations

import psycopg

DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    """Print pid, user, state, wait event, and query prefix."""

    sql = """
    SELECT pid, usename, state, wait_event_type, wait_event,
           left(regexp_replace(query, 'eyJ[A-Za-z0-9_.=-]+', '[redacted]', 'g'), 120)
    FROM pg_stat_activity
    WHERE datname = current_database()
      AND pid <> pg_backend_pid()
      AND state IS NOT NULL
    ORDER BY pid
    """
    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        for row in connection.execute(sql).fetchall():
            print(row)


if __name__ == "__main__":
    main()
