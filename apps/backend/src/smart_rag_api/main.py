"""FastAPI application entrypoint for the Smart RAG backend.

Importing this module must not construct provider clients, database pools, or
other networked dependencies. The app object exists so process startup and
import smoke tests can load the transport boundary.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Smart RAG API",
    version="0.1.0",
    description=(
        "Phase 1 foundation transport scaffold. Business routes are not "
        "implemented; readiness is unconfigured until later phases."
    ),
)


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    """Report process liveness only.

    Returns:
        A mapping with ``status=live``. Does not imply dependency readiness,
        authentication, retrieval, or ingestion capability.
    """

    return {"status": "live"}


@app.get("/health/ready", tags=["health"])
def ready() -> dict[str, str]:
    """Report foundation readiness as unconfigured.

    Returns:
        A mapping with ``status=unconfigured``. Required local dependencies and
        application wiring are owned by later Phase 1/2 packets.
    """

    return {
        "status": "unconfigured",
        "detail": "Phase 1 foundation scaffold; dependencies not wired.",
    }


def run() -> None:
    """Run the API with uvicorn when invoked as a console script.

    Side Effects:
        Starts an HTTP server. Does not initialize providers at import time.

    Raises:
        ModuleNotFoundError: If uvicorn is not installed in the environment.
    """

    import uvicorn

    uvicorn.run("smart_rag_api.main:app", host="0.0.0.0", port=8000, factory=False)


__all__ = ["app", "live", "ready", "run"]
