"""Unit tests for the immutable LightRAG pin and GraphRetriever protocols."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Protocol

import pytest
from smart_rag_core.retrieval.graph import (
    ADAPTER_MAX_GRAPH_CANDIDATES,
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    FORBIDDEN_AGE_GRAPH_STORAGE,
    GRAPH_FIELD_SEP,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_WHEEL_SHA256,
    SELECTED_GRAPH_STORAGE,
    GraphIndexer,
    GraphRetriever,
    ProseContextRejectedError,
    SourceIdContractError,
    apply_query_bounds,
    parse_source_id_list,
    reject_rendered_context_parser,
)
from smart_rag_core.retrieval.lightrag_pin import (
    TRANSITIVE_HARD_DEPENDENCIES,
    LightRagPinError,
    verify_lightrag_pin,
)
from smart_rag_core.retrieval.lightrag_qualification import (
    coerce_deletion_status,
    status_record_mapping,
)
from smart_rag_core.retrieval.lightrag_structured import (
    LightRagQueryFailure,
    parse_aquery_data_payload,
    to_graph_leads,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "uv.lock"
GRAPH_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "retrieval"
    / "graph.py"
)
ALLOWED_LIGHTRAG_IMPORT_PARTS: tuple[str, ...] = (
    "smart_rag_core/retrieval/lightrag_pin.py",
    "smart_rag_core/retrieval/lightrag_callbacks.py",
    "smart_rag_core/retrieval/lightrag_qualification.py",
)


def _imports_lightrag(path: Path) -> bool:
    """Return whether a Python file imports the vendor LightRAG package.

    Args:
        path: Source file.

    Returns:
        True when an ``import lightrag`` or ``from lightrag...`` node exists.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "lightrag" or alias.name.startswith("lightrag."):
                    return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "lightrag" or node.module.startswith("lightrag."):
                return True
    return False


def test_verify_lightrag_pin_matches_lock_and_install() -> None:
    """Installed 1.5.6, lock hashes, and required classes must match the pin."""

    record = verify_lightrag_pin(lock_path=LOCK_PATH)
    assert record.version == LIGHTRAG_PINNED_VERSION
    assert record.wheel_sha256 == LIGHTRAG_WHEEL_SHA256
    assert record.selected_graph_storage == SELECTED_GRAPH_STORAGE
    assert record.forbidden_age_storage == FORBIDDEN_AGE_GRAPH_STORAGE
    assert record.license_name.upper() in {"MIT", "MIT LICENSE"}


def test_wheel_hash_mismatch_fails_closed() -> None:
    """A wrong expected wheel digest must raise ``wheel_hash_mismatch``."""

    with pytest.raises(LightRagPinError, match="wheel_hash_mismatch"):
        verify_lightrag_pin(
            lock_path=LOCK_PATH,
            expected_wheel_sha256="0" * 64,
        )


def test_sdist_hash_mismatch_fails_closed() -> None:
    """A wrong expected sdist digest must raise ``sdist_hash_mismatch``."""

    with pytest.raises(LightRagPinError, match="sdist_hash_mismatch"):
        verify_lightrag_pin(
            lock_path=LOCK_PATH,
            expected_sdist_sha256="0" * 64,
        )


def test_age_storage_exists_but_is_not_selected() -> None:
    """PGGraphStorage must exist on the pin and must not be the selected engine."""

    record = verify_lightrag_pin(lock_path=LOCK_PATH)
    assert record.selected_graph_storage != record.forbidden_age_storage
    from lightrag.kg.pgtable_impl import PGTableGraphStorage
    from lightrag.kg.postgres_impl import PGGraphStorage

    assert PGTableGraphStorage.__name__ == SELECTED_GRAPH_STORAGE
    assert PGGraphStorage.__name__ == FORBIDDEN_AGE_GRAPH_STORAGE
    assert PGTableGraphStorage is not PGGraphStorage


def test_graph_retriever_and_indexer_are_protocols() -> None:
    """Application-facing graph types are Protocols, not vendor classes."""

    assert issubclass(GraphRetriever, Protocol)
    assert issubclass(GraphIndexer, Protocol)
    assert "retrieve_local" in GraphRetriever.__dict__
    assert "enqueue_insert" in GraphIndexer.__dict__


def test_graph_module_does_not_import_lightrag() -> None:
    """``graph.py`` must stay vendor-free."""

    assert GRAPH_MODULE.is_file()
    assert _imports_lightrag(GRAPH_MODULE) is False


def test_apps_backend_worker_agents_do_not_import_lightrag() -> None:
    """Deployable source trees must not import LightRAG classes."""

    roots = (
        REPO_ROOT / "apps" / "backend" / "src",
        REPO_ROOT / "apps" / "worker" / "src",
        REPO_ROOT / "apps" / "agents" / "src",
    )
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            if _imports_lightrag(path):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_core_lightrag_imports_stay_in_adapter_modules() -> None:
    """Only pin/callback/qualification modules may import LightRAG."""

    core_root = REPO_ROOT / "packages" / "core" / "src" / "smart_rag_core"
    offenders: list[str] = []
    for path in core_root.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT).as_posix()
        normalized = relative.replace("\\", "/")
        if any(part in normalized for part in ALLOWED_LIGHTRAG_IMPORT_PARTS):
            continue
        if _imports_lightrag(path):
            offenders.append(relative)
    assert offenders == []


def test_apply_query_bounds_clamps_and_rejects_non_positive() -> None:
    """Adapter bounds wrap vendor QueryParam values and reject invalid inputs."""

    bounds = apply_query_bounds(
        top_k=999,
        chunk_top_k=50,
        max_entity_tokens=99_000,
        max_relation_tokens=99_000,
        max_total_tokens=99_000,
        deadline_seconds=120.0,
    )
    assert bounds.top_k == ADAPTER_MAX_GRAPH_CANDIDATES
    assert bounds.chunk_top_k == ADAPTER_MAX_GRAPH_CANDIDATES
    with pytest.raises(ValueError, match="graph_query_bounds_must_be_positive"):
        apply_query_bounds(
            top_k=0,
            chunk_top_k=1,
            max_entity_tokens=1,
            max_relation_tokens=1,
            max_total_tokens=1,
            deadline_seconds=1.0,
        )
    with pytest.raises(ValueError, match="graph_query_deadline_must_be_positive"):
        apply_query_bounds(
            top_k=1,
            chunk_top_k=1,
            max_entity_tokens=1,
            max_relation_tokens=1,
            max_total_tokens=1,
            deadline_seconds=0.0,
        )


def test_graph_source_envelope_binds_and_strips_identity() -> None:
    """Identity envelopes are reversible and reject unsafe document IDs."""

    from smart_rag_core.retrieval.graph import (
        GraphSourceEnvelopeError,
        bind_graph_source_text,
        strip_graph_source_envelope,
    )

    bound = bind_graph_source_text(
        document_version_id="doc-version-1",
        normalized_text="Alpha Probe reports a finding.",
    )
    assert bound.startswith(
        "<<smart-rag-graph-source:graph_source_envelope_v1:doc-version-1>>\n"
    )
    assert strip_graph_source_envelope(bound) == "Alpha Probe reports a finding."
    other = bind_graph_source_text(
        document_version_id="doc-version-2",
        normalized_text="Alpha Probe reports a finding.",
    )
    assert bound != other
    assert strip_graph_source_envelope("no envelope") == "no envelope"
    with pytest.raises(GraphSourceEnvelopeError):
        bind_graph_source_text(document_version_id="bad id", normalized_text="x")


def test_source_id_parser_rejects_empty_ambiguous_and_truncated() -> None:
    """Delimiter parsing fails closed instead of inventing complete provenance."""

    assert parse_source_id_list("chunk-a", limit=DEFAULT_MAX_SOURCE_IDS_PER_ENTITY) == (
        "chunk-a",
    )
    joined = GRAPH_FIELD_SEP.join(("chunk-a", "chunk-b"))
    assert parse_source_id_list(joined, limit=200) == ("chunk-a", "chunk-b")
    with pytest.raises(SourceIdContractError, match="source_id_list_empty"):
        parse_source_id_list("  ", limit=200)
    with pytest.raises(SourceIdContractError, match="source_id_list_ambiguous"):
        parse_source_id_list(
            f"chunk-a{GRAPH_FIELD_SEP}{GRAPH_FIELD_SEP}chunk-b", limit=200
        )
    with pytest.raises(SourceIdContractError, match="source_id_list_ambiguous"):
        parse_source_id_list(f"chunk-a{GRAPH_FIELD_SEP}chunk-a", limit=200)
    capped = GRAPH_FIELD_SEP.join(f"c{index}" for index in range(200))
    with pytest.raises(SourceIdContractError, match="source_id_list_truncated"):
        parse_source_id_list(capped, limit=200)


def test_rendered_context_parser_is_rejected() -> None:
    """Human-rendered vendor context must never become evidence."""

    with pytest.raises(
        ProseContextRejectedError, match="rendered_graph_context_is_not_evidence"
    ):
        reject_rendered_context_parser("Entities: Alpha Probe\nRelationships: ...")


def test_structured_parser_ignores_description_keywords_file_path_reference() -> None:
    """Vendor description/keywords/file_path/reference_id are not lead IDs."""

    payload = {
        "status": "success",
        "message": "Query executed successfully",
        "data": {
            "entities": [
                {
                    "entity_name": "Alpha Probe",
                    "entity_type": "Concept",
                    "description": "not-an-id",
                    "source_id": "chunk-1",
                    "file_path": "secret/path.txt",
                    "created_at": 1786833846,
                    "reference_id": "1",
                }
            ],
            "relationships": [
                {
                    "src_id": "Alpha Probe",
                    "tgt_id": "Beta Probe",
                    "description": "not-an-id",
                    "keywords": "also-not-an-id",
                    "source_id": "chunk-1",
                    "file_path": "secret/path.txt",
                    "created_at": 1786833845,
                    "reference_id": "2",
                }
            ],
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "content": "synthetic",
                    "file_path": "secret/path.txt",
                    "reference_id": "3",
                }
            ],
            "references": [{"reference_id": "1", "file_path": "secret/path.txt"}],
        },
        "metadata": {
            "query_mode": "hybrid",
            "keywords": {
                "high_level": ["qualification"],
                "low_level": ["Alpha Probe"],
            },
        },
    }
    result = parse_aquery_data_payload(payload)
    leads = to_graph_leads(result)
    assert leads.mode == "hybrid"
    assert leads.entities[0].entity_name == "Alpha Probe"
    assert leads.entities[0].source_ids == ("chunk-1",)
    assert leads.chunks[0].chunk_id == "chunk-1"
    dumped = leads.model_dump()
    assert "description" not in dumped["entities"][0]
    assert "keywords" not in dumped["relations"][0]
    assert "file_path" not in dumped["entities"][0]
    assert "reference_id" not in dumped["chunks"][0]


def test_structured_parser_rejects_failure_and_truncated_source_ids() -> None:
    """Failure envelopes and capped source lists fail closed."""

    with pytest.raises(LightRagQueryFailure, match=r"empty"):
        parse_aquery_data_payload({"status": "failure", "message": "empty", "data": {}})
    with pytest.raises(LightRagQueryFailure, match="no_results"):
        parse_aquery_data_payload(
            {
                "status": "failure",
                "message": "Query returned no results",
                "data": {},
                "metadata": {"failure_reason": "no_results", "mode": "local"},
            }
        )
    capped = GRAPH_FIELD_SEP.join(f"c{index}" for index in range(200))
    payload = {
        "status": "success",
        "data": {
            "entities": [{"entity_name": "Alpha Probe", "source_id": capped}],
            "relationships": [],
            "chunks": [],
        },
        "metadata": {"query_mode": "local"},
    }
    result = parse_aquery_data_payload(payload)
    with pytest.raises(LightRagQueryFailure, match="source_id_list_truncated"):
        to_graph_leads(result)


def test_status_record_mapping_reads_postgres_dict_rows() -> None:
    """PGDocStatusStorage.get_by_id returns dicts; getattr would miss status."""

    mapping = status_record_mapping(
        {
            "status": "processed",
            "track_id": "monitor-only",
            "file_path": "opaque.txt",
            "metadata": {"is_duplicate": False},
        }
    )
    assert mapping["status"] == "processed"
    assert mapping["track_id"] == "monitor-only"
    assert mapping["file_path"] == "opaque.txt"


def test_unsupported_deletion_status_fails_closed() -> None:
    """Undocumented deletion statuses are not coerced into success."""

    from smart_rag_core.retrieval.lightrag_qualification import (
        LightRagQualificationError,
    )

    with pytest.raises(
        LightRagQualificationError, match="unsupported_deletion_status:partial"
    ):
        coerce_deletion_status("partial")
    assert coerce_deletion_status("not_found") == "not_found"


def test_transitive_hard_dependencies_are_recorded() -> None:
    """Packet 1 records LightRAG hard deps and does not add api/offline extras."""

    assert "pipmaster" in TRANSITIVE_HARD_DEPENDENCIES
    assert "google-genai" in TRANSITIVE_HARD_DEPENDENCIES
    assert "nano-vectordb" in TRANSITIVE_HARD_DEPENDENCIES
    core_toml = (REPO_ROOT / "packages" / "core" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "lightrag-hku[api]" not in core_toml
    assert "lightrag-hku[offline]" not in core_toml
