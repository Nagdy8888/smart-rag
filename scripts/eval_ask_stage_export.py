"""Export ID-only Hybrid stage diagnostics from operator checkpoints.

Reads ``run_id`` plus ``conversation_id`` from a private answers JSON.
Never prints passage, query, title, or answer text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from smart_rag_core.retrieval.profiles import RERANK_INVALID_SUBCODES

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HYBRID_FAMILIES = frozenset({"hybrid", "Hybrid"})
REQUIRED_FIELDS = (
    "source_resolution",
    "retrieval_profile_id",
    "fallback_reason",
    "rerank_fallback",
    "rerank_call_count",
    "embedding_call_count",
    "dense_ids",
    "bm25_ids",
    "term_ids",
    "fused_ids",
    "selected_ids",
    "rerank_pool_ids",
    "effective_route",
    "rerank_accounting_ok",
    "bm25_degraded_explicit",
)


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def operator_url() -> str:
    """Return the operator DSN from gitignored env files.

    Returns:
        Non-empty DSN.

    Raises:
        RuntimeError: When ``OPERATOR_SUPABASE_DB_URL`` is missing.
    """

    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        raise RuntimeError("missing_operator_url")
    return url


def export_ask_stages(
    answers: Mapping[str, Mapping[str, object]],
    *,
    postgres_url: str,
) -> dict[str, object]:
    """Join checkpoint diagnostics and ``llm_usage`` for recorded runs.

    Args:
        answers: Question id to row with ``run_id`` and ``conversation_id``.
        postgres_url: Operator DSN.

    Returns:
        Private JSON-ready mapping with per-run fields and aggregate
        unknown counts. Missing values are the string ``unknown``.
    """

    serde = JsonPlusSerializer()
    runs: dict[str, dict[str, object]] = {}
    unknown_total = 0
    accounting_ok = True
    bm25_explicit = True
    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE postgres")
        for question_id, row in answers.items():
            run_id = str(row.get("run_id") or "").strip()
            conversation_id = str(row.get("conversation_id") or "").strip()
            diagnostics = _hybrid_diagnostics(
                connection,
                serde=serde,
                conversation_id=conversation_id,
            )
            usage = _usage_kinds(connection, run_id)
            record = stage_record(diagnostics, usage)
            unknown = [name for name in REQUIRED_FIELDS if record[name] == "unknown"]
            record["unknown_fields"] = unknown
            unknown_total += len(unknown)
            if record["rerank_accounting_ok"] is not True:
                accounting_ok = False
            if not bm25_record_keeps_aggregate(record):
                bm25_explicit = False
            runs[question_id] = {
                "run_id": run_id or "unknown",
                **record,
            }
    return {
        "runs": runs,
        "unknown_required_fields": unknown_total,
        "rerank_accounting_ok": accounting_ok and unknown_total == 0,
        "bm25_degraded_explicit": bm25_explicit and unknown_total == 0,
    }


def _hybrid_diagnostics(
    connection: psycopg.Connection,
    *,
    serde: JsonPlusSerializer,
    conversation_id: str,
) -> Mapping[str, object] | None:
    """Load the latest Hybrid ``hybrid_diagnostics`` for one conversation.

    Args:
        connection: Operator session.
        serde: LangGraph JSON/msgpack serializer.
        conversation_id: Checkpoint ``thread_id``.

    Returns:
        Diagnostics mapping, or ``None`` when missing.
    """

    if not conversation_id:
        return None
    row = connection.execute(
        """
        SELECT DISTINCT ON (b.thread_id)
          b.type,
          b.blob
        FROM langgraph.checkpoint_blobs AS b
        WHERE b.channel = 'branch_results'
          AND b.thread_id = %s
        ORDER BY b.thread_id, b.version DESC
        """,
        (conversation_id,),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    payload = serde.loads_typed((str(row[0]), bytes(row[1])))
    branches: list[object] = (
        cast(list[object], payload) if isinstance(payload, list) else []
    )
    for item in branches:
        if not isinstance(item, Mapping):
            continue
        mapped = cast(Mapping[str, object], item)
        family = str(mapped.get("family") or "")
        kind = str(mapped.get("kind") or "")
        if family not in HYBRID_FAMILIES and kind != "hybrid":
            continue
        diagnostics = mapped.get("hybrid_diagnostics")
        if isinstance(diagnostics, Mapping):
            return cast(Mapping[str, object], diagnostics)
    return None


def _usage_kinds(connection: psycopg.Connection, run_id: str) -> set[str]:
    """Return ``llm_usage.usage_kind`` values for one run.

    Args:
        connection: Operator session.
        run_id: Admitted run id.

    Returns:
        Usage kinds. Empty when ``run_id`` is missing.
    """

    if not run_id:
        return set()
    try:
        UUID(run_id)
    except ValueError:
        return set()
    rows = connection.execute(
        """
        SELECT usage_kind
        FROM app.llm_usage
        WHERE run_id = %s
          AND usage_kind IN ('embedding', 'rerank')
        """,
        (run_id,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def stage_record(
    diagnostics: Mapping[str, object] | None,
    usage: set[str],
) -> dict[str, object]:
    """Build one run's measured-or-unknown stage fields.

    Args:
        diagnostics: Checkpoint Hybrid diagnostics.
        usage: ``embedding`` / ``rerank`` kinds present for the run.

    Returns:
        Stage mapping. Missing values are ``unknown``.
    """

    if diagnostics is None:
        return {name: "unknown" for name in REQUIRED_FIELDS}
    raw_fallback = str(diagnostics.get("fallback_reason") or "").strip()
    fallback = raw_fallback or "unknown"
    rerank_fallback = str(diagnostics.get("rerank_fallback") or "").strip() or "unknown"
    embedding_present = "embedding" in usage
    rerank_present = "rerank" in usage
    named_rerank_fallback = rerank_fallback not in {"", "none", "unknown"}
    if embedding_present and (rerank_present or named_rerank_fallback):
        accounting: bool | str = True
    elif not usage:
        accounting = "unknown"
    else:
        accounting = False
    bm25_explicit = bm25_explicit_flag(raw_fallback)
    dense_ids = _id_list_or_unknown(diagnostics.get("dense_ids"))
    bm25_ids = _id_list_or_unknown(diagnostics.get("bm25_ids"))
    term_ids = _id_list_or_unknown(diagnostics.get("term_ids"))
    fused_ids = _id_list_or_unknown(diagnostics.get("fused_ids"))
    retrieval_empty: bool | str
    if all(
        isinstance(item, list) for item in (dense_ids, bm25_ids, term_ids, fused_ids)
    ):
        retrieval_empty = not any((dense_ids, bm25_ids, term_ids, fused_ids))
    else:
        retrieval_empty = "unknown"
    return {
        "source_resolution": diagnostics.get("source_resolution") or "unknown",
        "retrieval_profile_id": diagnostics.get("retrieval_profile_id") or "unknown",
        "fallback_reason": fallback,
        "rerank_fallback": rerank_fallback,
        "rerank_call_count": _int_or_unknown(diagnostics.get("rerank_call_count")),
        "embedding_call_count": _int_or_unknown(
            diagnostics.get("embedding_call_count")
        ),
        "dense_ids": dense_ids,
        "bm25_ids": bm25_ids,
        "term_ids": term_ids,
        "fused_ids": fused_ids,
        "selected_ids": _id_list_or_unknown(diagnostics.get("selected_ids")),
        "rerank_pool_ids": _id_list_or_unknown(diagnostics.get("rerank_pool_ids")),
        "effective_route": diagnostics.get("effective_route") or "unknown",
        "rerank_accounting_ok": accounting,
        "bm25_degraded_explicit": bm25_explicit,
        "retrieval_empty": retrieval_empty,
        "stage_timings_ms": _timings_or_unknown(diagnostics.get("stage_timings_ms")),
        "rerank_invalid_subcode": _subcode_or_unknown(
            diagnostics.get("rerank_invalid_subcode")
        ),
        "rerank_partial": _bool_or_unknown(diagnostics.get("rerank_partial")),
        "rerank_ranked_count": _int_or_unknown(diagnostics.get("rerank_ranked_count")),
        "rerank_appended_count": _int_or_unknown(
            diagnostics.get("rerank_appended_count")
        ),
    }


def bm25_explicit_flag(raw_fallback: str) -> bool | str:
    """Classify whether one run's retrieve fallback names a BM25 outage.

    Args:
        raw_fallback: Stripped ``fallback_reason`` from diagnostics; may be
            empty.

    Returns:
        ``False`` for no degradation (``none`` or empty) and for reasons
        that can hide a BM25 outage (``term_unavailable``,
        ``dense_unavailable``). ``"unknown"`` for the literal ``unknown``.
        ``True`` for every other named reason.
    """

    if raw_fallback in {"", "none", "term_unavailable", "dense_unavailable"}:
        return False
    if raw_fallback == "unknown":
        return "unknown"
    return True


def bm25_record_keeps_aggregate(record: Mapping[str, object]) -> bool:
    """Return whether one run keeps the aggregate BM25-explicit flag true.

    A run whose ``fallback_reason`` is ``none`` had no outage to name, so
    its per-run ``False`` does not lower the promotion aggregate. Any
    other run must carry ``bm25_degraded_explicit is True``.

    Args:
        record: One ``stage_record`` result.

    Returns:
        True when the aggregate may stay true for this run.
    """

    if record.get("fallback_reason") == "none":
        return True
    return record.get("bm25_degraded_explicit") is True


def _timings_or_unknown(value: object) -> dict[str, int] | str:
    """Return non-negative integer stage timings or ``unknown``.

    Args:
        value: JSON value of ``stage_timings_ms``.

    Returns:
        String-keyed integer milliseconds, or ``unknown`` when missing or
        malformed.
    """

    if not isinstance(value, dict):
        return "unknown"
    timings: dict[str, int] = {}
    for key, item in cast(dict[object, object], value).items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            return "unknown"
        timings[str(key)] = item
    return timings


def _subcode_or_unknown(value: object) -> str:
    """Return the rerank validation sub-code, empty, or ``unknown``.

    Args:
        value: JSON value of ``rerank_invalid_subcode``.

    Returns:
        The string when it is empty or allow-listed, else ``unknown``.
    """

    if not isinstance(value, str):
        return "unknown"
    if value and value not in RERANK_INVALID_SUBCODES:
        return "unknown"
    return value


def _bool_or_unknown(value: object) -> bool | str:
    """Return a JSON boolean or ``unknown``.

    Args:
        value: JSON value.

    Returns:
        The boolean, or ``unknown`` when missing or not a boolean.
    """

    if isinstance(value, bool):
        return value
    return "unknown"


def _int_or_unknown(value: object) -> int | str:
    """Return a non-negative int or ``unknown``.

    Args:
        value: JSON value.

    Returns:
        Integer or ``unknown``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return "unknown"
    return value


def _id_list_or_unknown(value: object) -> list[str] | str:
    """Return a UUID-string list or ``unknown``.

    Args:
        value: JSON value.

    Returns:
        UUID strings, including empty lists, or ``unknown``.
    """

    if value is None:
        return "unknown"
    if not isinstance(value, list | tuple):
        return "unknown"
    items = cast(Sequence[object], value)
    ids: list[str] = []
    for item in items:
        text = str(item)
        try:
            UUID(text)
        except ValueError:
            return "unknown"
        ids.append(text)
    return ids


def main(argv: list[str] | None = None) -> int:
    """Write a private stage-export JSON for recorded Ask runs.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` when inputs or the operator DSN are missing.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if ".private-eval" not in {part.casefold() for part in args.out.resolve().parts}:
        print("blocked=out_not_private")
        return 2
    raw_obj: object = json.loads(args.answers.read_text(encoding="utf-8"))
    if not isinstance(raw_obj, dict):
        print("blocked=answers_not_object")
        return 2
    answers = {
        str(key): cast(dict[str, object], value)
        for key, value in cast(dict[object, object], raw_obj).items()
        if isinstance(value, dict)
    }
    try:
        url = operator_url()
    except RuntimeError as exc:
        print(f"blocked={exc}")
        return 2
    payload = export_ask_stages(answers, postgres_url=url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"runs={len(cast(dict[str, object], payload['runs']))}")
    print(f"unknown_required_fields={payload['unknown_required_fields']}")
    print(f"rerank_accounting_ok={payload['rerank_accounting_ok']}")
    print(f"bm25_degraded_explicit={payload['bm25_degraded_explicit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
