# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Company members use the signed-in console to ask questions against documents they are allowed to see. Owners and admins do that work and also govern documents, access, tools, usage, and evaluation. Hidden navigation is convenience only; the API still authorizes every call.

## Product Purpose

Smart RAG is the company console for asking questions of authorized evidence. A run returns an answer with citations the caller may inspect, or it stops with a typed refusal. It does not invent from text the caller cannot see, and it does not quietly move a company-document question onto the open web.

Success for a member is a cited answer from evidence they may use, or a clear refusal. Success for an owner or admin is that same answering behavior plus control of the corpus, access, and evaluation.

## Positioning

Retrieval is fused and then rechecked against access control. A verifier drops unsupported links. Answers cite canonical evidence chunks, including PDF paragraph citations and table provenance when those paths run. Graph inspection shows relationships, but answers still cite those chunks rather than graph prose. If nothing the caller may use is found, the run refuses instead of guessing.

## Operating Context

People sign in with hosted Supabase Auth and work in the console at the app origin. Ask is the workspace: one answer source per turn, chosen among Auto, Company documents, General, and Web. Documents, Tables, and Graph are the other primary destinations. Admin (team, tools, curation, usage, and evaluation) is available as a convenience for owners and admins. Account details are separate from primary navigation.

Arabic and English are both first-class in the corpus. The console streams a run over server-sent events, including progress, resume, and one terminal state.

## Capabilities and Constraints

Confirmed capabilities: authenticated Ask, document import and status, table analysis, graph inspection, account details, and owner/admin governance of team access, tools, curation, usage, and evaluation.

Durable constraints:

- Evidence the caller cannot see is not retrieved, cited, or described.
- Company-document questions do not fall through to the web unless Web is the chosen source.
- Browser tokens never read evidence tables directly. Roles are server-derived.
- Retrieved text, filenames, labels, and model output are untrusted and are not rendered as HTML.
- The console must keep loading, empty, permission, rate-limit, reconnect, deleted-source, and degraded-mode states.
- Keyboard access, focus management, WCAG AA contrast, and mobile behavior are existing requirements of this console.
- The 2026-09-17 company-documents run (37 of 100 fully correct on a strict-substring baseline) is an evaluation baseline, not a launch claim.

Open: no separate production visual system was confirmed beyond this console. This Next.js app is the product surface.

## Brand Commitments

The product name is Smart RAG.

## Evidence on Hand

Repository screenshots of sign-in, Ask, and Graph live under `docs/assets/readme/`. There are no confirmed customer testimonials, case studies, prices, or licensing claims. Future work must not invent them.

## Product Principles

- Show authorized evidence, or stop.
- A citation the caller can inspect is part of the answer.
- Members ask; owners and admins also govern. The interface does not decide permission.
- Web is an explicit source, not a silent fallback.
- This console is the product people use.
