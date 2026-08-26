// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { VerifiedAnswerReveal } from "./verified-answer-reveal";

describe("VerifiedAnswerReveal", () => {
  afterEach(() => {
    cleanup();
  });

  it("announces readiness once and skips without rendering HTML", async () => {
    const user = userEvent.setup();
    const onShowFull = vi.fn();
    const { rerender } = render(
      <VerifiedAnswerReveal
        presentationKey="c:r1"
        visibleText="Partial <img src=x>"
        isRevealing
        authoritativeReady
        onShowFull={onShowFull}
      />,
    );
    expect(screen.getByText("Verified answer ready")).toBeInTheDocument();
    expect(screen.getByText("Partial <img src=x>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Show full answer" }));
    expect(onShowFull).toHaveBeenCalledTimes(1);
    rerender(
      <VerifiedAnswerReveal
        presentationKey="c:r1"
        visibleText="Partial <img src=x> and more"
        isRevealing={false}
        authoritativeReady
        onShowFull={onShowFull}
      />,
    );
    expect(screen.queryByRole("button", { name: "Show full answer" })).toBeNull();
    expect(screen.getByText("Verified answer ready")).toBeInTheDocument();
  });
});
