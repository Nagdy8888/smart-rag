"""Unit tests for distroless CPython extra-library collection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = REPO_ROOT / "infra" / "docker" / "collect_runtime_shared_libs.py"


def _load_collector():
    """Load the collector module from its infra path.

    Returns:
        Loaded module.

    Raises:
        AssertionError: If the collector file cannot be imported.
    """

    spec = importlib.util.spec_from_file_location(
        "collect_runtime_shared_libs",
        COLLECTOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_ldd_output_skips_vdso_and_missing() -> None:
    """Resolved ldd paths are kept; vdso and missing rows are dropped."""

    module = _load_collector()
    text = """
        linux-vdso.so.1 (0x00007ffe8)
        libpython3.11.so.1.0 => /usr/local/lib/libpython3.11.so.1.0 (0x1)
        libffi.so.8 => /usr/lib/x86_64-linux-gnu/libffi.so.8 (0x2)
        libmissing.so.1 => not found
        /lib64/ld-linux-x86-64.so.2 (0x3)
    """
    parsed = [path.as_posix() for path in module.parse_ldd_output(text)]
    assert parsed == [
        "/usr/local/lib/libpython3.11.so.1.0",
        "/usr/lib/x86_64-linux-gnu/libffi.so.8",
        "/lib64/ld-linux-x86-64.so.2",
    ]


def test_should_copy_lib_skips_cpython_and_glibc() -> None:
    """CPython /usr/local trees and distroless glibc names are not copied."""

    module = _load_collector()
    assert module.should_copy_lib(Path("/usr/local/lib/libpython3.11.so.1.0")) is False
    assert module.should_copy_lib(Path("/lib/x86_64-linux-gnu/libc.so.6")) is False
    assert module.should_copy_lib(Path("/usr/lib/x86_64-linux-gnu/libffi.so.8")) is True
    assert (
        module.should_copy_lib(Path("/app/.venv/lib/python3.11/site-packages/x.so"))
        is False
    )


def test_destination_relative_merges_lib_into_usr() -> None:
    """Debian /lib paths are stored under usr/lib so COPY does not hit a symlink."""

    module = _load_collector()
    merged = module.destination_relative(Path("/lib/x86_64-linux-gnu/libffi.so.8"))
    assert merged.as_posix() == "usr/lib/x86_64-linux-gnu/libffi.so.8"
    already = module.destination_relative(
        Path("/usr/lib/x86_64-linux-gnu/libexpat.so.1")
    )
    assert already.as_posix() == "usr/lib/x86_64-linux-gnu/libexpat.so.1"
