import { Icon, type IconName } from "./icon";
import styles from "./styles/knowledge.module.css";

const AUTHORITY = {
  unreviewed: { label: "Unreviewed", tone: "warning", icon: "help" },
  draft: { label: "Draft", tone: "neutral", icon: "fileEdit" },
  approved: { label: "Approved", tone: "success", icon: "checkCircle" },
  superseded: { label: "Superseded", tone: "neutral", icon: "archive" },
};

export function AuthorityStatus({ status }: { status: keyof typeof AUTHORITY }) {
  const { label, tone, icon } = AUTHORITY[status];
  return <span className={styles.status} data-tone={tone}><Icon name={icon as IconName} aria-hidden="true" />{label}</span>;
}

export function KnowledgeNotice({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "warning" | "danger" }) {
  const noticeIcon = tone === "neutral" ? "help" : "alert";
  return <div className={styles.notice} data-tone={tone}><Icon name={noticeIcon} aria-hidden="true" /><div>{children}</div></div>;
}

export function ReviewStatus({ status }: { status: "open" | "resolved" | "dismissed" }) {
  const statusIcon = status === "resolved" ? "checkCircle" : status === "open" ? "clock" : "archive";
  return <span className={styles.status} data-tone={status === "resolved" ? "success" : status === "open" ? "active" : "neutral"}><Icon name={statusIcon} aria-hidden="true" />{status === "open" ? "Open" : status === "resolved" ? "Resolved" : "Dismissed"}</span>;
}

/** Fixed UTC formatting keeps policy dates stable across employee time zones. */
export function knowledgeDate(value: unknown, fallback = "Unknown") {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(T|$)/.test(value)) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? fallback : new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(date);
}
