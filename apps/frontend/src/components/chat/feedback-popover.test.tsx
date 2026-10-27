// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { FeedbackPopover } from "./feedback-popover";

describe("FeedbackPopover", () => {
  it("shares a review report only after explicit consent", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(<FeedbackPopover thumbsUp={false} onThumbs={vi.fn()} tag="outdated answer"
      onTag={vi.fn()} comment="" onComment={vi.fn()} onSubmit={submit} />);
    await user.click(screen.getByRole("button", { name: "Give feedback" }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(submit).toHaveBeenLastCalledWith(false);
    await user.click(screen.getByRole("checkbox", { name: /Share this question/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(submit).toHaveBeenLastCalledWith(true);
  });
  afterEach(() => {
    cleanup();
  });

  it("offers thumbs-up tags instead of diagnostic tags", async () => {
    const user = userEvent.setup();
    render(
      <FeedbackPopover
        thumbsUp
        onThumbs={vi.fn()}
        tag="helpful answer"
        onTag={vi.fn()}
        comment=""
        onComment={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Give feedback" }));
    expect(screen.getByRole("option", { name: "helpful answer" })).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "chunk/cleaning loss" }),
    ).not.toBeInTheDocument();
  });

  it("switches to diagnostic tags on thumbs down", async () => {
    const user = userEvent.setup();
    const onThumbs = vi.fn();
    const onTag = vi.fn();
    render(
      <FeedbackPopover
        thumbsUp
        onThumbs={onThumbs}
        tag="helpful answer"
        onTag={onTag}
        comment=""
        onComment={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Give feedback" }));
    await user.click(screen.getByRole("button", { name: "Thumbs down" }));
    expect(onThumbs).toHaveBeenCalledWith(false);
    expect(onTag).toHaveBeenCalledWith("chunk/cleaning loss");
  });
});
