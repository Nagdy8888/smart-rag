"""Seal Phase 4 dataset manifests without exposing holdout labels."""

from __future__ import annotations

from smart_rag_core.evaluation.seal import seal_corpus


def main() -> int:
    """Write frozen manifests, identifier rules, and term-coverage hashes.

    Returns:
        ``0`` when sealing succeeds.

    Side Effects:
        Writes files under ``tests/fixtures/evaluation/phase4/``.
    """

    hashes = seal_corpus()
    for name, digest in sorted(hashes.items()):
        print(f"{name}={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
