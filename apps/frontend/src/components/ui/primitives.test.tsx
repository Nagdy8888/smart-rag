// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import React from "react";
import "@testing-library/jest-dom/vitest";
import {
  MIXED_BIDI,
  XSS_ENTITY,
  XSS_FILENAME,
} from "../../lib/hostile-text-fixtures";
import { Badge } from "./badge";
import { Button } from "./button";
import { ConfirmDialog } from "./confirm-dialog";
import { PageHeader } from "./page-header";
import { CitationChip } from "./citation-chip";
import { DataTable } from "./data-table";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";
import { FileDropZone } from "./file-drop-zone";
import { Input } from "./input";
import { LimitationCallout } from "./limitation-callout";
import { LiveRegion } from "./live-region";
import { Spinner } from "./spinner";
import { StatusBanner } from "./status-banner";
import { StatusPill } from "./status-pill";
import { Textarea } from "./textarea";
import { CodeText, UserText } from "./user-text";
import { Menu } from "./menu";
import { Select } from "./select";
import { Sheet } from "./sheet";
import { Tooltip } from "./tooltip";

afterEach(() => {
  cleanup();
});

const HOSTILE = [XSS_FILENAME, XSS_ENTITY, MIXED_BIDI] as const;

/**
 * Assert a payload rendered as text and that no img/script role appeared.
 *
 * @param payload - Hostile fixture.
 */
function expectTextNotHtml(payload: string): void {
  expect(screen.getAllByText(payload, { exact: false }).length).toBeGreaterThan(0);
  expect(screen.queryByRole("img")).toBeNull();
  expect(document.querySelector("script")).toBeNull();
}

describe("primitives render hostile and mixed-direction text", () => {
  it("keeps XSS payloads as text in every primitive", () => {
    render(
      <div>
        <UserText value={XSS_FILENAME} />
        <UserText value={XSS_ENTITY} />
        <UserText value={MIXED_BIDI} />
        <CodeText value={MIXED_BIDI} />
        <Badge label={XSS_FILENAME} />
        <StatusPill status={XSS_ENTITY} />
        <StatusBanner>{XSS_FILENAME}</StatusBanner>
        <LimitationCallout>{XSS_ENTITY}</LimitationCallout>
        <LiveRegion>{MIXED_BIDI}</LiveRegion>
        <CitationChip index={1} citationId={XSS_FILENAME} />
        <ErrorState title="Error" message={XSS_ENTITY} />
        <EmptyState title="Empty">{XSS_FILENAME}</EmptyState>
        <Button aria-label="Hostile filename">{XSS_FILENAME}</Button>
        <Input label="Filename" defaultValue={XSS_FILENAME} readOnly />
        <Textarea label="Note" defaultValue={MIXED_BIDI} readOnly />
        <DataTable
          caption="Hostile rows"
          columns={[
            {
              id: "name",
              header: "Name",
              cell: (row: { name: string }) => <UserText value={row.name} />,
            },
          ]}
          rows={HOSTILE.map((name) => ({ name }))}
          getRowId={(row) => row.name}
        />
        <FileDropZone onFiles={() => undefined} label={XSS_FILENAME} />
        <Spinner label={XSS_ENTITY} />
      </div>,
    );

    for (const payload of HOSTILE) {
      expectTextNotHtml(payload);
    }
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Hostile filename" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveAttribute(
      "aria-label",
      "Citation 1",
    );
  });

  it("gives banners status or alert roles and buttons accessible names", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <div>
        <StatusBanner role="status">Ready</StatusBanner>
        <StatusBanner kind="error" role="alert">
          Denied
        </StatusBanner>
        <Button onClick={onClick}>Save</Button>
      </div>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Ready");
    expect(screen.getByRole("alert")).toHaveTextContent("Denied");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("keeps hostile option labels as text in Select and Menu", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <div>
        <Select
          label="Visibility"
          value="private"
          options={[
            { value: "private", label: XSS_FILENAME },
            { value: "shared", label: XSS_ENTITY },
          ]}
          onChange={() => undefined}
        />
        <Menu
          label="Row actions"
          trigger="Actions"
          items={[
            { id: "open", label: MIXED_BIDI, onSelect },
            { id: "delete", label: XSS_FILENAME, onSelect, danger: true },
          ]}
        />
        <Tooltip text={XSS_ENTITY}>
          <Button aria-label="Help">Help</Button>
        </Tooltip>
      </div>,
    );
    expect(screen.getByRole("combobox", { name: "Visibility" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: XSS_FILENAME })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Row actions" }));
    expect(screen.getByRole("menuitem", { name: XSS_FILENAME })).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("traps focus in a Sheet and restores the trigger", async () => {
    const user = userEvent.setup();
    function SheetHarness() {
      const [open, setOpen] = React.useState(false);
      const triggerRef = React.useRef<HTMLButtonElement>(null);
      return (
        <div>
          <Button ref={triggerRef} onClick={() => setOpen(true)}>
            Open sheet
          </Button>
          {open ? (
            <Sheet
              title="Sources"
              onClose={() => setOpen(false)}
              returnFocusRef={triggerRef}
            >
              <Button>Inside</Button>
              <p>{XSS_FILENAME}</p>
            </Sheet>
          ) : null}
        </div>
      );
    }
    render(<SheetHarness />);
    await user.click(screen.getByRole("button", { name: "Open sheet" }));
    expect(screen.getByRole("dialog", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByText(XSS_FILENAME)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Open sheet" })).toHaveFocus();
  });
});

describe("pending buttons and confirm dialog", () => {
  it("blocks duplicate pending clicks and shows the disabled reason", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button
        pending
        pendingLabel="Saving…"
        disabledReason="Save in progress"
        onClick={onClick}
      >
        Save
      </Button>,
    );
    const control = screen.getByRole("button", { name: "Saving…" });
    expect(control).toBeDisabled();
    expect(screen.getByText("Save in progress")).toBeInTheDocument();
    await user.click(control);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("renders a PageHeader lead without a duplicate title heading", () => {
    render(
      <PageHeader title="Documents" description="Current versions only." />,
    );
    expect(screen.queryByRole("heading", { name: "Documents" })).toBeNull();
    expect(screen.getByText("Current versions only.")).toBeInTheDocument();
  });

  it("focuses Cancel on a danger confirm and ignores Escape while pending", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    const { rerender } = render(
      <ConfirmDialog
        title="Delete report.pdf"
        danger
        confirmLabel="Delete"
        onClose={onClose}
        onConfirm={onConfirm}
      >
        This permanently removes report.pdf.
      </ConfirmDialog>,
    );
    const cancel = screen.getByRole("button", { name: "Cancel" });
    await waitFor(() => {
      expect(cancel).toHaveFocus();
    });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    onClose.mockClear();
    rerender(
      <ConfirmDialog
        title="Delete report.pdf"
        danger
        pending
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        onClose={onClose}
        onConfirm={onConfirm}
      >
        This permanently removes report.pdf.
      </ConfirmDialog>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Deleting…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});

describe("EmptyState", () => {
  it("renders title, body, and action", () => {
    render(
      <EmptyState
        title="Ask your company knowledge"
        body="Answers come from your authorized documents, with citations you can inspect."
        action={<Button>Try a prompt</Button>}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Ask your company knowledge" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Answers come from your authorized documents, with citations you can inspect.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try a prompt" })).toBeInTheDocument();
  });
});
