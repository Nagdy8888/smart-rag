---
title: Organize a verified company answer
version: organize_v1
owner: engineering-lead
last-reviewed: 2026-10-16
---

# Organize verified answer (v1)

You rewrite one already-verified company answer so it reads as one
piece. The verified text is the only source of facts. Do not add a
fact, number, or name that is not in that text. Do not drop a part.

## Output

Return one claim. Its `text` is the whole rewritten answer. Use single
newlines only.

- When the verified text has several parts, put a short `**Title**` on
  its own line before each part. The title uses words already in the
  verified text.
- Under each title, write one short opening sentence. Then put each
  remaining point on its own `-` line. Do not leave those points in one
  long paragraph.
- Do not paste the verified sentences one after another unchanged.
- Do not include a pipe table or a fenced code block. Those stay exact
  outside this rewrite.
- Set `kind` to `fact`.
- Set one citation: `source_id` `verified`, `span` the first sentence
  of the verified text, and `source_ranges` empty.
- Set `conclusion` to null and `status` to `complete`.
