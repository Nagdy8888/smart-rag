"""Print non-secret overlay ingest gates. Never prints credentials or source text."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
PDF_NAME = (
    "building-applications-with-ai-agents-designing-and-implementing-"
    "multiagent-systems-1 (1).pdf"
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


def _merged_env() -> dict[str, str]:
    """Return ``.env`` overlaid by ``.env.compose``.

    Returns:
        Combined mapping. Compose wins on conflicts.
    """

    merged = _parse_env(REPO / ".env")
    merged.update(_parse_env(REPO / ".env.compose"))
    return merged


def main() -> int:
    """Print boolean and status evidence for Packet 9/14 preconditions.

    Returns:
        Process exit code.
    """

    env = _merged_env()
    for key in (
        "APP_ENV",
        "MOCK_MODEL_MODE",
        "LANGSMITH_TRACING",
        "LANGSMITH_EXPORT_IO",
        "LANGSMITH_PROJECT",
        "WORKER_GRAPH_ENABLED",
        "SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED",
    ):
        print(f"{key}={env.get(key, '')}")
    print(
        "openai_key_present=" + str(bool(env.get("OPENAI_API_KEY", "").strip())).lower()
    )
    print(
        "langsmith_key_present="
        + str(bool(env.get("LANGSMITH_API_KEY", "").strip())).lower()
    )
    print("supabase_url_set=" + str(bool(env.get("SUPABASE_URL", "").strip())).lower())
    print(
        "operator_db_set="
        + str(
            bool(
                env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
                or env.get("WORKER_SUPABASE_DB_URL", "").strip()
            )
        ).lower()
    )
    print(
        "anon_set="
        + str(
            bool(
                env.get("SUPABASE_ANON_KEY", "").strip()
                or env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
            )
        ).lower()
    )
    print(
        "storage_admin_present="
        + str(bool(env.get("SUPABASE_STORAGE_ADMIN_SECRET", "").strip())).lower()
    )
    pdf = REPO / "dataset" / PDF_NAME
    print(f"pdf_exists={str(pdf.is_file()).lower()}")
    if pdf.is_file():
        payload = pdf.read_bytes()
        print(f"pdf_bytes={len(payload)}")
        print(f"pdf_sha256={hashlib.sha256(payload).hexdigest()}")
    openai = env.get("OPENAI_API_KEY", "").strip()
    if openai:
        headers = {"Authorization": f"Bearer {openai}"}
        with httpx.Client(timeout=30.0) as client:
            models = client.get("https://api.openai.com/v1/models", headers=headers)
            print(f"openai_models_status={models.status_code}")
            for path in (
                "/v1/organization",
                "/v1/organization/projects",
                "/dashboard/billing/subscription",
            ):
                response = client.get(f"https://api.openai.com{path}", headers=headers)
                print(
                    f"openai_path_{path.replace('/', '_')}_status={response.status_code}"
                )
    langsmith = env.get("LANGSMITH_API_KEY", "").strip()
    endpoint = env.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip(
        "/"
    )
    if langsmith:
        headers = {"x-api-key": langsmith}
        with httpx.Client(timeout=30.0) as client:
            for path in ("/info", "/api/v1/info", "/api/v1/workspaces"):
                response = client.get(f"{endpoint}{path}", headers=headers)
                print(
                    f"langsmith_{path.replace('/', '_')}_status={response.status_code}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
