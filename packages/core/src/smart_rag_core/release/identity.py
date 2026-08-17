"""Source, pin, migration, and configuration identity for the candidate freeze."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.jobs.limits import GRAPH_PIPELINE_VERSION, LIGHTRAG_HANDOFF_VERSION
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_VERSION,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_profile.versions import PROFILE_PROMPT_VERSION
from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    IDENTITY_SCHEMA_VERSION,
    PROCEED_DECISION,
)
from smart_rag_core.release.errors import CandidateIdentityError
from smart_rag_core.release.io import sha256_file
from smart_rag_core.retrieval.frozen_profile import load_frozen_profile
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_SDIST_SHA256,
    LIGHTRAG_WHEEL_SHA256,
)
from smart_rag_core.retrieval.profiles import (
    BM25_INDEX_SCHEMA_VERSION,
    HYBRID_DEFAULT_PROFILE_ID,
    NORMALIZATION_VERSION,
)
from smart_rag_core.retrieval.rerank_versions import RERANK_PROMPT_VERSION
from smart_rag_core.text.arabic_normalize import ARABIC_NORMALIZATION_VERSION

_PARADEDB_DIGEST = re.compile(
    r"paradedb/paradedb:pg17@sha256:([0-9a-f]{64})",
    re.IGNORECASE,
)


class MigrationFileRecord(BaseModel):
    """One repository migration file and its content hash.

    Attributes:
        filename: Basename under ``supabase/migrations``.
        sha256: SHA-256 of the file bytes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str = Field(min_length=1, max_length=256)
    sha256: str = Field(min_length=64, max_length=64)


class CandidateIdentityFreeze(BaseModel):
    """Machine-readable candidate identity freeze. No secrets.

    Attributes:
        schema_version: Frozen identity schema.
        git_commit_sha: HEAD commit.
        git_dirty: True when the worktree has uncommitted changes.
        uv_lock_sha256: Hash of ``uv.lock``.
        pnpm_lock_sha256: Hash of ``pnpm-lock.yaml``.
        frozen_retrieval_profile_id: Hybrid frozen profile id.
        embedding_model: Pinned embedding model.
        embedding_dimensions: Pinned embedding dimensions.
        prompt_versions: Prompt ids used by the shared gateway.
        migrations: Repository migration files and hashes.
        paradedb_image_digest: Digest-pinned ParadeDB image sha256.
        pg_search_version: Runtime extension version, or ``unverified_runtime``.
        bm25_index_schema_version: Projection index schema.
        bm25_normalization_version: Arabic normalization version.
        lightrag_version: Pinned LightRAG distribution version.
        lightrag_wheel_sha256: Wheel hash from the graph contract.
        lightrag_sdist_sha256: Sdist hash from the graph contract.
        lightrag_handoff_version: Durable job handoff pin.
        graph_pipeline_version: Mapping pipeline pin.
        app_env: Configuration profile environment.
        mock_model_mode: Whether the candidate Compose stack uses mocks.
        proceed_decision: Phase 8 pending / Phase 9 proceed note.
        compose_file: Candidate Compose path.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-identity-v1"] = IDENTITY_SCHEMA_VERSION
    git_commit_sha: str = Field(min_length=7, max_length=64)
    git_dirty: bool
    uv_lock_sha256: str = Field(min_length=64, max_length=64)
    pnpm_lock_sha256: str = Field(min_length=64, max_length=64)
    frozen_retrieval_profile_id: str = Field(min_length=1, max_length=64)
    embedding_model: str
    embedding_dimensions: int
    prompt_versions: dict[str, str]
    migrations: tuple[MigrationFileRecord, ...]
    paradedb_image_digest: str = Field(min_length=64, max_length=80)
    pg_search_version: str
    bm25_index_schema_version: str
    bm25_normalization_version: str
    lightrag_version: str
    lightrag_wheel_sha256: str
    lightrag_sdist_sha256: str
    lightrag_handoff_version: str
    graph_pipeline_version: str
    app_env: str
    mock_model_mode: bool
    proceed_decision: str
    compose_file: str


def collect_identity_freeze(
    repo_root: Path,
    *,
    pg_search_version: str = "unverified_runtime",
    app_env: str = "local",
    mock_model_mode: bool = True,
) -> CandidateIdentityFreeze:
    """Collect the Packet 1 identity freeze from the repository.

    Args:
        repo_root: Repository root.
        pg_search_version: Runtime ``pg_search`` version when known.
        app_env: Candidate configuration profile.
        mock_model_mode: Compose ``MOCK_MODEL_MODE`` actually used.

    Returns:
        Frozen identity record without secrets.

    Raises:
        CandidateIdentityError: If a required file or git identity is missing.
    """

    git_sha, dirty = _git_identity(repo_root)
    uv_lock = repo_root / "uv.lock"
    pnpm_lock = repo_root / "pnpm-lock.yaml"
    if not uv_lock.is_file() or not pnpm_lock.is_file():
        raise CandidateIdentityError("uv.lock or pnpm-lock.yaml is missing")
    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    compose = (repo_root / CANDIDATE_COMPOSE_FILE).read_text(encoding="utf-8")
    digest_match = _PARADEDB_DIGEST.search(compose)
    if digest_match is None:
        raise CandidateIdentityError("ParadeDB image digest missing from compose")
    return CandidateIdentityFreeze(
        git_commit_sha=git_sha,
        git_dirty=dirty,
        uv_lock_sha256=sha256_file(uv_lock),
        pnpm_lock_sha256=sha256_file(pnpm_lock),
        frozen_retrieval_profile_id=profile.profile_id,
        embedding_model=EMBEDDING_MODEL,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        prompt_versions={
            "query_profile": PROFILE_PROMPT_VERSION,
            "rerank": RERANK_PROMPT_VERSION,
            "answer": ANSWER_PROMPT_VERSION,
            "verifier": VERIFIER_PROMPT_VERSION,
        },
        migrations=tuple(_migration_records(repo_root)),
        paradedb_image_digest=digest_match.group(1),
        pg_search_version=pg_search_version,
        bm25_index_schema_version=BM25_INDEX_SCHEMA_VERSION,
        bm25_normalization_version=NORMALIZATION_VERSION,
        lightrag_version=LIGHTRAG_PINNED_VERSION,
        lightrag_wheel_sha256=LIGHTRAG_WHEEL_SHA256,
        lightrag_sdist_sha256=LIGHTRAG_SDIST_SHA256,
        lightrag_handoff_version=LIGHTRAG_HANDOFF_VERSION,
        graph_pipeline_version=GRAPH_PIPELINE_VERSION,
        app_env=app_env,
        mock_model_mode=mock_model_mode,
        proceed_decision=PROCEED_DECISION,
        compose_file=CANDIDATE_COMPOSE_FILE,
    )


def assert_identity_fields(freeze: CandidateIdentityFreeze) -> None:
    """Fail closed when a required freeze field is empty.

    Args:
        freeze: Identity freeze.

    Raises:
        CandidateIdentityError: If a required field is blank.
    """

    required = {
        "git_commit_sha": freeze.git_commit_sha,
        "uv_lock_sha256": freeze.uv_lock_sha256,
        "pnpm_lock_sha256": freeze.pnpm_lock_sha256,
        "frozen_retrieval_profile_id": freeze.frozen_retrieval_profile_id,
        "paradedb_image_digest": freeze.paradedb_image_digest,
        "bm25_index_schema_version": freeze.bm25_index_schema_version,
        "bm25_normalization_version": freeze.bm25_normalization_version,
        "lightrag_version": freeze.lightrag_version,
        "app_env": freeze.app_env,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise CandidateIdentityError(f"identity freeze missing fields: {missing}")
    if freeze.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise CandidateIdentityError("embedding dimension drift")
    if freeze.bm25_normalization_version != ARABIC_NORMALIZATION_VERSION:
        raise CandidateIdentityError("arabic normalization version drift")
    if not freeze.migrations:
        raise CandidateIdentityError("migration inventory is empty")
    if freeze.app_env != "local":
        raise CandidateIdentityError("candidate profile must be APP_ENV=local")


def list_migration_records(repo_root: Path) -> list[MigrationFileRecord]:
    """Hash every SQL file under ``supabase/migrations``.

    Args:
        repo_root: Repository root.

    Returns:
        Sorted migration file records.

    Raises:
        CandidateIdentityError: If the migrations directory is missing.
    """

    return _migration_records(repo_root)


def _migration_records(repo_root: Path) -> list[MigrationFileRecord]:
    """Hash every SQL file under ``supabase/migrations``."""

    directory = repo_root / "supabase" / "migrations"
    if not directory.is_dir():
        raise CandidateIdentityError("supabase/migrations is missing")
    records: list[MigrationFileRecord] = []
    for path in sorted(directory.glob("*.sql")):
        records.append(
            MigrationFileRecord(filename=path.name, sha256=sha256_file(path))
        )
    return records


def _git_identity(repo_root: Path) -> tuple[str, bool]:
    """Return HEAD SHA and dirty flag."""

    sha = _git_output(repo_root, ["rev-parse", "HEAD"])
    porcelain = _git_output(repo_root, ["status", "--porcelain"])
    return sha, bool(porcelain)


def _git_output(repo_root: Path, arguments: list[str]) -> str:
    """Run one git command and return stripped stdout."""

    git = shutil.which("git")
    if git is None:
        raise CandidateIdentityError("git executable is unavailable")
    completed = subprocess.run(  # noqa: S603
        [git, *arguments],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise CandidateIdentityError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()
