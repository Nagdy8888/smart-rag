// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { createChatViewState } from "../../lib/chat-view";
import { EMPTY_DEADLINE_PARTIAL_COPY } from "../../lib/run-details";
import type { RunProgressItem } from "../../lib/run-progress";
import { runStatusLine } from "./run-progress";
import {
  progressSummary,
  RunProgressTimeline,
} from "./run-progress-timeline";

function item(
  overrides: Partial<RunProgressItem> & Pick<RunProgressItem, "key">,
): RunProgressItem {
  return {
    id: `n:${overrides.key}`,
    kind: "node",
    phase: "completed",
    outcome: null,
    firstSequence: 1,
    lastSequence: 1,
    ...overrides,
  };
}

const COMPANY_ITEMS: readonly RunProgressItem[] = [
  item({ key: "company_scope", phase: "completed", firstSequence: 1, lastSequence: 2 }),
  item({ key: "disclose_optional_tools", phase: "completed", firstSequence: 3, lastSequence: 4 }),
  item({
    key: "web_search",
    kind: "tool",
    id: "t:web_search",
    phase: "completed",
    firstSequence: 5,
    lastSequence: 6,
  }),
  item({ key: "generate_answer", phase: "started", firstSequence: 7, lastSequence: 7 }),
];

const GENERAL_ITEMS: readonly RunProgressItem[] = [
  item({ key: "general_scope", phase: "started", firstSequence: 1, lastSequence: 1 }),
];

describe("RunProgressTimeline", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders only company fixture stages and tools that were emitted", () => {
    render(
      <RunProgressTimeline
        items={COMPANY_ITEMS}
        terminal={null}
        verificationCompleted={false}
        answerAvailable={false}
        collapsed={false}
      />,
    );
    expect(screen.getByText(/Company retrieval/)).toBeInTheDocument();
    expect(screen.getByText(/Optional tools/)).toBeInTheDocument();
    expect(screen.getByText(/Searching/)).toBeInTheDocument();
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.getAllByText("Generating…").length).toBeGreaterThan(0);
    expect(screen.queryByText("General answer")).not.toBeInTheDocument();
    expect(screen.queryByText("%")).not.toBeInTheDocument();
    expect(screen.queryByText(/ms|seconds|timestamp/i)).not.toBeInTheDocument();
  });

  it("renders a general fixture without company retrieval or tool rows", () => {
    render(
      <RunProgressTimeline
        items={GENERAL_ITEMS}
        terminal={null}
        verificationCompleted={false}
        answerAvailable={false}
        collapsed={false}
      />,
    );
    expect(screen.getAllByText("General answer").length).toBeGreaterThan(0);
    expect(screen.queryByText("Company retrieval")).not.toBeInTheDocument();
    expect(screen.queryByText("web_search")).not.toBeInTheDocument();
  });

  it("labels an unknown safe stage with a deterministic fallback", () => {
    render(
      <RunProgressTimeline
        items={[item({ key: "future_stage", phase: "started" })]}
        terminal={null}
        verificationCompleted={false}
        answerAvailable={false}
        collapsed={false}
      />,
    );
    expect(screen.getAllByText("Working: future_stage").length).toBeGreaterThan(0);
    expect(screen.getByText("future_stage")).toBeInTheDocument();
  });

  it("expands and collapses from the keyboard", async () => {
    const user = userEvent.setup();
    render(
      <RunProgressTimeline
        items={GENERAL_ITEMS}
        terminal={null}
        verificationCompleted={true}
        answerAvailable={true}
        collapsed={true}
      />,
    );
    const toggle = screen.getByRole("button", { name: "Show steps" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Hide steps" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("list")).toBeInTheDocument();
  });

  it("marks the active started row as the current step", () => {
    render(
      <RunProgressTimeline
        items={COMPANY_ITEMS}
        terminal={null}
        verificationCompleted={false}
        answerAvailable={false}
        collapsed={false}
      />,
    );
    const current = screen
      .getAllByText("Generating…")
      .map((node) => node.closest("[role='listitem']"))
      .find((node) => node !== null);
    expect(current).toHaveAttribute("aria-current", "step");
  });
});

describe("progressSummary", () => {
  it("uses truthful verified and terminal copy", () => {
    const base = {
      items: COMPANY_ITEMS,
      terminal: null,
      verificationCompleted: false,
      answerAvailable: false,
      collapsed: false,
    };
    expect(progressSummary(base)).toBe("Generating…");
    expect(
      progressSummary({
        ...base,
        verificationCompleted: true,
        answerAvailable: false,
      }),
    ).toBe("Verified — preparing display");
    expect(
      progressSummary({
        ...base,
        verificationCompleted: true,
        revealing: true,
        answerAvailable: true,
      }),
    ).toBe("Verified — displaying answer");
    expect(
      progressSummary({
        ...base,
        verificationCompleted: true,
        answerAvailable: true,
        collapsed: true,
      }),
    ).toBe("Verified answer");
    expect(progressSummary({ ...base, terminal: "cancelled" })).toBe(
      "Cancelled. Received tokens are kept.",
    );
    expect(
      progressSummary({ ...base, terminal: "error", answerAvailable: true }),
    ).toBe("Error");
    const deadlineChat = createChatViewState("k");
    deadlineChat.status = "deadline_exhausted";
    expect(
      progressSummary({
        ...base,
        terminal: "partial",
        answerAvailable: false,
        chat: deadlineChat,
      }),
    ).toBe(EMPTY_DEADLINE_PARTIAL_COPY);
    expect(screen.queryByText("%")).toBeNull();
  });
});

describe("runStatusLine", () => {
  it("maps web stages before generic search retrieval copy", () => {
    const chat = createChatViewState("k");
    chat.runId = "run-1";
    chat.stage = "web_search";
    expect(runStatusLine(chat)).toBe("Searching…");
    chat.stage = "web_scope";
    expect(runStatusLine(chat)).toBe("Searching…");
    chat.stage = "web_read";
    expect(runStatusLine(chat)).toBe("Reading…");
    chat.stage = "verify_answer";
    expect(runStatusLine(chat)).toBe("Verifying…");
  });
});
