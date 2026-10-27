import styles from "../ui/styles/knowledge.module.css";
import { AuthorityStatus, KnowledgeNotice, knowledgeDate } from "../ui/knowledge-status";
import type { CitationResponse } from "../../lib/types";
import { UserText } from "../ui/user-text";

/** Render only metadata returned by the authorized citation-detail request. */
export function SourceAuthority({ citation }: { citation: CitationResponse }) {
  const authority = citation.provenance?.authority;
  if (citation.source_unavailable || !authority || typeof authority !== "object" || Array.isArray(authority)) return null;
  const values = authority as Record<string, unknown>;
  const status = values.authority_status;
  if (typeof status !== "string" || !["unreviewed", "draft", "approved", "superseded"].includes(status)) return null;
  const fields = [["Version", typeof values.version_number === "number" ? String(values.version_number) : null], ["Accountable owner", values.owner_display_name ?? (values.owner_user_id ? "Assigned" : null)],
    ["Knowledge area", values.knowledge_area], ["Effective date", knowledgeDate(values.effective_at)], ["Review due", knowledgeDate(values.review_due_at, "Not scheduled")]];
  return <section className={styles.source} aria-label="Source authority"><div className={styles.header}><h3>Source authority</h3><AuthorityStatus status={status as "approved" | "unreviewed" | "draft" | "superseded"} /></div>
    <dl className={styles.metadata}>{fields.map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd><UserText value={typeof value === "string" ? value : "Unknown"} /></dd></div>)}</dl>
    {status === "unreviewed" ? <KnowledgeNotice tone="warning"><p>This source has not been approved. Its currentness is unconfirmed.</p></KnowledgeNotice> : null}
  </section>;
}
