# P06-23 — PDF heading extraction (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Conservative PDF heading classification for structure-aware chunking. PDF
parser version is `parser_v1_pdf_headings_v2`. Other formats stay `parser_v1`.
`get_text("text")` remains scanned/repeated-line detection. Structured
`get_text("dict")` emits per-line blocks so titles are not absorbed into body
copy; consecutive paragraph lines then merge so chunking can fill the
200–400 token band. Headings require a size jump above the page median.
Same-size bold labels stay paragraphs. Encrypted PDFs still fail closed.

Requirement: short standalone large titles become headings; bold body
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
| Host worker + rebuilt `smart-rag-parser-sandbox:local` ingest | `terminal_status=graph_ineligible` |

Proven: fixture title `Chapter One Title` is a heading and appears in
`section_path`; repeated `HEADER`/`FOOTER` removed; bold body stays
paragraph; mixed-script classifier unit; encrypted fail-closed; page labels
unchanged. Same-size bold short labels stay paragraphs. Consecutive body lines
merge.

Live Graph-disabled reingest of content hash
`72cdfc0f74bb1f60e0b61e950da06683e2db0aa04e90a59bdf271fcedfecf1f1`
(host worker; Compose worker cannot launch Docker):

| Parse | Parser version | Chunks | Distinct `section_path` | Result |
| --- | --- | ---: | ---: | --- |
| Stale sandbox | `parser_v1` | 641 | 0 | `graph_ineligible` |
| Headings v1 (per-line + same-size bold) | `parser_v1_pdf_headings_v1` | 3555 | n/a | `embedding_batch_over_limit` (2048) |
| Headings v2 | `parser_v1_pdf_headings_v2` | 1045 | 274 | `graph_ineligible`, `content_class=real_company`, graph flags false |

Host in-process count before the v2 ingest: 288 heading elements, 563
paragraphs, 1044 search representatives (under the 2048 embed cap). Live
chunks all carry a non-empty `section_path`. Do not reuse the v1 or stale
sandbox chunk IDs.

Unverified: human reseal of labels; hosted
`list_authorized_eval_passages` (function absent on the managed database).

Rollback: restore `parser_v1` for PDF and prior `get_text("blocks")` path.

Handoff: Packet 24 owns ranked-ID channel diagnostics. Freeze, Combined +10pp,
and holdout remain later operator gates. Resume historical Packet 10 only
after overlay acceptance.
