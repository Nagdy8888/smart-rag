// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { INFERENCE_LINKS_UNAVAILABLE } from "../../lib/citation-drawer";
import { applyAdmission, createChatViewState } from "../../lib/chat-view";
import type { ChatViewState } from "../../lib/chat-view";
import { RunDetailsSheet } from "./run-details-sheet";

function idleChat(): ChatViewState {
  return createChatViewState("idem-1");
}

function completedComposite(): ChatViewState {
  const admitted = applyAdmission(idleChat(), {
    run_id: "run-1",
    reservation_id: "res-1",
    route_family: "composite",
    reconnect: false,
  });
  return {
    ...admitted,
    terminal: "completed",
    stage: "verify_answer",
    status: "verified",
    requestedSearchScope: "company_documents",
    answerOrigin: "company_documents",
    diagnostics: {
      ...admitted.diagnostics,
      promptTokens: 258,
      completionTokens: 32,
      costUsd: 0.4,
      heartbeatCount: 1,
    },
    progress: {
      items: [],
      lastSequence: 0,
      verificationCompleted: true,
    },
  };
}

function correctedCombined(): ChatViewState {
  const base = completedComposite();
  return {
    ...base,
    diagnostics: {
      ...base.diagnostics,
      requestedRoute: "hybrid",
      effectiveRoute: "combined",
      correctedRoute: "combined",
      correctionReason: "relationship",
      unknownEvents: ["future_metric"],
      toolKeys: ["export_docx"],
      cacheStatus: "hit",
      coverageScore: 0.8,
    },
  };
}

function renderSheet(
  chat: ChatViewState,
  open = true,
  companyUsd = "3.2",
) {
  return render(
    <RunDetailsSheet
      open={open}
      onClose={vi.fn()}
      onOpen={vi.fn()}
      chat={chat}
      companyUsd={companyUsd}
    />,
  );
}

describe("RunDetailsSheet", () => {
  afterEach(() => {
    cleanup();
  });

  it("omits empty none rows, heartbeats, and raw stage names", () => {
    renderSheet(completedComposite());
    const details = screen.getByTestId("advanced-diagnostics");
    expect(details).toHaveTextContent("How this answer was produced.");
    expect(details).toHaveTextContent("Completed");
    expect(details).toHaveTextContent("Verified and ready.");
    expect(details).toHaveTextContent("Composite");
    expect(details).toHaveTextContent("Requested source");
    expect(details).toHaveTextContent("Company documents");
    expect(details).toHaveTextContent("Answer origin");
    expect(details).toHaveTextContent("Company documents");
    expect(details).toHaveTextContent("Searches documents, tables, and relationships.");
    expect(details).toHaveTextContent("258 prompt · 32 completion");
    expect(details).toHaveTextContent("290");
    expect(details).toHaveTextContent("Total tokens");
    expect(details).toHaveTextContent("This run");
    expect(details).toHaveTextContent("This chat");
    expect(details).toHaveTextContent(
      "Profile, search, answer, and verifier tokens for this question.",
    );
    expect(details).toHaveTextContent(
      "Every question in this conversation, including this run and the session title.",
    );
    expect(details).not.toHaveTextContent(
      "Session title generation is billed separately.",
    );
    expect(details).toHaveTextContent("$3.20");
    expect(details).toHaveTextContent("Account total");
    expect(details).toHaveTextContent("$0.40");
    expect(details).toHaveTextContent("This run spend");
    expect(details).toHaveTextContent("run-1");
    expect(details).not.toHaveTextContent("Requested route");
    expect(details).not.toHaveTextContent("Effective route");
    expect(details).not.toHaveTextContent("Corrected route");
    expect(details).not.toHaveTextContent("Heartbeats");
    expect(details).not.toHaveTextContent("none");
    expect(details).not.toHaveTextContent("verify_answer");
    expect(details).not.toHaveTextContent("verified");
    expect(screen.getByText(INFERENCE_LINKS_UNAVAILABLE)).toBeInTheDocument();
  });

  it("never labels an idle sheet as running", () => {
    renderSheet(idleChat());
    const details = screen.getByTestId("advanced-diagnostics");
    expect(details).not.toHaveTextContent("In progress");
    expect(details).not.toHaveTextContent("running");
    expect(
      screen.getByText(
        "Send a question to see how that answer was produced, including search mode and token usage.",
      ),
    ).toBeInTheDocument();
  });

  it("shows correction, tools, cache, coverage, and ignored events only when real", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderSheet(correctedCombined());
    const details = screen.getByTestId("advanced-diagnostics");
    expect(details).toHaveTextContent("Combined");
    expect(details).toHaveTextContent("Started as");
    expect(details).toHaveTextContent("Hybrid");
    expect(details).toHaveTextContent("The question needed relationship search.");
    expect(details).toHaveTextContent("export_docx");
    expect(details).toHaveTextContent("Reused a cached search");
    expect(details).toHaveTextContent("0.8");
    expect(details).toHaveTextContent("future_metric");
    await user.click(screen.getByRole("button", { name: "Copy run-1" }));
    expect(writeText).toHaveBeenCalledWith("run-1");
    expect(await screen.findByRole("button", { name: "Copy run-1" })).toHaveTextContent(
      "Copied",
    );
  });

  it("shows this run and the whole-chat total when later questions exist", () => {
    const chat: ChatViewState = {
      ...completedComposite(),
      chatPromptTokens: 700,
      chatCompletionTokens: 74,
    };
    renderSheet(chat);
    const details = screen.getByTestId("advanced-diagnostics");
    const thisRun = screen.getByRole("region", { name: "This run" });
    const thisChat = screen.getByRole("region", { name: "This chat" });
    expect(thisRun).toHaveTextContent("258");
    expect(thisRun).toHaveTextContent("32");
    expect(thisRun).toHaveTextContent("290");
    expect(thisChat).toHaveTextContent("958");
    expect(thisChat).toHaveTextContent("106");
    expect(thisChat).toHaveTextContent("1,064");
    expect(details).toHaveTextContent("This run 258 prompt · 32 completion");
    expect(details).toHaveTextContent("This chat 958 prompt · 106 completion");
  });

  it("labels a General answer as no document search, not Composite", () => {
    const chat: ChatViewState = {
      ...completedComposite(),
      requestedSearchScope: "general_knowledge",
      answerOrigin: "general_knowledge",
    };
    renderSheet(chat);
    const details = screen.getByTestId("advanced-diagnostics");
    expect(details).toHaveTextContent("No document search");
    expect(details).toHaveTextContent("Did not search company documents.");
    expect(details).toHaveTextContent("Requested source");
    expect(details).toHaveTextContent("General");
    expect(details).not.toHaveTextContent(
      "Searches documents, tables, and relationships.",
    );
  });
});
