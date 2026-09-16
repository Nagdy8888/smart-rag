// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { createChatViewState } from "../../lib/chat-view";
import {
  GENERIC_PRODUCTION_ERROR,
  INSUFFICIENT_EVIDENCE_COPY,
} from "../../lib/failure-copy";
import { ChatBanners } from "./chat-banners";

/**
 * Render ChatBanners with a live or terminal chat view.
 *
 * @param chat - Chat view under test.
 * @returns Testing Library view.
 */
function renderBanners(
  chat: ReturnType<typeof createChatViewState>,
) {
  return render(
    <ChatBanners
      visibleFailure={null}
      chat={chat}
      disconnected={false}
      reconnectAttempt={0}
      reconnectExhausted={false}
      nextRetryMs={null}
      feedbackStatus={null}
      deleteSuccess={false}
    />,
  );
}

describe("ChatBanners", () => {
  afterEach(() => {
    cleanup();
  });

  it("announces insufficient evidence instead of the generic fault", () => {
    const chat = createChatViewState("k");
    chat.terminal = "partial";
    chat.status = "insufficient_evidence";
    chat.diagnostics.limitationCodes = ["insufficient_evidence"];
    chat.answerText = INSUFFICIENT_EVIDENCE_COPY;
    renderBanners(chat);
    const live = screen.getByLabelText("Blocking errors");
    expect(live).toHaveTextContent(INSUFFICIENT_EVIDENCE_COPY);
    expect(screen.queryByText(GENERIC_PRODUCTION_ERROR)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps Something went wrong for unknown run_failed with no tokens", () => {
    const chat = createChatViewState("k");
    chat.runId = "run-1";
    chat.terminal = "error";
    chat.status = "run_failed";
    chat.failure = { kind: "protocol", detail: "run_failed" };
    renderBanners(chat);
    expect(
      screen.getByText("Something went wrong. Reference run-1."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Blocking errors")).toHaveTextContent(
      GENERIC_PRODUCTION_ERROR,
    );
  });
});
