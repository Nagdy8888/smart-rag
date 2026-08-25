"""Count durable events for one P08-22 run. No secret prints."""

from __future__ import annotations

import sys
from uuid import UUID

import psycopg

ADMIN_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> int:
    """Print local durable proof for one conversation/run pair."""

    conversation_id = UUID(sys.argv[1])
    run_id = UUID(sys.argv[2])
    with psycopg.connect(ADMIN_DSN) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM app.conversations WHERE id = %s),
              (SELECT count(*) FROM app.messages WHERE conversation_id = %s),
              (SELECT count(*) FROM app.runs WHERE id = %s),
              (SELECT status::text FROM app.runs WHERE id = %s),
              (SELECT count(*) FROM app.run_events WHERE run_id = %s),
              (SELECT count(*) FROM app.run_events WHERE run_id = %s AND event_type = 'token_delta'),
              (SELECT count(*) FROM app.run_events WHERE run_id = %s AND event_type IN (
                'completed', 'cancelled', 'error', 'deadline', 'partial'
              )),
              (SELECT string_agg(event_type, ',' ORDER BY sequence)
                 FROM app.run_events WHERE run_id = %s),
              (SELECT count(*) FROM app.llm_usage WHERE run_id = %s),
              (SELECT coalesce(sum(cost_usd), 0) FROM app.llm_usage WHERE run_id = %s),
              (SELECT coalesce(sum(total_tokens), 0) FROM app.llm_usage WHERE run_id = %s)
            """,
            (
                conversation_id,
                conversation_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
            ),
        ).fetchone()
        events = connection.execute(
            """
            SELECT sequence, event_type, left(coalesce(payload::text, ''), 200)
            FROM app.run_events
            WHERE run_id = %s
            ORDER BY sequence
            """,
            (run_id,),
        ).fetchall()
    print(
        "conversations={0} messages={1} runs={2} run_status={3} "
        "events={4} token_delta={5} terminals={6} event_types={7} "
        "usage_rows={8} cost_usd={9} tokens={10}".format(*row)
    )
    for sequence, event_type, payload in events:
        text = payload or ""
        lowered = text.lower()
        if any(
            needle in lowered
            for needle in ("sk-", "bearer ", "password", "api_key", "secret")
        ):
            text = "REDACTED"
        print(f"event seq={sequence} type={event_type} payload={text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
