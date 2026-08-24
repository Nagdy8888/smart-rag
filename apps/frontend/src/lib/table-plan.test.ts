import { describe, expect, it } from "vitest";
import {
  EMPTY_TABLE_PLAN_DRAFT,
  PLAN_INCOMPLETE_COPY,
  SQL_REJECTED_COPY,
  UNKNOWN_COLUMN_COPY,
  allowListedResultColumns,
  buildTableQueryPlan,
  clientComputedTableTotal,
  compileTablePlanDraft,
  resolveSelectedManifest,
  tableAnalyzeBody,
  tableExportAllowed,
  tablePlanCompileCopy,
} from "./table-plan";
import type { TableManifestResponse, TableQueryPlan } from "./types";

const MANIFEST: TableManifestResponse = {
  table_id: "11111111-1111-4111-8111-111111111111",
  document_id: "d1",
  version_id: "22222222-2222-4222-8222-222222222222",
  table_name: "Budget",
  sheet_name: "Sheet1",
  row_count: 2,
  column_count: 2,
};

describe("buildTableQueryPlan", () => {
  it("omits extra SQL-like fields from the posted plan", () => {
    const plan = buildTableQueryPlan({
      table_id: MANIFEST.table_id,
      version_id: MANIFEST.version_id,
      predicates: [{ column: "amount", operator: "gt", value: 1 }],
      sql: "SELECT * FROM secret",
    });
    expect(plan).not.toHaveProperty("sql");
    expect(JSON.stringify(plan)).not.toContain("SELECT");
    const body = tableAnalyzeBody({
      ...plan,
      sql: "DROP TABLE x",
    } as TableQueryPlan & { sql?: unknown });
    expect(body).toEqual({ plan: expect.not.objectContaining({ sql: expect.anything() }) });
    expect(JSON.stringify(body)).not.toContain("DROP");
  });

  it("does not sum displayed rows into a fake total", () => {
    expect(clientComputedTableTotal()).toBeNull();
  });

  it("keeps chat-run export disclosure separate from the tables page", () => {
    expect(tableExportAllowed([])).toBe(false);
    expect(tableExportAllowed(["export_csv"])).toBe(true);
  });
});

describe("resolveSelectedManifest", () => {
  const other: TableManifestResponse = {
    ...MANIFEST,
    table_id: "33333333-3333-4333-8333-333333333333",
    document_id: "d2",
    table_name: "Other",
  };

  it("preselects only an accessible tableId", () => {
    expect(
      resolveSelectedManifest([MANIFEST, other], null, MANIFEST.table_id, null)?.table_id,
    ).toBe(MANIFEST.table_id);
    expect(
      resolveSelectedManifest([MANIFEST], null, other.table_id, MANIFEST.document_id),
    ).toBeNull();
  });

  it("falls back to an accessible documentId when tableId is absent", () => {
    expect(
      resolveSelectedManifest([MANIFEST, other], null, null, "d2")?.table_id,
    ).toBe(other.table_id);
  });
});

describe("compileTablePlanDraft", () => {
  it("rejects an empty guided plan before submission", () => {
    const compiled = compileTablePlanDraft(MANIFEST, EMPTY_TABLE_PLAN_DRAFT);
    expect(compiled).toEqual({ ok: false, reason: "incomplete" });
    expect(tablePlanCompileCopy("incomplete")).toBe(PLAN_INCOMPLETE_COPY);
  });

  it("rejects unknown columns and SQL-shaped values before submission", () => {
    const unknown = compileTablePlanDraft(MANIFEST, {
      ...EMPTY_TABLE_PLAN_DRAFT,
      filters: [{ column: "1amount", operator: "eq", value: "1" }],
    });
    expect(unknown).toEqual({ ok: false, reason: "unknown_column" });
    expect(tablePlanCompileCopy("unknown_column")).toBe(UNKNOWN_COLUMN_COPY);

    const sql = compileTablePlanDraft(MANIFEST, {
      ...EMPTY_TABLE_PLAN_DRAFT,
      filters: [{ column: "amount", operator: "eq", value: "select 1 from t" }],
    });
    expect(sql).toEqual({ ok: false, reason: "sql" });
    expect(tablePlanCompileCopy("sql")).toBe(SQL_REJECTED_COPY);
  });

  it("compiles a valid filter plan", () => {
    const compiled = compileTablePlanDraft(MANIFEST, {
      ...EMPTY_TABLE_PLAN_DRAFT,
      filters: [{ column: "amount", operator: "gt", value: "10" }],
    });
    expect(compiled.ok).toBe(true);
    if (compiled.ok) {
      expect(compiled.plan.predicates).toEqual([
        { column: "amount", operator: "gt", value: 10 },
      ]);
      expect(compiled.plan).not.toHaveProperty("sql");
    }
  });
});

describe("allowListedResultColumns", () => {
  it("omits result keys that are not internal identifiers", () => {
    const listed = allowListedResultColumns([
      { amount: 1, "SELECT *": 2 },
    ]);
    expect(listed.columns).toEqual(["amount"]);
    expect(listed.omitted).toBe(true);
  });
});
