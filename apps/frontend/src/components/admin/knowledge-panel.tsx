"use client";

import { useId, useState } from "react";
import { Icon } from "../ui/icon";
import knowledge from "../ui/styles/knowledge.module.css";
import { ReviewStatus } from "../ui/knowledge-status";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listMaintenance, updateMaintenance, type MaintenanceItem, type MaintenanceUpdate } from "../../lib/api/knowledge-maintenance";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { sessionCacheScope } from "../../lib/query-keys";
import { displayText } from "../../lib/safe-text";
import { UserText } from "../ui/user-text";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Button } from "../ui/button";
import { KnowledgeOwnerSelect } from "../ui/knowledge-owner-select";
import styles from "./admin-tables.module.css";

const LABELS = { missing_owner: "Missing knowledge owner", overdue_review: "Review overdue",
  feedback: "Employee feedback", insufficient_evidence: "Unanswered question", conflicting_evidence: "Conflicting evidence" };

/** Maintenance is human review; feedback never becomes company truth automatically. */
export function KnowledgePanel() {
  const auth = useApiAuth();
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["knowledge-maintenance", sessionCacheScope(auth?.accessToken ?? null), offset],
    queryFn: () => listMaintenance(auth!, offset), enabled: auth !== null });
  return <section className={styles.panel} aria-label="Knowledge maintenance">
    <div className={knowledge.header}><div><h2>Knowledge maintenance</h2><p className={knowledge.lead}>Review source ownership, overdue guidance, and answer problems.</p></div></div>
    <p className={knowledge.scopeNote}><Icon name="lock" aria-hidden="true" />Private questions appear only for their creator or when explicitly shared for review. Source permissions still apply.</p>
    {query.isPending ? <p className={knowledge.lead} role="status">Loading review queue…</p> : query.isError ?
      <p role="alert">The review queue could not be loaded. <button className={knowledge.textAction} onClick={() => void query.refetch()}>Retry</button></p> :
      query.data?.length ? query.data.map((item) => <MaintenanceRow key={`${item.kind}:${item.source_id}:${item.revision}`} item={item} />) :
      <div className={knowledge.empty}><Icon name="curation" aria-hidden="true" /><div><h3>No visible maintenance items on this page.</h3><p className={knowledge.lead}>Ownership, review dates, and shared answer reports appear here when they need attention.</p></div></div>}
    <div className={knowledge.pagination}><p>Review queue, page {Math.floor(offset / 50) + 1}</p><div className={knowledge.actions}><Button variant="ghost" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button>
      <Button variant="ghost" disabled={query.data?.length !== 50 || query.isFetching || offset >= 10000} onClick={() => setOffset(offset + 50)}>Next</Button></div></div>
  </section>;
}

function MaintenanceRow({ item }: { item: MaintenanceItem }) {
  const auth = useApiAuth();
  const client = useQueryClient();
  const fieldId = useId();
  const [status, setStatus] = useState(item.status);
  const [assigned, setAssigned] = useState(item.assigned_to ?? "");
  const [reason, setReason] = useState(item.reason ?? "");
  const mutation = useMutation({ mutationFn: (body: MaintenanceUpdate) => updateMaintenance(auth!, item, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["knowledge-maintenance"] }) });
  return <article className={styles.reviewItem}>
    <div className={knowledge.reviewHeader}>
      <div><span className={knowledge.status}>{LABELS[item.kind]}</span><h3 className={knowledge.reviewTitle}><UserText value={item.title ?? "Untitled"} /></h3></div>
      <ReviewStatus status={item.status} />
    </div>
    {item.document_id ? <div className={knowledge.actions}><Link className={knowledge.textAction} href={`/documents/${encodeURIComponent(item.document_id)}`}>Review document</Link></div> : null}
    {Object.entries(item.report).some(([, value]) => value) ? <details className={knowledge.details}><summary>View report details</summary><div className={knowledge.reviewBody}>
      {Object.entries(item.report).filter(([, value]) => value).map(([key, value]) => <div key={key}><strong>{key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())}</strong><p dir="auto"><UserText value={value!} /></p></div>)}
    </div></details> : null}
    <form className={knowledge.formGrid} onSubmit={(event) => { event.preventDefault(); mutation.mutate({ expected_revision: item.revision, status,
      assigned_to: assigned || null, reason: reason.trim() || null }); }}>
      <KnowledgeOwnerSelect label="Assigned reviewer" value={assigned} onChange={setAssigned} reviewersOnly />
      <Select id={`${fieldId}-status`} label="Review status" value={status} options={["open", "resolved", "dismissed"].map((value) => ({ value, label: value.charAt(0).toUpperCase() + value.slice(1) }))}
        onChange={(event) => setStatus(event.target.value as MaintenanceItem["status"])} />
      <div className={knowledge.full}><Input fullWidth id={`${fieldId}-reason`} label="Review reason or expected correction" required={status !== "open"} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      <div className={`${knowledge.actions} ${knowledge.full}`}><Button type="submit" variant="primary" data-action-id="knowledge.review.save" pending={mutation.isPending}>Save review</Button></div>
      {mutation.isError ? <p className={knowledge.full} role="alert">Could not save. Refresh the queue to check permissions and newer changes.</p> : null}
    </form>
    {item.status === "resolved" && item.kind === "feedback" && item.report.question && item.reason ?
      <a className={knowledge.textAction} data-action-id="knowledge.review.export" download={`knowledge-regression-${item.source_id}.json`} href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify({
        schema: "company-knowledge-regression-draft-v1", split: "regression", status: "needs_gold_review",
        case_id: `feedback-${item.source_id}`, question: displayText(item.report.question), expected_behavior: displayText(item.reason),
        source_run_id: item.run_id,
      }, null, 2))}`}>Download regression draft for evaluation review</a> : null}
  </article>;
}
