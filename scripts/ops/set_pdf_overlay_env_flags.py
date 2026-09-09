"""Upsert ignored overlay env flags. Prints key names only."""

from __future__ import annotations

from pathlib import Path


def upsert(path: Path, mapping: dict[str, str]) -> None:
    """Replace or append selected keys in one env file.

    Args:
        path: Gitignored env file.
        mapping: Keys and values to write.
    """

    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in mapping:
                out.append(f"{key}={mapping[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in mapping.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"updated={path.name}")
    print("keys=" + ",".join(mapping))


def main() -> int:
    """Update ``.env`` and ``.env.compose`` overlay flags.

    Returns:
        Process exit code.
    """

    mapping = {
        "SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED": "true",
        "LANGSMITH_EXPORT_IO": "false",
        "WORKER_GRAPH_ENABLED": "false",
    }
    for name in (".env", ".env.compose"):
        path = Path(name)
        if path.is_file():
            upsert(path, mapping)
        else:
            print(f"missing={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
