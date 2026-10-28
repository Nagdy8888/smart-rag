"""Creator-only Web presentation metadata and transcript compatibility."""

from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from smart_rag_api.services.conversation_transcript import list_conversation_messages

from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    ensure_local_postgres,
    insert_conversation,
    insert_user_profile,
)


def test_recorded_scope_origin_and_foreign_denial() -> None:
    """Read real metadata without inventing origin or widening ownership."""
    with psycopg.connect(ensure_local_postgres()) as connection:
        with connection.transaction(force_rollback=True):
            user, foreign = uuid4(), uuid4()
            with connection.cursor() as cursor:
                insert_user_profile(cursor, user_id=user, role="owner")
                insert_user_profile(cursor, user_id=foreign, role="member")
                conversation = insert_conversation(cursor, user_id=user)
                version = authorization_version(cursor)
            caller = caller_context(user, "owner", version)
            result, _ = admit(connection, caller=caller, conversation_id=conversation)
            connection.execute("SET LOCAL ROLE app_api")
            args = (user, "owner", version, result.context.run_id)
            row = connection.execute(
                "SELECT * FROM app.get_run_presentation_v1(%s,%s,%s,%s)", args
            ).fetchone()
            assert row is not None and row[1] is None
            connection.execute(
                "SELECT * FROM app.append_run_event(%s,%s,%s,%s,'answer_origin',%s)",
                (*args, Jsonb({"origin": "web"})),
            )
            assert connection.execute(
                "SELECT * FROM app.get_run_presentation_v1(%s,%s,%s,%s)", args
            ).fetchone() == (row[0], "web")
            messages = list_conversation_messages(
                connection, caller=caller, conversation_id=conversation
            )
            assert all(
                message.requested_search_scope == row[0]
                for message in messages
                if message.run_id
            )
            assert (
                connection.execute(
                    "SELECT * FROM app.get_run_presentation_v1(%s,'member',%s,%s)",
                    (foreign, version, result.context.run_id),
                ).fetchall()
                == []
            )
            assert (
                connection.execute(
                    "SELECT * FROM app.get_run_presentation_v1(%s,%s,%s,NULL)", args[:3]
                ).fetchall()
                == []
            )
            connection.execute("RESET ROLE")
            for role in ("anon", "authenticated", "app_worker"):
                assert connection.execute(
                    "SELECT has_function_privilege(%s,'app.get_run_presentation_v1(uuid,text,bigint,uuid)','EXECUTE')",
                    (role,),
                ).fetchone() == (False,)
