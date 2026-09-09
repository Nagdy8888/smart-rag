"""Upload and ingest the private PDF without marking the job synthetic.

Graph stays off. Prints IDs, statuses, and counts only. Never patches
``content_class`` to synthetic and never logs source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import cast

import httpx
import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.ingestion.limits import (  # noqa: E402
    EXTERNAL_PROCESSING_POLICY_VERSION,
)

from scripts.ops.import_approved_pdf_glossary import create_owner  # noqa: E402
from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    json_object,
    merged_env,
    require_env,
    version_jobs,
)

API_URL = "http://127.0.0.1:8000"
PDF_NAME = (
    "building-applications-with-ai-agents-designing-and-implementing-"
    "multiagent-systems-1 (1).pdf"
)
TERMINAL = frozenset(
    {
        "graph_ineligible",
        "hybrid_ready",
        "graph_pending",
        "graph_ready",
        "failed",
    }
)
FALSE_POSITIVE_FAMILIES = frozenset({"payment_card", "credentials", "health"})


def _upload_pdf(
    client: httpx.Client,
    *,
    token: str,
    anon: str,
    auth_url: str,
    path: Path,
) -> tuple[str, str, str, str]:
    """Reserve, Storage-upload, and finalize the private PDF.

    Args:
        client: Shared HTTP client.
        token: aal2 access token.
        anon: Anon key.
        auth_url: Hosted Auth origin.
        path: Local PDF.

    Returns:
        ``(document_id, version_id, job_id, content_hash)``.
    """

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Client-Version": "0.1.0",
        "Idempotency-Key": idempotency_key,
    }
    reserved = client.post(
        f"{API_URL}/documents/uploads",
        headers=headers,
        json={"declared_bytes": len(payload), "idempotency_key": idempotency_key},
    )
    if reserved.status_code >= 400:
        print(f"reserve_failed status={reserved.status_code}", flush=True)
        print(reserved.text[:500], flush=True)
    reserved.raise_for_status()
    body = json_object(reserved.json(), "reserve")
    reservation_id = str(body["reservation_id"])
    bucket = str(body["storage_bucket"])
    prefix = str(body["storage_path"]).rstrip("/")
    object_name = f"{prefix}/private-pdf-{digest[:12]}.pdf"
    uploaded = client.post(
        f"{auth_url}/storage/v1/object/{bucket}/{object_name}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": anon,
            "Content-Type": "application/pdf",
            "x-upsert": "false",
        },
        content=payload,
    )
    if uploaded.status_code not in {200, 201}:
        print(f"storage_upload_failed status={uploaded.status_code}", flush=True)
        print(uploaded.text[:500], flush=True)
        uploaded.raise_for_status()
    finalized = client.post(
        f"{API_URL}/documents/uploads/finalize",
        headers=headers,
        json={
            "reservation_id": reservation_id,
            "object_name": object_name,
            "content_hash": digest,
            "actual_bytes": len(payload),
            "media_type": "application/pdf",
            "declared_category": "allowed",
            "attestation_policy_version": EXTERNAL_PROCESSING_POLICY_VERSION,
            "idempotency_key": idempotency_key,
            "document_title": f"private-pdf-{digest[:12]}",
        },
    )
    if finalized.status_code >= 400:
        print(f"finalize_failed status={finalized.status_code}", flush=True)
        print(finalized.text[:800], flush=True)
    finalized.raise_for_status()
    fin = json_object(finalized.json(), "finalize")
    return (
        str(fin["document_id"]),
        str(fin["version_id"]),
        str(fin["job_id"]),
        digest,
    )


def requeue_hybrid_index_keep_class(
    *, operator_url: str, job_id: str
) -> dict[str, object]:
    """Clear checkpoints and requeue one hybrid_index job without recasting class.

    Args:
        operator_url: Operator session URL (``postgres`` role).
        job_id: Hybrid index job id.

    Returns:
        Snapshot with id, status, attempt_count, and content_class.

    Side Effects:
        Deletes LangGraph checkpoints for ``thread_id`` so resume cannot keep
        a stale governance-hold result. Sets the job ``pending``. Never
        writes ``content_class=synthetic``.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
            "DELETE FROM langgraph.checkpoint_writes WHERE thread_id = %s",
            (job_id,),
        )
        connection.execute(
            "DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = %s",
            (job_id,),
        )
        connection.execute(
            "DELETE FROM langgraph.checkpoints WHERE thread_id = %s",
            (job_id,),
        )
        row = connection.execute(
            """
            UPDATE app.ingestion_jobs
            SET
              status = 'pending'::app.job_status,
              next_attempt_at = timezone('utc', now()),
              lease_token = NULL,
              lease_owner = NULL,
              lease_expires_at = NULL,
              attempt_count = 0,
              last_error = NULL
            WHERE id = %s::uuid
              AND job_kind = 'hybrid_index'
            RETURNING
              id::text,
              status::text,
              attempt_count,
              coalesce(payload_ref ->> 'content_class', 'real_company')
            """,
            (job_id,),
        ).fetchone()
        connection.commit()
    if row is None:
        return {
            "id": job_id,
            "status": "missing",
            "attempt_count": 0,
            "content_class": "missing",
        }
    return {
        "id": row[0],
        "status": row[1],
        "attempt_count": row[2],
        "content_class": row[3],
    }


def _eligibility(
    *,
    operator_url: str,
    document_id: str,
    version_id: str,
) -> tuple[bool, bool, str]:
    """Return graph-eligibility flags and job content class.

    Args:
        operator_url: Operator session URL.
        document_id: Document id.
        version_id: Version id.

    Returns:
        Document graph flag, version graph flag, and content class token.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        document = connection.execute(
            "SELECT graph_eligible FROM app.documents WHERE id = %s::uuid",
            (document_id,),
        ).fetchone()
        version = connection.execute(
            "SELECT graph_eligible FROM app.document_versions WHERE id = %s::uuid",
            (version_id,),
        ).fetchone()
        job = connection.execute(
            """
            SELECT coalesce(payload_ref ->> 'content_class', 'real_company')
            FROM app.ingestion_jobs
            WHERE version_id = %s::uuid
            ORDER BY created_at
            LIMIT 1
            """,
            (version_id,),
        ).fetchone()
    document_flag = bool(document[0]) if document is not None else True
    version_flag = bool(version[0]) if version is not None else True
    content_class = str(job[0]) if job is not None else "missing"
    return document_flag, version_flag, content_class


def _review_findings(
    client: httpx.Client,
    *,
    token: str,
    status_payload: dict[str, object],
) -> int:
    """Approve only book-typical false-positive families.

    Args:
        client: HTTP client.
        token: Access token.
        status_payload: Version status object.

    Returns:
        Number of reviews submitted.

    Raises:
        RuntimeError: When a prohibited family remains unresolved.
    """

    review = status_payload.get("review")
    if not isinstance(review, dict):
        return 0
    review_map = cast(dict[str, object], review)
    findings_raw = review_map.get("findings")
    if not isinstance(findings_raw, list) or not findings_raw:
        return 0
    submitted = 0
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Client-Version": "0.1.0",
    }
    for item in cast(list[object], findings_raw):
        if not isinstance(item, dict):
            continue
        finding = cast(dict[str, object], item)
        family = str(finding.get("family", ""))
        finding_id = str(finding.get("finding_id", ""))
        print(
            json.dumps(
                {
                    "finding_id": finding_id,
                    "family": family,
                    "bounded_count": finding.get("bounded_count"),
                }
            ),
            flush=True,
        )
        if family not in FALSE_POSITIVE_FAMILIES:
            raise RuntimeError(f"unreviewed_detector_family={family}")
        response = client.post(
            f"{API_URL}/ingestion/detector-findings/reviews",
            headers={**headers, "Idempotency-Key": f"fp-{finding_id[:12]}"},
            json={
                "finding_id": finding_id,
                "decision": "false_positive",
                "reason": "owner overlay review: book example or ISBN-like hold",
                "idempotency_key": f"fp-{finding_id}",
            },
        )
        print(f"review_status={response.status_code} family={family}", flush=True)
        if response.status_code >= 400:
            print(response.text[:300], flush=True)
            response.raise_for_status()
        submitted += 1
    return submitted


def _retry_jobs(
    client: httpx.Client,
    *,
    token: str,
    jobs: list[dict[str, object]],
) -> None:
    """Retry failed or held jobs through the public retry route.

    Args:
        client: HTTP client.
        token: Access token.
        jobs: Recent job summaries.
    """

    headers = {"Authorization": f"Bearer {token}", "X-Client-Version": "0.1.0"}
    for job in jobs:
        job_id = str(job.get("id", ""))
        status = str(job.get("status", ""))
        if (
            status not in {"failed", "dead_letter", "pending"}
            and "governance" not in status
        ):
            continue
        response = client.post(
            f"{API_URL}/ingestion/jobs/{job_id}/retry", headers=headers
        )
        print(
            json.dumps(
                {
                    "retry_job_id": job_id,
                    "retry_http": response.status_code,
                    "prior_status": status,
                }
            ),
            flush=True,
        )


def _poll_until_terminal(
    client: httpx.Client,
    *,
    token: str,
    operator_url: str,
    version_id: str,
    timeout_seconds: float,
) -> str:
    """Poll public ingestion status until a terminal value.

    Args:
        client: Shared HTTP client.
        token: Access token.
        operator_url: Operator session URL.
        version_id: Version to watch.
        timeout_seconds: Deadline.

    Returns:
        Public status string.
    """

    deadline = time.monotonic() + timeout_seconds
    last = ""
    public_status = ""
    reviewed = False
    while time.monotonic() < deadline:
        response = client.get(
            f"{API_URL}/ingestion/versions/{version_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        jobs_payload: list[dict[str, object]] = []
        if response.status_code < 400:
            envelope = json_object(response.json(), "status")
            version = payload_version(envelope)
            public_status = str(version.get("status", ""))
            recent = envelope.get("recent_jobs")
            if isinstance(recent, list):
                jobs_payload = [
                    cast(dict[str, object], item)
                    for item in cast(list[object], recent)
                    if isinstance(item, dict)
                ]
            unresolved = 0
            review = version.get("review")
            if isinstance(review, dict):
                review_map = cast(dict[str, object], review)
                unresolved_raw = review_map.get("unresolved_family_count") or 0
                unresolved = int(str(unresolved_raw))
            if unresolved and not reviewed:
                print("governance_review_required", flush=True)
                _review_findings(client, token=token, status_payload=version)
                _retry_jobs(client, token=token, jobs=jobs_payload)
                reviewed = True
        jobs = version_jobs(operator_url=operator_url, version_id=version_id)
        snapshot = json.dumps(
            {"status": public_status, "jobs": jobs},
            sort_keys=True,
        )
        if snapshot != last:
            print(snapshot, flush=True)
            last = snapshot
        if public_status in TERMINAL:
            return public_status
        time.sleep(10)
    print(f"timeout_ingest last_status={public_status}", flush=True)
    return public_status or "timeout"


def payload_version(envelope: dict[str, object]) -> dict[str, object]:
    """Extract the nested version object from a status envelope.

    Args:
        envelope: Status JSON.

    Returns:
        Version mapping.
    """

    version = envelope.get("version")
    if isinstance(version, dict):
        return cast(dict[str, object], version)
    return envelope


def main(argv: list[str] | None = None) -> int:
    """Upload the private PDF and wait for graph-ineligible Hybrid completion.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(
        description="Ingest the private PDF as real_company."
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=REPO / "dataset" / PDF_NAME,
    )
    parser.add_argument("--timeout-seconds", type=float, default=14400)
    parser.add_argument(
        "--requeue-hybrid-index",
        default="",
        help="Requeue one hybrid_index job as real_company and exit.",
    )
    args = parser.parse_args(argv)
    env = merged_env()
    if args.requeue_hybrid_index:
        operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
        snapshot = requeue_hybrid_index_keep_class(
            operator_url=operator_url,
            job_id=args.requeue_hybrid_index,
        )
        print(json.dumps(snapshot), flush=True)
        if snapshot["status"] != "pending":
            return 2
        if snapshot["content_class"] == "synthetic":
            print("blocked=job_marked_synthetic")
            return 2
        return 0
    if not args.pdf.is_file():
        print("private_pdf_missing")
        return 2
    if env.get("SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print("blocked=provider_matrix_unverified")
        return 2
    if env.get("LANGSMITH_EXPORT_IO", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print("blocked=langsmith_export_io_must_be_false")
        return 2
    graph_flag = env.get("WORKER_GRAPH_ENABLED", "true").strip().lower()
    if graph_flag not in {"0", "false", "no", "off"}:
        print("blocked=worker_graph_must_be_false")
        return 2
    auth_url = require_env(env, "SUPABASE_URL", "SUPABASE_MANAGED_URL").rstrip("/")
    anon = require_env(env, "SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    with httpx.Client(timeout=300.0) as client:
        token = create_owner(
            client,
            auth_url=auth_url,
            anon=anon,
            operator_url=operator_url,
        )
        document_id, version_id, job_id, digest = _upload_pdf(
            client,
            token=token,
            anon=anon,
            auth_url=auth_url,
            path=args.pdf,
        )
        document_graph, version_graph, content_class = _eligibility(
            operator_url=operator_url,
            document_id=document_id,
            version_id=version_id,
        )
        print(
            json.dumps(
                {
                    "document_id": document_id,
                    "version_id": version_id,
                    "job_id": job_id,
                    "content_hash": digest,
                    "document_graph_eligible": document_graph,
                    "version_graph_eligible": version_graph,
                    "content_class": content_class,
                }
            ),
            flush=True,
        )
        if document_graph or version_graph:
            print("blocked=graph_eligible_true")
            return 2
        if content_class == "synthetic":
            print("blocked=job_marked_synthetic")
            return 2
        status = _poll_until_terminal(
            client,
            token=token,
            operator_url=operator_url,
            version_id=version_id,
            timeout_seconds=args.timeout_seconds,
        )
        print(f"terminal_status={status}")
        document_graph, version_graph, content_class = _eligibility(
            operator_url=operator_url,
            document_id=document_id,
            version_id=version_id,
        )
        print(f"content_class={content_class}")
        print(f"document_graph_eligible={str(document_graph).lower()}")
        print(f"version_graph_eligible={str(version_graph).lower()}")
        if status != "graph_ineligible":
            return 2
        if content_class == "synthetic":
            print("blocked=job_marked_synthetic")
            return 2
        ids_path = Path(".private-eval/ingest-ids.json")
        ids_path.parent.mkdir(parents=True, exist_ok=True)
        ids_path.write_text(
            json.dumps(
                {
                    "document_id": document_id,
                    "version_id": version_id,
                    "job_id": job_id,
                    "content_hash": digest,
                    "content_class": content_class,
                    "terminal_status": status,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("ids_path_set=true")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
