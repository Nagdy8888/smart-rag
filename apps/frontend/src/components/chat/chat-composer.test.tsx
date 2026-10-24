// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ChatComposer } from "./chat-composer";

/**
 * Render the composer with send/stop stubs.
 *
 * @param overrides - Partial composer props.
 * @returns RTL render result.
 */
function renderComposer(
  overrides: Partial<Parameters<typeof ChatComposer>[0]> = {},
) {
  return render(
    <ChatComposer
      onSubmit={vi.fn(async () => true)}
      disabled={false}
      sending={false}
      running={false}
      onStop={vi.fn()}
      onReconnect={vi.fn()}
      showReconnect={false}
      {...overrides}
    />,
  );
}

describe("ChatComposer", () => {
  afterEach(() => {
    cleanup();
  });

  it("clears the field on send before admission resolves", async () => {
    const user = userEvent.setup();
    let finish: ((value: boolean) => void) | undefined;
    const onSubmit = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          finish = resolve;
        }),
    );
    renderComposer({ onSubmit });
    await user.type(screen.getByLabelText("Message"), "hello from the box");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByLabelText("Message")).toHaveValue("");
    expect(onSubmit).toHaveBeenCalledWith("hello from the box");
    await act(async () => { finish?.(true); });
  });

  it("restores the draft when send returns false", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => false);
    renderComposer({ onSubmit });
    await user.type(screen.getByLabelText("Message"), "keep this draft");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByLabelText("Message")).toHaveValue("keep this draft");
  });

  it("blocks a second send and preserves a new draft when admission fails", async () => {
    const user = userEvent.setup();
    let finish: ((value: boolean) => void) | undefined;
    const onSubmit = vi.fn(() => new Promise<boolean>((resolve) => { finish = resolve; }));
    renderComposer({ onSubmit });
    await user.type(screen.getByLabelText("Message"), "first question");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByRole("button", { name: /^Sending/ })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Sending your message");
    await user.type(screen.getByLabelText("Message"), "next draft{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await act(async () => { finish?.(false); });
    expect(screen.getByLabelText("Message")).toHaveValue("first question\n\nnext draft");
  });

  it("allows drafting during a run and keeps Stop actionable", async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    const onSubmit = vi.fn();
    renderComposer({ running: true, onStop, onSubmit });
    expect(screen.getByRole("status")).toHaveTextContent("Working on your answer");
    await user.type(screen.getByLabelText("Message"), "a follow-up{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Message")).toHaveValue("a follow-up");
  });

  it("shows a labeled busy control while admission is pending", () => {
    renderComposer({ sending: true });
    const send = screen.getByRole("button", { name: "Sending…" });
    expect(send).toHaveAttribute("aria-busy", "true");
    expect(send).toBeDisabled();
    expect(send.querySelector("[aria-hidden='true']")).not.toBeNull();
  });
});
