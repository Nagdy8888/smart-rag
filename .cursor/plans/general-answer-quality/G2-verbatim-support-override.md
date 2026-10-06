# G2 - Keep claims that appear word-for-word in their cited passage

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.

**Depends on:** G1b committed, pushed, green, and kept.
**Live run:** yes (dev40). **Target stage:** `5b_removed_after_draft`
with cause `refused_after_draft` or `trimmed_or_rewritten` must go down
against the G1b run. **Stop rule:** revert if that count does not go
down, or if strict passes drop by more than 3.

## Goal

The gpt-4o-mini verifier sometimes rejects a claim that is a literal copy
of its cited passage (13 such rejections in the baseline analysis), most
often fenced code and pipe-table rows. A claim whose normalized text is
a substring of the normalized text of a passage it cites is supported by
definition. Make that rule deterministic: the verifier still runs, but
its "unsupported" verdict is ignored for such links. No prompt, model,
schema, or call-count change.

## Read first (confirm each exists)

- `packages/core/src/smart_rag_core/query_answer/verifier.py`:
  `def apply_verifier_payload(` (line ~50; body builds `unsupported = {`
  then `return drop_unsupported_paragraphs(payload, frozenset(unsupported))`)
  and `def run_verifier_batch(` (line ~73; signature
  `payload, *, caller, already_called`; calls
  `updated = apply_verifier_payload(payload, verdicts)`).
- `apps/agents/src/smart_rag_agents/query/nodes/verify.py` line ~237:

  ```python
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
            )
  ```

  The local name `fusion` is in scope there (it is passed to
  `bind_company_atomic_links(payload, fusion=fusion, ...)` above).
- `packages/core/src/smart_rag_core/query_answer/models.py`
  `class AtomicLink` fields: `link_id`, `claim` (max 2000), `chunk_ids`,
  `web_source_ids`, `table_id`, `source_ranges`, `kind`, `priority`.
- `packages/core/src/smart_rag_core/query_fusion/models.py`
  `class FusionResult` (field `evidence`) and `class ScoredPassage`
  (fields `chunk_id`, `citation_text`).
- `tests/support/answer_verifier.py` `verifier_passage(n, *, text, rank=1)`
  and `verifier_fusion(*passages)`.
- Other callers of `run_verifier_batch` / `apply_verifier_payload`:
  `scripts/eval_ask_oracle_context.py` line ~504,
  `tests/unit/test_answer_verifier.py`,
  `tests/unit/test_answer_paragraph_citations.py`. They keep working
  unchanged because the new parameters are keyword-only with defaults.

## Step 1 - `verifier.py` (exact code)

Replace the import block at the top (lines 3-15) with:

```python
from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Callable

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.paragraphs import drop_unsupported_paragraphs
from smart_rag_core.query_answer.versions import MAX_VERIFIER_CALLS, MAX_VERIFIER_LINKS
from smart_rag_core.query_fusion.models import FusionResult
```

Keep `VerifierLinkVerdict` only if the file still uses it (ruff F401
tells you); do not remove other names that are used.

Directly below `VerifierCaller = Callable[...]` add:

```python
VERBATIM_MIN_CHARS = 12
_FENCE_LINE = re.compile(r"^[ \t]*```[\w+-]*[ \t]*$", re.MULTILINE)
_TABLE_RULE_LINE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$",
    re.MULTILINE,
)
_QUOTE_FOLD = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
)


def verbatim_key(text: str) -> str:
    """Normalize text for the word-for-word support comparison.

    Removes Markdown fence lines, table separator rows, and pipe characters
    (the answer adds them only to meet a requested shape), unescapes HTML
    entities, folds curly quotes, applies NFKC and casefold, and collapses
    all whitespace to single spaces.

    Args:
        text: Claim text or canonical passage text.

    Returns:
        Normalized comparison key. Empty when ``text`` has no content.
    """

    stripped = _FENCE_LINE.sub(" ", text)
    stripped = _TABLE_RULE_LINE.sub(" ", stripped)
    stripped = stripped.replace("|", " ")
    folded = html.unescape(stripped).translate(_QUOTE_FOLD)
    return " ".join(unicodedata.normalize("NFKC", folded).casefold().split())


def verbatim_supported_link_ids(
    payload: AnswerPayload,
    fusion: FusionResult,
) -> frozenset[str]:
    """Return fact links whose claim occurs word-for-word in a cited passage.

    Only company-document fact links that cite at least one chunk are
    eligible. Table-value links, Web links, and inference links are never
    eligible. Claims shorter than ``VERBATIM_MIN_CHARS`` after normalization
    are skipped so a bare number or word cannot bypass the verifier.

    Args:
        payload: Answer after deterministic checks.
        fusion: Fusion evidence the answer was generated from.

    Returns:
        Link IDs that are supported by literal containment.
    """

    texts = {item.chunk_id: verbatim_key(item.citation_text) for item in fusion.evidence}
    supported: set[str] = set()
    for link in payload.atomic_links:
        if link.kind != "fact" or link.table_id or link.web_source_ids:
            continue
        claim = verbatim_key(link.claim)
        if len(claim) < VERBATIM_MIN_CHARS:
            continue
        if any(claim in texts.get(chunk_id, "") for chunk_id in link.chunk_ids):
            supported.add(link.link_id)
    return frozenset(supported)
```

Replace the whole `apply_verifier_payload` function with:

```python
def apply_verifier_payload(
    payload: AnswerPayload,
    verdicts: VerifierPayload,
    *,
    verbatim_ids: frozenset[str] = frozenset(),
) -> AnswerPayload:
    """Remove unsupported links and any paragraph that depends on them.

    A verifier rejection is ignored for links in ``verbatim_ids`` because
    their claim is a literal copy of a cited passage.

    Args:
        payload: Answer after deterministic checks.
        verdicts: One structured verifier batch.
        verbatim_ids: Link IDs proven supported by literal containment.

    Returns:
        Answer with unsupported links omitted. Paragraphs that named a
        rejected link are dropped and ``answer_text`` is rebuilt. When
        no paragraph survives, the original prose is replaced by a
        citation-free refusal.
    """

    unsupported = {
        item.link_id for item in verdicts.link_verdicts if not item.supported
    } - verbatim_ids
    return drop_unsupported_paragraphs(payload, frozenset(unsupported))
```

In `run_verifier_batch`:

1. Change the signature to:

   ```python
   def run_verifier_batch(
       payload: AnswerPayload,
       *,
       caller: VerifierCaller | None,
       already_called: int,
       fusion: FusionResult | None = None,
   ) -> tuple[AnswerPayload, int, tuple[str, ...]]:
   ```

2. Add to its `Args:` section after `already_called`:

   ```text
           fusion: Evidence used for the word-for-word support override.
               None disables the override.
   ```

3. Replace the line `updated = apply_verifier_payload(payload, verdicts)`
   with:

   ```python
       verbatim = (
           verbatim_supported_link_ids(payload, fusion)
           if fusion is not None
           else frozenset()
       )
       updated = apply_verifier_payload(payload, verdicts, verbatim_ids=verbatim)
   ```

Do not change `select_material_links`, `_force_partial_if_omitted`,
`mock_verifier_payload`, the caps, or the omitted-link handling.

## Step 2 - `verify.py` (exact edit)

Replace:

```python
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
            )
```

with:

```python
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
                fusion=fusion,
            )
```

In the docstring of the verify node function (the function containing
this call), in the paragraph describing the verifier, add one sentence:
"Links whose claim occurs word-for-word in a cited passage stay
supported even when the verifier rejects them." Do not change other
lines. Leave `scripts/eval_ask_oracle_context.py` unchanged.

## Step 3 - Tests (exact code)

Create `tests/unit/test_verifier_verbatim_support.py`:

```python
"""Word-for-word support override for verifier rejections."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.verifier import (
    apply_verifier_payload,
    run_verifier_batch,
    verbatim_key,
    verbatim_supported_link_ids,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage

CODE_CHUNK = "def load_rows(path):\n    return [row for row in read(path)]"
PROSE_CHUNK = "The cache keeps 128 entries per worker."
CODE_CLAIM = (
    "```python\ndef load_rows(path):\n    return [row for row in read(path)]\n```"
)


def _payload(
    claims: tuple[str, str],
    *,
    table_id: str | None = None,
) -> tuple[AnswerPayload, FusionResult]:
    """Build a two-paragraph answer citing the code and prose chunks.

    Args:
        claims: Claim text for links ``l1`` (code chunk) and ``l2`` (prose).
        table_id: Optional table id set on link ``l2``.

    Returns:
        Answer payload and its fusion evidence.
    """

    fusion = verifier_fusion(
        verifier_passage(1, text=CODE_CHUNK),
        verifier_passage(2, text=PROSE_CHUNK, rank=2),
    )
    ids = tuple(item.chunk_id for item in fusion.evidence)
    payload = AnswerPayload(
        paragraphs=tuple(
            AnswerParagraph(
                paragraph_index=index, text=claim, link_ids=(f"l{index + 1}",)
            )
            for index, claim in enumerate(claims)
        ),
        citations=tuple(
            AnswerCitation(
                chunk_id=ids[index],
                span=claim,
                paragraph_index=index,
                atomic_link_id=f"l{index + 1}",
            )
            for index, claim in enumerate(claims)
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=claims[0],
                chunk_ids=(ids[0],),
                kind="fact",
                priority=1,
            ),
            AtomicLink(
                link_id="l2",
                claim=claims[1],
                chunk_ids=(ids[1],),
                table_id=table_id,
                kind="fact",
                priority=2,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    return payload, fusion


def _reject_all(links: tuple[AtomicLink, ...]) -> VerifierPayload:
    """Return a verifier batch that rejects every link.

    Args:
        links: Links selected for verification.

    Returns:
        Verifier payload with every verdict unsupported.
    """

    return VerifierPayload(
        link_verdicts=tuple(
            VerifierLinkVerdict(
                link_id=item.link_id, supported=False, reason="unsupported_link"
            )
            for item in links
        )
    )


def test_verbatim_key_drops_shape_markup() -> None:
    """Fences, table rules, pipes, entities, and quotes are normalized."""

    assert verbatim_key("```python\nA  b\n```") == "a b"
    assert verbatim_key("| A | B |\n|---|---|\n| 1 | 2 |") == "a b 1 2"
    assert verbatim_key("&lt;x&gt; \u201cq\u201d") == '<x> "q"'


def test_literal_claims_are_supported() -> None:
    """A fenced code copy and an exact sentence both count as verbatim."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    assert verbatim_supported_link_ids(payload, fusion) == frozenset({"l1", "l2"})


def test_changed_value_is_not_supported() -> None:
    """A claim with a different number is not a literal copy."""

    payload, fusion = _payload(
        (CODE_CLAIM, "The cache keeps 256 entries per worker.")
    )
    assert verbatim_supported_link_ids(payload, fusion) == frozenset({"l1"})


def test_short_claim_is_never_verbatim() -> None:
    """A claim shorter than the minimum cannot bypass the verifier."""

    payload, fusion = _payload((CODE_CLAIM, "128 entries"))
    assert "l2" not in verbatim_supported_link_ids(payload, fusion)


def test_table_value_link_is_not_eligible() -> None:
    """Table-value links keep their verifier verdict."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK), table_id="t1")
    assert "l2" not in verbatim_supported_link_ids(payload, fusion)


def test_rejection_ignored_only_for_verbatim_links() -> None:
    """The verbatim link survives; the changed claim is still dropped."""

    payload, fusion = _payload(
        (CODE_CLAIM, "The cache keeps 256 entries per worker.")
    )
    updated = apply_verifier_payload(
        payload,
        _reject_all(payload.atomic_links),
        verbatim_ids=verbatim_supported_link_ids(payload, fusion),
    )
    assert tuple(item.link_id for item in updated.atomic_links) == ("l1",)
    assert "256" not in updated.answer_text
    assert updated.status != "refused"


def test_run_batch_applies_override_with_fusion() -> None:
    """With fusion, a full rejection of literal claims keeps both links."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    updated, calls, omitted = run_verifier_batch(
        payload, caller=_reject_all, already_called=0, fusion=fusion
    )
    assert calls == 1
    assert omitted == ()
    assert tuple(item.link_id for item in updated.atomic_links) == ("l1", "l2")


def test_run_batch_without_fusion_keeps_old_behavior() -> None:
    """Without fusion, every rejected link is dropped as before."""

    payload, _fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    updated, _calls, _omitted = run_verifier_batch(
        payload, caller=_reject_all, already_called=0
    )
    assert updated.status == "refused"
    assert updated.atomic_links == ()
```

Run:

```powershell
uv run python -m pytest tests/unit/test_verifier_verbatim_support.py tests/unit/test_answer_verifier.py tests/unit/test_answer_paragraph_citations.py -q
```

If `test_run_batch_without_fusion_keeps_old_behavior` fails only on the
`atomic_links == ()` line, read `drop_unsupported_paragraphs` in
`packages/core/src/smart_rag_core/query_answer/paragraphs.py`, and
replace that one assert with the field the existing test
`test_all_paragraphs_removed_is_citation_free_refusal` in
`tests/unit/test_answer_paragraph_citations.py` checks
(`updated.paragraphs == ()`). Report the change. Any other failure:
stop and report.

## Step 4 - Lint, types, guard, full tiers

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/query_answer/verifier.py apps/agents/src/smart_rag_agents/query/nodes/verify.py tests/unit/test_verifier_verbatim_support.py
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
uv run python scripts/check_gold_literals.py
```

All must exit 0.

## Step 5 - Docs

- Find the verifier doc: `rg -l "verifier" docs/agent docs/retrieval docs/architecture`.
  In the page that describes the verify node, add a short subsection
  `### Word-for-word support override` that says: what qualifies (fact
  link, company documents, cites a chunk, no `table_id`, normalized claim
  of at least 12 characters contained in a cited passage after removing
  fences, table rules, and pipes, unescaping entities, folding quotes,
  NFKC, casefold, whitespace collapse); what it does (ignores a verifier
  rejection for that link only); what it never does (no extra model call,
  no change for inference, table, or Web links); the failure mode
  (a literal copy cited from the wrong passage is still dropped, because
  only cited chunks are compared). Update the existing mermaid diagram
  on that page if it shows the verify steps.
- ADR `docs/adr/ADR-general-answer-quality.md`, `## Decision` item 2:
  add "Implemented in G2 on <TODAY>."
- `docs/README.md`: update date cells of edited docs.

## Step 6 - Commit, rebuild, dev40, stop rule

```powershell
git status --short
git add packages/core/src/smart_rag_core/query_answer/verifier.py
git add apps/agents/src/smart_rag_agents/query/nodes/verify.py
git add tests/unit/test_verifier_verbatim_support.py
git add <each edited doc, one by one>
git commit -m "fix(verify): keep claims copied word-for-word from cited passages (G2)"
git push
gh pr checks --watch --fail-fast
```

Rebuild the image, run the probe (`G2 present` must print), run dev40
with `$run = "dev40-g2"`, run the stage report, compare with
`dev40-g1b`. Look at `5b_removed_after_draft` split by cause
(`refused_after_draft`, `trimmed_or_rewritten`). Apply the stop rule at
the top. Fill `## After G2` in the evidence doc (counts only), commit
`docs(eval): G2 dev40 results`, push, wait for green checks.

## Done when

- [ ] `verbatim_supported_link_ids` and `verbatim_key` exist with Google
      docstrings; `apply_verifier_payload` and `run_verifier_batch` take
      the new keyword-only parameters with defaults.
- [ ] `verify.py` passes `fusion=fusion`; the probe prints `G2 present`.
- [ ] The 8 new tests and all existing verifier tests pass.
- [ ] Lint, types, unit, contract, guard exit 0.
- [ ] Docs updated; dev40 ran; stop-rule decision recorded with numbers;
      PR checks green.

## Commit messages

```text
fix(verify): keep claims copied word-for-word from cited passages (G2)
docs(eval): G2 dev40 results
```

## Do not

- Do not change the verifier prompt, model, schema, `MAX_VERIFIER_LINKS`,
  or `MAX_VERIFIER_CALLS`.
- Do not skip the verifier call when every link is verbatim (call
  accounting stays the same in this packet).
- Do not compare against passages the link does not cite.
- Do not run the holdout.
