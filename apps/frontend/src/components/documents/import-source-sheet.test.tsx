// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ClassifiedApiError } from "../../lib/api";
import { XSS_FILENAME } from "../../lib/hostile-text-fixtures";
import { ImportSourceSheet, type ImportSourceSheetProps } from "./import-source-sheet";

afterEach(() => {
  cleanup();
});

/**
 * Build controlled sheet props with spies.
 *
 * @param override - Partial props.
 * @returns Sheet props.
 */
function sheetProps(override: Partial<ImportSourceSheetProps> = {}): ImportSourceSheetProps {
  return {
    onClose: vi.fn(),
    tab: "file",
    onTabChange: vi.fn(),
    showUpload: true,
    showCrawl: true,
    file: null,
    onFile: vi.fn(),
    category: "allowed",
    onCategory: vi.fn(),
    title: "",
    onTitle: vi.fn(),
    attested: false,
    onAttested: vi.fn(),
    allowPaidPost: true,
    onUpload: vi.fn(),
    uploadPhase: null,
    uploadNote: null,
    uploadError: null,
    uploadPending: false,
    startUrl: "",
    onStartUrl: vi.fn(),
    approvedDomain: "",
    onApprovedDomain: vi.fn(),
    crawlTitle: "",
    onCrawlTitle: vi.fn(),
    maxDepth: 2,
    onMaxDepth: vi.fn(),
    maxPages: 50,
    onMaxPages: vi.fn(),
    onCrawl: vi.fn(),
    crawlError: null,
    crawlNote: null,
    crawlPending: false,
    ...override,
  };
}

describe("ImportSourceSheet", () => {
  it("keeps Upload disabled until a file is attested", () => {
    render(<ImportSourceSheet {...sheetProps()} />);
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("renders a hostile filename as text on the Files tab", async () => {
    const onUpload = vi.fn();
    const file = new File(["hello"], XSS_FILENAME, { type: "application/pdf" });
    render(<ImportSourceSheet {...sheetProps({ file, attested: true, onUpload })} />);
    expect(screen.getByText(XSS_FILENAME)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
    expect(document.querySelector("script")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(onUpload).toHaveBeenCalledTimes(1);
  });

  it("shows the 403 crawl banner on the Website tab", () => {
    render(
      <ImportSourceSheet
        {...sheetProps({
          tab: "website",
          attested: true,
          startUrl: "https://example.com/docs",
          approvedDomain: "example.com",
          crawlError: new ClassifiedApiError({
            kind: "auth",
            status: 403,
            detail: "forbidden",
          }),
        })}
      />,
    );
    expect(
      screen.getByText(/Members receive HTTP 403 from the server/),
    ).toBeInTheDocument();
  });

  it("switches tabs without calling FastAPI", () => {
    const onTabChange = vi.fn();
    render(<ImportSourceSheet {...sheetProps({ onTabChange })} />);
    fireEvent.click(screen.getByRole("button", { name: "Website" }));
    expect(onTabChange).toHaveBeenCalledWith("website");
    expect(screen.queryByRole("button", { name: "Add website" })).toBeNull();
  });
});
