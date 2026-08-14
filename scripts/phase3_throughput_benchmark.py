#!/usr/bin/env python3
"""Bounded Phase 3 ingestion throughput probe for Packet 8 exit evidence.

Measures local parse→chunk→mock-embed stages only. Full ``Hybrid Ready`` throughput
requires live Supabase Storage, worker leases, ClamAV, and ParadeDB projection;
this script reports those blockers instead of fabricating end-to-end rates.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.embeddings.contextual import (
    build_contextual_embedding_text,
)
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.ingestion.parser.adapters import parse_file

from tests.fixtures.parser import build_pdf_text_fixture

SIGNED_TEXT_PAGES_PER_HOUR = 500
SIGNED_OCR_PAGES_PER_HOUR = 100


@dataclass(frozen=True)
class ThroughputSample:
    """One bounded throughput measurement row."""

    stage: str
    iterations: int
    pages_processed: int
    elapsed_seconds: float
    pages_per_hour: float


@dataclass(frozen=True)
class ThroughputReport:
    """Aggregate throughput report for evidence handoff."""

    hardware_note: str
    mock_model_mode: bool
    signed_text_gate: int
    signed_ocr_gate: int
    samples: list[ThroughputSample]
    text_gate_met: bool | None
    ocr_gate_met: bool | None
    hybrid_ready_gate: str
    blockers: list[str]


def _measure_text_pipeline(*, iterations: int, tmp_dir: Path) -> ThroughputSample:
    """Run parse→chunk→mock embed on the programmatic PDF fixture."""

    payload, digest = build_pdf_text_fixture()
    path = tmp_dir / "bench.pdf"
    path.write_bytes(payload)
    start = time.perf_counter()
    pages = 0
    for _ in range(iterations):
        parsed = parse_file(path, digest, "pdf")
        chunked = chunk_parse_result(
            parsed,
            document_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
            version_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        )
        for chunk in chunked.chunks:
            contextual = build_contextual_embedding_text(
                document_title="bench",
                chunk=chunk,
            )
            _ = mock_embedding_vector(contextual)
        pages += 2
    elapsed = max(time.perf_counter() - start, 1e-9)
    rate = pages / elapsed * 3600.0
    return ThroughputSample(
        stage="parse_chunk_mock_embed_text_pdf",
        iterations=iterations,
        pages_processed=pages,
        elapsed_seconds=elapsed,
        pages_per_hour=rate,
    )


def build_report(*, iterations: int) -> ThroughputReport:
    """Construct an honest throughput report with gate posture."""

    tmp_dir = Path(".pytest_cache/phase3_throughput")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    sample = _measure_text_pipeline(iterations=iterations, tmp_dir=tmp_dir)
    text_met = sample.pages_per_hour >= SIGNED_TEXT_PAGES_PER_HOUR
    blockers = [
        "End-to-end Hybrid Ready throughput not measured: requires live Compose stack "
        "(Supabase Storage upload, ClamAV scan/promote, worker graph, ParadeDB verify).",
        "OCR pages/hour not measured on this host: scanned-PDF OCR benchmark needs "
        "parser-sandbox image + Tesseract and full worker path.",
    ]
    return ThroughputReport(
        hardware_note="local dev host; single-process benchmark",
        mock_model_mode=True,
        signed_text_gate=SIGNED_TEXT_PAGES_PER_HOUR,
        signed_ocr_gate=SIGNED_OCR_PAGES_PER_HOUR,
        samples=[sample],
        text_gate_met=text_met if iterations > 0 else None,
        ocr_gate_met=None,
        hybrid_ready_gate="not_run",
        blockers=blockers,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Optional CLI argument vector.

    Returns:
        ``2`` when Hybrid Ready throughput was not measured; ``1`` when measured
        gates miss; ``0`` only when both signed gates are proven.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20, help="Loop count")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path(".pytest_cache/phase3_throughput_report.json"),
        help="Write machine-readable report here",
    )
    args = parser.parse_args(argv)
    report = build_report(iterations=max(args.iterations, 1))
    payload = {
        **asdict(report),
        "samples": [asdict(sample) for sample in report.samples],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if report.hybrid_ready_gate == "not_run":
        return 2
    return 0 if report.text_gate_met and report.ocr_gate_met else 1


if __name__ == "__main__":
    sys.exit(main())
