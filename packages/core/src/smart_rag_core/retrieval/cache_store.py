"""Authorization-safe retrieval cache. Values are IDs and ranks only.

Valkey is never authority. Every hit must call
``recheck_retrieval_candidates`` (or an injected equivalent) before IDs
become evidence. A failed recheck drops candidates and never serves stale
payloads.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from smart_rag_core.retrieval.cache_key import cache_payload, hybrid_cache_key
from smart_rag_core.retrieval.profiles import (
    BM25_INDEX_SCHEMA_VERSION,
    HYBRID_DEFAULT_PROFILE_ID,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.runtime.valkey import (
    CACHE_KEY_PREFIX,
    MemoryValkeyClient,
    ValkeyClient,
    ValkeyTimeoutError,
)

LOGGER = logging.getLogger(__name__)

RESULT_TTL_SECONDS = 30
PROFILE_TTL_SECONDS = 300


def _default_profile() -> str:
    """Return the frozen Hybrid profile id.

    Returns:
        Allow-listed profile identifier.
    """

    return HYBRID_DEFAULT_PROFILE_ID


def _default_index() -> str:
    """Return the frozen BM25 index schema version.

    Returns:
        Index version string.
    """

    return BM25_INDEX_SCHEMA_VERSION


class RetrievalCacheMode(StrEnum):
    """Whether Hybrid may read or write the ID/rank cache.

    ``cold_bypass`` still uses the production ranking path. It skips cache
    get/put so exams cannot reuse a warm Ask result.
    """

    NORMAL = "normal"
    COLD_BYPASS = "cold_bypass"


class CacheEvent(StrEnum):
    """Observability events required by Phase 6 packet 5."""

    HIT = "cache_hit"
    MISS = "cache_miss"
    INVALIDATED = "cache_invalidated"
    RECHECK_FAILED = "cache_recheck_failed"


class RecheckFn(Protocol):
    """Authoritative Postgres recheck used on every cache hit."""

    def __call__(self, chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Return survivors in scan order.

        Args:
            chunk_ids: Cached IDs. Never trusted as evidence.

        Returns:
            Authorized current-version candidates.
        """

        ...


@dataclass(frozen=True, slots=True)
class CachedRetrieval:
    """ID/rank payload after a successful recheck.

    Attributes:
        chunk_ids: Rechecked canonical IDs.
        ranks: Cached ranks aligned with surviving IDs.
        event: ``cache_hit`` when served from cache after recheck.
    """

    chunk_ids: tuple[UUID, ...]
    ranks: tuple[int, ...]
    event: CacheEvent


def _prefixed(digest: str) -> str:
    """Apply the cache key prefix.

    Args:
        digest: SHA-256 hex from ``hybrid_cache_key``.

    Returns:
        Prefixed Valkey key.
    """

    return f"{CACHE_KEY_PREFIX}{digest}"


def _emit(event: CacheEvent, **fields: object) -> None:
    """Emit a structured cache event without passage text.

    Args:
        event: Required cache event name.
        **fields: Additional non-secret fields.
    """

    LOGGER.info(
        event.value,
        extra={"event": event.value, **fields},
    )


class RetrievalCacheStore:
    """Best-effort ID/rank cache in front of mandatory Postgres recheck.

    Args constructor stores the client and TTLs. Losing the cache cannot
    weaken ACL, deletion, or current-version enforcement.
    """

    def __init__(
        self,
        client: ValkeyClient,
        *,
        result_ttl_seconds: int = RESULT_TTL_SECONDS,
        profile_ttl_seconds: int = PROFILE_TTL_SECONDS,
    ) -> None:
        """Bind a Valkey-compatible client.

        Args:
            client: Cache instance (Valkey or in-memory). Never limits Valkey.
            result_ttl_seconds: Retrieval ID/rank TTL (default 30).
            profile_ttl_seconds: Profile/embedding TTL (default 300).
        """

        self._client = client
        self._result_ttl = result_ttl_seconds
        self._profile_ttl = profile_ttl_seconds

    @classmethod
    def in_memory(
        cls,
        *,
        result_ttl_seconds: int = RESULT_TTL_SECONDS,
        profile_ttl_seconds: int = PROFILE_TTL_SECONDS,
    ) -> RetrievalCacheStore:
        """Return a store backed by ``MemoryValkeyClient``.

        Args:
            result_ttl_seconds: Retrieval TTL.
            profile_ttl_seconds: Profile TTL.

        Returns:
            In-process store for unit tests.
        """

        return cls(
            MemoryValkeyClient(),
            result_ttl_seconds=result_ttl_seconds,
            profile_ttl_seconds=profile_ttl_seconds,
        )

    def put_results(
        self,
        *,
        principal_scope_hash: str,
        query_normalized: str,
        visibility_generation: int,
        chunk_ids: tuple[UUID, ...],
        ranks: tuple[int, ...],
        retrieval_profile_id: str | None = None,
        index_version: str | None = None,
    ) -> str:
        """Store IDs and ranks only.

        Args:
            principal_scope_hash: Server-derived ACL scope hash.
            query_normalized: Normalized query text.
            visibility_generation: Document visibility generation.
            chunk_ids: Canonical IDs.
            ranks: Fused ranks.
            retrieval_profile_id: Optional allow-listed profile.
            index_version: Optional BM25 index version.

        Returns:
            Cache key digest.

        Raises:
            ValueError: If payload lengths differ or the profile is unknown.
        """

        digest = hybrid_cache_key(
            principal_scope_hash=principal_scope_hash,
            query_normalized=query_normalized,
            visibility_generation=visibility_generation,
            retrieval_profile_id=(
                retrieval_profile_id
                if retrieval_profile_id is not None
                else _default_profile()
            ),
            index_version=index_version
            if index_version is not None
            else _default_index(),
        )
        payload = cache_payload(chunk_ids, ranks)
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        try:
            self._client.set(_prefixed(digest), encoded, self._result_ttl)
        except ValkeyTimeoutError:
            LOGGER.info(
                "cache_write_skipped",
                extra={"event": "cache_write_skipped"},
            )
        return digest

    def put_profile(self, key: str, payload: bytes) -> None:
        """Store a profile/embedding blob with the 300s TTL.

        Args:
            key: Application key; prefix is applied.
            payload: Non-evidence bytes (embedding vector or profile JSON).
        """

        try:
            self._client.set(_prefixed(key), payload, self._profile_ttl)
        except ValkeyTimeoutError:
            LOGGER.info(
                "cache_write_skipped",
                extra={"event": "cache_write_skipped"},
            )

    def invalidate(self, digest: str) -> None:
        """Best-effort delete of one result key.

        Args:
            digest: ``hybrid_cache_key`` digest.
        """

        try:
            self._client.delete(_prefixed(digest))
        except ValkeyTimeoutError:
            pass
        _emit(CacheEvent.INVALIDATED, key_digest=digest[:12])

    def get_results(
        self,
        *,
        principal_scope_hash: str,
        query_normalized: str,
        visibility_generation: int,
        recheck: RecheckFn,
        retrieval_profile_id: str | None = None,
        index_version: str | None = None,
        on_recheck_error: Callable[[BaseException], None] | None = None,
    ) -> CachedRetrieval | None:
        """Load IDs, recheck, and drop stale hits.

        Args:
            principal_scope_hash: Server-derived ACL scope hash.
            query_normalized: Normalized query text.
            visibility_generation: Document visibility generation.
            recheck: Authoritative Postgres recheck.
            retrieval_profile_id: Optional profile id.
            index_version: Optional index version.
            on_recheck_error: Optional hook when recheck raises.

        Returns:
            Rechecked IDs/ranks on a valid hit, otherwise None (miss or drop).
        """

        digest = hybrid_cache_key(
            principal_scope_hash=principal_scope_hash,
            query_normalized=query_normalized,
            visibility_generation=visibility_generation,
            retrieval_profile_id=(
                retrieval_profile_id
                if retrieval_profile_id is not None
                else _default_profile()
            ),
            index_version=index_version
            if index_version is not None
            else _default_index(),
        )
        try:
            raw = self._client.get(_prefixed(digest))
        except ValkeyTimeoutError:
            _emit(CacheEvent.MISS, reason="valkey_unavailable")
            return None
        if raw is None:
            _emit(CacheEvent.MISS, key_digest=digest[:12])
            return None
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            self.invalidate(digest)
            _emit(CacheEvent.RECHECK_FAILED, reason="payload_invalid")
            return None
        if not isinstance(decoded, dict):
            self.invalidate(digest)
            return None
        payload = cast(dict[str, object], decoded)
        raw_ids = payload.get("chunk_ids")
        raw_ranks = payload.get("ranks")
        if not isinstance(raw_ids, list) or not isinstance(raw_ranks, list):
            self.invalidate(digest)
            return None
        if "snippet" in payload or "text" in payload or "passage" in payload:
            self.invalidate(digest)
            _emit(CacheEvent.RECHECK_FAILED, reason="forbidden_payload_field")
            return None
        try:
            id_items = cast(list[object], raw_ids)
            rank_items = cast(list[object], raw_ranks)
            chunk_ids = tuple(UUID(str(item)) for item in id_items)
            ranks = tuple(int(str(item)) for item in rank_items)
        except (ValueError, TypeError):
            self.invalidate(digest)
            return None
        if len(chunk_ids) != len(ranks):
            self.invalidate(digest)
            return None
        rank_by_id = dict(zip(chunk_ids, ranks, strict=True))
        try:
            survivors = recheck(chunk_ids)
        except Exception as exc:
            _emit(CacheEvent.RECHECK_FAILED, reason="recheck_exception")
            if on_recheck_error is not None:
                on_recheck_error(exc)
            self.invalidate(digest)
            return None
        survivor_ids = tuple(item.chunk_id for item in survivors)
        if len(survivor_ids) != len(chunk_ids) or survivor_ids != chunk_ids:
            _emit(
                CacheEvent.RECHECK_FAILED,
                reason="acl_delete_or_version_flip",
                cached=len(chunk_ids),
                survived=len(survivor_ids),
            )
            self.invalidate(digest)
            return None
        _emit(CacheEvent.HIT, key_digest=digest[:12], count=len(survivor_ids))
        return CachedRetrieval(
            chunk_ids=survivor_ids,
            ranks=tuple(rank_by_id[item] for item in survivor_ids),
            event=CacheEvent.HIT,
        )
