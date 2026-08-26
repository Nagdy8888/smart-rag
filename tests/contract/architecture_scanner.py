"""AST scanner for query-vertical module, facade, and test-import budgets."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

HARD_LINE_CAP = 600
TARGET_LINE_CAP = 400
TEST_LINE_TARGET = 500
DOC_LINE_TARGET = 300
MAX_TOP_LEVEL_DEFS = 12

QUERY_VERTICAL_ROOTS: tuple[str, ...] = (
    "apps/agents/src/smart_rag_agents/query",
    "apps/backend/src/smart_rag_api/services/sse",
    "apps/backend/src/smart_rag_api/services/sse_stream.py",
    "apps/backend/src/smart_rag_api/services/query_graph_runtime.py",
    "packages/core/src/smart_rag_core/query_admission",
    "packages/core/src/smart_rag_core/query_answer",
    "packages/core/src/smart_rag_core/query_profile",
    "packages/core/src/smart_rag_core/query_routing",
    "packages/core/src/smart_rag_core/retrieval/hybrid_run",
    "packages/core/src/smart_rag_core/observability/query_run_trace.py",
    "packages/core/src/smart_rag_core/observability/query_trace",
    "packages/core/src/smart_rag_core/evaluation/agent_eval",
    "scripts/agent_eval_cli",
    "packages/core/src/smart_rag_core/evaluation/langsmith_agent_runner",
    "packages/core/src/smart_rag_core/evaluation/online_agent_runner.py",
    "packages/core/src/smart_rag_core/evaluation/online_envelope.py",
    "packages/core/src/smart_rag_core/evaluation/online_suite.py",
)

QUERY_VERTICAL_TESTS: tuple[str, ...] = (
    "tests/unit/test_query_",
    "tests/unit/test_answer_verifier",
    "tests/unit/test_knowledge_scope.py",
    "tests/unit/test_langsmith_",
    "tests/unit/test_agent_eval.py",
    "tests/unit/test_query_agent_eval_trace.py",
    "tests/unit/test_query_run_sse_trace.py",
    "tests/unit/test_hybrid_run.py",
    "tests/unit/test_matrix_rule_precedence.py",
    "tests/unit/test_routing_plan_snapshots.py",
    "tests/unit/test_scope_graph_routes.py",
    "tests/contract/test_query_",
    "tests/contract/test_sse_",
    "tests/contract/test_query_admission_api.py",
)

QUERY_VERTICAL_DOCS: tuple[str, ...] = (
    "docs/agent/QUERY_ROUTING.md",
    "docs/development/phase-06-agent-intelligence-evidence.md",
    "docs/development/phase-06",
    "docs/development/LANGSMITH_TRACING.md",
    "docs/evaluation/PHASE6_EVAL_REGISTRY.md",
)

# Exact relative path -> reason. Must shrink to empty by final-gates.
ARCHITECTURE_EXCEPTIONS: dict[str, str] = {}


@dataclass(frozen=True)
class ArchitectureViolation:
    """One architecture-budget failure.

    Attributes:
        path: Repository-relative POSIX path.
        metric: Observed value.
        limit: Allowed maximum.
        kind: Which rule failed.
        packet: Suggested owning cleanup packet.
    """

    path: str
    metric: int
    limit: int
    kind: str
    packet: str

    def format(self) -> str:
        """Return a one-line report.

        Returns:
            Path, metric, limit, rule, and suggested packet.
        """

        return (
            f"{self.path}: {self.kind}={self.metric} limit={self.limit} "
            f"packet={self.packet}"
        )


def _posix(repo_root: Path, path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _is_exception(rel: str) -> bool:
    """Return whether ``rel`` has a temporary architecture exception."""

    return rel in ARCHITECTURE_EXCEPTIONS


def iter_query_vertical_python(repo_root: Path) -> list[Path]:
    """Return authored query-vertical production Python files.

    Args:
        repo_root: Repository root.

    Returns:
        Sorted file paths under the declared production roots.
    """

    found: list[Path] = []
    for root in QUERY_VERTICAL_ROOTS:
        target = repo_root / root
        if target.is_file() and target.suffix == ".py":
            found.append(target)
            continue
        if not target.is_dir():
            continue
        found.extend(sorted(target.rglob("*.py")))
    return found


def iter_query_vertical_tests(repo_root: Path) -> list[Path]:
    """Return query-vertical test modules.

    Args:
        repo_root: Repository root.

    Returns:
        Test paths whose relative POSIX path starts with a declared prefix.
    """

    found: list[Path] = []
    for path in sorted((repo_root / "tests").rglob("test_*.py")):
        rel = _posix(repo_root, path)
        if any(rel.startswith(prefix) for prefix in QUERY_VERTICAL_TESTS):
            found.append(path)
    return found


def _top_level_defs(tree: ast.AST) -> list[ast.AST]:
    """Return top-level class and function definitions."""

    return [
        node
        for node in getattr(tree, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def is_compatibility_facade(source: str) -> bool:
    """Return whether a module contains only re-exports and aliases.

    Args:
        source: Python source.

    Returns:
        True when every runtime statement is an import, ``__all__``, alias,
        or ``TYPE_CHECKING`` guard.
    """

    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Assign):
            names = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
            if names <= {"__all__"} or names:
                continue
            return False
        if isinstance(node, ast.AnnAssign):
            continue
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                continue
            if (
                isinstance(test, ast.Attribute)
                and isinstance(test.value, ast.Name)
                and test.attr == "TYPE_CHECKING"
            ):
                continue
            return False
        return False
    return True


def scan_line_budgets(repo_root: Path) -> list[ArchitectureViolation]:
    """Fail authored runtime modules over the 600-line hard cap.

    Args:
        repo_root: Repository root.

    Returns:
        Hard-cap violations. Target overruns are reported separately.
    """

    findings: list[ArchitectureViolation] = []
    for path in iter_query_vertical_python(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        source = path.read_text(encoding="utf-8")
        if is_compatibility_facade(source):
            continue
        count = len(source.splitlines())
        if count > HARD_LINE_CAP:
            findings.append(
                ArchitectureViolation(
                    rel, count, HARD_LINE_CAP, "physical_lines", "final-gates"
                )
            )
    return findings


def scan_line_targets(repo_root: Path) -> list[ArchitectureViolation]:
    """Report runtime modules over the 400-line target.

    Args:
        repo_root: Repository root.

    Returns:
        Target overruns that still respect the 600-line hard cap.
    """

    findings: list[ArchitectureViolation] = []
    for path in iter_query_vertical_python(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        source = path.read_text(encoding="utf-8")
        if is_compatibility_facade(source):
            continue
        count = len(source.splitlines())
        if TARGET_LINE_CAP < count <= HARD_LINE_CAP:
            findings.append(
                ArchitectureViolation(
                    rel, count, TARGET_LINE_CAP, "line_target", "tests-docs-dead-code"
                )
            )
    return findings


_ORCHESTRATION_FILES = frozenset(
    {
        "retriever.py",
        "service.py",
        "executors.py",
        "runtime.py",
        "graph.py",
        "main.py",
        "live_runtime.py",
    }
)


def scan_top_level_definitions(repo_root: Path) -> list[ArchitectureViolation]:
    """Fail orchestration and node modules with more than 12 top-level defs.

    Helper, schema, and mapping modules may exceed this count. Compatibility
    facades are ignored.

    Args:
        repo_root: Repository root.

    Returns:
        Definition-count violations for orchestration/node modules.
    """

    findings: list[ArchitectureViolation] = []
    nodes_root = "apps/agents/src/smart_rag_agents/query/nodes/"
    node_exceptions = {
        "__init__.py",
        "shared.py",
        "state_codec.py",
        "tokens.py",
        "topology.py",
    }
    for path in iter_query_vertical_python(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        in_nodes = rel.startswith(nodes_root) and path.name not in node_exceptions
        if not in_nodes and path.name not in _ORCHESTRATION_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        if is_compatibility_facade(source):
            continue
        tree = ast.parse(source)
        count = len(_top_level_defs(tree))
        if count > MAX_TOP_LEVEL_DEFS:
            findings.append(
                ArchitectureViolation(
                    rel,
                    count,
                    MAX_TOP_LEVEL_DEFS,
                    "top_level_defs",
                    "tests-docs-dead-code",
                )
            )
    return findings


def scan_node_modules(repo_root: Path) -> list[ArchitectureViolation]:
    """Fail node modules that export more than one ``*_node`` body.

    Args:
        repo_root: Repository root.

    Returns:
        Multi-node module violations. ``topology.py`` may hold routers only.
    """

    findings: list[ArchitectureViolation] = []
    nodes = repo_root / "apps/agents/src/smart_rag_agents/query/nodes"
    if not nodes.is_dir():
        return findings
    for path in sorted(nodes.glob("*.py")):
        rel = _posix(repo_root, path)
        if path.name in {"__init__.py", "topology.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node_defs = [
            item.name
            for item in _top_level_defs(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name.endswith("_node")
        ]
        if len(node_defs) > 1:
            findings.append(
                ArchitectureViolation(
                    rel, len(node_defs), 1, "exported_nodes", "scope-node-graph"
                )
            )
    return findings


def scan_cycle_guards(repo_root: Path) -> list[ArchitectureViolation]:
    """Fail unused hybrid-run import-order guards.

    Args:
        repo_root: Repository root.

    Returns:
        Files that still import ``_hybrid_run_cycle_guard``.
    """

    findings: list[ArchitectureViolation] = []
    for path in iter_query_vertical_python(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Import):
                continue
            for alias in node.names:
                if alias.asname == "_hybrid_run_cycle_guard":
                    findings.append(
                        ArchitectureViolation(
                            rel, 1, 0, "cycle_guard", "tests-docs-dead-code"
                        )
                    )
    return findings


def scan_test_private_imports(repo_root: Path) -> list[ArchitectureViolation]:
    """Fail query-vertical tests that import another ``test_*.py`` module.

    Args:
        repo_root: Repository root.

    Returns:
        Cross-test private-import violations.
    """

    findings: list[ArchitectureViolation] = []
    for path in iter_query_vertical_tests(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            imported_names: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                imported_names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                module = node.names[0].name if node.names else ""
            imports_test_module = any(
                name.startswith("test_") for name in imported_names
            )
            if (
                ".test_" in module
                or module.startswith("tests.unit.test_")
                or module.startswith("tests.contract.test_")
                or imports_test_module
            ):
                findings.append(
                    ArchitectureViolation(
                        rel, 1, 0, "test_private_import", "tests-docs-dead-code"
                    )
                )
                break
    return findings


def scan_test_line_targets(repo_root: Path) -> list[ArchitectureViolation]:
    """Report query-vertical tests over the 500-line target.

    Args:
        repo_root: Repository root.

    Returns:
        Test modules that still exceed the documentation budget.
    """

    findings: list[ArchitectureViolation] = []
    for path in iter_query_vertical_tests(repo_root):
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > TEST_LINE_TARGET:
            findings.append(
                ArchitectureViolation(
                    rel, count, TEST_LINE_TARGET, "test_lines", "tests-docs-dead-code"
                )
            )
    return findings


def scan_doc_line_targets(repo_root: Path) -> list[ArchitectureViolation]:
    """Report query documentation files over the 300-line target.

    Args:
        repo_root: Repository root.

    Returns:
        Markdown files that still exceed the packet-evidence budget.
    """

    findings: list[ArchitectureViolation] = []
    paths: list[Path] = []
    for root in QUERY_VERTICAL_DOCS:
        target = repo_root / root
        if target.is_file():
            paths.append(target)
        elif target.is_dir():
            paths.extend(sorted(target.glob("*.md")))
    for path in paths:
        rel = _posix(repo_root, path)
        if _is_exception(rel):
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > DOC_LINE_TARGET:
            findings.append(
                ArchitectureViolation(
                    rel, count, DOC_LINE_TARGET, "doc_lines", "tests-docs-dead-code"
                )
            )
    return findings


def scan_architecture(repo_root: Path) -> list[ArchitectureViolation]:
    """Run every hard architecture rule.

    Args:
        repo_root: Repository root.

    Returns:
        Hard-fail findings. Target overruns are not included.
    """

    return [
        *scan_line_budgets(repo_root),
        *scan_top_level_definitions(repo_root),
        *scan_node_modules(repo_root),
        *scan_cycle_guards(repo_root),
        *scan_test_private_imports(repo_root),
    ]
