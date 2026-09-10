# P06-23 — PDF heading extraction (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Conservative PDF heading classification for structure-aware chunking. PDF
parser version is `parser_v1_pdf_headings_v1`. Other formats stay `parser_v1`.
`get_text("text")` remains scanned/repeated-line detection. Structured
`get_text("dict")` emits per-line blocks so titles are not absorbed into body
copy. Bold uses flags bit 4. Encrypted PDFs still fail closed.

Requirement: short standalone large/bold titles become headings; bold body
sentences stay paragraphs; repeated headers are removed.

Files:

- [`packages/core/src/smart_rag_core/ingestion/parser/adapters/pdf_adapter.py`](../../../packages/core/src/smart_rag_core/ingestion/parser/adapters/pdf_adapter.py)
- [`packages/core/src/smart_rag_core/ingestion/parser/helpers.py`](../../../packages/core/src/smart_rag_core/ingestion/parser/helpers.py)
- [`packages/core/src/smart_rag_core/ingestion/parser/limits.py`](../../../packages/core/src/smart_rag_core/ingestion/parser/limits.py)
- [`tests/unit/test_pdf_heading_extraction.py`](../../../tests/unit/test_pdf_heading_extraction.py)
- [`tests/fixtures/parser/__init__.py`](../../../tests/fixtures/parser/__init__.py)
- Chunking/ingestion limit docs

Verification:

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_pdf_heading_extraction.py tests/unit/test_pdf_page_labels.py tests/unit/test_parser_adapters.py -q` | 0 |

Proven: fixture title `Chapter One Title` is a heading and appears in
`section_path`; repeated `HEADER`/`FOOTER` removed; bold body stays
paragraph; mixed-script classifier unit; encrypted fail-closed; page labels
unchanged.

Unverified: live reingest of the private PDF as a new Graph-disabled version.
Heading counts on the operator corpus.

Rollback: restore `parser_v1` for PDF and prior `get_text("blocks")` path.

Handoff: Packet 24 owns ranked-ID channel diagnostics. Live reingest remains
operator-owned.
