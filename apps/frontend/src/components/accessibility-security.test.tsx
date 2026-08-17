// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import "@testing-library/jest-dom/vitest";
import {
  BIDI_CONTROL,
  CITATION_LOGICAL_SENTENCE,
  DIACRITICS_AR,
  LONG_URL,
  MIXED_BIDI,
  XSS_ENTITY,
  XSS_FILENAME,
  XSS_JAVASCRIPT_URL,
} from "../lib/hostile-text-fixtures";
import { GENERIC_PRODUCTION_ERROR } from "../lib/failure-copy";
import { CitationChip } from "./ui/citation-chip";
import { Drawer } from "./ui/drawer";
import { LimitationCallout } from "./ui/limitation-callout";
import { LogicalHighlight } from "./ui/logical-highlight";
import { ReviewedContentFixtures } from "./ui/reviewed-content-fixtures";
import { RovingList } from "./ui/roving-list";
import { StatusBanner } from "./ui/status-banner";

afterEach(() => {
  cleanup();
});

/**
 * Harness that opens a drawer from a chip and restores focus.
 *
 * @returns Drawer demo.
 */
function DrawerHarness() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLElement | null>(null);
  return (
    <div>
      <CitationChip
        index={1}
        citationId={XSS_FILENAME}
        onSelect={(trigger) => {
          triggerRef.current = trigger;
          setOpen(true);
        }}
      />
      {open ? (
        <Drawer
          title="Citation 1"
          onClose={() => setOpen(false)}
          returnFocusRef={triggerRef}
        >
          <LogicalHighlight text={CITATION_LOGICAL_SENTENCE} start={7} end={11} />
          <p>{XSS_JAVASCRIPT_URL}</p>
        </Drawer>
      ) : null}
    </div>
  );
}

describe("logical highlight fixture", () => {
  it("wraps ACME in a mark of text nodes for offsets 7–11", () => {
    render(
      <LogicalHighlight text={CITATION_LOGICAL_SENTENCE} start={7} end={11} />,
    );
    const mark = document.querySelector("mark");
    expect(mark?.textContent).toBe("ACME");
    expect(mark?.querySelector("*")).toBeNull();
    expect(screen.getByText("ACME")).toBeInTheDocument();
  });
});

describe("error focus", () => {
  it("moves focus to a 426/402/MFA error StatusBanner", () => {
    render(
      <StatusBanner kind="error" role="alert">
        {GENERIC_PRODUCTION_ERROR}
      </StatusBanner>,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("tabindex", "-1");
    expect(alert).toHaveFocus();
    expect(alert).toHaveTextContent(GENERIC_PRODUCTION_ERROR);
  });
});

describe("citation drawer keyboard", () => {
  it("closes on Escape and restores focus to the chip", async () => {
    const user = userEvent.setup();
    render(<DrawerHarness />);
    const chip = screen.getByRole("button", { name: "Citation 1" });
    await user.click(chip);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.querySelector("mark")?.textContent).toBe("ACME");
    expect(screen.queryByRole("link")).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(chip).toHaveFocus();
  });
});

describe("roving list", () => {
  it("moves with arrow keys among conversation rows", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <RovingList
        aria-label="Conversations"
        items={[
          { id: "a", item: "Alpha" },
          { id: "b", item: "Beta" },
        ]}
        onSelect={onSelect}
      >
        {(item) => item}
      </RovingList>,
    );
    const first = screen.getByRole("option", { name: "Alpha" });
    const second = screen.getByRole("option", { name: "Beta" });
    expect(first).toHaveAttribute("tabindex", "0");
    expect(second).toHaveAttribute("tabindex", "-1");
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(second).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("Beta");
  });
});

describe("reviewed fixtures stay inert", () => {
  it("renders XSS, javascript URLs, bidi controls, and mixed text as text", () => {
    render(<ReviewedContentFixtures />);
    expect(screen.getAllByText(XSS_FILENAME, { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(XSS_ENTITY, { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(MIXED_BIDI, { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText(DIACRITICS_AR, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(LONG_URL, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(XSS_JAVASCRIPT_URL, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(BIDI_CONTROL, { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByRole("link", { name: /javascript:/i })).toBeNull();
  });
});

describe("A11Y-02 warning body color", () => {
  it("uses an icon plus the sentence, not warning-colored body text alone", () => {
    render(
      <LimitationCallout tone="warning">Private BM25 is unavailable.</LimitationCallout>,
    );
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("Private BM25 is unavailable.");
    expect(status.querySelector("[aria-hidden='true']")).not.toBeNull();
  });
});
