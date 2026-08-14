"""No-network parser sandbox contracts and format adapters.

This package init must stay importable inside ``smart-rag-parser-sandbox``
without governance, JWKS, or database dependencies. Import ``ParserService``
from ``smart_rag_core.ingestion.parser.service`` in worker/agent code.
"""

from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ElementKind,
    ParseDisposition,
    ParseResult,
    TypedElement,
)

__all__ = [
    "CLEANING_POLICY_VERSION",
    "PARSER_CONFIG_VERSION",
    "CoverageAccounting",
    "ElementKind",
    "ParseDisposition",
    "ParseResult",
    "TypedElement",
]
