"""Live company-documents Ask regression using environment credentials.

Private gold stays under gitignored ``.private-eval/``. Each question uses a
fresh conversation. Passwords are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.accuracy_promotion import (  # noqa: E402
    decide_accuracy_promotion,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
    CompanyAskQuestion,
    load_ask_regression_credentials,
    load_private_gold,
    run_scored_questions,
    write_redacted_summary,
)
from smart_rag_core.evaluation.dual_metric import (  # noqa: E402
    RetrievalStageAttribution,
    SourceResolutionStage,
)
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES  # noqa: E402

_RUN_TIMEOUT_S = 125.0
_CLIENT_VERSION = "0.1.0"
_SEARCH_SCOPE = "company_documents"


def main(argv: list[str] | None = None) -> int:
    """Run the company Ask regression with dual-metric scoring.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` when the run completed and a redacted summary was written.
        ``2`` on configuration or readiness failure.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Ask each private gold question on company_documents with a fresh "
            "conversation and score full answers."
        )
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help="Optional gitignored JSON with email, password, and base_url.",
    )
    parser.add_argument("--progress", type=Path, default=None)
    parser.add_argument("--answers-out", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        environ = _credentials_environ(args.credentials)
        creds = load_ask_regression_credentials(environ)
        questions = load_private_gold(args.gold)
    except (AskRegressionConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"blocked={exc}", file=sys.stderr)
        return 2
    ready = httpx.get(f"{creds.base_url}/health/ready", timeout=10.0)
    ready_payload: object = ready.json() if ready.status_code == 200 else {}
    body = _json_mapping(ready_payload)
    if body.get("query_ready") is not True:
        print("blocked=not_query_ready", file=sys.stderr)
        return 2
    answers: dict[str, dict[str, object]] = {}
    if args.answers_out is not None and args.answers_out.is_file():
        existing_obj: object = json.loads(args.answers_out.read_text(encoding="utf-8"))
        if isinstance(existing_obj, dict):
            answers = {
                str(key): _json_mapping(cast(object, value))
                for key, value in cast(dict[object, object], existing_obj).items()
                if isinstance(value, dict)
            }
    with httpx.Client() as client:
        token = _login(client, environ)
        token_started = time.monotonic()
        pending = [item for item in questions if item.question_id not in answers]
        for index, question in enumerate(pending, start=1):
            if time.monotonic() - token_started > 2400:
                token = _login(client, environ)
                token_started = time.monotonic()
            conversation_id = _create_conversation(client, creds.base_url, token)
            streamed = _ask_one(
                client,
                creds.base_url,
                token,
                conversation_id,
                question.prompt,
            )
            if streamed.get("http_status") in {401, 403}:
                token = _login(client, environ)
                token_started = time.monotonic()
                streamed = _ask_one(
                    client,
                    creds.base_url,
                    token,
                    conversation_id,
                    question.prompt,
                )
            answers[question.question_id] = {
                "answer_text": str(streamed.get("answer") or ""),
                "status": str(
                    streamed.get("limitation") or streamed.get("terminal") or ""
                ),
                "reason": str(streamed.get("limitation") or ""),
                "conversation_id": conversation_id,
                "origin": str(streamed.get("origin") or ""),
                "stages": streamed.get("stages") or {},
            }
            done = len(answers)
            if args.progress is not None:
                args.progress.write_text(
                    json.dumps(
                        {
                            "progress": f"{done}/{len(questions)}",
                            "last_id": question.question_id,
                            "last_terminal": streamed.get("terminal"),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if args.answers_out is not None:
                args.answers_out.parent.mkdir(parents=True, exist_ok=True)
                args.answers_out.write_text(
                    json.dumps(answers, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            print(
                f"{done}/{len(questions)} id={question.question_id} "
                f"terminal={streamed.get('terminal')}",
                flush=True,
            )
            if index < len(pending):
                time.sleep(3.0)
    parsed_answers, stages, statuses, reasons = _answers_for_scorer(answers, questions)
    results = run_scored_questions(
        questions,
        answers=parsed_answers,
        stages=stages,
        factory=_MappedConversationFactory(answers, questions),
        answer_status=statuses,
        terminal_reason=reasons,
    )
    if args.answers_out is not None:
        args.answers_out.parent.mkdir(parents=True, exist_ok=True)
        args.answers_out.write_text(
            json.dumps(answers, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    summary = dict(write_redacted_summary(results, args.out))
    origin_leaks = sum(
        1
        for row in answers.values()
        if str(row.get("origin") or "")
        in {"web", "general_knowledge", "user_supplied_text"}
    )
    decision = decide_accuracy_promotion(
        summary,
        acl_leaks=origin_leaks,
        bm25_degraded_explicit=True,
        holdout_opened=False,
        disjoint_real_document_count=0,
        sample_gold_in_production=False,
        rerank_accounting_ok=True,
    )
    print(
        "questions={questions} strict_pass={strict_pass} "
        "grounded_fact_pass={grounded_fact_pass} "
        "deadline_failures={deadline_failures} "
        "sample_promoted={promoted} generalization={generalization}".format(
            promoted=str(decision.sample_promoted).lower(),
            generalization=str(decision.generalization_claimed).lower(),
            **summary,
        ),
        flush=True,
    )
    print(f"reasons={','.join(decision.reasons) or 'none'}", flush=True)
    return 0


class _MappedConversationFactory:
    """Replay conversation ids in gold-question order."""

    def __init__(
        self,
        answers: Mapping[str, Mapping[str, object]],
        questions: tuple[CompanyAskQuestion, ...],
    ) -> None:
        """Store captured conversation ids.

        Args:
            answers: Live rows keyed by question id.
            questions: Gold order.
        """

        self._unused = [
            str(answers[item.question_id].get("conversation_id") or uuid4())
            for item in questions
        ]

    def create_conversation(self) -> str:
        """Return the next captured conversation id.

        Returns:
            Opaque conversation id.
        """

        if not self._unused:
            return str(uuid4())
        return self._unused.pop(0)


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

    Args:
        client: HTTP client.
        base_url: Ask origin.
        token: Bearer token.

    Returns:
        Conversation id.
    """

    last: httpx.Response | None = None
    for _attempt in range(6):
        last = client.post(
            f"{base_url}/conversations",
            headers=_auth_headers(token, paid=True),
            json={"title": "Company Ask regression"},
            timeout=30.0,
        )
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


def _ask_one(
    client: httpx.Client,
    base_url: str,
    token: str,
    conversation_id: str,
    question: str,
) -> dict[str, object]:
    """Admit one company_documents question and wait for the SSE terminal.

    Args:
        client: HTTP client.
        base_url: Ask origin.
        token: Bearer token.
        conversation_id: Fresh conversation.
        question: User question.

    Returns:
        Streamed answer, stages, limitation, and terminal.
    """

    idempotency = str(uuid4())
    for _attempt in range(4):
        admit = client.post(
            f"{base_url}/conversations/{conversation_id}/messages",
            headers=_auth_headers(token, paid=True, idempotency=idempotency),
            json={
                "message": question,
                "idempotency_key": idempotency,
                "search_scope": _SEARCH_SCOPE,
            },
            timeout=30.0,
        )
        if admit.status_code == 429:
            retry_after = float(admit.headers.get("Retry-After") or 60)
            time.sleep(min(retry_after, 90.0))
            continue
        if admit.status_code >= 400:
            return {
                "http_status": admit.status_code,
                "answer": "",
                "terminal": "error",
                "limitation": "",
                "origin": "",
                "stages": {},
            }
        admit_body = _json_mapping(admit.json())
        run_id = str(admit_body.get("run_id") or "")
        streamed = _read_sse(client, base_url, token, run_id)
        streamed["http_status"] = admit.status_code
        return streamed
    return {
        "http_status": 429,
        "answer": "",
        "terminal": "error",
        "limitation": "rate_limited",
        "origin": "",
        "stages": {},
    }


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
        Answer text, terminal, limitation, origin, and stage fields.
    """

    started = time.monotonic()
    answer_parts: list[str] = []
    terminal = ""
    limitation = ""
    origin = ""
    coverage_score: float | None = None
    citation_count = 0
    correction = "none"
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
                    elif event_name == "citation_preview":
                        ids = payload.get("citation_ids")
                        if isinstance(ids, list):
                            citation_count = len(cast(list[object], ids))
                    elif event_name == "route_correction":
                        correction = str(payload.get("reason") or "applied_alternate")
                    elif event_name in TERMINAL_SSE_EVENT_TYPES:
                        terminal = event_name
                        if event_name == "partial" and not limitation:
                            limitation = str(payload.get("reason") or "")
                        break
                event_name = ""
                data_lines = []
                continue
            if raw.startswith("event:"):
                event_name = raw[6:].strip()
            elif raw.startswith("data:"):
                data_lines.append(raw[5:].lstrip())
    fused_count = citation_count
    if fused_count == 0 and coverage_score is not None:
        fused_count = 1
    return {
        "answer": "".join(answer_parts).strip(),
        "terminal": terminal or "timeout",
        "limitation": limitation,
        "origin": origin,
        "stages": {
            "source_resolution": SourceResolutionStage.UNSCOPED.value,
            "fused_count": fused_count,
            "coverage_score": coverage_score,
            "correction_outcome": correction,
            "verifier_status": limitation or terminal,
            "retrieval_empty": fused_count == 0 and terminal == "error",
        },
    }


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


def _answers_for_scorer(
    answers: Mapping[str, Mapping[str, object]],
    questions: tuple[CompanyAskQuestion, ...],
) -> tuple[
    dict[str, str],
    dict[str, RetrievalStageAttribution],
    dict[str, str],
    dict[str, str],
]:
    """Convert live rows into scorer inputs.

    Args:
        answers: Live captured rows.
        questions: Gold questions.

    Returns:
        Answers, stages, statuses, and reasons.
    """

    del questions
    parsed: dict[str, str] = {}
    stages: dict[str, RetrievalStageAttribution] = {}
    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for key, raw in answers.items():
        parsed[key] = str(raw.get("answer_text") or "")
        if raw.get("status"):
            statuses[key] = str(raw["status"])
        if raw.get("reason"):
            reasons[key] = str(raw["reason"])
        stage_raw_obj = raw.get("stages")
        if not isinstance(stage_raw_obj, Mapping):
            stages[key] = RetrievalStageAttribution()
            continue
        stage_raw = _json_mapping(cast(object, stage_raw_obj))
        resolution = str(stage_raw.get("source_resolution", "unscoped"))
        try:
            source_resolution = SourceResolutionStage(resolution)
        except ValueError:
            source_resolution = SourceResolutionStage.UNSCOPED
        coverage = stage_raw.get("coverage_score")
        fused_count = stage_raw.get("fused_count", 0)
        stages[key] = RetrievalStageAttribution(
            source_resolution=source_resolution,
            fused_count=_as_int(fused_count),
            coverage_score=(
                float(coverage)
                if isinstance(coverage, (int, float)) and not isinstance(coverage, bool)
                else None
            ),
            correction_outcome=str(stage_raw.get("correction_outcome", "none")),
            verifier_status=(
                str(stage_raw["verifier_status"])
                if stage_raw.get("verifier_status")
                else None
            ),
            retrieval_empty=bool(stage_raw.get("retrieval_empty", False)),
        )
    return parsed, stages, statuses, reasons


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


def _as_int(value: object) -> int:
    """Coerce a JSON number to int.

    Args:
        value: Parsed JSON value.

    Returns:
        Integer, or ``0`` when the value is missing or not numeric.
    """

    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
