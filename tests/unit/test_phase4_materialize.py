"""Unit tests for Phase 4 Packet 9 Wave 1B open-split eval materialization."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import uuid4

import pytest
from smart_rag_core.evaluation.classes import QueryClass, RuntimeOwner
from smart_rag_core.evaluation.materialize import (
    GOLD_CHUNK_MARKER,
    SIDECAR_SCHEMA_VERSION,
    GoldIdSidecar,
    build_compact_source,
    build_sidecar,
    document_visibility_for_case,
    map_gold_ids,
    materialize_phase4_eval_corpus,
    select_phase4_retrieve_cases,
    write_compact_sources,
    write_sidecar,
)
from smart_rag_core.evaluation.schema import DatasetSplit

REPO_ROOT = Path(__file__).resolve().parents[2]
MATERIALIZE_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "materialize.py"
)
MATERIALIZE_SCRIPT = REPO_ROOT / "scripts" / "materialize_phase4_eval_corpus.py"
HYBRID_READY_DRIVER = REPO_ROOT / "tests" / "contract" / "hybrid_ready_driver.py"
_DEFERRED = {
    QueryClass.RELATIONSHIP,
    QueryClass.MULTI_HOP,
    QueryClass.GRAPH_MAPPING,
    QueryClass.PROMPT_INJECTION,
}


def test_select_filters_phase4_open_splits_and_excludes_deferred() -> None:
    """Open-split selection keeps Phase 4 retrieve classes only."""

    cases = select_phase4_retrieve_cases()
    assert cases
    assert all(
        case.split in {DatasetSplit.DEVELOPMENT, DatasetSplit.QUALIFICATION}
        for case in cases
    )
    assert all(case.runtime_owner is RuntimeOwner.PHASE_4 for case in cases)
    assert all(case.query_class not in _DEFERRED for case in cases)
    development = select_phase4_retrieve_cases(split="development")
    qualification = select_phase4_retrieve_cases(split="qualification")
    assert development
    assert qualification
    assert {case.case_id for case in development}.isdisjoint(
        {case.case_id for case in qualification}
    )
    assert {case.case_id for case in development} | {
        case.case_id for case in qualification
    } == {case.case_id for case in cases}


def test_injected_sealed_split_case_is_dropped() -> None:
    """Caller-supplied sealed-split cases cannot enter the materializer set."""

    template = select_phase4_retrieve_cases(limit=1)[0]
    injected = template.model_copy(
        update={
            "case_id": "p4-exact_code-9998",
            "split": DatasetSplit.HOLDOUT,
        }
    )
    selected = select_phase4_retrieve_cases(cases=[template, injected])
    assert template.case_id in {case.case_id for case in selected}
    assert injected.case_id not in {case.case_id for case in selected}


def test_deferred_class_is_excluded_even_when_injected() -> None:
    """Relationship-class cases cannot be materialized for Phase 4 retrieve."""

    template = select_phase4_retrieve_cases(limit=1)[0]
    injected = template.model_copy(
        update={
            "case_id": "p4-relationship-0001",
            "query_class": QueryClass.RELATIONSHIP,
            "runtime_owner": RuntimeOwner.PHASE_5_AND_6,
            "source_family_id": "p4-fam-relationship-0001",
        }
    )
    selected = select_phase4_retrieve_cases(cases=[template, injected])
    assert all(case.query_class is not QueryClass.RELATIONSHIP for case in selected)


def test_compact_source_contains_gold_codes_aliases_answers_and_arabic() -> None:
    """Compact markdown includes labeled codes, aliases, answers, and Arabic."""

    cases = select_phase4_retrieve_cases()
    exact = next(case for case in cases if case.query_class is QueryClass.EXACT_CODE)
    source = build_compact_source(exact)
    codes = exact.expected_profile.codes.value
    assert isinstance(codes, list)
    assert codes
    assert str(codes[0]) in source.markdown_text
    assert exact.acceptable_answers[0] in source.markdown_text
    assert exact.evidence_links[0].chunk_id is not None
    assert (
        f"{GOLD_CHUNK_MARKER}{exact.evidence_links[0].chunk_id}" in source.markdown_text
    )
    alias = next(case for case in cases if case.query_class is QueryClass.ALIAS)
    alias_source = build_compact_source(alias)
    aliases = alias.expected_profile.approved_aliases.value
    assert isinstance(aliases, list)
    assert str(aliases[0]) in alias_source.markdown_text
    arabic = next(case for case in cases if case.query_class is QueryClass.ARABIC_MIXED)
    arabic_source = build_compact_source(arabic)
    assert arabic.query in arabic_source.markdown_text
    assert "\u0625\u062c\u0627\u0632\u0629" in arabic_source.markdown_text


def test_tabular_path_emits_table_file(tmp_path: Path) -> None:
    """Tabular aggregation writes a CSV beside the compact markdown."""

    tabular = next(
        case
        for case in select_phase4_retrieve_cases()
        if case.query_class is QueryClass.TABULAR_AGGREGATION
    )
    source = build_compact_source(tabular)
    assert source.table_csv is not None
    assert source.table_filename is not None
    codes = tabular.expected_profile.codes.value
    assert isinstance(codes, list)
    assert str(codes[0]) in source.table_csv
    write_compact_sources([tabular], tmp_path)
    csv_path = tmp_path / "sources" / source.table_filename
    markdown_path = tmp_path / "sources" / source.markdown_filename
    assert csv_path.is_file()
    assert markdown_path.is_file()
    assert str(codes[0]) in csv_path.read_text(encoding="utf-8")


def test_acl_negative_is_restricted_not_public() -> None:
    """ACL-negative gold uses the restricted actor and restricted visibility."""

    acl = next(
        case
        for case in select_phase4_retrieve_cases()
        if case.query_class is QueryClass.ACL_NEGATIVE
    )
    assert acl.acl_actor.restricted is True
    assert document_visibility_for_case(acl) == "restricted"
    exact = next(
        case
        for case in select_phase4_retrieve_cases()
        if case.query_class is QueryClass.EXACT_CODE
    )
    assert exact.acl_actor.restricted is False
    assert document_visibility_for_case(exact) == "company_visible"


def test_sidecar_schema_maps_synthetic_chunk_id_to_uuid() -> None:
    """Sidecar records map generator gold ids onto real chunk UUIDs."""

    case = next(
        item
        for item in select_phase4_retrieve_cases()
        if item.query_class is QueryClass.EXACT_CODE and item.evidence_links
    )
    synthetic = case.evidence_links[0].chunk_id
    assert synthetic is not None
    real_chunk = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    records = map_gold_ids(
        case,
        document_id=document_id,
        version_id=version_id,
        chunk_texts=((real_chunk, f"{GOLD_CHUNK_MARKER}{synthetic} body"),),
    )
    assert len(records) == 1
    assert records[0].synthetic_chunk_id == synthetic
    assert records[0].chunk_id == real_chunk
    assert records[0].document_id == document_id
    assert records[0].version_id == version_id
    sidecar = build_sidecar([case])
    assert sidecar.schema_version == SIDECAR_SCHEMA_VERSION
    assert sidecar.holdout_opened is False
    assert sidecar.runtime_owner == "phase_4"
    parsed = GoldIdSidecar.model_validate(sidecar.model_dump(mode="json"))
    assert parsed.case_count == 1
    assert parsed.sidecar_sha256


def test_write_sidecar_refuses_sealed_manifest_directory(tmp_path: Path) -> None:
    """Sidecar writes cannot target the sealed dataset manifests folder."""

    sealed = tmp_path / "manifests"
    sealed.mkdir()
    sidecar = build_sidecar(select_phase4_retrieve_cases(limit=1))
    with pytest.raises(ValueError, match="sealed dataset manifests"):
        write_sidecar(sidecar, sealed)


def test_materialize_writes_sources_and_sidecar_without_docker(tmp_path: Path) -> None:
    """Dry materialization writes compact files and a closed sidecar."""

    sidecar = materialize_phase4_eval_corpus(
        output_dir=tmp_path,
        split="development",
        limit=3,
    )
    assert sidecar.holdout_opened is False
    assert sidecar.case_count == 3
    payload = json.loads((tmp_path / "gold_id_map.json").read_text(encoding="utf-8"))
    assert payload["holdout_opened"] is False
    assert (tmp_path / "sources").is_dir()
    markdown_files = list((tmp_path / "sources").glob("*.md"))
    assert len(markdown_files) == 3


def test_materialize_module_and_script_are_holdout_blind() -> None:
    """Materializer sources must not call holdout load APIs."""

    for path in (MATERIALIZE_MODULE, MATERIALIZE_SCRIPT):
        dumped = ast.dump(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )
        assert "load_holdout" not in dumped
        assert "HOLDOUT" not in dumped
        assert "HoldoutAccess" not in dumped
        assert "generate_corpus" not in dumped


def test_hybrid_ready_driver_uses_shared_embedding_gateway() -> None:
    """Hybrid Ready persist uses create_embedding_gateway, not a private mock."""

    source = HYBRID_READY_DRIVER.read_text(encoding="utf-8")
    dumped = ast.dump(ast.parse(source, filename=str(HYBRID_READY_DRIVER)))
    assert "create_embedding_gateway" in dumped
    assert "MockEmbeddingAdapter" not in dumped
    tree = ast.parse(source, filename=str(HYBRID_READY_DRIVER))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
    assert "persist_parse_to_bm25_outbox" in names
    assert "drive_hybrid_ready" in names
    assert "list_persisted_chunk_texts" in names
