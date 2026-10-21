"""Offline synthetic reproductions for the 2026-10-20 review.

Run from the repository root with the project's Python environment.
No database, provider credential, network call, or application edit is needed.
These assertions demonstrate current weaknesses; they should stop passing
when the corresponding production behavior is fixed.
"""

from types import SimpleNamespace
from uuid import uuid4

from smart_rag_agents.query.nodes.organize import _apply_rewrite, _pack_paragraphs
from smart_rag_api.services.sse.registry import QueryRunRegistry
from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.security.jwks import JwksVerifier, _JwksCache


def main() -> None:
    """Print the reviewed synthetic behavior without contacting any service."""
    verified = "Alpha runs first. Beta runs second."
    payload = AnswerPayload(
        answer_text=verified,
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0, text=verified, link_ids=("link-1",)
            ),
        ),
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        status="complete",
    )
    contradicted = "**Alpha**\nAlpha never runs first. Beta runs second."
    result = _apply_rewrite(payload, contradicted, verified, ())
    assert result.answer_text == contradicted
    assert result.status == "complete"
    print("AG-01: contradictory rewrite accepted with complete status")

    arabic = (
        "**\u0627\u0644\u0646\u062a\u064a\u062c\u0629**\n"
        "\u062a\u0645 \u0625\u0644\u063a\u0627\u0621 "
        "\u062c\u0645\u064a\u0639 \u0627\u0644\u0636\u0648\u0627\u0628\u0637 "
        "\u0627\u0644\u0623\u0645\u0646\u064a\u0629."
    )
    assert _apply_rewrite(payload, arabic, verified, ()).answer_text == arabic
    print("AG-01: unrelated actual Arabic Unicode accepted")

    blocks = [f"```text\nblock {index}\n```" for index in range(7)]
    packed = _pack_paragraphs(
        payload, ["**Alpha**\n" + verified, *blocks], ["link-1"]
    )
    retained = sum(block in packed.answer_text for block in blocks)
    assert retained == 5
    print(f"AG-05: {len(blocks)} exact blocks supplied; {retained} retained")

    registry = QueryRunRegistry()
    for _ in range(1000):
        run_id = uuid4()
        registry.remember_input(run_id, "synthetic private question")
        registry.get_or_create(run_id)
        registry.drop(run_id)
    assert len(registry._inputs) == 1000
    assert len(registry._live) == 0
    print("BE-01: 1000 dropped runs retain 1000 inputs and zero live handles")

    verifier = JwksVerifier(supabase_url="https://example.invalid")
    empty_keys = SimpleNamespace(keys=[])
    verifier._get_cached_jwks = lambda: _JwksCache(
        jwks=empty_keys, fetched_at=0
    )
    fetches = []

    def fake_fetch(**_kwargs):
        """Count synthetic key refreshes without making network requests."""
        fetches.append(1)
        return empty_keys

    verifier._fetch_jwks = fake_fetch
    for _ in range(10):
        verifier._resolve_signing_key("synthetic-unknown-kid")
    assert len(fetches) == 10
    print("SEC-03: 10 unknown-kid resolutions cause 10 fake refreshes")
    print("Network calls: 0. Application/database mutations: 0.")


if __name__ == "__main__":
    main()
