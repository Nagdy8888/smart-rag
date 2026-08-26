"""Print redacted in-container DSN topology. Never prints credentials."""

from __future__ import annotations

import subprocess
from urllib.parse import urlparse


def _classify(raw: str) -> str:
    """Return host/user/port labels.

    Args:
        raw: Environment assignment ``NAME=value``.

    Returns:
        Classification string.
    """

    name, _, value = raw.partition("=")
    parsed = urlparse(value)
    host = parsed.hostname or ""
    user = (parsed.username or "").split(".")[0]
    hosted = host.endswith(".supabase.co") or host.endswith("pooler.supabase.com")
    loopback = host in {"127.0.0.1", "localhost", "host.docker.internal"}
    return (
        f"{name} user={user or '-'} host_suffix={host[-28:]} "
        f"port={parsed.port or 'default'} hosted={hosted} loopback={loopback}"
    )


def _service_env(service: str, names: tuple[str, ...]) -> None:
    """Print classified environment values from one Compose service.

    Args:
        service: Compose service name.
        names: Environment variable names.
    """

    command = [
        "docker",
        "compose",
        "--env-file",
        ".env.compose",
        "exec",
        "-T",
        service,
        "python",
        "-c",
        "import os; "
        + "; ".join(f"print('{name}='+(os.environ.get('{name}') or ''))" for name in names),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"service={service} exit={completed.returncode}")
    if completed.returncode != 0:
        err = (completed.stderr or "").replace("\n", " ")[:200]
        print(f"stderr_redacted_len={len(completed.stderr or '')} hint={err[:80]}")
        return
    for line in completed.stdout.splitlines():
        if "=" in line:
            print(_classify(line))


def main() -> int:
    """Classify API and worker database targets.

    Returns:
        Process exit code.
    """

    _service_env(
        "api",
        (
            "SUPABASE_URL",
            "SUPABASE_DB_URL",
            "LANGGRAPH_CHECKPOINT_URL",
            "LIGHTRAG_DB_URL",
        ),
    )
    _service_env(
        "worker",
        (
            "SUPABASE_URL",
            "SUPABASE_DB_URL",
            "LANGGRAPH_CHECKPOINT_URL",
            "LIGHTRAG_DB_URL",
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
