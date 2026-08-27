// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
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
    finish?.(true);
  });

  it("restores the draft when send returns false", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => false);
    renderComposer({ onSubmit });
    await user.type(screen.getByLabelText("Message"), "keep this draft");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByLabelText("Message")).toHaveValue("keep this draft");
  });

  it("keeps Sending as a circular busy control without squeezing the label", () => {
    renderComposer({ sending: true });
    const send = screen.getByRole("button", { name: "Sending…" });
    expect(send).toHaveAttribute("aria-busy", "true");
    expect(send).toBeDisabled();
    expect(send.querySelector("[aria-hidden='true']")).not.toBeNull();
  });
});
