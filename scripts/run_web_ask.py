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
            streamed: dict[str, object]
            try:
                conversation_id = _create_conversation(client, creds.base_url, token)
                streamed = _ask_web_one(
                    client,
                    base_url=creds.base_url,
                    token=token,
                    conversation_id=conversation_id,
                    question=prompt,
                )
            except Exception as exc:
                empty_stages: dict[str, object] = {}
                streamed = {
                    "http_status": 0,
                    "answer": "",
                    "terminal": "error",
                    "limitation": type(exc).__name__[:64],
                    "origin": "",
                    "run_id": "",
                    "error_code": type(exc).__name__[:64],
                    "stages": empty_stages,
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
    for item in cast(list[object], payload):
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


def _score_phrases(answer: str, facts: object) -> dict[str, object]:
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
    for fact in cast(list[object], facts):
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
            except Exception:
                detail = admit.text[:128]
            empty_stages: dict[str, object] = {}
            return {
                "http_status": admit.status_code,
                "answer": "",
                "terminal": "error",
                "limitation": detail or f"http_{admit.status_code}",
                "error_code": detail or f"http_{admit.status_code}",
                "origin": "",
                "run_id": "",
                "has_web_citations": False,
                "stages": empty_stages,
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
    empty_stages: dict[str, object] = {}
    return {
        "http_status": 429,
        "answer": "",
        "terminal": "error",
        "limitation": "rate_limited",
        "error_code": "rate_limited",
        "origin": "",
        "run_id": "",
        "has_web_citations": False,
        "stages": empty_stages,
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
    if isinstance(stages, Mapping):
        stage_map = cast(Mapping[str, object], stages)
        if stage_map.get("web_citation_count"):
            return True
    return False


def _credentials_environ(path: Path | None) -> dict[str, str]:
    """Merge process env with an optional gitignored credentials file.

    Args:
        path: JSON file under ``.private-eval/``, or None.

    Returns:
        Environment mapping for :func:`load_ask_regression_credentials`.

    Raises:
        AskRegressionConfigError: If the path is not private.
    """

    from scripts.ops.ingest_demo_plot_slices import merged_env

    environ = dict(merged_env())
    if path is None:
        return environ
    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError("credentials must live under .private-eval")
    payload_obj: object = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload_obj, dict):
        raise AskRegressionConfigError("credentials JSON must be an object")
    payload = _json_mapping(cast(object, payload_obj))
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    if email:
        environ["SMART_RAG_EVAL_EMAIL"] = email
    if password:
        environ["SMART_RAG_EVAL_PASSWORD"] = password
    if base_url:
        environ["SMART_RAG_EVAL_BASE_URL"] = base_url
    return environ


def _login(client: httpx.Client, environ: Mapping[str, str]) -> str:
    """Password-grant an evaluator JWT.

    Args:
        client: HTTP client.
        environ: Merged environment.

    Returns:
        Access token.

    Raises:
        RuntimeError: Login failed.
    """

    from scripts.ops.ingest_demo_plot_slices import merged_env

    env = merged_env()
    supabase_url = (
        env.get("NEXT_PUBLIC_SUPABASE_URL") or env.get("SUPABASE_URL") or ""
    ).rstrip("/")
    anon = (
        env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or env.get("SUPABASE_ANON_KEY") or ""
    )
    creds = load_ask_regression_credentials(environ)
    if not supabase_url or not anon:
        raise RuntimeError("missing_supabase_public_config")
    response = client.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon, "Content-Type": "application/json"},
        json={"email": creds.email, "password": creds.password},
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"login_failed:{response.status_code}")
    token_payload = _json_mapping(response.json())
    token = str(token_payload.get("access_token") or "")
    if not token:
        raise RuntimeError("login_missing_access_token")
    return token


def _create_conversation(client: httpx.Client, base_url: str, token: str) -> str:
    """Create one conversation for a single question.

    Retries read timeouts (5 s pause) and HTTP 429 (Retry-After, capped at
    90 s) up to six attempts. Each POST uses a 60 s timeout.

    Args:
        client: HTTP client.
        base_url: Ask origin.
        token: Bearer token.

    Returns:
        Conversation id.

    Raises:
        RuntimeError: All six attempts timed out or were rate-limited.
        httpx.HTTPStatusError: The last response was a non-429 HTTP error.
    """

    last: httpx.Response | None = None
    for _attempt in range(6):
        try:
            last = client.post(
                f"{base_url}/conversations",
                headers=_auth_headers(token, paid=True),
                json={"title": "Company Ask regression"},
                timeout=60.0,
            )
        except httpx.TimeoutException:
            time.sleep(5.0)
            continue
        if last.status_code == 429:
            retry_after = float(last.headers.get("Retry-After") or 60)
            time.sleep(min(retry_after, 90.0))
            continue
        last.raise_for_status()
        created = _json_mapping(last.json())
        return str(created["conversation_id"])
    if last is not None:
        last.raise_for_status()
    raise RuntimeError("conversation_create_rate_limited")


def _read_sse(
    client: httpx.Client,
    base_url: str,
    token: str,
    run_id: str,
) -> dict[str, object]:
    """Consume GET /runs/{id}/events until a terminal event.

    Args:
        client: HTTP client.
        base_url: Ask origin.
        token: Bearer token.
        run_id: Admitted run.

    Returns:
        Answer text, terminal, limitation, origin, and stage fields, plus
        ``first_frame_seconds`` and ``sse_seconds``.
    """

    started = time.monotonic()
    answer_parts: list[str] = []
    terminal = ""
    limitation = ""
    origin = ""
    coverage_score: float | None = None
    correction = "none"
    citation_count = 0
    path_steps: list[str] = []
    open_stage = ""
    first_frame_seconds: float | None = None
    with client.stream(
        "GET",
        f"{base_url}/runs/{run_id}/events?after=0",
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        timeout=httpx.Timeout(_RUN_TIMEOUT_S + 15.0, connect=15.0),
    ) as stream:
        event_name = ""
        data_lines: list[str] = []
        for raw in stream.iter_lines():
            if time.monotonic() - started > _RUN_TIMEOUT_S:
                break
            if raw == "":
                if event_name and data_lines:
                    loaded: object
                    try:
                        loaded = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError:
                        loaded = {}
                    payload = _json_mapping(loaded)
                    if event_name == "token_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, str):
                            answer_parts.append(delta)
                    elif event_name == "limitation":
                        limitation = str(payload.get("code") or "")
                    elif event_name == "answer_origin":
                        origin = str(payload.get("origin") or "")
                    elif event_name == "coverage":
                        raw_score = payload.get("coverage_score")
                        if isinstance(raw_score, (int, float)) and not isinstance(
                            raw_score, bool
                        ):
                            coverage_score = float(raw_score)
                    elif event_name == "route_correction":
                        correction = str(payload.get("reason") or "applied_alternate")
                        path_steps.append(f"route_correction:{correction}")
                    elif event_name == "deadline":
                        limitation = limitation or "deadline_exhausted"
                        path_steps.append("deadline:deadline_exhausted")
                    elif event_name == "citation_preview":
                        citation_count += 1
                    elif event_name == "status":
                        open_stage = _record_status(payload, path_steps, open_stage)
                    elif event_name in TERMINAL_SSE_EVENT_TYPES:
                        terminal = event_name
                        if event_name == "partial" and not limitation:
                            limitation = str(payload.get("reason") or "")
                        if event_name == "error" and not limitation:
                            limitation = str(payload.get("code") or "error")
                        break
                event_name = ""
                data_lines = []
                continue
            if raw.startswith("event:"):
                event_name = raw[6:].strip()
                if first_frame_seconds is None:
                    first_frame_seconds = round(time.monotonic() - started, 3)
            elif raw.startswith("data:"):
                data_lines.append(raw[5:].lstrip())
    if open_stage:
        path_steps.append(open_stage)
    stages: dict[str, object] = {
        "coverage_score": coverage_score,
        "correction_outcome": correction,
        "verifier_status": limitation or terminal,
    }
    return {
        "answer": "".join(answer_parts).strip(),
        "terminal": terminal or "timeout",
        "limitation": limitation,
        "origin": origin,
        "citation_count": citation_count,
        "path": ">".join(path_steps) if path_steps else "-",
        "first_frame_seconds": first_frame_seconds,
        "sse_seconds": round(time.monotonic() - started, 3),
        "stages": stages,
    }


def _record_status(
    payload: Mapping[str, object],
    path_steps: list[str],
    open_stage: str,
) -> str:
    """Append a finished graph stage and remember a stage that is still open.

    Args:
        payload: Status event payload.
        path_steps: Completed or failed stage tokens collected so far.
        open_stage: Stage that has started and not yet finished.

    Returns:
        The still-open stage token, or an empty string when the latest
        status finished a stage.
    """

    stage = str(payload.get("stage") or "stage")
    status = str(payload.get("status") or "status")
    phase = str(payload.get("phase") or "")
    if phase == "started":
        return f"{stage}:started"
    if phase in {"completed", "failed"}:
        path_steps.append(f"{stage}:{status}")
        return ""
    return open_stage


def _auth_headers(
    token: str,
    *,
    paid: bool,
    idempotency: str | None = None,
) -> dict[str, str]:
    """Build Ask API headers.

    Args:
        token: Bearer token.
        paid: Whether this is a paid mutation.
        idempotency: Optional UUID string.

    Returns:
        Header map.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if paid:
        headers["X-Client-Version"] = _CLIENT_VERSION
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    return headers


def _json_mapping(value: object) -> dict[str, object]:
    """Coerce JSON objects to a string-keyed mapping.

    Args:
        value: Parsed JSON value.

    Returns:
        String-keyed mapping, or empty when the value is not an object.
    """

    if not isinstance(value, Mapping):
        return {}
    typed = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed.items()}


if __name__ == "__main__":
    raise SystemExit(main())
