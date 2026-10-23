# Smart RAG repository guidance

Read [.agents/SKILL_SELECTION.md](.agents/SKILL_SELECTION.md) to select the
appropriate project-local skill. Load its `SKILL.md` before applying it.

The existing RAG implementation skills remain the primary source for this
project's authorization, evidence, ingestion, budget, and release contracts.
Imported skills supplement those contracts; installation alone does not start
every workflow, enable hooks, publish issues, or authorize unrelated changes.

Preserve current user instructions, approved plans, corpus assets, private
configuration, and evaluation history. Do not claim an incomplete live evaluation
is a pass. Keep application checks strict; imported upstream tools are not part
of the application runtime.
