import { describe, expect, it } from "vitest";
import {
  buildTableQueryPlan,
  clientComputedTableTotal,
  tableAnalyzeBody,
  tableExportAllowed,
} from "./table-plan";
import type { TableQueryPlan } from "./types";

describe("buildTableQueryPlan", () => {
  it("omits extra SQL-like fields from the posted plan", () => {
    const plan = buildTableQueryPlan({
      table_id: "11111111-1111-4111-8111-111111111111",
      version_id: "22222222-2222-4222-8222-222222222222",
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

  it("hides export without a chat-run disclosure", () => {
    expect(tableExportAllowed([])).toBe(false);
    expect(tableExportAllowed(["export_csv"])).toBe(true);
  });
});
