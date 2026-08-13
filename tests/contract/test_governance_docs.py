"""Contract tests for governance documentation sign-off frontmatter."""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import check_governance_signoff


def test_governance_documents_pass_signoff_gate() -> None:
    """Accepted governance docs must carry approver and evidence fields."""

    assert check_governance_signoff() == []


def test_claimed_status_without_approver_is_rejected(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """Documentation checks reject signed/verified without approver evidence."""

    security_dir = tmp_path / "security"
    security_dir.mkdir()
    incomplete = security_dir / "OPENAI_DATA_GOVERNANCE.md"
    incomplete.write_text(
        "---\ntitle: x\nstatus: signed\n---\n\n# Incomplete\n",
        encoding="utf-8",
    )
    sibling = security_dir / "SUBPROCESSOR_GOVERNANCE.md"
    sibling.write_text(
        "---\n"
        "title: y\n"
        "status: accepted\n"
        'approver: "user"\n'
        "approval_date: 2026-08-13\n"
        "policy_version: v1\n"
        "real_company_content_external_processing: prohibited\n"
        "---\n\n# Ok\n",
        encoding="utf-8",
    )

    import scripts.check_docs as check_docs

    monkeypatch.setattr(  # type: ignore[attr-defined]
        check_docs,
        "GOVERNANCE_DOCUMENTS",
        (incomplete, sibling),
    )
    errors = check_docs.check_governance_signoff()
    assert any("without required frontmatter field 'approver'" in item for item in errors)
