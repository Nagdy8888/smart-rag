/**
 * Relative timestamps and session-rail age groups for the Ask surface.
 */

export const CONVERSATION_AGE_GROUPS = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Older",
] as const;

export type ConversationAgeGroup = (typeof CONVERSATION_AGE_GROUPS)[number];

const MS_PER_SECOND = 1000;
const MS_PER_MINUTE = 60 * MS_PER_SECOND;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const MS_PER_DAY = 24 * MS_PER_HOUR;
const WEEK_MS = 7 * MS_PER_DAY;

/**
 * Return a start-of-local-day Date for `value`.
 *
 * @param value - Instant used as the calendar day.
 * @returns Local midnight on that day.
 */
function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

/**
 * Format an ISO timestamp with `Intl.RelativeTimeFormat`.
 *
 * Instants older than seven days use a short month/day date instead.
 *
 * @param iso - ISO-8601 timestamp.
 * @param now - Comparison instant. Defaults to the current time.
 * @returns Relative phrase or short date. Invalid input returns an empty string.
 */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const diffMs = date.getTime() - now.getTime();
  if (Math.abs(diffMs) >= WEEK_MS) {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(date);
  }
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const abs = Math.abs(diffMs);
  if (abs < MS_PER_MINUTE) {
    return rtf.format(Math.round(diffMs / MS_PER_SECOND), "second");
  }
  if (abs < MS_PER_HOUR) {
    return rtf.format(Math.round(diffMs / MS_PER_MINUTE), "minute");
  }
  if (abs < MS_PER_DAY) {
    return rtf.format(Math.round(diffMs / MS_PER_HOUR), "hour");
  }
  return rtf.format(Math.round(diffMs / MS_PER_DAY), "day");
}

/**
 * Bucket a conversation timestamp for the Sessions rail.
 *
 * @param iso - ISO-8601 created time, or null when unknown.
 * @param now - Comparison instant. Defaults to the current time.
 * @returns One of Today, Yesterday, Previous 7 days, or Older.
 */
export function conversationAgeGroup(
  iso: string | null,
  now: Date = new Date(),
): ConversationAgeGroup {
  if (iso === null || iso === "") {
    return "Older";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "Older";
  }
  const today = startOfLocalDay(now);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - 7);
  if (date >= today) {
    return "Today";
  }
  if (date >= yesterday) {
    return "Yesterday";
  }
  if (date >= weekStart) {
    return "Previous 7 days";
  }
  return "Older";
}
