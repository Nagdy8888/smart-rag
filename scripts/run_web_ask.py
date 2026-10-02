"""Live Ask Web regression using environment credentials.

Private gold stays under gitignored ``.private-eval/``. Each question uses a
fresh conversation with ``search_scope=web``. Passwords and answer bodies are
never printed to stdout; full answers are written only to the private
``--answers-out`` path.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
    load_ask_regression_credentials,
)
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES  # noqa: E402

from scripts.run_company_ask import (  # noqa: E402
    _auth_headers,
    _create_conversation,
    _credentials_environ,
    _json_mapping,
    _login,
    _read_sse,
)

_RUN_TIMEOUT_S = 125.0
_SEARCH_SCOPE = "web"
_CLIENT_VERSION = "0.1.0"


def main(argv: list[str] | None = None) -> int:
    """Run one Web Ask pass over a private gold file.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` when the summary was written. ``2`` on config/readiness failure.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Ask each private gold question with search_scope=web and score "
            "required phrases."
        )
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--credentials",
        type=Path,
        default=REPO / ".private-eval" / "eval-credentials.json",
    )
    parser.add_argument("--answers-out", type=Path, default=None)
    parser.add_argument("--progress", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        environ = _credentials_environ(args.credentials)
        creds = load_ask_regression_credentials(environ)
        questions = _load_web_gold(args.gold)
    except (AskRegressionConfigError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"blocked={exc}", file=sys.stderr)
        return 2
    ready = httpx.get(f"{creds.base_url}/health/ready", timeout=60.0)
    ready_payload: object = ready.json() if ready.status_code == 200 else {}
    body = _json_mapping(ready_payload)
    if body.get("query_ready") is not True:
        print("blocked=not_query_ready", file=sys.stderr)
        return 2
    meta = httpx.get(f"{creds.base_url}/api/meta", timeout=30.0)
    meta_body = _json_mapping(meta.json() if meta.status_code == 200 else {})
    if meta_body.get("web_search_enabled") is not True:
        print("blocked=web_search_disabled", file=sys.stderr)
        return 2

    answers: dict[str, dict[str, object]] = {}
    rows: list[dict[str, object]] = []
    started = time.monotonic()
    with httpx.Client(timeout=_RUN_TIMEOUT_S) as client:
        token = _login(client, environ)
        for index, question in enumerate(questions, start=1):
            qid = str(question["id"])
            prompt = str(question["prompt"])
            print(f"ask {index}/{len(questions)} id={qid}", flush=True)
            try:
                conversation_id = _create_conversation(
                    client, creds.base_url, token
                )
                streamed = _ask_web_one(
                    client,
                    base_url=creds.base_url,
                    token=token,
                    conversation_id=conversation_id,
                    question=prompt,
                )
            except Exception as exc:  # noqa: BLE001 - capture and continue
                streamed = {
                    "http_status": 0,
                    "answer": "",
                    "terminal": "error",
                    "limitation": type(exc).__name__[:64],
                    "origin": "",
                    "run_id": "",
                    "error_code": type(exc).__name__[:64],
                    "stages": {},
                }
            answer_text = str(streamed.get("answer") or "")
            phrase_hits = _score_phrases(answer_text, question["facts"])
            row = {
                "id": qid,
                "kind": question.get("kind"),
                "http_status": streamed.get("http_status"),
                "terminal": streamed.get("terminal"),
                "limitation": streamed.get("limitation"),
                "error_code": streamed.get("error_code"),
                "origin": streamed.get("origin"),
                "run_id": streamed.get("run_id"),
                "phrase_hit_count": phrase_hits["hit_count"],
                "phrase_required_count": phrase_hits["required_count"],
                "phrase_pass": phrase_hits["pass"],
                "missed_fact_ids": phrase_hits["missed_fact_ids"],
                "answer_chars": len(answer_text),
                "has_web_citations": bool(streamed.get("has_web_citations")),
                "timing": streamed.get("timing"),
            }
            rows.append(row)
            answers[qid] = {
                "prompt": prompt,
                "answer": answer_text,
                "terminal": streamed.get("terminal"),
                "limitation": streamed.get("limitation"),
                "error_code": streamed.get("error_code"),
                "origin": streamed.get("origin"),
                "run_id": streamed.get("run_id"),
                "http_status": streamed.get("http_status"),
                "phrase_pass": phrase_hits["pass"],
                "missed_fact_ids": phrase_hits["missed_fact_ids"],
                "has_web_citations": bool(streamed.get("has_web_citations")),
            }
            if args.progress is not None:
                args.progress.write_text(
                    json.dumps({"completed": index, "rows": rows}, indent=2),
                    encoding="utf-8",
                )

    passed = sum(1 for row in rows if row.get("phrase_pass") is True)
    failed_rows = [row for row in rows if row.get("phrase_pass") is not True]
    summary = {
        "search_scope": _SEARCH_SCOPE,
        "base_url": creds.base_url,
        "question_count": len(rows),
        "phrase_pass_count": passed,
        "phrase_fail_count": len(failed_rows),
        "wall_seconds": round(time.monotonic() - started, 3),
        "client_version": _CLIENT_VERSION,
        "rows": rows,
        "failures": [
            {
                "id": row["id"],
                "terminal": row.get("terminal"),
                "limitation": row.get("limitation"),
                "error_code": row.get("error_code"),
                "http_status": row.get("http_status"),
                "origin": row.get("origin"),
                "missed_fact_ids": row.get("missed_fact_ids"),
                "has_web_citations": row.get("has_web_citations"),
                "answer_chars": row.get("answer_chars"),
            }
            for row in failed_rows
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.answers_out is not None:
        args.answers_out.parent.mkdir(parents=True, exist_ok=True)
        args.answers_out.write_text(json.dumps(answers, indent=2), encoding="utf-8")
    print(
        f"done questions={len(rows)} phrase_pass={passed} "
        f"phrase_fail={len(failed_rows)} out={args.out}",
        flush=True,
    )
    return 0


def _load_web_gold(path: Path) -> list[dict[str, object]]:
    """Load the private Web gold list.

    Args:
        path: JSON array under ``.private-eval/``.

    Returns:
        Question objects with ``id``, ``prompt``, and ``facts``.

    Raises:
        ValueError: If the gold shape is invalid.
        AskRegressionConfigError: If the path is not private.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError("web gold must live under .private-eval")
    payload: object = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("web gold must be a non-empty JSON array")
    questions: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("web gold item must be an object")
        typed = cast(dict[str, object], item)
        qid = str(typed.get("id") or "").strip()
        prompt = str(typed.get("prompt") or "").strip()
        facts = typed.get("facts")
        if not qid or not prompt or not isinstance(facts, list) or not facts:
            raise ValueError(f"invalid web gold item id={qid or '?'}")
        questions.append(typed)
    return questions


def _score_phrases(
    answer: str, facts: object
) -> dict[str, object]:
    """Score whether each fact has at least one canonical phrase in the answer.

    Args:
        answer: Model answer text.
        facts: Gold fact list.

    Returns:
        Hit counts, pass flag, and missed fact ids.
    """

    haystack = answer.casefold()
    required = 0
    hits = 0
    missed: list[str] = []
    if not isinstance(facts, list):
        return {
            "required_count": 0,
            "hit_count": 0,
            "pass": False,
            "missed_fact_ids": ["invalid_facts"],
        }
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        typed = cast(dict[str, object], fact)
        fact_id = str(typed.get("id") or "fact")
        canonical = typed.get("canonical")
        if not isinstance(canonical, list) or not canonical:
            continue
        required += 1
        phrases = [str(item) for item in cast(Sequence[object], canonical)]
        if any(phrase and phrase.casefold() in haystack for phrase in phrases):
            hits += 1
        else:
            missed.append(fact_id)
    return {
        "required_count": required,
        "hit_count": hits,
        "pass": required > 0 and hits == required,
        "missed_fact_ids": missed,
    }


def _ask_web_one(
    client: httpx.Client,
    *,
    base_url: str,
    token: str,
    conversation_id: str,
    question: str,
) -> dict[str, object]:
    """Admit one Web question and wait for the SSE terminal.

    Args:
        client: HTTP client.
        base_url: Ask origin.
        token: Bearer token.
        conversation_id: Fresh conversation.
        question: User question.

    Returns:
        Streamed answer fields plus timing and citation flags.
    """

    idempotency = str(uuid4())
    ask_started = time.monotonic()
    for _attempt in range(4):
        post_started = time.monotonic()
        admit = client.post(
            f"{base_url}/conversations/{conversation_id}/messages",
            headers=_auth_headers(token, paid=True, idempotency=idempotency),
            json={
                "message": question,
                "idempotency_key": idempotency,
                "search_scope": _SEARCH_SCOPE,
            },
            timeout=60.0,
        )
        if admit.status_code == 429:
            retry_after = float(admit.headers.get("Retry-After") or 60)
            time.sleep(min(retry_after, 90.0))
            continue
        if admit.status_code >= 400:
            detail = ""
            try:
                payload = _json_mapping(admit.json())
                detail = str(payload.get("detail") or "")[:128]
            except Exception:  # noqa: BLE001 - best-effort detail only
                detail = admit.text[:128]
            return {
                "http_status": admit.status_code,
                "answer": "",
                "terminal": "error",
                "limitation": detail or f"http_{admit.status_code}",
                "error_code": detail or f"http_{admit.status_code}",
                "origin": "",
                "run_id": "",
                "has_web_citations": False,
                "stages": {},
            }
        post_seconds = round(time.monotonic() - post_started, 3)
        admit_body = _json_mapping(admit.json())
        run_id = str(admit_body.get("run_id") or "")
        streamed = _read_sse(client, base_url, token, run_id)
        streamed["http_status"] = admit.status_code
        streamed["run_id"] = run_id
        streamed["error_code"] = str(
            streamed.get("limitation") or streamed.get("terminal") or ""
        )[:64]
        citation_count = streamed.get("citation_count")
        streamed["has_web_citations"] = (
            isinstance(citation_count, int) and citation_count > 0
        ) or _has_web_citations(streamed)
        streamed["timing"] = {
            "post_seconds": post_seconds,
            "first_frame_seconds": streamed.pop("first_frame_seconds", None),
            "sse_seconds": streamed.pop("sse_seconds", None),
            "wall_seconds": round(time.monotonic() - ask_started, 3),
        }
        return streamed
    return {
        "http_status": 429,
        "answer": "",
        "terminal": "error",
        "limitation": "rate_limited",
        "error_code": "rate_limited",
        "origin": "",
        "run_id": "",
        "has_web_citations": False,
        "stages": {},
    }


def _has_web_citations(streamed: Mapping[str, object]) -> bool:
    """Return whether the streamed payload reports any web citations.

    Args:
        streamed: SSE aggregation dict from ``_read_sse``.

    Returns:
        True when at least one web citation id or count is present.
    """

    if streamed.get("web_citation_count"):
        return True
    citations = streamed.get("web_citations")
    if isinstance(citations, list) and citations:
        return True
    stages = streamed.get("stages")
    if isinstance(stages, Mapping) and stages.get("web_citation_count"):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
