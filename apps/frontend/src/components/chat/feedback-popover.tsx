/**
 * Compact feedback popover after thumbs selection.
 */

"use client";

import { useState } from "react";

import { feedbackTagsFor, type FeedbackTag } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Popover } from "../ui/popover";
import { Select } from "../ui/select";
import knowledge from "../ui/styles/knowledge.module.css";
import styles from "./chat-transcript.module.css";

export type FeedbackPopoverProps = {
  /** Thumbs up selected. */
  thumbsUp: boolean;
  /** Set thumbs. */
  onThumbs: (up: boolean) => void;
  /** Catalog tag. */
  tag: FeedbackTag;
  /** Tag change. */
  onTag: (tag: FeedbackTag) => void;
  /** Optional comment. */
  comment: string;
  /** Comment change. */
  onComment: (value: string) => void;
  /** Submit existing catalog payload. */
  onSubmit: (shareWithReviewers?: boolean) => void;
  /** True while submit is in flight. */
  pending?: boolean;
};

/**
 * Keep the selected tag inside the current thumb catalog.
 *
 * @param thumbsUp - Selected polarity.
 * @param tag - Current tag.
 * @param onThumbs - Persist polarity.
 * @param onTag - Persist tag when polarity changes the catalog.
 */
function selectThumbs(
  thumbsUp: boolean,
  tag: FeedbackTag,
  onThumbs: (up: boolean) => void,
  onTag: (tag: FeedbackTag) => void,
): void {
  onThumbs(thumbsUp);
  const options = feedbackTagsFor(thumbsUp);
  if (!options.includes(tag)) {
    onTag(options[0]);
  }
}

/**
 * Render thumbs plus a popover for tag/comment.
 *
 * @param props - Controlled feedback fields.
 * @returns Footer controls. Tag options follow the selected thumb.
 */
export function FeedbackPopover({
  thumbsUp,
  onThumbs,
  tag,
  onTag,
  comment,
  onComment,
  onSubmit,
  pending = false,
}: FeedbackPopoverProps) {
  const tagOptions = feedbackTagsFor(thumbsUp);
  const [share, setShare] = useState(false);
  return (
    <Popover label="Give feedback" trigger="Give feedback">
      <div className={styles.feedbackForm}>
          <div className={styles.row}>
            <Button
              type="button"
              variant={thumbsUp ? "primary" : "ghost"}
              onClick={() => selectThumbs(true, tag, onThumbs, onTag)}
            >
              Thumbs up
            </Button>
            <Button
              type="button"
              variant={!thumbsUp ? "primary" : "ghost"}
              onClick={() => selectThumbs(false, tag, onThumbs, onTag)}
            >
              Thumbs down
            </Button>
          </div>
          <Select
            label="Tag"
            value={tag}
            options={tagOptions.map((item) => ({ value: item, label: item }))}
            onChange={(event) => onTag(event.target.value as FeedbackTag)}
          />
          <Input
            label="Comment"
            value={comment}
            onChange={(event) => onComment(event.target.value)}
          />
          <label className={knowledge.consent}><input data-action-id="knowledge.feedback.share" type="checkbox" checked={share} onChange={(event) => setShare(event.target.checked)} />
            <span>Share this question, answer, and feedback with workspace owners and admins for knowledge review.</span>
          </label>
          <Button
            type="button"
            data-action-id="ask.feedback"
            pending={pending}
            pendingLabel="Submitting…"
            onClick={() => onSubmit(share)}
          >
            Submit feedback
          </Button>

        </div>
      </Popover>
  );
}
