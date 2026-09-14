"""Pinned identities for the isolated PDF parser bake-off."""

from __future__ import annotations

from typing import Literal

SCHEMA_VERSION = "parser-bakeoff-v1"
COMMAND_VERSION = "parser_bakeoff_cli_v1"
ANYDOC_PACKAGE_VERSION = "0.2.4"
ANYDOC_PARSER_VERSION = "anydoc_pdf_0_2_4_local"
ANYDOC_CLEANING_VERSION = "anydoc_markdown_0_2_4"
ANYDOC_OCR_MODE = "reject"
ANYDOC_SCANNED_PAGES = "openai_ocr"
ANYDOC_IMAGE = "smart-rag-parser-bakeoff:local"
ANYDOC_SANDBOX_TIMEOUT_SECONDS = 300
OPENAI_OCR_MAX_PAGES = 20
OPENAI_OCR_DPI = 150
OPENAI_OCR_TIMEOUT_SECONDS = 60
OPENAI_OCR_MAX_IMAGE_BYTES = 5_000_000
OPENAI_OCR_MAX_OUTPUT_TOKENS = 4000
OPENAI_OCR_MAX_OUTPUT_CHARS = 16_384
PAGE_OCR_PROMPT_VERSION = "parser_bakeoff_page_ocr_v1"
CURRENT_LANE = "current"
ANYDOC_LANE = "anydoc_local"
LaneId = Literal["current", "anydoc_local"]
LANE_IDS: tuple[LaneId, ...] = (CURRENT_LANE, ANYDOC_LANE)
SELECTED_PDF_RELATIVE = (
    "dataset/building-applications-with-ai-agents-designing-and-implementing-"
    "multiagent-systems-1 (1).pdf"
)
PRIVATE_ROOT = ".private-eval/parser-bakeoff"
DOCUMENT_TITLE_PREFIX = "parser-bakeoff"
BOOTSTRAP_SEED = 20260909
BOOTSTRAP_RESAMPLES = 2000
HASH_CHUNK_BYTES = 65_536
PARSE_RESULT_NAME = "parse-result.json"
CHUNK_SUMMARY_NAME = "chunk-summary.json"
INGEST_IDS_NAME = "ingest-ids.json"
GOLD_MAP_NAME = "gold-map.json"
MAPPING_REVIEW_NAME = "mapping-review.json"
RETRIEVAL_REPORT_NAME = "retrieval-report.json"
AGENT_REPORT_NAME = "agent-report.json"
NEUTRAL_CASES_NAME = "neutral-cases.json"
COMPARISON_JSON_NAME = "comparison.json"
COMPARISON_MD_NAME = "comparison.md"
CLEANUP_RECEIPT_NAME = "cleanup-receipt.json"
FORBIDDEN_SPLIT = "holdout"
ALLOWED_SPLITS = frozenset({"development", "qualification"})
FORBIDDEN_SANDBOX_ENV = frozenset(
    {
        "OPENAI_API_KEY",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_API_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "STORAGE_ADMIN_SECRET",
        "LANGSMITH_API_KEY",
        "OPERATOR_SUPABASE_DB_URL",
        "SUPABASE_DB_URL",
    }
)
