---
name: implement-structured-table
description: Implements deterministic CSV/XLSX filtering, grouping, aggregation, comparison, and provenance with validated TableQueryPlan and sandboxed DuckDB. Use for spreadsheet calculations, Parquet access, or structured-table tools.
---

# Implement Structured Table Execution

Read the selected active packet only: Phase 3 table-artifact creation, Phase 4 structured retrieval, Phase 6 composition, or Phase 9/10 release proof. Load no sibling or later-phase packet. Ordinary cell/text lookup remains Hybrid; typed aggregation routes deterministically to `StructuredTable` with no catalog discovery.

## Contract

1. The model may emit only a validated declarative `TableQueryPlan`: authorized table/version IDs, allow-listed columns, typed predicates, aggregations, grouping, ordering, and row limit.
2. Users and models never provide executable SQL, paths, extensions, pragmas, or functions.
3. Resolve table IDs to server-authorized private Parquet artifacts; never trust a client/model path.
4. Run DuckDB in a sandbox with read-only permitted artifacts, no network/extensions/filesystem escape, bounded memory, scanned bytes/rows, output rows, and a three-second statement deadline.
5. Reject ambiguous headers, unsupported formulas/types, mixed units/currencies, missing provenance, non-finite values, and over-limit plans with clarification/refusal.
6. Return deterministic values plus table/version IDs, workbook/sheet, exact source ranges, operation, predicates, units, and row counts.
7. The answer model explains the deterministic result but never recalculates or changes it.

## Proof

Test authorization/IDOR, malicious plans, path traversal, extension/network attempts, timeout/memory/row limits, nulls, dates/timezones, decimal precision, formulas, duplicate headers, mixed currencies, hidden sheets, Unicode/Arabic, aggregation correctness, exact range provenance, retries, and Composite composition with Hybrid/Combined.
