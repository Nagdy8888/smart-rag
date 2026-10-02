/**
 * Empty-state gallery that renders canned answers with the live formatters.
 */

"use client";

import { useState } from "react";
import {
  ANSWER_FORMAT_SAMPLES,
  answerFormatSample,
  type AnswerFormatSampleId,
} from "../../lib/answer-format-samples";
import { AnswerContentPreview } from "./answer-surface";
import chatStyles from "./chat-transcript.module.css";

/**
 * Show code, table, prose, and mixed samples inside the Ask column.
 *
 * Visible when the transcript is empty so formatting can be inspected
 * without sending a question. Uses the same render path as live answers.
 *
 * @returns Gallery with tab controls and a live preview.
 */
export function AnswerFormatGallery() {
  const [activeId, setActiveId] = useState<AnswerFormatSampleId>("code");
  const sample = answerFormatSample(activeId);

  return (
    <div
      className={chatStyles.formatGallery}
      data-testid="answer-format-gallery"
      aria-label="Answer format samples"
    >
      <div className={chatStyles.formatGalleryHeader}>
        <p className={chatStyles.formatGalleryTitle}>See answer formatting</p>
        <p className={chatStyles.formatGalleryBlurb}>{sample.blurb}</p>
      </div>
      <div
        className={chatStyles.formatGalleryTabs}
        role="tablist"
        aria-label="Format sample"
      >
        {ANSWER_FORMAT_SAMPLES.map((item) => {
          const selected = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`format-tab-${item.id}`}
              aria-selected={selected}
              aria-controls="format-sample-panel"
              tabIndex={selected ? 0 : -1}
              className={chatStyles.formatGalleryTab}
              data-selected={selected ? "true" : "false"}
              data-action-id="ask.format_sample"
              data-sample={item.id}
              onClick={() => {
                setActiveId(item.id);
              }}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      <div
        className={chatStyles.formatGalleryPanel}
        role="tabpanel"
        id="format-sample-panel"
        aria-labelledby={`format-tab-${sample.id}`}
        data-testid="answer-format-preview"
        data-sample={sample.id}
      >
        <AnswerContentPreview text={sample.answer} />
      </div>
    </div>
  );
}
