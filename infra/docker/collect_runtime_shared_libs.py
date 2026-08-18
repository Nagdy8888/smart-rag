"""Copy Debian shared libraries that CPython and native wheels need at runtime.

Distroless/cc-debian13 already ships glibc and libstdc++. Official CPython
still loads libffi (ctypes), OpenSSL, compression libraries, and wheel
``.so`` dependencies from ``/usr/lib``. Copying those files without
``/var/lib/dpkg`` keeps perl-base out of the scanned runtime.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
SKIP_DIR_PREFIXES: tuple[str, ...] = ("/usr/local/", "/app/")
DISTROLESS_PROVIDED: frozenset[str] = frozenset(
    {
        "ld-linux-x86-64.so.2",
        "libBrokenLocale.so.1",
        "libanl.so.1",
        "libc.so.6",
        "libdl.so.2",
        "libgcc_s.so.1",
        "libm.so.6",
        "libpthread.so.0",
        "libresolv.so.2",
        "librt.so.1",
        "libstdc++.so.6",
        "libthread_db.so.1",
        "libutil.so.1",
        "linux-vdso.so.1",
    }
)


def is_elf(path: Path) -> bool:
    """Return whether ``path`` starts with ELF magic.

    Args:
        path: Candidate file.

    Returns:
        True when the first four bytes are ELF magic.
    """

    try:
        with path.open("rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


def iter_elf_files(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Walk roots and return ELF files and directories' nested ELF files.

    Args:
        roots: Files or directories to scan.

    Returns:
        Deduplicated ELF paths in stable order.
    """

    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        candidates: list[Path]
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [path for path in root.rglob("*") if path.is_file()]
        else:
            continue
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen or not is_elf(path):
                continue
            seen.add(resolved)
            found.append(path)
    return tuple(found)


def parse_ldd_output(text: str) -> tuple[Path, ...]:
    """Parse ``ldd`` stdout into resolved shared-library paths.

    Args:
        text: Raw ``ldd`` output.

    Returns:
        Absolute paths that ``ldd`` mapped after ``=>``, plus absolute
        loader lines. Missing libraries are omitted.
    """

    paths: list[Path] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "linux-vdso.so" in line or "not found" in line:
            continue
        if "=>" in line:
            _name, remainder = line.split("=>", 1)
            token = remainder.strip().split()[0]
            if token.startswith("/"):
                paths.append(Path(token))
            continue
        token = line.split()[0]
        if token.startswith("/"):
            paths.append(Path(token))
    return tuple(paths)


def should_copy_lib(path: Path) -> bool:
    """Return whether a resolved library belongs in the distroless extra tree.

    Args:
        path: Path ``ldd`` resolved.

    Returns:
        False for CPython ``/usr/local`` trees and libraries distroless/cc
        already ships.
    """

    posix = path.as_posix()
    if any(posix.startswith(prefix) for prefix in SKIP_DIR_PREFIXES):
        return False
    return path.name not in DISTROLESS_PROVIDED


def destination_relative(source: Path) -> Path:
    """Map a host library path onto the distroless merged ``/usr`` tree.

    Debian ``/lib`` is a symlink to ``usr/lib``. Copying a ``lib/`` directory
    onto that symlink fails with ``cannot copy to non-directory``.

    Args:
        source: Path ``ldd`` resolved.

    Returns:
        Path relative to the extra-library output root.
    """

    posix = source.as_posix()
    if posix.startswith("/lib/") and not posix.startswith("/lib64/"):
        posix = "/usr" + posix
    return Path(*Path(posix).parts[1:])


def ldd_libraries(binary: Path) -> tuple[Path, ...]:
    """Run ``ldd`` on one ELF file.

    Args:
        binary: ELF path.

    Returns:
        Resolved library paths. Empty when ``ldd`` fails.
    """

    ldd = shutil.which("ldd")
    if ldd is None:
        return ()
    completed = subprocess.run(  # noqa: S603 - fixed ldd binary, ELF paths from the builder
        [ldd, str(binary)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ()
    return parse_ldd_output(completed.stdout or "")


def copy_library(source: Path, output_root: Path) -> None:
    """Copy one library to the output tree using the soname path.

    Docker ``COPY`` flattens symlinks, so the destination is a regular file
    named as ``ldd`` displayed (for example ``libffi.so.8``).

    Args:
        source: Path ``ldd`` resolved, possibly a symlink.
        output_root: Destination root that will be copied onto distroless.

    Raises:
        OSError: If the source cannot be read or the destination cannot be
            written.
    """

    relative = destination_relative(source)
    destination = output_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.resolve(), destination, follow_symlinks=True)


def collect_runtime_shared_libs(
    *,
    roots: tuple[Path, ...],
    output_root: Path,
) -> tuple[str, ...]:
    """Collect extra shared libraries for a distroless CPython runtime.

    Args:
        roots: Trees that contain the interpreter and native wheels.
        output_root: Directory that receives the extra ``/usr/lib`` files.

    Returns:
        Sorted POSIX destination paths that were copied.

    Raises:
        ValueError: If ``output_root`` is empty.
    """

    if not str(output_root):
        raise ValueError("output_root is required")
    output_root.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    for binary in iter_elf_files(roots):
        for library in ldd_libraries(binary):
            if not should_copy_lib(library):
                continue
            relative = destination_relative(library).as_posix()
            if relative in copied:
                continue
            copy_library(library, output_root)
            copied.add(relative)
    return tuple(sorted(copied))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the collector.

    Args:
        argv: Argument list; ``sys.argv[1:]`` when omitted.

    Returns:
        Parsed namespace with ``output`` and ``root``.
    """

    parser = argparse.ArgumentParser(
        description="Copy extra shared libraries for a distroless CPython image.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination tree copied onto distroless as /",
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=[],
        help="ELF tree to scan (repeatable). Defaults to /usr/local and /app.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the collector and print how many libraries were copied.

    Args:
        argv: Argument list; ``sys.argv[1:]`` when omitted.

    Returns:
        Process exit code.
    """

    args = parse_args(argv)
    roots = tuple(args.root) or (Path("/usr/local"), Path("/app"))
    copied = collect_runtime_shared_libs(roots=roots, output_root=args.output)
    sys.stdout.write(f"copied {len(copied)} shared libraries\n")
    for path in copied:
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
