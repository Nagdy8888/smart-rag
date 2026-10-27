"""Version an existing development corpus without opening an immutable holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import cast

from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.schema import DatasetSplit

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    """Hash source bytes without publishing private question or answer text."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_pack(private_gold: Path, output: Path) -> dict[str, object]:
    """Snapshot known development gold; preserve all existing source files."""
    private_root = (ROOT / ".private-eval").resolve()
    source = private_gold.resolve()
    destination = output.resolve()
    if not source.is_relative_to(private_root) or not destination.is_relative_to(
        private_root
    ):
        raise ValueError("private_evaluation_paths_required")
    if source.name not in {"dev40-2026-10-v3.json"}:
        raise ValueError("only_explicitly_development_gold_is_allowlisted")
    if destination.exists():
        raise ValueError("evaluation_pack_already_exists")
    cases = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("development_gold_empty")
    cases = cast(list[object], cases)
    selected = [
        case.model_dump(mode="json")
        for case in generate_corpus()
        if case.split is DatasetSplit.DEVELOPMENT
    ]
    memory = ROOT / "tests/fixtures/query-memory-linked50-v4.json"
    release = ROOT / "tests/fixtures/agent_release_v1.json"
    manifest: dict[str, object] = {
        "schema": "company-knowledge-evaluation-v1",
        "split": "development",
        "purpose": "Reliability baseline; synthetic contracts and private corpus quality are separate measures.",
        "private_corpus": {
            "file": "company-gold.json",
            "source": source.name,
            "source_sha256": digest(source),
            "count": len(cases),
        },
        "synthetic_corpus": {
            "file": "synthetic-development.json",
            "count": len(selected),
            "classes": dict(Counter(str(case["query_class"]) for case in selected)),
            "languages": dict(Counter(str(case["language"]) for case in selected)),
        },
        "connected_followups": {
            "file": str(memory.relative_to(ROOT)),
            "sha256": digest(memory),
        },
        "release_integrity": {
            "file": str(release.relative_to(ROOT)),
            "sha256": digest(release),
        },
        "governance_contracts": "tests/contract/test_company_knowledge.py",
        "quality_targets": "docs/QUALITY_TARGETS.md",
        "required_metrics": [
            "correctness",
            "citation_support",
            "knowledge_outcome",
            "current_source_selection",
            "permission_isolation",
            "latency_p50_p95",
            "cost_usd",
            "answer_rate",
            "refusal_rate",
        ],
        "live_status": "not_run",
        "holdout_opened": False,
    }
    destination.mkdir(parents=True)
    (destination / "company-gold.json").write_bytes(source.read_bytes())
    (destination / "synthetic-development.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    """Build one new private pack, printing only safe counts and status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-gold", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_pack(args.private_gold, args.out)
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "live_status": result["live_status"],
                "holdout_opened": result["holdout_opened"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
