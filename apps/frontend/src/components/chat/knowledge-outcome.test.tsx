// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KnowledgeOutcome } from "./knowledge-outcome";
import { SourceAuthority } from "./source-authority";

afterEach(cleanup);

describe("knowledge evidence presentation", () => {
  it("leaves historical unknown outcomes unlabeled", () => {
    const { container } = render(<KnowledgeOutcome result={null} />);
    expect(container.textContent).toBe("");
  });
  it("shows support separately from source approval and uncovered sections", () => {
    render(<KnowledgeOutcome result={{ outcome: "partial", limitations: ["source_unreviewed"], unanswered_parts: ["Contractor eligibility"] }} />);
    expect(screen.getByText("Partial answer")).toBeTruthy();
    expect(screen.getByText(/currentness is unconfirmed/)).toBeTruthy();
    expect(screen.getByText("Contractor eligibility")).toBeTruthy();
  });
  it("never reveals authority metadata for an unavailable citation", () => {
    const { container } = render(<SourceAuthority citation={{ citation_id: "c", citation_index: 0, chunk_id: null,
      source_unavailable: true, provenance: { authority: { authority_status: "approved", owner_user_id: "hidden" } } }} />);
    expect(container.textContent).toBe("");
  });
});
