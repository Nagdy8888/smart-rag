// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  MIXED_BIDI,
  XSS_ENTITY,
  XSS_FILENAME,
} from "../../lib/hostile-text-fixtures";
import { Badge } from "./badge";
import { Button } from "./button";
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
});
