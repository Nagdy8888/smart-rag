"""CMU plot-summary demo slices: 200 Graph plots and 800 Hybrid-only plots.

Do not ingest ``plot_summaries.txt`` whole. Graph indexes an entire version.
Split so LightRAG never sees the Hybrid-only file.
"""

from __future__ import annotations

from pathlib import Path

GRAPH_SLICE_FILENAME = "plot_summaries.graph-200.txt"
HYBRID_SLICE_FILENAME = "plot_summaries.hybrid-800.txt"
SOURCE_FILENAME = "plot_summaries.txt"

GRAPH_SLICE_LINE_COUNT = 200
HYBRID_SLICE_LINE_COUNT = 800
# 1-indexed inclusive ranges in the source dump.
GRAPH_SLICE_START_LINE = 1
HYBRID_SLICE_START_LINE = 201


class DemoPlotSliceError(ValueError):
    """Raised when the source dump cannot yield the demo slices."""


def movie_summaries_dir(repo_root: Path) -> Path:
    """Return the committed MovieSummaries dataset directory.

    Args:
        repo_root: Repository root.

    Returns:
        ``docs/datasets/MovieSummaries``.
    """

    return repo_root / "docs" / "datasets" / "MovieSummaries"


def cut_line_range(
    lines: tuple[str, ...],
    *,
    start_line: int,
    count: int,
) -> tuple[str, ...]:
    """Return ``count`` source lines starting at 1-indexed ``start_line``.

    Args:
        lines: Full source lines without trailing newlines stripped of CR.
        start_line: 1-indexed first line to include.
        count: Number of lines to take.

    Returns:
        Slice lines, still without a trailing newline on each item.

    Raises:
        DemoPlotSliceError: If the range is empty, overlaps nothing, or the
            dump is too short.
    """

    if start_line < 1 or count < 1:
        raise DemoPlotSliceError("demo_plot_slice_range_invalid")
    start = start_line - 1
    end = start + count
    if end > len(lines):
        raise DemoPlotSliceError("demo_plot_source_too_short")
    sliced = lines[start:end]
    if len(sliced) != count:
        raise DemoPlotSliceError("demo_plot_slice_count_mismatch")
    if any(not item.strip() for item in sliced):
        raise DemoPlotSliceError("demo_plot_slice_blank_line")
    return sliced


def load_source_lines(source_path: Path) -> tuple[str, ...]:
    """Load plot dump lines with newlines stripped.

    Args:
        source_path: ``plot_summaries.txt``.

    Returns:
        One entry per non-empty-preserving line (blank lines still counted).

    Raises:
        DemoPlotSliceError: If the file is missing.
    """

    if not source_path.is_file():
        raise DemoPlotSliceError("demo_plot_source_missing")
    raw = source_path.read_text(encoding="utf-8")
    return tuple(line.rstrip("\r") for line in raw.splitlines())


def write_slice_file(path: Path, lines: tuple[str, ...]) -> None:
    """Write one demo slice as a single ``.txt`` upload.

    Args:
        path: Destination path.
        lines: Plot lines.

    Side Effects:
        Overwrites ``path`` with newline-terminated UTF-8 text.
    """

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def cut_demo_plot_slices(repo_root: Path) -> tuple[Path, Path]:
    """Cut graph-200 and hybrid-800 files from the CMU dump.

    Args:
        repo_root: Repository root.

    Returns:
        ``(graph_200_path, hybrid_800_path)``.

    Raises:
        DemoPlotSliceError: If the source is missing or too short.

    Side Effects:
        Writes both slice files under ``docs/datasets/MovieSummaries/``.
    """

    dataset = movie_summaries_dir(repo_root)
    source = dataset / SOURCE_FILENAME
    lines = load_source_lines(source)
    graph_lines = cut_line_range(
        lines,
        start_line=GRAPH_SLICE_START_LINE,
        count=GRAPH_SLICE_LINE_COUNT,
    )
    hybrid_lines = cut_line_range(
        lines,
        start_line=HYBRID_SLICE_START_LINE,
        count=HYBRID_SLICE_LINE_COUNT,
    )
    graph_ids = {item.split("\t", 1)[0] for item in graph_lines}
    hybrid_ids = {item.split("\t", 1)[0] for item in hybrid_lines}
    if graph_ids & hybrid_ids:
        raise DemoPlotSliceError("demo_plot_slices_overlap")
    graph_path = dataset / GRAPH_SLICE_FILENAME
    hybrid_path = dataset / HYBRID_SLICE_FILENAME
    write_slice_file(graph_path, graph_lines)
    write_slice_file(hybrid_path, hybrid_lines)
    return graph_path, hybrid_path
