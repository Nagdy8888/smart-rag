"""In-container AnyDoc runner. Emits ParseResult JSON only; never prints source text."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from smart_rag_core.evaluation.parser_bakeoff.anydoc import (  # noqa: E402
    anydoc_config_extra,
    convert_with_anydoc,
    failed_lane_result,
    map_anydoc_exception,
    parse_anydoc_markdown_bytes,
)
from smart_rag_core.evaluation.parser_bakeoff.constants import (  # noqa: E402
    ANYDOC_CLEANING_VERSION,
    ANYDOC_PARSER_VERSION,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError  # noqa: E402
from smart_rag_core.ingestion.parser.types import ParseDisposition, ParseResult  # noqa: E402


def _failed(content_hash: str, code: str) -> ParseResult:
    """Build a zero-element AnyDoc failure.

    Args:
        content_hash: Expected PDF SHA-256.
        code: Sanitized failure code.

    Returns:
        Failed parse result.
    """

    return failed_lane_result(
        content_hash=content_hash,
        parser_version=ANYDOC_PARSER_VERSION,
        cleaning_version=ANYDOC_CLEANING_VERSION,
        format_key="pdf",
        code=code,
        extra=anydoc_config_extra(),
    )


def main() -> int:
    """Convert one mounted PDF with local AnyDoc and write JSON.

    Returns:
        ``0`` on a non-failed disposition, otherwise ``1``.
    """

    if len(sys.argv) != 2:
        print("usage: runner.py '<json-request>'", file=sys.stderr)
        return 2
    request = json.loads(sys.argv[1])
    input_path = Path(str(request["input_path"]))
    output_path = Path(str(request["output_path"]))
    content_hash = str(request["content_hash"])
    payload = input_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != content_hash:
        result = _failed(content_hash, "hash_mismatch")
        output_path.write_text(result.model_dump_json(), encoding="utf-8")
        print(f"disposition={result.disposition.value} failure_code=hash_mismatch")
        return 1
    try:
        markdown = convert_with_anydoc(input_path)
        if not markdown.strip():
            result = _failed(content_hash, "malformed")
        else:
            result = parse_anydoc_markdown_bytes(markdown, content_hash=content_hash)
    except BakeoffError as exc:
        result = _failed(content_hash, exc.code)
    except Exception as exc:
        result = _failed(content_hash, map_anydoc_exception(exc))
    output_path.write_text(result.model_dump_json(), encoding="utf-8")
    print(
        f"disposition={result.disposition.value} "
        f"elements={len(result.elements)} "
        f"parser_version={result.parser_version}"
    )
    return 0 if result.disposition is not ParseDisposition.FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
