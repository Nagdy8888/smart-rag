"""Native PDF cell coordinates remain usable calculation provenance."""

import json

from smart_rag_core.tables.service import source_range_labels


def test_pdf_cell_has_exact_page_and_rectangle() -> None:
    """PDF cells retain their original rectangle rather than fake sheet cells."""
    payload = json.dumps(
        {
            "cells": [
                {
                    "format": "pdf",
                    "page_index": 114,
                    "bbox_x0": 75.6,
                    "bbox_y0": 380.467,
                    "bbox_x1": 92.637,
                    "bbox_y1": 391.132,
                }
            ]
        }
    )
    assert source_range_labels(payload, workbook="book.pdf", sheet="Table 5-1") == (
        "book.pdf!Physical PDF page 115!bbox(75.6,380.467,92.637,391.132)",
    )


def test_missing_or_invalid_pdf_coordinates_still_refuse() -> None:
    """Unlocatable PDF cells never acquire invented provenance."""
    for cell in (
        {"format": "pdf", "page_index": 1},
        {
            "format": "pdf",
            "page_index": -1,
            "bbox_x0": 1,
            "bbox_y0": 1,
            "bbox_x1": 2,
            "bbox_y1": 2,
        },
    ):
        assert (
            source_range_labels(
                json.dumps({"cells": [cell]}), workbook="book.pdf", sheet=None
            )
            == ()
        )
