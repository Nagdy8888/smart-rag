"use client";

import { useMemo } from "react";
import type { ApiAuth } from "../../../lib/api";
import { isCompanyPdfCitation } from "../../../lib/citation-label";
import type { CitationResponse } from "../../../lib/types";

/** Build a page request only after the selected authorized citation detail settles. */
export function useCitationPageSource({
  auth,
  runId,
  citation,
  pending,
}: {
  auth: ApiAuth | null;
  runId: string | null;
  citation: CitationResponse | null;
  pending: boolean;
}) {
  return useMemo(() => {
    if (
      pending ||
      auth === null ||
      runId === null ||
      citation === null ||
      citation.source_unavailable ||
      !isCompanyPdfCitation(citation)
    )
      return null;
    const page = citation.pdf_page_number;
    if (typeof page !== "number" || !Number.isInteger(page) || page < 1)
      return null;
    return { auth, runId, citationId: citation.citation_id };
  }, [auth, runId, citation, pending]);
}
