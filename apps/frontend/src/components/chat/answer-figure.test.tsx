// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { AnswerFigure } from "./answer-figure";

const auth = vi.hoisted(() => ({ token: null as string | null }));
vi.mock("../../lib/auth/session-provider", () => ({
  useOptionalSession: () => ({ accessToken: auth.token }),
}));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); auth.token = null; });

it("loads the authorized image inline and releases its blob URL on unmount", async () => {
  auth.token = "local-test-token";
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["png"], { type: "image/png" }) });
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:authorized-figure"), revokeObjectURL });
  const { unmount } = render(<AnswerFigure figureId="a1111111-1111-4111-8111-111111111111" caption="Figure 3-4. Controller diagram." />);
  const image = await screen.findByRole("img", { name: "Figure 3-4. Controller diagram." });
  expect(image).toHaveAttribute("src", "blob:authorized-figure");
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/figures/a1111111-1111-4111-8111-111111111111"), expect.objectContaining({ headers: { Authorization: "Bearer local-test-token" } }));
  expect(screen.getByRole("button", { name: "Enlarge diagram" })).toBeInTheDocument();
  unmount();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:authorized-figure");
});

it("keeps denied images unavailable without falling back to an external URL", async () => {
  auth.token = "expired-token";
  const fetchMock = vi.fn().mockResolvedValue({ ok: false });
  vi.stubGlobal("fetch", fetchMock);
  render(<AnswerFigure figureId="abcd" caption="Diagram" />);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Diagram preview is unavailable."));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("does not request private image bytes before sign-in", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<AnswerFigure figureId="abcd" caption="Diagram" />);
  expect(fetchMock).not.toHaveBeenCalled();
});
