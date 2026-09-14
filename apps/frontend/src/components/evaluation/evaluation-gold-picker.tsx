/**
 * Keyboard-operable 0–3 required-source picker from current authorized passages.
 */

"use client";

import {
  boundedPassagePreview,
  evalGoldPageCaption,
  QUIZ_MAX_GOLD_CHUNKS,
} from "../../lib/eval-workspace";
import type { PdfEvalGoldLocator, PdfEvalPassage } from "../../lib/types";
import { Button } from "../ui/button";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import styles from "./evaluation.module.css";

export type EvaluationGoldPickerProps = {
  /** ACL-visible document title, or a fallback. Hostile. */
  documentTitle: string;
  /** Current passage page plus any extra pages. */
  passages: readonly PdfEvalPassage[];
  /** Selected chunk IDs, 0–3. */
  selectedIds: readonly string[];
  /** Saved locators for page labels of selected gold. */
  gold: readonly PdfEvalGoldLocator[];
  /** Toggle a chunk. */
  onToggle: (chunkId: string) => void;
  /** Next passage cursor. */
  nextChunkId: string | null;
  /** Passage load-more pending. */
  loadMorePending: boolean;
  /** Fetch the next passage page. */
  onLoadMore: () => void;
  /** Gold PUT pending. */
  savePending: boolean;
  /** Persist selected chunk IDs. */
  onSave: () => void;
  /** Gold save error copy. */
  saveError: string | null;
  /** True when selected IDs differ from saved gold. */
  selectionDirty: boolean;
};

type PassageRow = {
  chunkId: string;
  heading: string;
  pageCaption: string;
  preview: string;
  missing: boolean;
};

/**
 * Build picker rows, then selected-before-unselected with stable order.
 *
 * @param passages - Authorized current passages.
 * @param selectedIds - Selected chunk IDs.
 * @param gold - Saved locators.
 * @returns Ordered rows.
 */
function buildPassageRows(
  passages: readonly PdfEvalPassage[],
  selectedIds: readonly string[],
  gold: readonly PdfEvalGoldLocator[],
): PassageRow[] {
  const selectedSet = new Set(selectedIds);
  const seen = new Set<string>();
  const rows: PassageRow[] = [];
  for (const locator of gold) {
    if (!selectedSet.has(locator.chunk_id) || seen.has(locator.chunk_id)) {
      continue;
    }
    seen.add(locator.chunk_id);
    const passage = passages.find((item) => item.chunk_id === locator.chunk_id);
    rows.push({
      chunkId: locator.chunk_id,
      heading: locator.section_path.join(" / ") || (passage?.heading_path.join(" / ") ?? ""),
      pageCaption: evalGoldPageCaption({
        pageLabel: locator.page_label,
        pageNumber: locator.page_number ?? passage?.page_number ?? null,
      }),
      preview: boundedPassagePreview(passage?.raw_text ?? ""),
      missing: passage === undefined,
    });
  }
  for (const passage of passages) {
    if (seen.has(passage.chunk_id)) {
      continue;
    }
    seen.add(passage.chunk_id);
    const locator = gold.find((item) => item.chunk_id === passage.chunk_id);
    rows.push({
      chunkId: passage.chunk_id,
      heading: passage.heading_path.join(" / "),
      pageCaption: evalGoldPageCaption({
        pageLabel: locator?.page_label ?? null,
        pageNumber: passage.page_number,
      }),
      preview: boundedPassagePreview(passage.raw_text),
      missing: false,
    });
  }
  for (const chunkId of selectedIds) {
    if (seen.has(chunkId)) {
      continue;
    }
    seen.add(chunkId);
    rows.push({
      chunkId,
      heading: "",
      pageCaption: "Page unknown",
      preview: "",
      missing: true,
    });
  }
  const selectedRows = rows.filter((row) => selectedSet.has(row.chunkId));
  const otherRows = rows.filter((row) => !selectedSet.has(row.chunkId));
  return [...selectedRows, ...otherRows];
}

/**
 * Render labeled checkboxes for current passages, including non-citation chunks.
 *
 * @param props - Passages, selection, and save handlers.
 * @returns Required-source picker. Native checkboxes are keyboard-operable.
 */
export function EvaluationGoldPicker({
  documentTitle,
  passages,
  selectedIds,
  gold,
  onToggle,
  nextChunkId,
  loadMorePending,
  onLoadMore,
  savePending,
  onSave,
  saveError,
  selectionDirty,
}: EvaluationGoldPickerProps) {
  const selectedSet = new Set(selectedIds);
  const rows = buildPassageRows(passages, selectedIds, gold);
  const atMax = selectedIds.length >= QUIZ_MAX_GOLD_CHUNKS;

  return (
    <section
      className={styles.goldPicker}
      id="eval-gold-picker"
      tabIndex={-1}
      aria-label="Required source passages"
      data-action-id="eval.passages"
    >
      <h3>Required source passages</h3>
      <p className={styles.muted}>
        Select up to 3 current passages that must be found for this question.
        Saving source changes returns an approved case to draft review.
      </p>
      <p className={styles.muted}>
        {`${String(selectedIds.length)} of ${String(QUIZ_MAX_GOLD_CHUNKS)} selected`}
      </p>
      {atMax ? (
        <p className={styles.muted}>
          Remove a selected passage before choosing another.
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className={styles.muted}>No current passages for this document.</p>
      ) : (
        <ul className={styles.goldList}>
          {rows.map((row) => {
            const checked = selectedSet.has(row.chunkId);
            const blocked = !checked && atMax;
            return (
              <li
                key={row.chunkId}
                className={
                  checked ? `${styles.goldItem} ${styles.goldItemSelected}` : styles.goldItem
                }
              >
                <input
                  type="checkbox"
                  id={`eval-gold-${row.chunkId}`}
                  checked={checked}
                  disabled={blocked}
                  onChange={() => {
                    if (blocked) {
                      return;
                    }
                    onToggle(row.chunkId);
                  }}
                />
                <div className={styles.goldBody}>
                  <label htmlFor={`eval-gold-${row.chunkId}`}>
                    <span>
                      <UserText value={documentTitle} />
                      {" · "}
                      {row.pageCaption}
                      {checked ? <span className={styles.muted}> Selected</span> : null}
                    </span>
                    {row.heading ? (
                      <span className={styles.muted}>
                        {" "}
                        <UserText value={row.heading} />
                      </span>
                    ) : null}
                    {row.missing ? (
                      <span className={styles.muted}>
                        {" "}
                        Missing from current passages. Remap from the list below.
                      </span>
                    ) : null}
                  </label>
                  {row.preview ? (
                    <details>
                      <summary>Preview passage</summary>
                      <p className={styles.preview} dir="auto">
                        <UserText value={row.preview} />
                      </p>
                    </details>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {nextChunkId ? (
        <Button
          type="button"
          data-action-id="eval.passages_more"
          pending={loadMorePending}
          pendingLabel="Loading passages…"
          onClick={onLoadMore}
        >
          Load more passages
        </Button>
      ) : null}
      <Button
        type="button"
        data-action-id="eval.gold_save"
        pending={savePending}
        pendingLabel="Saving gold…"
        disabled={!selectionDirty}
        disabledReason={
          selectionDirty ? undefined : "No source changes to save."
        }
        onClick={onSave}
      >
        Save source passages
      </Button>
      {saveError ? (
        <StatusBanner kind="error" role="status">
          {saveError}
        </StatusBanner>
      ) : null}
    </section>
  );
}
