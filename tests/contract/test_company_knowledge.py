"""Real Postgres authority, privacy, consent, and optimistic-review contracts."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.contract.test_rls_matrix import rls_auth_version, rls_insert_profile


@pytest.fixture
def db() -> Iterator[psycopg.Connection]:
    """Use only an explicitly configured local fixture; roll back all test data."""
    connection = try_connect(require_supabase_db_url())
    if connection is None:
        pytest.skip("Local contract database unavailable")
    connection.autocommit = False
    connection.execute(
        "INSERT INTO app.company_settings(id) VALUES ('00000000-0000-0000-0000-000000000001') ON CONFLICT DO NOTHING"
    )
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_governance_acl_revision_and_cache_generation(db: psycopg.Connection) -> None:
    """Metadata changes are privileged, audited, and invalidate selection caches."""
    owner, member, document, version = (uuid4() for _ in range(4))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner, role="owner")
        rls_insert_profile(cursor, user_id=member, role="member")
        authz = rls_auth_version(cursor)
    db.execute(
        "INSERT INTO app.documents(id,title) VALUES (%s,'Governance fixture')",
        (document,),
    )
    db.execute(
        "INSERT INTO app.document_versions(id,document_id,version_number) VALUES (%s,%s,1)",
        (version, document),
    )
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s",
        (version, document),
    )
    before = db.execute(
        "SELECT visibility_generation FROM app.company_settings"
    ).fetchone()
    db.execute("SET LOCAL ROLE app_api")
    params = (owner, "owner", authz, document)
    row = db.execute(
        "SELECT app.get_document_governance(%s,%s,%s,%s)", params
    ).fetchone()
    assert row is not None and row[0]["authority_status"] == "unreviewed"
    body = {
        "version_id": str(version),
        "expected_generation": 1,
        "owner_user_id": str(owner),
        "knowledge_area": "Operations",
        "review_due_at": "2026-10-01",
        "authority_status": "approved",
        "effective_at": "2026-10-01T00:00:00Z",
    }
    with db.transaction():
        with pytest.raises(psycopg.errors.RaiseException, match="forbidden"):
            with db.transaction():
                db.execute(
                    "SELECT app.update_document_governance(%s,%s,%s,%s,%s)",
                    (member, "member", authz, document, Jsonb(body)),
                )
    result = db.execute(
        "SELECT app.update_document_governance(%s,%s,%s,%s,%s)", (*params, Jsonb(body))
    ).fetchone()
    assert result is not None and result[0]["governance_generation"] == 2
    assert result[0]["owner_user_id"] == str(owner)
    with pytest.raises(psycopg.errors.RaiseException, match="governance_conflict"):
        with db.transaction():
            db.execute(
                "SELECT app.update_document_governance(%s,%s,%s,%s,%s)",
                (*params, Jsonb(body)),
            )
    missing = db.execute(
        "SELECT app.get_document_governance(%s,%s,%s,%s)", (*params[:3], uuid4())
    ).fetchone()
    assert missing is not None and missing[0] is None
    db.execute("RESET ROLE")
    after = db.execute(
        "SELECT visibility_generation FROM app.company_settings"
    ).fetchone()
    assert before is not None and after is not None and after[0] > before[0]
    audit = db.execute(
        "SELECT count(*) FROM app.audit_events WHERE event_type='document.governance_updated'"
    ).fetchone()
    assert audit is not None and audit[0] == 1


def test_feedback_consent_and_private_run_outcomes(db: psycopg.Connection) -> None:
    """Admin role alone never exposes another employee's question or outcome."""
    owner, employee, conversation, run = (uuid4() for _ in range(4))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner, role="owner")
        rls_insert_profile(cursor, user_id=employee, role="member")
        authz = rls_auth_version(cursor)
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, employee),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id) VALUES (%s,%s,%s)",
        (run, conversation, employee),
    )
    db.execute("SET LOCAL ROLE app_api")
    result: dict[str, object] = {"outcome": "insufficient_evidence", "limitations": []}
    args = (employee, "member", authz, run)
    db.execute(
        "SELECT app.record_run_knowledge_result(%s,%s,%s,%s,%s)", (*args, Jsonb(result))
    )
    own = db.execute(
        "SELECT app.get_run_knowledge_result(%s,%s,%s,%s)", args
    ).fetchone()
    foreign = db.execute(
        "SELECT app.get_run_knowledge_result(%s,%s,%s,%s)", (owner, "owner", authz, run)
    ).fetchone()
    assert own is not None and own[0] == result
    assert foreign is not None and foreign[0] is None
    owner_args = (owner, "owner", authz)
    assert not db.execute(
        "SELECT * FROM app.list_knowledge_maintenance(%s,%s,%s,50,0)", owner_args
    ).fetchall()
    feedback_row = db.execute(
        "SELECT app.submit_run_feedback(%s,%s,%s,%s,1::smallint,NULL,'outdated answer')",
        args,
    ).fetchone()
    assert feedback_row is not None
    feedback = UUID(str(feedback_row[0]))
    assert not db.execute(
        "SELECT * FROM app.list_knowledge_maintenance(%s,%s,%s,50,0)", owner_args
    ).fetchall()

    db.execute(
        "SELECT app.share_knowledge_feedback(%s,%s,%s,%s)",
        (employee, "member", authz, feedback),
    )
    items = db.execute(
        "SELECT kind,source_id FROM app.list_knowledge_maintenance(%s,%s,%s,50,0)",
        owner_args,
    ).fetchall()
    assert ("feedback", feedback) in items
    assert ("insufficient_evidence", run) in items
    with pytest.raises(psycopg.errors.RaiseException, match="forbidden"):
        with db.transaction():
            db.execute(
                "SELECT * FROM app.list_knowledge_maintenance(%s,%s,%s,50,0)",
                (employee, "member", authz),
            )
    review = {
        "expected_revision": 0,
        "status": "resolved",
        "reason": "Upload the current policy",
        "assigned_to": str(owner),
    }
    db.execute(
        "SELECT app.update_knowledge_maintenance(%s,%s,%s,%s,%s,%s)",
        (*owner_args, "feedback", feedback, Jsonb(review)),
    )
    with pytest.raises(psycopg.errors.RaiseException, match="governance_conflict"):
        with db.transaction():
            db.execute(
                "SELECT app.update_knowledge_maintenance(%s,%s,%s,%s,%s,%s)",
                (*owner_args, "feedback", feedback, Jsonb(review)),
            )
    db.execute("RESET ROLE")
    db.execute(
        "UPDATE app.conversations SET deleted_at=now() WHERE id=%s", (conversation,)
    )
    db.execute("SET LOCAL ROLE app_api")
    assert not db.execute(
        "SELECT * FROM app.list_knowledge_maintenance(%s,%s,%s,50,0)", owner_args
    ).fetchall()


def test_run_scope_is_immutable_and_never_broadens_on_version_change(
    db: psycopg.Connection,
) -> None:
    """Clearing the conversation does not change an admitted run's source."""
    user, conversation, document, version, run, replacement = (
        uuid4() for _ in range(6)
    )
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=user, role="member")
        authz = rls_auth_version(cursor)
    db.execute("UPDATE app.company_settings SET knowledge_reliability_enabled=true")
    db.execute(
        "INSERT INTO app.documents(id,title) VALUES (%s,'Scope fixture')", (document,)
    )
    db.execute(
        "INSERT INTO app.document_versions(id,document_id,version_number) VALUES (%s,%s,1),(%s,%s,2)",
        (version, document, replacement, document),
    )
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s",
        (version, document),
    )
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, user),
    )
    args = (user, "member", authz)
    db.execute("SET LOCAL ROLE app_api")
    db.execute(
        "SELECT app.conversation_knowledge_scope(%s,%s,%s,%s,true,%s)",
        (*args, conversation, document),
    )
    db.execute("RESET ROLE")
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id) VALUES (%s,%s,%s)",
        (run, conversation, user),
    )
    db.execute("SET LOCAL ROLE app_api")
    db.execute(
        "SELECT app.conversation_knowledge_scope(%s,%s,%s,%s,true,NULL)",
        (*args, conversation),
    )
    selected = db.execute(
        "SELECT app.get_run_knowledge_scope(%s,%s,%s,%s)", (*args, run)
    ).fetchone()
    assert selected is not None and selected[0]["version_id"] == str(version)
    db.execute("RESET ROLE")
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s",
        (replacement, document),
    )
    db.execute("SET LOCAL ROLE app_api")
    with pytest.raises(psycopg.errors.RaiseException, match="not_found"):
        with db.transaction():
            db.execute("SELECT app.get_run_knowledge_scope(%s,%s,%s,%s)", (*args, run))


def test_pending_clarification_resume_is_private_and_idempotent(
    db: psycopg.Connection,
) -> None:
    """A response resumes the original question once, without another clarification loop."""
    user, other, conversation, first_run, next_run = (uuid4() for _ in range(5))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=user, role="member")
        rls_insert_profile(cursor, user_id=other, role="owner")
        authz = rls_auth_version(cursor)
    db.execute("UPDATE app.company_settings SET knowledge_reliability_enabled=true")
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, user),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id) VALUES (%s,%s,%s),(%s,%s,%s)",
        (first_run, conversation, user, next_run, conversation, user),
    )
    db.execute("SET LOCAL ROLE app_api")
    args = (user, "member", authz)
    db.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,%s)",
        (*args, first_run, "Which leave policy applies?", "Which country do you mean?"),
    )
    with pytest.raises(psycopg.errors.RaiseException, match="not_found"):
        with db.transaction():
            db.execute(
                "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,NULL)",
                (other, "owner", authz, next_run, "Egypt"),
            )
    row = db.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,NULL)",
        (*args, next_run, "Egypt"),
    ).fetchone()
    assert row is not None and row[0]["resumed"]
    assert row[0]["query"] == "Which leave policy applies?\nUser clarification: Egypt"
    replay = db.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,NULL)",
        (*args, next_run, "Egypt"),
    ).fetchone()
    assert replay == row
    with pytest.raises(psycopg.errors.RaiseException, match="invalid_clarification"):
        with db.transaction():
            db.execute(
                "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,%s)",
                (*args, next_run, "Egypt", "Which country?"),
            )


def test_deleted_evidence_blocks_history_and_replay_without_erasing_messages(
    db: psycopg.Connection,
) -> None:
    """A saved answer cannot bypass deletion through transcript or SSE replay."""
    from smart_rag_api.services.conversation_transcript import (
        list_conversation_messages,
    )
    from smart_rag_core.security.identity import CallerContext, UserRole

    user, conversation, run, doc, version, chunk = (uuid4() for _ in range(6))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=user, role="member")
        authz = rls_auth_version(cursor)
    db.execute(
        "INSERT INTO app.documents(id,title) VALUES (%s,'History fixture')", (doc,)
    )
    db.execute(
        "INSERT INTO app.document_versions(id,document_id,version_number) VALUES (%s,%s,1)",
        (version, doc),
    )
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s", (version, doc)
    )
    db.execute(
        "INSERT INTO app.document_chunks(id,document_id,version_id,chunk_index,raw_text) VALUES (%s,%s,%s,0,'Original evidence')",
        (chunk, doc, version),
    )
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, user),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id) VALUES (%s,%s,%s)",
        (run, conversation, user),
    )
    db.execute(
        "INSERT INTO app.messages(conversation_id,run_id,role,content) VALUES (%s,%s,'assistant','Original checked answer')",
        (conversation, run),
    )
    db.execute(
        "INSERT INTO app.citations(run_id,chunk_id,citation_index) VALUES (%s,%s,0)",
        (run, chunk),
    )
    args = (user, "member", authz, run)
    db.execute("SET LOCAL ROLE app_api")
    before = db.execute(
        "SELECT app.run_knowledge_history_unavailable(%s,%s,%s,%s)", args
    ).fetchone()
    assert before is not None and before[0] is False
    db.execute("RESET ROLE")
    db.execute("UPDATE app.documents SET deleted_at=now() WHERE id=%s", (doc,))
    with db.cursor() as cursor:
        authz = rls_auth_version(cursor)
    args = (user, "member", authz, run)
    db.execute("SET LOCAL ROLE app_api")
    after = db.execute(
        "SELECT app.run_knowledge_history_unavailable(%s,%s,%s,%s)", args
    ).fetchone()
    assert after is not None and after[0] is True
    with pytest.raises(psycopg.errors.RaiseException, match="not_found"):
        with db.transaction():
            db.execute("SELECT * FROM app.list_run_events_after(%s,%s,%s,%s,0)", args)
    caller = CallerContext(
        user_id=str(user), role=UserRole.MEMBER, authorization_version=authz
    )
    messages = list_conversation_messages(
        db, caller=caller, conversation_id=conversation
    )
    assert len(messages) == 1 and "Original checked answer" not in messages[0].content
    assert "Source unavailable" in messages[0].content
    db.execute("RESET ROLE")
    stored = db.execute(
        "SELECT content FROM app.messages WHERE run_id=%s", (run,)
    ).fetchone()
    assert stored is not None and stored[0] == "Original checked answer"


def test_knowledge_ownership_never_grants_source_access(db: psycopg.Connection) -> None:
    """A responsibility label cannot grant restricted-document access."""
    owner, member, document = (uuid4() for _ in range(3))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner, role="owner")
        rls_insert_profile(cursor, user_id=member, role="member")
    db.execute(
        "INSERT INTO app.documents(id,title,visibility,created_by,knowledge_owner_user_id,knowledge_area) VALUES (%s,'Private fixture','restricted',%s,%s,'HR')",
        (document, owner, member),
    )
    with db.cursor() as cursor:
        authz = rls_auth_version(cursor)
    db.execute("SET LOCAL ROLE app_api")
    result = db.execute(
        "SELECT app.get_document_governance(%s,%s,%s,%s)",
        (member, "member", authz, document),
    ).fetchone()
    assert result is not None and result[0] is None
    with pytest.raises(psycopg.errors.RaiseException, match="authorization_rejected"):
        with db.transaction():
            db.execute(
                "SELECT app.get_document_governance(%s,%s,%s,%s)",
                (member, "owner", authz, document),
            )
    privilege = db.execute(
        "SELECT has_function_privilege('authenticated','app.get_document_governance(uuid,text,bigint,uuid)','EXECUTE')"
    ).fetchone()
    assert privilege is not None and privilege[0] is False


def test_explicit_version_replacement_preserves_current_pointer(
    db: psycopg.Connection,
) -> None:
    """Approval and supersession use explicit versions without publishing uploads."""
    owner, doc, old, replacement = (uuid4() for _ in range(4))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner, role="owner")
        authz = rls_auth_version(cursor)
    db.execute(
        "INSERT INTO app.documents(id,title) VALUES (%s,'Version fixture')", (doc,)
    )
    db.execute(
        "INSERT INTO app.document_versions(id,document_id,version_number) VALUES (%s,%s,1),(%s,%s,2)",
        (old, doc, replacement, doc),
    )
    db.execute(
        "UPDATE app.documents SET current_version_id=%s WHERE id=%s", (replacement, doc)
    )
    db.execute("SET LOCAL ROLE app_api")
    args = (owner, "owner", authz, doc)
    approved: dict[str, object] = {
        "version_id": str(replacement),
        "expected_generation": 1,
        "owner_user_id": str(owner),
        "authority_status": "approved",
        "effective_at": "2026-10-01T00:00:00Z",
    }
    db.execute(
        "SELECT app.update_document_governance(%s,%s,%s,%s,%s)",
        (*args, Jsonb(approved)),
    )
    superseded = {
        **approved,
        "version_id": str(old),
        "expected_generation": 2,
        "authority_status": "superseded",
        "superseded_by_version_id": str(replacement),
    }
    result = db.execute(
        "SELECT app.update_document_governance(%s,%s,%s,%s,%s)",
        (*args, Jsonb(superseded)),
    ).fetchone()
    assert (
        result is not None
        and result[0]["version_id"] == str(old)
        and result[0]["authority_status"] == "superseded"
    )
    current = db.execute(
        "SELECT app.get_document_governance(%s,%s,%s,%s)", args
    ).fetchone()
    assert (
        current is not None
        and current[0]["version_id"] == str(replacement)
        and current[0]["authority_status"] == "approved"
    )


def test_conversation_delete_cascades_private_scope_and_review_notes(
    db: psycopg.Connection,
) -> None:
    """The normal delete operation removes newly introduced private state too."""
    from smart_rag_core.conversations import delete_conversation
    from smart_rag_core.security.identity import CallerContext, UserRole

    user, owner, conversation, run = (uuid4() for _ in range(4))
    with db.cursor() as cursor:
        rls_insert_profile(cursor, user_id=user, role="member")
        rls_insert_profile(cursor, user_id=owner, role="owner")
        authz = rls_auth_version(cursor)
    db.execute("UPDATE app.company_settings SET knowledge_reliability_enabled=true")
    db.execute(
        "INSERT INTO app.conversations(id,creator_user_id) VALUES (%s,%s)",
        (conversation, user),
    )
    db.execute(
        "INSERT INTO app.runs(id,conversation_id,creator_user_id) VALUES (%s,%s,%s)",
        (run, conversation, user),
    )
    db.execute("SET LOCAL ROLE app_api")
    args = (user, "member", authz)
    db.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,%s)",
        (*args, run, "Which policy?", "Which department?"),
    )
    row = db.execute(
        "SELECT app.submit_run_feedback(%s,%s,%s,%s,1::smallint,NULL,'incomplete answer')",
        (*args, run),
    ).fetchone()
    assert row is not None
    feedback = UUID(str(row[0]))
    db.execute("SELECT app.share_knowledge_feedback(%s,%s,%s,%s)", (*args, feedback))
    review = {
        "expected_revision": 0,
        "status": "resolved",
        "reason": "Private review note",
    }
    db.execute(
        "SELECT app.update_knowledge_maintenance(%s,%s,%s,'feedback',%s,%s)",
        (owner, "owner", authz, feedback, Jsonb(review)),
    )
    delete_conversation(
        db,
        caller=CallerContext(
            user_id=str(user), role=UserRole.MEMBER, authorization_version=authz
        ),
        conversation_id=conversation,
    )
    db.execute("RESET ROLE")
    context = db.execute(
        "SELECT count(*) FROM app.conversation_knowledge_context WHERE conversation_id=%s",
        (conversation,),
    ).fetchone()
    notes = db.execute(
        "SELECT count(*) FROM app.knowledge_maintenance_reviews WHERE source_feedback_id=%s",
        (feedback,),
    ).fetchone()
    assert context is not None and context[0] == 0
    assert notes is not None and notes[0] == 0
