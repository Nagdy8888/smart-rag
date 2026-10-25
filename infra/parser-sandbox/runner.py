"""In-container parser runner with no network and no secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from smart_rag_core.ingestion.figures.materialize import render_pdf_figures
from smart_rag_core.ingestion.parser.adapters import infer_format, parse_file
from smart_rag_core.ingestion.parser.exceptions import ParserError
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
)


def main() -> int:
    """Parse one mounted input file and write JSON result."""

    if len(sys.argv) != 2:
        print("usage: runner.py '<json-request>'", file=sys.stderr)
        return 2
    request = json.loads(sys.argv[1])
    input_path = Path(str(request["input_path"]))
    output_path = Path(str(request["output_path"]))
    content_hash = str(request["content_hash"])
    format_key = request.get("format_key")
    media_type = request.get("media_type")
    try:
        resolved = format_key or infer_format(input_path, media_type)
        result = parse_file(input_path, content_hash, resolved)
        if resolved == "pdf":
            result = render_pdf_figures(result, input_path.read_bytes())
    except ParserError as exc:
        result = ParseResult(
            disposition=ParseDisposition.FAILED,
            format=str(format_key or "unknown"),
            content_hash=content_hash,
            parser_version=PARSER_CONFIG_VERSION,
            cleaning_version=CLEANING_POLICY_VERSION,
            config_hash=ParseResult.stable_config_hash(
                PARSER_CONFIG_VERSION,
                CLEANING_POLICY_VERSION,
            ),
            coverage=CoverageAccounting(
                total_elements=0,
                text_elements=0,
                media_only_elements=0,
                removed_nodes=0,
                unsupported_regions=0,
                char_coverage_ratio=0.0,
            ),
            resource_metrics=ParserResourceMetrics(wall_seconds=0.0),
            detail=f"{exc.code}: {exc.detail}",
        )
    output_path.write_text(result.model_dump_json(), encoding="utf-8")
    # Never duplicate untrusted parser output on the Docker log/stdout path.
    return 0 if result.disposition is not ParseDisposition.FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
