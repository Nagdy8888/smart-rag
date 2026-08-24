/**
 * Compact feedback popover after thumbs selection.
 */

"use client";

import { FEEDBACK_TAGS, type FeedbackTag } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Popover } from "../ui/popover";
import { Select } from "../ui/select";
import styles from "./chat.module.css";

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
  onSubmit: () => void;
};

/**
 * Render thumbs plus a popover for tag/comment.
 *
 * @param props - Controlled feedback fields.
 * @returns Footer controls. Does not change the ten-tag catalog.
 */
export function FeedbackPopover({
  thumbsUp,
  onThumbs,
  tag,
  onTag,
  comment,
  onComment,
  onSubmit,
}: FeedbackPopoverProps) {
  return (
    <div className={styles.answerFooter}>
      <Button type="button" variant={thumbsUp ? "primary" : "ghost"} onClick={() => onThumbs(true)}>
        Thumbs up
      </Button>
      <Button
        type="button"
        variant={!thumbsUp ? "primary" : "ghost"}
        onClick={() => onThumbs(false)}
      >
        Thumbs down
      </Button>
      <Popover label="Feedback details" trigger="Add details">
        <div className={styles.feedbackForm}>
          <Select
            label="Tag"
            value={tag}
            options={FEEDBACK_TAGS.map((item) => ({ value: item, label: item }))}
            onChange={(event) => onTag(event.target.value as FeedbackTag)}
          />
          <Input
            label="Comment"
            value={comment}
            onChange={(event) => onComment(event.target.value)}
          />
          <Button type="button" onClick={onSubmit}>
            Submit feedback
          </Button>
        </div>
      </Popover>
    </div>
  );
}
