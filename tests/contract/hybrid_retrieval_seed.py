"""Shared seed helpers for Phase 4 Packet 2 Hybrid retrieval contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


@dataclass(frozen=True, slots=True)
class HybridRetrievalSeed:
    """IDs and callers for one retrieval fixture.

    Attributes:
        owner: Owner caller context.
        member: Member caller context.
        disabled: Disabled member caller context.
        owner_id: Owner user UUID.
        member_id: Member user UUID.
        disabled_id: Disabled user UUID.
        auth_version: Live authorization version.
        visible_document_id: Company-visible document.
        restricted_document_id: Restricted document granted only to the owner.
        visible_version_id: Current visible version.
        restricted_version_id: Current restricted version.
        stale_version_id: Non-current version that must not retrieve.
        visible_chunk_ids: Current visible chunk IDs in insert order.
        restricted_chunk_id: Restricted chunk ID.
        stale_chunk_id: Chunk on the stale version.
        deleted_chunk_id: Soft-deleted current-version chunk.
        arabic_chunk_id: Arabic-language visible chunk.
        code_chunk_id: Chunk seeded with the unique INV-SR code.
        token: Unique suffix so leftover committed fixtures cannot collide.
        dense_query_text: Unique text whose mock embedding is the ANN query.
        restricted_text: Unique restricted passage text.
        code_term: Unique INV-SR code for the term channel.
        alias_term: Unique alias for the code.
        raw_arabic: Unnormalized Arabic citation text.
    """

    owner: CallerContext
    member: CallerContext
    disabled: CallerContext
    owner_id: UUID
    member_id: UUID
    disabled_id: UUID
    auth_version: int
    visible_document_id: UUID
    restricted_document_id: UUID
    visible_version_id: UUID
    restricted_version_id: UUID
    stale_version_id: UUID
    visible_chunk_ids: tuple[UUID, ...]
    restricted_chunk_id: UUID
    stale_chunk_id: UUID
    deleted_chunk_id: UUID
    arabic_chunk_id: UUID
    code_chunk_id: UUID
    token: str
    dense_query_text: str
    restricted_text: str
    code_term: str
    alias_term: str
    raw_arabic: str


def _insert_auth_user(cursor: psycopg.Cursor, user_id: UUID, email: str) -> None:
    """Insert one disposable auth user.

    Args:
        cursor: Open Postgres cursor.
        user_id: Auth user UUID.
        email: Unique email.
    """

    cursor.execute(
        """
        INSERT INTO auth.users (
          id, instance_id, aud, role, email, encrypted_password,
          email_confirmed_at, created_at, updated_at
        )
        VALUES (
          %s,
          '00000000-0000-0000-0000-000000000000'::uuid,
          'authenticated',
          'authenticated',
          %s,
          crypt('test-password', gen_salt('bf')),
          timezone('utc', now()),
          timezone('utc', now()),
          timezone('utc', now())
        )
        ON CONFLICT (id) DO NOTHING
        """,
        (user_id, email),
    )


def _vector_literal(text: str) -> str:
    """Return a pgvector literal from a mock embedding of ``text``.

    Args:
        text: Seed string.

    Returns:
        Square-bracket vector literal.
    """

    values = mock_embedding_vector(text)
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def seed_hybrid_retrieval_fixture(
    connection: psycopg.Connection,
) -> HybridRetrievalSeed:
    """Insert one committed Hybrid retrieval fixture and return its IDs.

    Args:
        connection: Superuser Postgres connection. Must be idle after return.

    Returns:
        Seeded IDs and server-derived callers.
    """

    owner_id = uuid4()
    member_id = uuid4()
    disabled_id = uuid4()
    visible_document_id = uuid4()
    restricted_document_id = uuid4()
    visible_version_id = uuid4()
    restricted_version_id = uuid4()
    stale_version_id = uuid4()
    visible_chunk_ids = tuple(uuid4() for _ in range(8))
    restricted_chunk_id = uuid4()
    stale_chunk_id = uuid4()
    deleted_chunk_id = uuid4()
    arabic_chunk_id = visible_chunk_ids[6]
    code_chunk_id = visible_chunk_ids[7]
    token = uuid4().hex[:8]
    code_digits = f"{int(token[:4], 16) % 10000:04d}"
    code_term = f"INV-SR-{code_digits}"
    alias_term = f"invoice {code_digits} {token}"
    dense_query_text = f"dense-seed-00 annual leave policy {token}"
    restricted_text = f"restricted salary ledger {token}"
    raw_arabic = f"سياسة الإجازات السنوية تمنح الموظف خمسة عشر يوماً {token}"

    with connection.cursor() as cursor:
        _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        _insert_auth_user(cursor, member_id, f"{member_id}@example.com")
        _insert_auth_user(cursor, disabled_id, f"{disabled_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled, disabled_at)
            VALUES
              (%s, 'owner', true, true, NULL),
              (%s, 'member', true, true, NULL),
              (%s, 'member', true, true, timezone('utc', now()))
            """,
            (owner_id, member_id, disabled_id),
        )

        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Visible Policy', 'company_visible', %s),
              (%s, 'Restricted Ledger', 'restricted', %s)
            """,
            (visible_document_id, owner_id, restricted_document_id, owner_id),
        )
        arabic_document_id = uuid4()
        arabic_version_id = uuid4()
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES (%s, 'Arabic Leave Policy', 'company_visible', %s)
            """,
            (arabic_document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, language
            )
            VALUES
              (%s, %s, 1, 'parsing', 'en'),
              (%s, %s, 2, 'hybrid_ready', 'en'),
              (%s, %s, 1, 'hybrid_ready', 'en'),
              (%s, %s, 1, 'hybrid_ready', 'ar')
            """,
            (
                stale_version_id,
                visible_document_id,
                visible_version_id,
                visible_document_id,
                restricted_version_id,
                restricted_document_id,
                arabic_version_id,
                arabic_document_id,
            ),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (visible_version_id, visible_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (restricted_version_id, restricted_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (arabic_version_id, arabic_document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_acl (document_id, grantee_user_id, granted_by)
            VALUES (%s, %s, %s)
            """,
            (restricted_document_id, owner_id, owner_id),
        )

        for index, chunk_id in enumerate(visible_chunk_ids[:6]):
            text = f"dense-seed-{index:02d} annual leave policy {token}"
            cursor.execute(
                """
                INSERT INTO app.document_chunks (
                  id, document_id, version_id, chunk_index, raw_text,
                  embedding, contextual_text, is_search_representative
                )
                VALUES (
                  %s, %s, %s, %s, %s,
                  %s::extensions.vector, %s, true
                )
                """,
                (
                    chunk_id,
                    visible_document_id,
                    visible_version_id,
                    index,
                    text,
                    _vector_literal(text),
                    f"Visible Policy\n{text}",
                ),
            )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              embedding, contextual_text, is_search_representative
            )
            VALUES (
              %s, %s, %s, 0, %s,
              %s::extensions.vector, %s, true
            )
            """,
            (
                arabic_chunk_id,
                arabic_document_id,
                arabic_version_id,
                raw_arabic,
                _vector_literal(raw_arabic),
                f"Arabic Leave Policy\n{raw_arabic}",
            ),
        )
        code_text = f"Invoice {code_term} requires delivery within thirty days {token}"
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              embedding, contextual_text, is_search_representative
            )
            VALUES (
              %s, %s, %s, 7, %s,
              %s::extensions.vector, %s, true
            )
            """,
            (
                code_chunk_id,
                visible_document_id,
                visible_version_id,
                code_text,
                _vector_literal(code_text),
                f"Visible Policy\n{code_text}",
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              embedding, is_search_representative, deleted_at
            )
            VALUES (
              %s, %s, %s, 8, 'deleted passage',
              %s::extensions.vector, true, timezone('utc', now())
            )
            """,
            (
                deleted_chunk_id,
                visible_document_id,
                visible_version_id,
                _vector_literal("deleted passage"),
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              embedding, is_search_representative
            )
            VALUES (
              %s, %s, %s, 0, 'stale version passage',
              %s::extensions.vector, true
            )
            """,
            (
                stale_chunk_id,
                visible_document_id,
                stale_version_id,
                _vector_literal("stale version passage"),
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              embedding, is_search_representative
            )
            VALUES (
              %s, %s, %s, 0, %s,
              %s::extensions.vector, true
            )
            """,
            (
                restricted_chunk_id,
                restricted_document_id,
                restricted_version_id,
                restricted_text,
                _vector_literal(restricted_text),
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_search_terms (chunk_id, term)
            VALUES (%s, %s), (%s, %s)
            """,
            (code_chunk_id, code_term, code_chunk_id, "Visible Policy"),
        )
        cursor.execute(
            """
            INSERT INTO app.search_aliases (alias, canonical_term, language)
            VALUES (%s, %s, 'en')
            ON CONFLICT (alias_normalized) DO UPDATE
            SET canonical_term = EXCLUDED.canonical_term
            """,
            (alias_term, code_term),
        )
        cursor.execute("SELECT app.current_authorization_version()")
        version_row = cursor.fetchone()
        assert version_row is not None
        auth_version = int(version_row[0])

    connection.commit()
    owner = CallerContext(
        user_id=str(owner_id),
        role=UserRole.OWNER,
        authorization_version=auth_version,
        disabled=False,
        upload_enabled=True,
        mfa_enrolled=True,
    )
    member = CallerContext(
        user_id=str(member_id),
        role=UserRole.MEMBER,
        authorization_version=auth_version,
        disabled=False,
        upload_enabled=True,
        mfa_enrolled=True,
    )
    disabled = CallerContext(
        user_id=str(disabled_id),
        role=UserRole.MEMBER,
        authorization_version=auth_version,
        disabled=True,
        upload_enabled=True,
        mfa_enrolled=True,
    )
    return HybridRetrievalSeed(
        owner=owner,
        member=member,
        disabled=disabled,
        owner_id=owner_id,
        member_id=member_id,
        disabled_id=disabled_id,
        auth_version=auth_version,
        visible_document_id=visible_document_id,
        restricted_document_id=restricted_document_id,
        visible_version_id=visible_version_id,
        restricted_version_id=restricted_version_id,
        stale_version_id=stale_version_id,
        visible_chunk_ids=visible_chunk_ids,
        restricted_chunk_id=restricted_chunk_id,
        stale_chunk_id=stale_chunk_id,
        deleted_chunk_id=deleted_chunk_id,
        arabic_chunk_id=arabic_chunk_id,
        code_chunk_id=code_chunk_id,
        token=token,
        dense_query_text=dense_query_text,
        restricted_text=restricted_text,
        code_term=code_term,
        alias_term=alias_term,
        raw_arabic=raw_arabic,
    )


def normalized_arabic_hash(text: str) -> str:
    """Return the hex SHA-256 of the ``arabic_norm_v1`` form.

    Args:
        text: Raw Unicode text.

    Returns:
        Hex digest of the normalized search form.
    """

    import hashlib

    return hashlib.sha256(normalize_arabic_v1(text).encode("utf-8")).hexdigest()
