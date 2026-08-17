/**
 * Extra-forbid administration body builders.
 */

import { describe, expect, it } from "vitest";
import {
  buildEntityRuleConcurrencyBody,
  buildGlossaryImportBody,
  buildInvitationCreateBody,
} from "./admin-bodies";

describe("admin extra-forbid builders", () => {
  it("drops sql from glossary import and entries", () => {
    const body = buildGlossaryImportBody({
      source_name: "sme",
      source_version: "1",
      idempotency_key: "idem-gloss-1",
      sql: "select 1",
      entries: [
        {
          entry_key: "CODE.1",
          canonical_term: "Code",
          language: "en",
          entry_type: "product_code",
          effective_scope: "company",
          sql: "drop table x",
          extra: "nope",
        },
      ],
    } as never);
    expect(body).toEqual({
      source_name: "sme",
      source_version: "1",
      idempotency_key: "idem-gloss-1",
      entries: [
        {
          entry_key: "CODE.1",
          canonical_term: "Code",
          language: "en",
          entry_type: "product_code",
          effective_scope: "company",
        },
      ],
    });
  });

  it("approve body is row_version only", () => {
    expect(buildEntityRuleConcurrencyBody(7)).toEqual({ row_version: 7 });
  });

  it("viewer invitations cannot set upload_enabled on the client builder", () => {
    const body = buildInvitationCreateBody({
      email: "v@b.test",
      role: "viewer",
      upload_enabled: true,
    });
    expect(body.upload_enabled).toBe(false);
  });
});
