"""Contract tests for the isolated AnyDoc bake-off sandbox."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_IMAGE,
    FORBIDDEN_SANDBOX_ENV,
)
from smart_rag_core.evaluation.parser_bakeoff.lanes import anydoc_docker_command
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.ingestion.parser.limits import PARSER_SANDBOX_MEMORY_MB_HARD

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "infra" / "parser-bakeoff" / "Dockerfile"
RUNNER = REPO_ROOT / "infra" / "parser-bakeoff" / "runner.py"


def test_anydoc_dockerfile_is_non_root_and_local_only() -> None:
    """Bake-off image drops privileges and pins local AnyDoc."""

    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER 10001:10001" in content
    assert (
        "COPY infra/parser-bakeoff/sandbox_evaluation_init.py "
        "/app/smart_rag_core/evaluation/__init__.py"
    ) in content
    assert (
        "COPY infra/parser-bakeoff/sandbox_adapters_init.py "
        "/app/smart_rag_core/ingestion/parser/adapters/__init__.py"
    ) in content
    eval_stub = (
        REPO_ROOT / "infra" / "parser-bakeoff" / "sandbox_evaluation_init.py"
    ).read_text(encoding="utf-8")
    adapter_stub = (
        REPO_ROOT / "infra" / "parser-bakeoff" / "sandbox_adapters_init.py"
    ).read_text(encoding="utf-8")
    for stub in (eval_stub, adapter_stub):
        assert not any(
            line.lstrip().startswith(("import ", "from ")) for line in stub.splitlines()
        )
    requirements = (
        REPO_ROOT / "infra" / "parser-bakeoff" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "firecrawl-anydoc==0.2.4" in requirements
    assert "pypdf==5.9.0" in requirements
    adapters = (
        REPO_ROOT
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "ingestion"
        / "parser"
        / "adapters"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "anydoc" not in adapters.lower()


def test_anydoc_docker_command_is_airgapped() -> None:
    """Runtime argv must include network none, resource caps, and no secrets."""

    command = anydoc_docker_command(
        container_name="smart-rag-anydoc-test",
        input_dir=Path("input-dir"),
        output_dir=Path("output-dir"),
        request_json='{"content_hash":"abc"}',
    )
    joined = " ".join(command)
    assert "--network" in command
    assert "none" in command
    assert "--read-only" in command
    assert "10001:10001" in command
    assert f"{PARSER_SANDBOX_MEMORY_MB_HARD}m" in joined
    assert "--cpus" in command
    assert "--pids-limit" in command
    assert "RAYON_NUM_THREADS=1" in joined
    assert "size=256m" in joined
    assert ANYDOC_IMAGE in command
    for secret in FORBIDDEN_SANDBOX_ENV:
        assert secret not in joined
    runner = RUNNER.read_text(encoding="utf-8")
    assert "convert_with_anydoc" in runner
    assert "print(markdown" not in runner
    assert "FIRECRAWL_API_KEY" not in runner
    constants = (
        REPO_ROOT
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "evaluation"
        / "parser_bakeoff"
        / "constants.py"
    ).read_text(encoding="utf-8")
    assert 'ANYDOC_OCR_MODE = "reject"' in constants
    assert 'ANYDOC_SCANNED_PAGES = "openai_ocr"' in constants
    ocr_gateway = (
        REPO_ROOT
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "gateways"
        / "openai_page_ocr.py"
    ).read_text(encoding="utf-8")
    assert "files.create" not in ocr_gateway
    assert "client.files" not in ocr_gateway
    assert "traced_openai_client" not in ocr_gateway
    assert "wrap_openai(" not in ocr_gateway
    assert "FIRECRAWL" not in ocr_gateway
    assert "store=False" in ocr_gateway
    assert '"emit_markdown"' in runner
    assert '"probe_ocr_pages"' in runner


def test_anydoc_docker_command_rejects_secret_request() -> None:
    """Request JSON must not smuggle provider secrets."""

    try:
        anydoc_docker_command(
            container_name="x",
            input_dir=Path("input-dir"),
            output_dir=Path("output-dir"),
            request_json='{"OPENAI_API_KEY":"secret"}',
        )
    except BakeoffError as exc:
        assert exc.code == "sandbox_secret"
    else:
        raise AssertionError("secret request must fail closed")
