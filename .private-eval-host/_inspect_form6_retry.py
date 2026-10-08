"""Inspect form-6 retry answers for gold needles and trailing junk."""

from __future__ import annotations

import html
import json
from pathlib import Path


def main() -> None:
    """Print compact diagnostics for each retry answer."""

    answers = json.loads(
        Path(".private-eval/code-table-form-6-retry-answers.json").read_text(
            encoding="utf-8"
        )
    )
    needles = (
        "# --",
        "call_model",
        "Table 2-1.",
        "Llama 3.1 Instruct Turbo",
        "Gemma 2",
        "72.1",
        "Langfuse",
        "SigNoz",
        "A2A Protocol",
        "Hallucination rates",
        "YOUR_WOLFRAM_ALPHA_APP_ID",
        "Cancel an order that hasn't shipped.",
    )
    for qid in ("ct01", "ct05", "ct13", "ct14", "ct15", "ct16"):
        row = answers[qid]
        text = html.unescape(str(row.get("answer_text") or ""))
        print("=" * 72)
        print(
            f"{qid} status={row.get('status')} len={len(text)} pipes={text.count('|')}"
        )
        for needle in needles:
            if needle in text:
                print(f"  HIT {needle!r}")
        head = text[:300].replace("\n", " / ")
        tail = text[-200:].replace("\n", " / ") if len(text) > 300 else ""
        print(f"  HEAD {head}")
        if tail:
            print(f"  TAIL {tail}")


if __name__ == "__main__":
    main()
