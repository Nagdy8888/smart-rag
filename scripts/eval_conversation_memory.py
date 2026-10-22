"""Run connected development questions through one authenticated app conversation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
from langchain_core.runnables import RunnableConfig
from smart_rag_core.settings.base import snapshot_process_environ

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from scripts import run_company_ask as ask  # noqa: E402


def source_fingerprint() -> str:
    """Hash application source, including untracked modules and pinned prompts."""
    digest = hashlib.sha256()
    for root in (
        REPO / "apps/agents/src",
        REPO / "apps/backend/src",
        REPO / "packages/core/src",
    ):
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".md"}:
                digest.update(path.relative_to(REPO).as_posix().encode("utf8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
    return digest.hexdigest()


def assess(turn: dict[str, Any], text: str, citations: list[Any]) -> list[str]:
    """Score recall, native formats, grounding and code explanations independently."""
    issues: list[str] = []
    kind = turn["check"]
    lower = text.casefold()
    refusal = bool(
        re.search(
            r"insufficient|could not support|cannot (?:find|answer)|not (?:provided|specified)|does not (?:provide|contain)|لا (?:تتوفر|يوجد)|غير متاح",
            lower,
        )
    )
    if not text.strip():
        issues.append("empty_answer")
    for pattern in turn.get("required_patterns", []):
        if not re.search(pattern, text, flags=re.I):
            issues.append("required_topic_missing:" + pattern)
    if kind in {"recall7", "recall9", "final_recall"}:
        if "harbor maple" not in lower:
            issues.append("nickname_forgotten")
        pattern = (
            r"\b(?:7|seven)\b|سبعة" if kind == "recall7" else r"\b(?:9|nine)\b|تسعة|تسع"
        )
        if not re.search(pattern, lower):
            issues.append("current_reviewer_limit_forgotten")
        if kind != "recall7" and re.search(
            r"\b(?:revised|changed|updated)\s+from\s+(?:nine|9)\b", lower
        ):
            issues.append("current_reviewer_limit_contradicted")
    if kind in {"language_recall", "final_recall"}:
        if not re.search(r"english|الإنجليزية|الانجليزية", lower) or not re.search(
            r"arabic|العربية", lower
        ):
            issues.append("language_preference_forgotten")
    if turn["scope"] == "company_documents" and kind != "refusal":
        if refusal and len(text) < 350:
            issues.append("supported_followup_refused")
        if not any(not c.get("source_unavailable") for c in citations):
            issues.append("no_authorized_citations")
    if kind == "refusal" and not refusal:
        issues.append("unsupported_fact_not_refused")
    if kind in {"table", "arabic_table"} and not re.search(r"(?m)^\s*\|.+\|", text):
        issues.append("table_missing")
    if kind == "arabic_table":
        table_text = "\n".join(
            line for line in text.splitlines() if line.lstrip().startswith("|")
        )
        if len(re.findall(r"[\u0600-\u06ff]", table_text)) < 30:
            issues.append("arabic_table_cells_missing")
    if kind == "figure" and not re.search(r"\[\[figure:[A-Za-z0-9-]{1,64}\]\]", text):
        issues.append("source_image_missing")
    if kind.startswith("arabic_") and len(re.findall(r"[\u0600-\u06ff]", text)) < 30:
        issues.append("arabic_missing")
    if kind in {"code", "code_explanation"}:
        blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", text, re.S)
        if not blocks:
            issues.append("python_block_missing")
        for block in blocks:
            try:
                ast.parse(block)
            except SyntaxError:
                issues.append("invalid_python")
        if kind == "code_explanation":
            prose = re.sub(r"```.*?```", "", text, flags=re.S)
            if len(prose.strip()) < 80 or not (
                "actor" in prose.casefold() and "critic" in prose.casefold()
            ):
                issues.append("substantive_code_explanation_missing")
    return issues


def main() -> int:
    """Run one conversation; credentials remain in the environment, never logs."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Git is required to record evaluation provenance")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--auth-url", default="http://127.0.0.1:54321")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO / "tests/fixtures/query-memory-linked50-v4.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--conversation-id", type=UUID)
    parser.add_argument("--start-at", type=int, default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.dataset.read_text(encoding="utf8"))
    turns = data["turns"][: args.limit]
    total_turns = len(turns)
    if not 1 <= args.start_at <= total_turns:
        parser.error("--start-at must identify a turn in the selected dataset")
    if args.start_at > 1 and args.conversation_id is None:
        parser.error("--start-at requires --conversation-id to preserve chat context")
    turns = turns[args.start_at - 1 :]
    if (args.out / "results.json").exists():
        raise SystemExit("Use a fresh output folder to preserve the existing run.")
    environ = snapshot_process_environ()
    checkpoint = None
    if environ.get("EVAL_DB_URL"):
        from smart_rag_agents.query.checkpointer import open_query_checkpointer

        checkpoint = open_query_checkpointer(environ["EVAL_DB_URL"], max_size=1)
    rows: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=100) as client:
            response = client.post(
                args.auth_url + "/auth/v1/token?grant_type=password",
                headers={"apikey": environ["EVAL_ANON_KEY"]},
                json={
                    "email": environ["EVAL_USER_EMAIL"],
                    "password": environ["EVAL_USER_PASSWORD"],
                },
            )
            response.raise_for_status()
            token = response.json()["access_token"]
            headers = {"Authorization": "Bearer " + token}
            conversation = (
                str(args.conversation_id)
                if args.conversation_id is not None
                else ask.create_conversation(client, args.api, token)
            )
            (args.out / "provenance.json").write_text(
                json.dumps(
                    {
                        "dataset_id": data["dataset_id"],
                        "dataset_sha256": hashlib.sha256(
                            args.dataset.read_bytes()
                        ).hexdigest(),
                        "conversation_id": conversation,
                        "single_conversation": True,
                        "continuation": args.conversation_id is not None,
                        "start_at": args.start_at,
                        "application_source_sha256": source_fingerprint(),
                        "git_head": subprocess.check_output(  # noqa: S603 - fixed arguments, resolved executable
                            [git_executable, "rev-parse", "HEAD"], cwd=REPO, text=True
                        ).strip(),
                        "working_tree_sha256": hashlib.sha256(
                            subprocess.check_output(  # noqa: S603 - fixed arguments, resolved executable
                                [git_executable, "diff", "HEAD"], cwd=REPO
                            )
                            + b"".join(
                                path.read_bytes()
                                for path in sorted(
                                    REPO.glob(
                                        "apps/agents/src/smart_rag_agents/prompts/*.md"
                                    )
                                )
                            )
                        ).hexdigest(),
                    },
                    indent=2,
                ),
                encoding="utf8",
            )
            print(f"ONE CHAT: {conversation}", flush=True)
            for number, turn in enumerate(turns, args.start_at):
                print(
                    f"[{number:02}/{total_turns}] ASK {turn['id']}: {turn['question']}",
                    flush=True,
                )
                started = time.monotonic()
                ask.set_search_scope(turn["scope"])
                result = ask.ask_one(
                    client, args.api, token, conversation, turn["question"]
                )
                run_id = str(result.get("run_id") or "")
                message: dict[str, Any] = {}
                citations: list[Any] = []
                if run_id:
                    for _ in range(30):
                        page = client.get(
                            f"{args.api}/conversations/{conversation}/messages?limit=50",
                            headers=headers,
                        )
                        page.raise_for_status()
                        message = next(
                            (
                                m
                                for m in page.json().get("items", [])
                                if m.get("role") == "assistant"
                                and m.get("run_id") == run_id
                            ),
                            cast(dict[str, Any], {}),
                        )
                        if message:
                            break
                        time.sleep(0.5)
                    citation_response = client.get(
                        f"{args.api}/runs/{run_id}/citations", headers=headers
                    )
                    citation_response.raise_for_status()
                    citations = citation_response.json()
                text = html.unescape(
                    message.get("content") or str(result.get("answer") or "")
                )
                memory: dict[str, Any] = {}
                if checkpoint and run_id:
                    snapshot = checkpoint.saver.get_tuple(
                        cast(
                            RunnableConfig,
                            {
                                "configurable": {
                                    "thread_id": conversation,
                                    "checkpoint_ns": "",
                                }
                            },
                        )
                    )
                    if snapshot:
                        state = snapshot.checkpoint["channel_values"]
                        records = cast(
                            list[dict[str, Any]], state.get("memory_records") or []
                        )
                        memory = {
                            "summary_status": state.get("memory_summary_status"),
                            "loaded_records": len(records),
                            "summary_loaded": any(
                                r.get("role") == "system" for r in records
                            ),
                            "verifier_verdicts": cast(
                                dict[str, Any], state.get("verification") or {}
                            ).get("verifier_link_verdicts", []),
                        }
                issues = assess(turn, text, citations)
                if not run_id:
                    issues.append(
                        f"admission_http_{result.get('http_status', 'unknown')}"
                    )
                if not message:
                    issues.append("assistant_persistence_missing")
                row = {
                    "id": turn["id"],
                    "conversation_id": conversation,
                    "run_id": run_id,
                    "question": turn["question"],
                    "check": turn["check"],
                    "stream": result,
                    "answer": text,
                    "citations": citations,
                    "memory": memory,
                    "issues": issues,
                    "seconds": round(time.monotonic() - started, 2),
                }
                rows.append(row)
                (args.out / "results.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf8"
                )
                print(
                    f"[{number:02}/{total_turns}] {'PASS' if not issues else 'FAIL'} {turn['id']} {row['seconds']}s citations={len(citations)} memory={memory} issues={issues}",
                    flush=True,
                )
                print("ANSWER: " + text[:240].replace("\n", " | "), flush=True)
                if not run_id:
                    print(
                        "STOP: admission failed; remaining turns were not sent.",
                        flush=True,
                    )
                    break
                time.sleep(2)
        summary = {
            "turns": len(rows),
            "planned_turns": len(turns),
            "start_at": args.start_at,
            "continuation": args.conversation_id is not None,
            "complete": len(rows) == len(turns) and all(r["run_id"] for r in rows),
            "passed": sum(not r["issues"] for r in rows),
            "conversation_count": len({r["conversation_id"] for r in rows}),
            "summary_writes": sum(
                r["memory"].get("summary_status") == "written" for r in rows
            ),
            "failures": [
                {"id": r["id"], "issues": r["issues"]} for r in rows if r["issues"]
            ],
            "interpretation": "development checks, not independent semantic adjudication or holdout",
        }
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf8"
        )
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        if checkpoint:
            checkpoint.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
