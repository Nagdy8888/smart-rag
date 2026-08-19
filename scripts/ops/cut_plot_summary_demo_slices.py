"""Write CMU plot-summary demo slices for Hybrid/Graph ingest.

Does not ingest files. Does not copy the 42k-line dump.
"""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.demo_corpus import cut_demo_plot_slices


def main() -> int:
    """Cut ``plot_summaries.graph-200.txt`` and ``plot_summaries.hybrid-800.txt``.

    Returns:
        Process exit code.

    Side Effects:
        Overwrites the two slice files under ``docs/datasets/MovieSummaries/``.
    """

    repo_root = Path(__file__).resolve().parents[2]
    graph_path, hybrid_path = cut_demo_plot_slices(repo_root)
    print(f"wrote {graph_path}")
    print(f"wrote {hybrid_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
