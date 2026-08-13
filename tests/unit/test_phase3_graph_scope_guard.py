"""Repository guard: Phase 3 must not emit Graph Ready or Phase 5 mappings."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("graph_ready", "Phase 3 must not set Graph Ready lifecycle"),
    ("Graph Ready", "Phase 3 must not claim Graph Ready in runtime code"),
    ("lightrag_source_map", "Phase 5 owns source map writes"),
    ("lightrag_chunk_map", "Phase 5 owns chunk map writes"),
    ("graph_evidence_map", "Phase 5 owns evidence map writes"),
)

ALLOWED_PATH_PARTS: tuple[str, ...] = (
    "tests/",
    ".cursor/plans/",
    "docs/",
    "supabase/migrations/20260812135053_lightrag_maps_v1.sql",
    "packages/core/src/smart_rag_core/schema/",
)


def _is_allowed(path: Path) -> bool:
    normalized = path.as_posix()
    return any(part in normalized for part in ALLOWED_PATH_PARTS)


def test_phase3_runtime_has_no_graph_ready_or_mapping_writes() -> None:
    """Fail if runtime ingestion/indexing code writes Phase 5 graph artifacts."""

    repo_root = Path(__file__).resolve().parents[2]
    scan_roots = (
        repo_root / "apps",
        repo_root / "packages" / "core" / "src" / "smart_rag_core" / "ingestion",
        repo_root / "packages" / "core" / "src" / "smart_rag_core" / "retrieval",
    )
    violations: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _is_allowed(path):
                continue
            text = path.read_text(encoding="utf-8")
            for pattern, reason in FORBIDDEN_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(repo_root)}: {reason} ({pattern})")
    assert not violations, "\n".join(violations)
