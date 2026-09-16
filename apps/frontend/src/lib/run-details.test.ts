// @vitest-environment node

import { describe, expect, it } from "vitest";
import {
  cacheStatusLabel,
  correctionReasonLabel,
  isDeadlinePartialStatus,
  isRealDetailValue,
  routeIcon,
  routeLabel,
  routeSummary,
  runStatusLabel,
  runStatusSummary,
  runStatusTone,
  searchModeRoute,
} from "./run-details";

describe("isRealDetailValue", () => {
  it("rejects empty placeholders", () => {
    expect(isRealDetailValue(null)).toBe(false);
    expect(isRealDetailValue("")).toBe(false);
    expect(isRealDetailValue("—")).toBe(false);
    expect(isRealDetailValue("none")).toBe(false);
    expect(isRealDetailValue("None")).toBe(false);
  });

  it("keeps catalog values", () => {
    expect(isRealDetailValue("composite")).toBe(true);
  });
});

describe("routeLabel", () => {
  it("maps known families and isolates unknown text", () => {
    expect(routeLabel("composite")).toBe("Composite");
    expect(routeLabel("hybrid")).toBe("Hybrid");
    expect(routeLabel("combined")).toBe("Combined");
    expect(routeLabel("structured_table")).toBe("Tables");
    expect(routeLabel("graph_inspection")).toBe("Graph inspection");
    expect(routeLabel("web_research")).toBe("Web research");
    expect(routeLabel("<script>x</script>")).toBe("<script>x</script>");
    expect(routeLabel(null)).toBeNull();
    expect(routeLabel("none")).toBeNull();
  });
});

describe("routeSummary", () => {
  it("explains known families only", () => {
    expect(routeSummary("composite")).toBe(
      "Searches documents, tables, and relationships.",
    );
    expect(routeSummary("web_research")).toBe(
      "Searches the public web. Does not search company documents.",
    );
    expect(routeSummary("custom_family")).toBeNull();
    expect(routeSummary(null)).toBeNull();
  });
});

describe("searchModeRoute", () => {
  it("prefers General and Web origin over the Composite envelope", () => {
    expect(
      searchModeRoute({
        requestedSearchScope: "general_knowledge",
        answerOrigin: "general_knowledge",
        routeFamily: "composite",
        diagnostics: { effectiveRoute: "composite" },
      }),
    ).toBe("no_retrieval");
    expect(
      searchModeRoute({
        requestedSearchScope: "web",
        answerOrigin: "web",
        routeFamily: "composite",
        diagnostics: { effectiveRoute: "web_research" },
      }),
    ).toBe("web_research");
    expect(
      searchModeRoute({
        requestedSearchScope: "company_documents",
        answerOrigin: "company_documents",
        routeFamily: "composite",
        diagnostics: { effectiveRoute: "composite" },
      }),
    ).toBe("composite");
  });
});

describe("runStatusLabel", () => {
  it("never says running when runId is null", () => {
    expect(runStatusLabel(null, null)).toBeNull();
    expect(runStatusLabel("completed", null)).toBe("Completed");
    expect(runStatusLabel(null, "run-1")).toBe("In progress");
    expect(runStatusLabel("partial", "run-1")).toBe("Partial");
    expect(runStatusLabel("cancelled", "run-1")).toBe("Cancelled");
    expect(runStatusLabel("error", "run-1")).toBe("Error");
    expect(runStatusLabel("deadline", "run-1")).toBe("Deadline reached");
  });
});

describe("correctionReasonLabel", () => {
  it("maps the relationship reason and isolates unknown text", () => {
    expect(correctionReasonLabel("relationship")).toBe(
      "The question needed relationship search.",
    );
    expect(correctionReasonLabel(null)).toBeNull();
    expect(correctionReasonLabel("<img>")).toBe("<img>");
  });
});

describe("runStatusTone and runStatusSummary", () => {
  it("maps catalog terminals without inventing running when idle", () => {
    expect(runStatusTone("completed", "run-1")).toBe("success");
    expect(runStatusTone("error", "run-1")).toBe("danger");
    expect(runStatusTone("partial", "run-1")).toBe("warning");
    expect(runStatusTone(null, null)).toBe("neutral");
    expect(runStatusSummary("completed", true)).toBe("Verified and ready.");
    expect(runStatusSummary("completed", false)).toBe("The run finished.");
    expect(runStatusSummary(null, false)).toBe("Working on this question.");
  });
});

describe("isDeadlinePartialStatus", () => {
  it("recognizes retrieve-time deadline reasons", () => {
    expect(isDeadlinePartialStatus("deadline_exhausted")).toBe(true);
    expect(isDeadlinePartialStatus("deadline")).toBe(true);
    expect(isDeadlinePartialStatus("verified_partial")).toBe(false);
    expect(isDeadlinePartialStatus(null)).toBe(false);
  });
});

describe("routeIcon and cacheStatusLabel", () => {
  it("picks a known icon and friendly cache copy", () => {
    expect(routeIcon("composite")).toBe("search");
    expect(routeIcon("structured_table")).toBe("tables");
    expect(routeIcon("graph_inspection")).toBe("graph");
    expect(cacheStatusLabel("hit")).toBe("Reused a cached search");
    expect(cacheStatusLabel(null)).toBeNull();
  });
});
