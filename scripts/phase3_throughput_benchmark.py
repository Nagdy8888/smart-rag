#!/usr/bin/env python3
"""Bounded Phase 3 ingestion throughput probe for Packet 8 exit evidence.

Measures parse→chunk→mock-embed locally and, when local Supabase + ParadeDB
are reachable, drives one synthetic version through BM25 verify + Hybrid Ready.
Mocks are limited to embedding vectors. QT-ING-001/002 are not invented.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
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
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
)
from smart_rag_core.ingestion.parser.types import ParseResult

from tests.contract.hybrid_ready_driver import drive_hybrid_ready, parse_local_bytes
from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_host_reachable,
    resolve_supabase_db_url,
    try_connect,
)
from tests.fixtures.parser import build_ocr_scanned_pdf, build_pdf_text_fixture

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
    projection_lag_seconds: float | None
    queue_fairness_note: str
    resource_peaks_note: str
    mock_cost_usd: float
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
        pages += max(parsed.resource_metrics.pages_processed, 1)
    elapsed = max(time.perf_counter() - start, 1e-9)
    return ThroughputSample(
        stage="parse_chunk_mock_embed_text_pdf",
        iterations=iterations,
        pages_processed=pages,
        elapsed_seconds=elapsed,
        pages_per_hour=pages / elapsed * 3600.0,
    )


def _ocr_text_extracted(parsed: object) -> bool:
    """Return whether OCR produced searchable text rather than media-only figures."""

    elements = getattr(parsed, "elements", ())
    for element in elements:
        text = getattr(element, "text", None)
        metadata = getattr(element, "metadata", {}) or {}
        if text and not metadata.get("ocr_unavailable"):
            return True
    return False


def _measure_ocr_pipeline(
    *, iterations: int, tmp_dir: Path
) -> tuple[ThroughputSample, bool, ParseResult | None, str]:
    """Run OCR parse on the image-only scanned PDF fixture.

    Uses the parser sandbox image when present so Tesseract runs in the
    product isolation path; otherwise falls back to in-process pytesseract.
    """

    payload, digest = build_ocr_scanned_pdf()
    path = tmp_dir / "bench_ocr.pdf"
    path.write_bytes(payload)
    sandbox = ParserSandboxLauncher(
        config=SandboxLaunchConfig(image="smart-rag-parser-sandbox:local")
    )
    image_exists = False
    if sandbox.config.use_docker:
        docker = shutil.which("docker")
        inspect = subprocess.run(  # noqa: S603 - fixed local docker inspect argv
            [docker or "docker", "image", "inspect", "smart-rag-parser-sandbox:local"],
            capture_output=True,
            check=False,
        )
        image_exists = inspect.returncode == 0
    use_docker = sandbox.config.use_docker and image_exists
    backend = "sandbox" if use_docker else "inprocess"
    start = time.perf_counter()
    pages = 0
    ocr_text = False
    last_parsed: ParseResult | None = None
    for _ in range(iterations):
        if use_docker:
            parsed = sandbox.run(
                payload=payload,
                content_hash=digest,
                filename="bench_ocr.pdf",
                format_key="pdf",
            )
        else:
            parsed = parse_file(path, digest, "pdf")
        last_parsed = parsed
        pages += max(
            parsed.resource_metrics.ocr_pages,
            parsed.resource_metrics.pages_processed,
            1,
        )
        ocr_text = ocr_text or _ocr_text_extracted(parsed)
        chunk_parse_result(
            parsed,
            document_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
            version_id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
        )
    elapsed = max(time.perf_counter() - start, 1e-9)
    sample = ThroughputSample(
        stage=f"parse_chunk_ocr_scanned_pdf_{backend}",
        iterations=iterations,
        pages_processed=pages,
        elapsed_seconds=elapsed,
        pages_per_hour=pages / elapsed * 3600.0,
    )
    return sample, ocr_text, last_parsed, backend


def _drive_one_hybrid_ready(
    *,
    postgres_url: str,
    parade_url: str,
    parse_result: ParseResult,
    title: str,
    filename: str,
) -> tuple[bool, str]:
    """Drive one parse result to verified Hybrid Ready.

    Returns:
        ``(passed, detail)``.
    """

    try:
        result = drive_hybrid_ready(
            supabase_url=postgres_url,
            parade_url=parade_url,
            parse_result=parse_result,
            title=title,
            filename=filename,
        )
    except Exception as exc:
        return False, f"{exc.__class__.__name__}:{exc}"
    if result.hybrid_ready:
        return True, "ok"
    return False, f"{result.status}/{result.detail}"


def _drive_hybrid_ready(
    *,
    ocr_parsed: ParseResult | None,
) -> tuple[bool, bool | None, float | None, str]:
    """Drive synthetic text and optional OCR fixtures to verified Hybrid Ready.

    Returns:
        ``(text_passed, ocr_passed_or_none, lag_seconds, detail)``.
    """

    postgres_url = resolve_supabase_db_url()
    parade_url = packet8_paradedb_url()
    if try_connect(postgres_url) is None or not paradedb_host_reachable() or parade_url is None:
        return False, None, None, "stack_unavailable"
    text_payload, _text_digest = build_pdf_text_fixture()
    text_parsed = parse_local_bytes(text_payload, filename="bench.pdf", format_key="pdf")
    started = time.perf_counter()
    text_ok, text_detail = _drive_one_hybrid_ready(
        postgres_url=postgres_url,
        parade_url=parade_url,
        parse_result=text_parsed,
        title=f"throughput-text-{uuid.uuid4()}",
        filename="bench.pdf",
    )
    ocr_ok: bool | None = None
    ocr_detail = "skipped_no_ocr_text"
    if ocr_parsed is not None:
        ocr_ok, ocr_detail = _drive_one_hybrid_ready(
            postgres_url=postgres_url,
            parade_url=parade_url,
            parse_result=ocr_parsed,
            title=f"throughput-ocr-{uuid.uuid4()}",
            filename="bench_ocr.pdf",
        )
    lag = max(time.perf_counter() - started, 1e-9)
    detail = f"text={text_detail};ocr={ocr_detail}"
    return text_ok, ocr_ok, lag, detail


def build_report(*, iterations: int) -> ThroughputReport:
    """Construct an honest throughput report with gate posture."""

    tmp_dir = Path(".pytest_cache/phase3_throughput")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    text_sample = _measure_text_pipeline(iterations=iterations, tmp_dir=tmp_dir)
    ocr_sample, ocr_text, ocr_parsed, ocr_backend = _measure_ocr_pipeline(
        iterations=max(iterations // 2, 1), tmp_dir=tmp_dir
    )
    hybrid_ocr_parsed = ocr_parsed if ocr_text else None
    text_ok, ocr_ok, lag, hybrid_detail = _drive_hybrid_ready(
        ocr_parsed=hybrid_ocr_parsed
    )
    blockers: list[str] = []
    if hybrid_detail == "stack_unavailable":
        blockers.append(
            "End-to-end Hybrid Ready not measured: local Supabase/ParadeDB unreachable."
        )
        hybrid_gate = "not_run"
        text_met = None
        ocr_met = None
    elif not text_ok:
        blockers.append(f"Text Hybrid Ready driver failed ({hybrid_detail}).")
        hybrid_gate = "failed"
        text_met = False
        ocr_met = False
    else:
        hybrid_gate = "passed" if ocr_ok is not False else "partial"
        text_met = text_sample.pages_per_hour >= SIGNED_TEXT_PAGES_PER_HOUR
        ocr_met = (
            ocr_ok is True
            and ocr_text
            and ocr_sample.pages_per_hour >= SIGNED_OCR_PAGES_PER_HOUR
        )
        if not ocr_text:
            detail = ""
            if ocr_parsed is not None:
                detail = f" disposition={ocr_parsed.disposition} detail={ocr_parsed.detail[:240]}"
            blockers.append(
                "QT-ING-002 not counted: OCR produced no searchable text "
                f"(backend={ocr_backend}; Tesseract missing or media-only).{detail}"
            )
        elif ocr_ok is False:
            blockers.append(f"OCR Hybrid Ready driver failed ({hybrid_detail}).")
        if not text_met:
            blockers.append(
                f"QT-ING-001 missed: {text_sample.pages_per_hour:.1f} < {SIGNED_TEXT_PAGES_PER_HOUR}"
            )
        if ocr_text and ocr_ok is True and not ocr_met:
            blockers.append(
                f"QT-ING-002 missed: {ocr_sample.pages_per_hour:.1f} < {SIGNED_OCR_PAGES_PER_HOUR}"
            )
    return ThroughputReport(
        hardware_note="local dev host; mock embeddings only",
        mock_model_mode=True,
        signed_text_gate=SIGNED_TEXT_PAGES_PER_HOUR,
        signed_ocr_gate=SIGNED_OCR_PAGES_PER_HOUR,
        samples=[text_sample, ocr_sample],
        text_gate_met=text_met,
        ocr_gate_met=ocr_met,
        hybrid_ready_gate=hybrid_gate,
        projection_lag_seconds=lag,
        queue_fairness_note="single-worker synthetic job; fairness not load-tested",
        resource_peaks_note="not sampled; Phase 9 launch-hardware remeasure required",
        mock_cost_usd=0.0,
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
