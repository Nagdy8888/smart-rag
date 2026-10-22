# Code colors and inline source images — 22 October 2026

## Behavior

All answer code blocks use IDE-style syntax colors for supported languages,
including Python, JavaScript, TypeScript, SQL, JSON, HTML, CSS, and shell.
The pinned `lowlight` 3.3.0 dependency produces syntax trees, rendered only
as React spans and text. No raw HTML is injected. Copy preserves the exact
displayed source, including literal entities. Unknown languages and snippets
above 32,768 characters fall back to unchanged plain text.

Figure rendering accepts both hash and UUID identifiers, renders every distinct
image in a paragraph, and avoids repeating an image within an answer. Figure
markers inside code remain code. A source citation with typed figure metadata
also displays the image if the answer omitted its marker. Images load through
the existing authenticated API and retain enlargement controls; model-provided
external URLs are never used as image sources.

The agent now resolves exact numbered image references introduced in its answer
against authorized retrieved assets, even when the original question did not
request an image. Explicit numbered requests retain priority, and unrelated
retrieved diagrams are excluded. Missing or denied assets show the existing
unavailable state; these changes cannot recover an image absent from retrieval.

## Verification

- 116 focused frontend tests passed, followed by three authenticated-image
  lifecycle, denial, and signed-out tests.
- 47 focused Python tests passed, including English, abbreviated, and Arabic
  answer-introduced figure references and exclusion of unrelated images.
- Frontend TypeScript, production build, ESLint, Python Ruff, and targeted
  Pyright passed. ESLint retains the two existing native-image optimization
  warnings for authenticated blob previews.
- Browser inspection confirmed distinct computed token colors in the real
  signed-in app. Local API readiness returned 200 after applying source changes.
- All six syntax color roles measured 5.59:1 or higher against the code surface.
- A real company-document question about Figure 3-4 displayed the original
  autonomy-slider image inline, with source citations and working enlargement.
  The answer retained its existing partial status. An earlier Auto-scope wording
  refused before searching company sources; this renderer change does not fix
  that separate routing limitation.

This is local development verification, not evidence of deployment or a new
50-question acceptance run. The earlier full strict result remains 39/50.
