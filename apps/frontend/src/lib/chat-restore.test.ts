import { describe, expect, it } from "vitest";
import {
  citationsForSources,
  clampCitationCount,
  feedbackTargetRunId,
  latestSettledRunId,
  parseTranscriptSourceKind,
  selectedCitationRecord,
  showSourcesControl,
} from "./chat-restore";
import type { CitationResponse, ConversationMessage } from "./types";

const LIVE: CitationResponse = {
  citation_id: "live",
  citation_index: 0,
  chunk_id: "c1",
  provenance: {},
  source_unavailable: false,
};
const HIST: CitationResponse = {
  citation_id: "hist",
  citation_index: 0,
  chunk_id: "c2",
  provenance: {},
  source_unavailable: false,
};

describe("latestSettledRunId", () => {
  it("returns the newest assistant run_id", () => {
    const messages: ConversationMessage[] = [
      {
        message_id: "u1",
        role: "user",
        content: "q1",
        created_at: "t1",
        run_id: null,
      },
      {
        message_id: "a1",
        role: "assistant",
        content: "a1",
        created_at: "t2",
        run_id: "run-old",
        citation_count: 1,
      },
      {
        message_id: "a2",
        role: "assistant",
        content: "a2",
        created_at: "t3",
        run_id: "run-new",
        citation_count: 2,
      },
    ];
    expect(latestSettledRunId(messages)).toBe("run-new");
  });
});

describe("feedbackTargetRunId", () => {
  it("uses the live run only after that answer is terminal", () => {
    expect(feedbackTargetRunId("live", "completed", "view", "settled")).toBe(
      "live",
    );
    expect(feedbackTargetRunId("live", null, "view", "settled")).toBe("view");
    expect(feedbackTargetRunId(null, null, null, "settled")).toBe("settled");
    expect(feedbackTargetRunId("reconnect", null, null, "settled")).toBe(
      "settled",
    );
  });
});

describe("citationsForSources", () => {
  it("does not mix live and historical lists", () => {
    expect(citationsForSources(null, "live", [LIVE], [HIST])).toEqual([LIVE]);
    expect(citationsForSources("hist", "live", [LIVE], [HIST])).toEqual([HIST]);
    expect(citationsForSources("live", "live", [LIVE], [HIST])).toEqual([LIVE]);
  });
});

describe("transcript metadata parsers", () => {
  it("clamps citation_count and keeps mixed source_kind null", () => {
    expect(clampCitationCount(3)).toBe(3);
    expect(clampCitationCount(99)).toBe(50);
    expect(clampCitationCount(-2)).toBe(0);
    expect(parseTranscriptSourceKind("web")).toBe("web");
    expect(parseTranscriptSourceKind("company_document")).toBe(
      "company_document",
    );
    expect(parseTranscriptSourceKind(null)).toBeNull();
  });
});

describe("showSourcesControl", () => {
  it("hides Sources for general origin and keeps empty-chrome Sources", () => {
    expect(showSourcesControl(null, null)).toBe(true);
    expect(showSourcesControl("general_knowledge", null)).toBe(false);
    expect(showSourcesControl("general_knowledge", "hist")).toBe(true);
    expect(showSourcesControl("company_documents", null)).toBe(true);
  });
});

describe("selectedCitationRecord", () => {
  it("prefers the matching detail row", () => {
    expect(selectedCitationRecord([LIVE], "live", HIST)).toEqual(LIVE);
    expect(
      selectedCitationRecord([LIVE], "live", { ...LIVE, evidence_excerpt: "span" }),
    ).toMatchObject({ evidence_excerpt: "span" });
  });
});
