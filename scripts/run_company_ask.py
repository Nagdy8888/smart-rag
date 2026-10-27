"""Live company-documents Ask regression using environment credentials.

Private gold stays under gitignored ``.private-eval/``. Each question uses a
fresh conversation. Passwords are never printed. ``--verbose`` adds a scored
diagnosis line per question after the live terminal, reason, and coverage.
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
import psycopg

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.accuracy_promotion import (  # noqa: E402
    decide_accuracy_promotion,
)
from smart_rag_core.evaluation.company_ask_diagnosis import (  # noqa: E402
    classify_ask_drop,
)
from smart_rag_core.evaluation.company_ask_langsmith import (  # noqa: E402
    DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
    CompanyAskLangSmithClient,
    CompanyAskLangSmithError,
    publish_company_ask_experiment,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
    CompanyAskQuestion,
    CompanyAskResult,
    load_ask_regression_credentials,
    load_private_gold,
    run_scored_questions,
    write_redacted_summary,
)
from smart_rag_core.evaluation.dual_metric import (  # noqa: E402
    RetrievalStageAttribution,
    SourceResolutionStage,
)
from smart_rag_core.settings import (  # noqa: E402
    get_process_environ,
    set_process_environ,
    setdefault_process_environ,
)
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES  # noqa: E402

from scripts.eval_ask_stage_export import (  # noqa: E402
    export_ask_stages,
    operator_url,
)

_RUN_TIMEOUT_S = 125.0
_CLIENT_VERSION = "0.1.0"
_SEARCH_SCOPE = "company_documents"
_search_scope_override: str | None = None


def main(argv: list[str] | None = None) -> int:
    """Run the company Ask regression with dual-metric scoring.

    The ready probe and Ask HTTP client use a 60 s timeout. Conversation
    create and admit retries survive hosted Auth/readiness blips. A second
    TimeoutException, TransportError, HTTPStatusError, or RuntimeError
    records a timeout row instead of aborting remaining questions.

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
    parser.add_argument(
        "--stage-export",
        type=Path,
        default=None,
        help="Private JSON for measured Hybrid stage fields.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "After scoring, print one diagnosis line per question: drop bucket, "
            "missed fact ids, rerank, profile, gold-page fusion, and citation "
            "failure codes. Never prints the answer body or gold phrases."
        ),
    )
    parser.add_argument(
        "--langsmith-publish",
        action="store_true",
        help=(
            "After local dual-metric scoring, publish a LangSmith dataset + "
            "experiment. Requires --answers-out, APP_ENV=local, and "
            "--upload-private-content."
        ),
    )
    parser.add_argument(
        "--upload-private-content",
        action="store_true",
        help=(
            "Required with --langsmith-publish. Uploads prompts, answers, and "
            "gold phrases to LangSmith (local only)."
        ),
    )
    parser.add_argument(
        "--langsmith-project",
        default=DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
        help=(
            "LangSmith project for --langsmith-publish "
            f"(default {DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT})."
        ),
    )
    parser.add_argument(
        "--langsmith-experiment-prefix",
        default=None,
        help="Optional sanitized experiment prefix suffix for LangSmith.",
    )
    args = parser.parse_args(argv)
    try:
        environ = _credentials_environ(args.credentials)
        creds = load_ask_regression_credentials(environ)
        questions = load_private_gold(args.gold)
    except (AskRegressionConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"blocked={exc}", file=sys.stderr)
        return 2
    ready = httpx.get(f"{creds.base_url}/health/ready", timeout=60.0)
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
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        token = _login(client, environ)
        token_started = time.monotonic()
        pending = [item for item in questions if item.question_id not in answers]
        for index, question in enumerate(pending, start=1):
            if time.monotonic() - token_started > 2400:
                token = _login(client, environ)
                token_started = time.monotonic()
            streamed: dict[str, object]
            conversation_id = ""
            try:
                conversation_id = _create_conversation(client, creds.base_url, token)
                streamed = _ask_one(
                    client,
                    creds.base_url,
                    token,
                    conversation_id,
                    question.prompt,
                )
            except (
                httpx.TimeoutException,
                httpx.TransportError,
                httpx.HTTPStatusError,
                RuntimeError,
            ):
                token = _login(client, environ)
                token_started = time.monotonic()
                try:
                    conversation_id = _create_conversation(
                        client, creds.base_url, token
                    )
                    streamed = _ask_one(
                        client,
                        creds.base_url,
                        token,
                        conversation_id,
                        question.prompt,
                    )
                except (
                    httpx.TimeoutException,
                    httpx.TransportError,
                    httpx.HTTPStatusError,
                    RuntimeError,
                ):
                    streamed = {
                        "answer": "",
                        "terminal": "timeout",
                        "limitation": "timeout",
                        "origin": "",
                        "run_id": "",
                        "http_status": 0,
                    }
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
                "run_id": str(streamed.get("run_id") or ""),
                "origin": str(streamed.get("origin") or ""),
                "stages": _json_mapping(streamed.get("stages")),
                "timing": _json_mapping(streamed.get("timing")),
                "knowledge_result": _json_mapping(streamed.get("knowledge_result")),
                "usage": _json_mapping(streamed.get("usage")),
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
                format_live_ask_line(
                    done=done,
                    total=len(questions),
                    question_id=question.question_id,
                    terminal=streamed.get("terminal"),
                    reason=streamed.get("limitation"),
                    origin=streamed.get("origin"),
                    coverage=_stage_value(streamed, "coverage_score"),
                    correction=_stage_value(streamed, "correction_outcome"),
                    citations=_citation_count(streamed.get("citation_count")),
                    path=str(streamed.get("path") or "-"),
                ),
                flush=True,
            )
            if index < len(pending):
                time.sleep(3.0)
    stage_export = _join_stage_export(answers, args.stage_export)
    _apply_stage_export(answers, stage_export)
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
    if args.verbose:
        _print_verbose_diagnosis(
            gold_path=args.gold,
            questions=questions,
            results=results,
            answers=answers,
        )
    summary = dict(write_redacted_summary(results, args.out))
    from smart_rag_core.evaluation.knowledge_metrics import summarize_knowledge_metrics

    knowledge_metrics = summarize_knowledge_metrics(questions, results, answers)
    args.out.with_name(f"{args.out.stem}-knowledge-metrics.json").write_text(
        json.dumps(knowledge_metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    origin_leaks = sum(
        1
        for row in answers.values()
        if str(row.get("origin") or "")
        in {"web", "general_knowledge", "user_supplied_text"}
    )
    decision = decide_accuracy_promotion(
        summary,
        acl_leaks=origin_leaks,
        bm25_degraded_explicit=bool(stage_export.get("bm25_degraded_explicit")),
        holdout_opened=False,
        disjoint_real_document_count=0,
        sample_gold_in_production=False,
        rerank_accounting_ok=bool(stage_export.get("rerank_accounting_ok")),
        unknown_required_fields=unknown_required_count(stage_export, len(questions)),
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
    if args.langsmith_publish:
        if args.answers_out is None:
            print("blocked=langsmith_publish_requires_answers_out", file=sys.stderr)
            return 2
        try:
            from langsmith import Client

            set_process_environ("LANGSMITH_PROJECT", args.langsmith_project)
            set_process_environ("LANGCHAIN_PROJECT", args.langsmith_project)
            from company_ask_langsmith_enrich import (
                enrich_diagnosis_signals,
                enrich_run_usage,
            )

            setdefault_process_environ("LANGSMITH_TRACING", "true")
            setdefault_process_environ("LANGCHAIN_TRACING_V2", "true")
            answer_rows = {
                question_id: {str(field): value for field, value in row.items()}
                for question_id, row in answers.items()
            }
            diagnosis = enrich_diagnosis_signals(
                questions,
                answer_rows=answer_rows,
                results=results,
            )
            usage = enrich_run_usage(answer_rows)
            published = publish_company_ask_experiment(
                cast(CompanyAskLangSmithClient, Client()),
                questions=questions,
                answer_rows=answer_rows,
                app_env=(get_process_environ("APP_ENV") or "").strip() or "local",
                project_name=args.langsmith_project,
                upload_private_content=args.upload_private_content,
                experiment_prefix=args.langsmith_experiment_prefix,
                diagnosis=diagnosis,
                usage=usage,
            )
        except CompanyAskLangSmithError as exc:
            print(f"blocked=langsmith_publish:{exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"blocked=langsmith_publish_failed:{exc}", file=sys.stderr)
            return 2
        print(
            "langsmith_project={project} dataset={dataset} experiment_url={url}".format(
                project=published.project_name,
                dataset=published.dataset_name,
                url=published.experiment_url or "unavailable",
            ),
            flush=True,
        )
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

    Retries read timeouts (5 s pause) and HTTP 429 (Retry-After, capped at
    90 s) up to six attempts. Each POST uses a 60 s timeout so a slow
    ``/health/ready`` path cannot abort the 100-question loop.

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
        Streamed answer, stages, limitation, and terminal. A streamed run
        also has ``timing`` with ``post_seconds``, ``first_frame_seconds``,
        ``sse_seconds``, and ``wall_seconds`` (3 decimals). Timing never
        changes the retry or sleep behavior.
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
                "search_scope": _search_scope_override or _SEARCH_SCOPE,
            },
            timeout=60.0,
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
                "run_id": "",
                "stages": {},
            }
        post_seconds = round(time.monotonic() - post_started, 3)
        admit_body = _json_mapping(admit.json())
        run_id = str(admit_body.get("run_id") or "")
        streamed = _read_sse(client, base_url, token, run_id)
        streamed["http_status"] = admit.status_code
        streamed["run_id"] = run_id
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
        "origin": "",
        "run_id": "",
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
        Answer text, terminal, limitation, origin, and stage fields, plus
        ``first_frame_seconds`` (stream open to the first ``event:`` line,
        or None) and ``sse_seconds`` (stream open to return).
    """

    started = time.monotonic()
    answer_parts: list[str] = []
    terminal = ""
    limitation = ""
    origin = ""
    knowledge: dict[str, object] = {}
    usage: dict[str, object] = {}
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
                        knowledge = _json_mapping(payload.get("knowledge_result"))
                    elif event_name == "usage":
                        usage = {
                            key: payload[key]
                            for key in (
                                "prompt_tokens",
                                "completion_tokens",
                                "cost_usd",
                            )
                            if key in payload
                        }
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
    return {
        "answer": "".join(answer_parts).strip(),
        "terminal": terminal or "timeout",
        "limitation": limitation,
        "origin": origin,
        "citation_count": citation_count,
        "knowledge_result": knowledge,
        "usage": usage,
        "path": ">".join(path_steps) if path_steps else "-",
        "first_frame_seconds": first_frame_seconds,
        "sse_seconds": round(time.monotonic() - started, 3),
        "stages": {
            "coverage_score": coverage_score,
            "correction_outcome": correction,
            "verifier_status": limitation or terminal,
        },
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


def _join_stage_export(
    answers: Mapping[str, Mapping[str, object]],
    destination: Path | None,
) -> dict[str, object]:
    """Load measured Hybrid diagnostics for recorded runs.

    Args:
        answers: Question rows with ``run_id`` and ``conversation_id``.
        destination: Optional private JSON path.

    Returns:
        Export mapping. Missing operator access yields unknown counts.
    """

    unknown: dict[str, object] = {
        "runs": {},
        "unknown_required_fields": len(answers),
        "rerank_accounting_ok": False,
        "bm25_degraded_explicit": False,
    }
    try:
        url = operator_url()
        payload = export_ask_stages(answers, postgres_url=url)
    except (RuntimeError, OSError, psycopg.Error):
        payload = unknown
    if destination is not None:
        if ".private-eval" not in {
            part.casefold() for part in destination.resolve().parts
        }:
            return unknown
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _apply_stage_export(
    answers: dict[str, dict[str, object]],
    stage_export: Mapping[str, object],
) -> None:
    """Copy measured stage fields onto answer rows.

    Args:
        answers: Mutable question rows.
        stage_export: Export from :func:`export_ask_stages`.
    """

    runs = stage_export.get("runs")
    if not isinstance(runs, Mapping):
        return
    runs_map = cast(Mapping[str, object], runs)
    for question_id, row in answers.items():
        exported = runs_map.get(question_id)
        if not isinstance(exported, Mapping):
            continue
        exported_map = cast(Mapping[str, object], exported)
        existing = row.get("stages")
        stages: dict[str, object] = (
            dict(cast(Mapping[str, object], existing))
            if isinstance(existing, Mapping)
            else {}
        )
        for key, value in exported_map.items():
            if key == "run_id":
                continue
            stages[str(key)] = value
        row["stages"] = stages


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
        coverage = stage_raw.get("coverage_score")
        fused_ids = stage_raw.get("fused_ids")
        fused_count = (
            len(cast(list[object], fused_ids)) if isinstance(fused_ids, list) else 0
        )
        retrieval_empty = stage_raw.get("retrieval_empty")
        stages[key] = RetrievalStageAttribution(
            source_resolution=_measured_source_resolution(
                stage_raw.get("source_resolution")
            ),
            fused_count=fused_count,
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
            retrieval_empty=retrieval_empty is True,
            rerank_fallback=(
                str(stage_raw["rerank_fallback"])
                if stage_raw.get("rerank_fallback")
                and str(stage_raw.get("rerank_fallback")) != "unknown"
                else None
            ),
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


def unknown_required_count(
    stage_export: Mapping[str, object],
    question_count: int,
) -> int:
    """Read the measured unknown-field count without treating zero as missing.

    Args:
        stage_export: Export from :func:`export_ask_stages`.
        question_count: Fallback when the export omitted the count.

    Returns:
        Non-negative unknown-field count.
    """

    value = stage_export.get("unknown_required_fields")
    if isinstance(value, bool) or not isinstance(value, int):
        return question_count
    return max(value, 0)


def format_live_ask_line(
    *,
    done: int,
    total: int,
    question_id: str,
    terminal: object,
    reason: object,
    origin: object,
    coverage: object,
    correction: object,
    citations: int = 0,
    path: str = "-",
) -> str:
    """Format one live Ask progress line without the answer body.

    Args:
        done: Questions finished, including resumed rows.
        total: Gold question count.
        question_id: Gold question id.
        terminal: SSE terminal event name.
        reason: Limitation or partial reason code.
        origin: Answer origin token.
        coverage: Coverage score, or None when the event was absent.
        correction: Route-correction outcome.
        citations: Citation preview events observed on the stream.
        path: Finished graph stages in order, separated by ``>``.

    Returns:
        One terminal line. It omits answer text and gold phrases.
    """

    return (
        f"{done}/{total} id={question_id} "
        f"terminal={_token(terminal)} "
        f"reason={_token(reason)} "
        f"origin={_token(origin)} "
        f"coverage={_coverage_text(coverage)} "
        f"correction={_token(correction, empty='none')} "
        f"citations={citations} "
        f"path={path or '-'}"
    )


def format_diagnosis_line(
    *,
    question_id: str,
    outcome: str,
    strict_pass: bool,
    grounded: bool,
    missed_fact_ids: tuple[str, ...],
    terminal: str,
    reason: str,
    origin: str,
    coverage: object,
    rerank_call_count: object,
    rerank_fallback: object,
    profile: object,
    resolution: object,
    gold_page: int | None,
    gold_page_in_fusion: bool | None,
    gold_page_in_fused: bool | None = None,
    gold_page_in_rerank_pool: bool | None = None,
    citation_failures: tuple[str, ...],
) -> str:
    """Format one scored diagnosis line without answer text or gold phrases.

    Args:
        question_id: Gold question id.
        outcome: Dual-metric outcome value.
        strict_pass: Whether every canonical phrase matched.
        grounded: Whether every required fact matched.
        missed_fact_ids: Fact ids whose canonical phrases missed.
        terminal: Stored answer status.
        reason: Stored limitation or terminal reason.
        origin: Answer origin token.
        coverage: Coverage score from the SSE capture or stage export.
        rerank_call_count: Measured rerank calls, or unknown.
        rerank_fallback: Measured rerank fallback token.
        profile: Retrieval profile id.
        resolution: Source-resolution token.
        gold_page: Page recorded on the private gold item.
        gold_page_in_fusion: Whether that page was in fused evidence.
        gold_page_in_fused: Whether that page was in ``fused_ids``.
        gold_page_in_rerank_pool: Whether that page entered the rerank pool.
        citation_failures: Deterministic citation failure codes.

    Returns:
        One diagnosis line, including the drop bucket.
    """

    drop = classify_ask_drop(
        outcome=outcome,
        grounded=grounded,
        gold_page_in_fusion=gold_page_in_fusion,
        citation_failures=citation_failures,
        gold_page_in_fused=gold_page_in_fused,
        gold_page_in_rerank_pool=gold_page_in_rerank_pool,
    )
    missed = ",".join(missed_fact_ids) if missed_fact_ids else "-"
    failures = ",".join(citation_failures) if citation_failures else "-"
    page_text = str(gold_page) if gold_page is not None else "-"
    return (
        f"DIAG id={question_id} drop={drop} outcome={outcome} "
        f"strict={int(strict_pass)} grounded={int(grounded)} "
        f"missed={missed} terminal={_token(terminal)} "
        f"reason={_token(reason)} origin={_token(origin)} "
        f"coverage={_coverage_text(coverage)} "
        f"rerank={_token(rerank_call_count)}/{_token(rerank_fallback)} "
        f"profile={_token(profile)} resolution={_token(resolution)} "
        f"gold_page={page_text} in_fusion={_yes_no(gold_page_in_fusion)} "
        f"in_fused={_yes_no(gold_page_in_fused)} "
        f"in_pool={_yes_no(gold_page_in_rerank_pool)} failures={failures}"
    )


def _yes_no(value: bool | None) -> str:
    """Render a measured boolean as a diagnosis token.

    Args:
        value: Measured flag, or None when the stage was not exported.

    Returns:
        ``yes``, ``no``, or ``unknown``.
    """

    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _token(value: object, *, empty: str = "-") -> str:
    """Render a diagnostic token without embedding answer text.

    Args:
        value: Field from an SSE capture or stage export.
        empty: Text used for a missing token.

    Returns:
        A single whitespace-free token.
    """

    text = str(value or "").strip()
    if not text:
        return empty
    return text.replace(" ", "_")


def _coverage_text(coverage: object) -> str:
    """Render a coverage score, or ``missing`` when it was not measured.

    Args:
        coverage: Numeric coverage score, or another JSON value.

    Returns:
        Two-decimal score text, or ``missing``.
    """

    if isinstance(coverage, bool) or not isinstance(coverage, (int, float)):
        return "missing"
    return f"{float(coverage):.2f}"


def _measured_coverage(
    stages: Mapping[str, object],
    checkpoint: Mapping[str, object],
) -> object:
    """Prefer a numeric stream coverage score, then the checkpoint score.

    Args:
        stages: Stage fields stored on the answer row.
        checkpoint: Fusion and branch checkpoint fields.

    Returns:
        A numeric coverage score, or None when neither source measured one.
    """

    streamed = stages.get("coverage_score")
    if isinstance(streamed, (int, float)) and not isinstance(streamed, bool):
        return streamed
    return checkpoint.get("coverage")


def _citation_count(value: object) -> int:
    """Return a citation preview count from an SSE capture.

    Args:
        value: ``citation_count`` field.

    Returns:
        Non-negative count, or zero when the field is absent.
    """

    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _stage_value(streamed: Mapping[str, object], key: str) -> object:
    """Read one nested stage field from an SSE capture.

    Args:
        streamed: Return value of ``_consume_events``.
        key: Stage field name.

    Returns:
        The field value, or None when stages are absent.
    """

    stages = streamed.get("stages")
    if not isinstance(stages, Mapping):
        return None
    return cast(Mapping[str, object], stages).get(key)


def _print_verbose_diagnosis(
    *,
    gold_path: Path,
    questions: tuple[CompanyAskQuestion, ...],
    results: tuple[CompanyAskResult, ...] | list[CompanyAskResult],
    answers: Mapping[str, Mapping[str, object]],
) -> None:
    """Print one diagnosis line per question and a drop histogram.

    Checkpoint lookup failures are reported as ``unknown`` fusion and ``-``
    citation codes. The password, DSN, answer body, and gold phrases are not
    printed.

    Args:
        gold_path: Private gold file, used only for page numbers.
        questions: Gold questions in run order.
        results: Scored results aligned with ``questions``.
        answers: Live rows with conversation ids and stage fields.
    """

    pages = _gold_pages(gold_path)
    checkpoints = _checkpoint_diagnosis(answers)
    buckets: dict[str, int] = {}
    by_id = {item.question_id: item for item in results}
    for question in questions:
        result = by_id.get(question.question_id)
        if result is None:
            continue
        row = answers.get(question.question_id, {})
        stages = _json_mapping(row.get("stages"))
        checkpoint = checkpoints.get(question.question_id, {})
        gold_page = pages.get(question.question_id)
        fusion_pages = checkpoint.get("pages")
        on_page = _page_in_fusion(gold_page, fusion_pages)
        in_fused = _page_in_fusion(gold_page, checkpoint.get("fused_pages"))
        in_pool = _page_in_fusion(gold_page, checkpoint.get("pool_pages"))
        failure_names = _string_tuple(checkpoint.get("failures"))
        line = format_diagnosis_line(
            question_id=question.question_id,
            outcome=result.score.outcome.value,
            strict_pass=result.score.strict_pass,
            grounded=result.score.grounded_fact_pass,
            missed_fact_ids=_missed_fact_ids(question, result),
            terminal=str(row.get("status") or ""),
            reason=str(row.get("reason") or ""),
            origin=str(row.get("origin") or ""),
            coverage=_measured_coverage(stages, checkpoint),
            rerank_call_count=stages.get("rerank_call_count"),
            rerank_fallback=stages.get("rerank_fallback"),
            profile=stages.get("retrieval_profile_id"),
            resolution=stages.get("source_resolution"),
            gold_page=gold_page,
            gold_page_in_fusion=on_page,
            gold_page_in_fused=in_fused,
            gold_page_in_rerank_pool=in_pool,
            citation_failures=failure_names,
        )
        print(line, flush=True)
        drop = line.split(" ", 3)[2].split("=", 1)[1]
        buckets[drop] = buckets.get(drop, 0) + 1
    histogram = ",".join(f"{name}:{count}" for name, count in sorted(buckets.items()))
    print(f"drop_histogram={histogram or 'none'}", flush=True)


def _missed_fact_ids(
    question: CompanyAskQuestion,
    result: CompanyAskResult,
) -> tuple[str, ...]:
    """Return fact ids whose canonical phrases did not match.

    Args:
        question: Gold question.
        result: Scored result for that question.

    Returns:
        Fact ids in gold order. Phrase text is not included.
    """

    missed = set(result.score.missed_canonical)
    return tuple(
        fact.fact_id
        for fact in question.facts
        if any(phrase in missed for phrase in fact.canonical_phrases)
    )


def _gold_pages(path: Path) -> dict[str, int | None]:
    """Read optional page numbers from private gold.

    Args:
        path: Gold JSON array.

    Returns:
        Question id to page. Missing pages are None.
    """

    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    pages: dict[str, int | None] = {}
    if not isinstance(loaded, list):
        return pages
    for item in cast(list[object], loaded):
        mapping = _json_mapping(item)
        if not mapping:
            continue
        page = mapping.get("page")
        pages[str(mapping.get("id", ""))] = page if isinstance(page, int) else None
    return pages


def _page_in_fusion(gold_page: int | None, fusion_pages: object) -> bool | None:
    """Decide whether the gold page was present in fused evidence.

    Args:
        gold_page: Page from private gold.
        fusion_pages: Page numbers loaded from the fusion checkpoint.

    Returns:
        True or False when both sides were measured, else None.
    """

    if gold_page is None or not isinstance(fusion_pages, tuple):
        return None
    return gold_page in fusion_pages


def _checkpoint_diagnosis(
    answers: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Load fusion pages and citation failure codes for each conversation.

    Args:
        answers: Live rows containing ``conversation_id``.

    Returns:
        Question id to fusion pages, fused and pool pages, citation
        failures, and coverage. Empty when the operator database cannot
        be read.
    """

    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except ImportError:
        print("checkpoint=unavailable", flush=True)
        return {}
    try:
        postgres_url = operator_url()
    except RuntimeError:
        print("checkpoint=unavailable", flush=True)
        return {}
    serde = JsonPlusSerializer()
    found: dict[str, dict[str, object]] = {}
    try:
        with psycopg.connect(postgres_url, connect_timeout=20) as connection:
            for question_id, row in answers.items():
                thread_id = str(row.get("conversation_id") or "")
                if not thread_id:
                    continue
                fusion = _load_checkpoint_channel(
                    connection, serde, thread_id, "fusion"
                )
                verification = _load_checkpoint_channel(
                    connection, serde, thread_id, "verification"
                )
                branches = _load_checkpoint_channel(
                    connection, serde, thread_id, "branch_results"
                )
                fused_ids = _hybrid_diagnostic_ids(branches, "fused_ids")
                pool_ids = _hybrid_diagnostic_ids(branches, "rerank_pool_ids")
                page_of = _pages_for_chunk_ids(connection, (*fused_ids, *pool_ids))
                found[question_id] = {
                    "pages": _fusion_pages(fusion),
                    "failures": _citation_failures(verification),
                    "coverage": _hybrid_coverage(branches),
                    "fused_pages": tuple(
                        page_of[item] for item in fused_ids if item in page_of
                    ),
                    "pool_pages": tuple(
                        page_of[item] for item in pool_ids if item in page_of
                    ),
                }
    except psycopg.Error:
        print("checkpoint=unavailable", flush=True)
        return {}
    return found


def _load_checkpoint_channel(
    connection: psycopg.Connection,
    serde: object,
    thread_id: str,
    channel: str,
) -> object:
    """Load the latest LangGraph blob for one channel.

    Args:
        connection: Operator database connection.
        serde: ``JsonPlusSerializer`` instance.
        thread_id: Conversation id used as the checkpoint thread.
        channel: Checkpoint channel name.

    Returns:
        Deserialized channel value, or None when the blob is absent.
    """

    row = connection.execute(
        """
        SELECT type, blob
        FROM langgraph.checkpoint_blobs
        WHERE thread_id = %s AND channel = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (thread_id, channel),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    loads_typed = getattr(serde, "loads_typed", None)
    if not callable(loads_typed):
        return None
    return loads_typed((str(row[0]), bytes(row[1])))


def _fusion_pages(payload: object) -> tuple[int, ...]:
    """Return page numbers stored on fused evidence.

    Args:
        payload: Deserialized fusion channel.

    Returns:
        Page numbers. Empty when fusion evidence was not stored.
    """

    evidence = _json_mapping(payload).get("evidence")
    if not isinstance(evidence, list):
        return ()
    pages: list[int] = []
    for item in cast(list[object], evidence):
        page = _json_mapping(item).get("page_number")
        if isinstance(page, int) and not isinstance(page, bool):
            pages.append(page)
    return tuple(pages)


def _hybrid_coverage(payload: object) -> float | None:
    """Return the Hybrid branch coverage score from a checkpoint channel.

    Args:
        payload: Deserialized ``branch_results`` channel.

    Returns:
        Coverage score, or None when the Hybrid branch did not store one.
    """

    if not isinstance(payload, list):
        return None
    for item in cast(list[object], payload):
        mapping = _json_mapping(item)
        if mapping.get("kind") != "hybrid":
            continue
        score = mapping.get("coverage_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return float(score)
    return None


def _hybrid_diagnostic_ids(payload: object, field: str) -> tuple[str, ...]:
    """Return one ID list from the Hybrid branch's persisted diagnostics.

    Args:
        payload: Deserialized ``branch_results`` channel.
        field: ``fused_ids``, ``rerank_pool_ids``, or ``selected_ids``.

    Returns:
        String chunk ids, or empty when the branch or field is absent.
    """

    if not isinstance(payload, list):
        return ()
    for item in cast(list[object], payload):
        mapping = _json_mapping(item)
        if mapping.get("kind") != "hybrid" and mapping.get("family") not in {
            "hybrid",
            "Hybrid",
        }:
            continue
        diagnostics = _json_mapping(mapping.get("hybrid_diagnostics"))
        raw = diagnostics.get(field)
        if isinstance(raw, list):
            return tuple(str(value) for value in cast(list[object], raw))
        return ()
    return ()


def _pages_for_chunk_ids(
    connection: psycopg.Connection,
    chunk_ids: Sequence[str],
) -> dict[str, int]:
    """Map chunk ids to ``page_number`` through the operator connection.

    Args:
        connection: Operator database connection.
        chunk_ids: Chunk id strings from stage diagnostics.

    Returns:
        Chunk id to page for rows that carry an integer page.
    """

    unique = [item for item in dict.fromkeys(chunk_ids) if item]
    if not unique:
        return {}
    rows = connection.execute(
        """
        SELECT id::text, page_number
        FROM app.document_chunks
        WHERE id = ANY(%s::uuid[])
        """,
        (unique,),
    ).fetchall()
    return {
        str(row[0]): int(row[1])
        for row in rows
        if isinstance(row[1], int) and not isinstance(row[1], bool)
    }


def _citation_failures(payload: object) -> tuple[str, ...]:
    """Return deterministic citation failure codes.

    Args:
        payload: Deserialized verification channel.

    Returns:
        Failure codes. Empty when verification stored none.
    """

    raw = _json_mapping(payload).get("deterministic_failures")
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for item in cast(list[object], raw):
        value = getattr(item, "value", None)
        text = value if isinstance(value, str) else str(item)
        names.append(text.rsplit(".", 1)[-1])
    return tuple(names)


def _string_tuple(value: object) -> tuple[str, ...]:
    """Keep only string items from a checkpoint tuple.

    Args:
        value: Candidate failure-code tuple.

    Returns:
        String items, or empty when the value is not a tuple of strings.
    """

    if not isinstance(value, tuple):
        return ()
    return tuple(
        item for item in cast(tuple[object, ...], value) if isinstance(item, str)
    )


def _measured_source_resolution(value: object) -> SourceResolutionStage:
    """Map a measured resolution token, or keep the dataclass default.

    Args:
        value: Exported ``source_resolution``.

    Returns:
        Named stage when the token is one of the known values.
    """

    try:
        return SourceResolutionStage(str(value or ""))
    except ValueError:
        return SourceResolutionStage.UNSCOPED


if __name__ == "__main__":
    raise SystemExit(main())


def set_search_scope(scope: str) -> None:
    """Select the client source preference for reusable conversation probes."""
    if scope not in {"auto", "company_documents", "general_knowledge", "web"}:
        raise ValueError("invalid_search_scope")
    global _search_scope_override
    _search_scope_override = scope


def create_conversation(client: httpx.Client, base_url: str, token: str) -> str:
    """Create one authorized conversation for multi-turn probes."""
    return _create_conversation(client, base_url, token)


def ask_one(
    client: httpx.Client, base_url: str, token: str, conversation_id: str, question: str
) -> dict[str, object]:
    """Send one user turn through the normal admission and SSE path."""
    return _ask_one(client, base_url, token, conversation_id, question)
