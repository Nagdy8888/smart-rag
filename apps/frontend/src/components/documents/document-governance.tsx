"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { documentGovernance, governanceVersions, type DocumentGovernance, type GovernanceUpdate } from "../../lib/api/document-governance";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { sessionCacheScope } from "../../lib/query-keys";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Button } from "../ui/button";
import { UserText } from "../ui/user-text";
import { KnowledgeOwnerSelect } from "../ui/knowledge-owner-select";
import styles from "./documents.module.css";
import knowledge from "../ui/styles/knowledge.module.css";
import { AuthorityStatus, KnowledgeNotice, knowledgeDate } from "../ui/knowledge-status";

/** Live authority metadata, kept separate from extraction/indexing status. */
export function DocumentGovernancePanel({ documentId, canManage, currentVersionId }: {
  documentId: string; canManage: boolean; currentVersionId?: string | null;
}) {
  const auth = useApiAuth();
  const [versionId, setVersionId] = useState<string | null>(null);
  const versions = useQuery({ queryKey: ["document-governance-versions", documentId, sessionCacheScope(auth?.accessToken ?? null)],
    queryFn: () => governanceVersions(auth!, documentId), enabled: auth !== null && canManage });
  const query = useQuery({
    queryKey: ["document-governance", documentId, sessionCacheScope(auth?.accessToken ?? null), versionId],
    queryFn: () => documentGovernance(auth!, documentId, undefined, undefined, versionId),
    enabled: auth !== null,
  });
  return <section className={styles.section} aria-label="Knowledge authority">
    <div className={knowledge.header}><div><h2>Knowledge authority</h2><p className={knowledge.lead}>Who maintains this source and when it applies.</p></div>{query.data ? <AuthorityStatus status={query.data.authority_status} /> : null}</div>
    {canManage && versions.data?.length ? <Select label="Document version" value={versionId ?? ""}
      options={[{ value: "", label: "Current version" }, ...versions.data.map((version) => ({ value: version.version_id!, label: `Version ${version.version_number ?? "unknown"} · ${version.authority_status}` }))]}
      onChange={(event) => setVersionId(event.target.value || null)} /> : null}
    {query.isPending ? <p role="status">Loading authority details…</p> : query.isError ?
      <p role="alert">Authority details could not be loaded. <button onClick={() => void query.refetch()}>Retry</button></p> :
      query.data ? <>
        {query.data.authority_status === "unreviewed" ? <KnowledgeNotice tone="warning"><p>This source has not been approved. Its currentness is unconfirmed.</p></KnowledgeNotice> : null}
        <dl className={knowledge.metadata}>
          <div><dt>Knowledge area</dt><dd><UserText value={query.data.knowledge_area ?? "Unassigned"} /></dd></div>
          <div><dt>Accountable owner</dt><dd><UserText value={query.data.owner_display_name ?? (query.data.owner_user_id ? "Assigned" : "Unassigned")} /></dd></div>
          <div><dt>Effective date</dt><dd>{knowledgeDate(query.data.effective_at)}</dd></div>
          <div><dt>Review due</dt><dd>{knowledgeDate(query.data.review_due_at, "Not scheduled")}</dd></div>
        </dl>
        {query.data.review_due_at && query.data.review_due_at < new Date().toISOString().slice(0, 10) ?
          <KnowledgeNotice tone="warning"><p>Review overdue. This does not automatically expire the source.</p></KnowledgeNotice> : null}
        {!query.data.reliability_enabled ? <p className={knowledge.lead}>Authority-aware answering is not enabled for this workspace.</p> : null}
        {canManage && query.data.version_id ? <GovernanceForm key={`${documentId}:${query.data.version_id}:${query.data.governance_generation}`}
          documentId={documentId} current={query.data} versions={versions.data ?? []}
          currentVersionId={currentVersionId ?? (versionId === null ? query.data.version_id : null)} /> : null}
      </> : null}
  </section>;
}

function GovernanceForm({ documentId, current, versions, currentVersionId }: {
  documentId: string; current: DocumentGovernance; versions: DocumentGovernance[]; currentVersionId: string | null;
}) {
  const auth = useApiAuth();
  const client = useQueryClient();
  const [owner, setOwner] = useState(current.owner_user_id ?? "");
  const [area, setArea] = useState(current.knowledge_area ?? "");
  const [review, setReview] = useState(current.review_due_at ?? "");
  const [effective, setEffective] = useState(current.effective_at?.slice(0, 10) ?? "");
  const [authority, setAuthority] = useState(current.authority_status);
  const [replacement, setReplacement] = useState(current.superseded_by_version_id ?? "");
  const mutation = useMutation({
    mutationFn: (body: GovernanceUpdate) => documentGovernance(auth!, documentId, body),
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: ["document-governance", documentId] }),
      client.invalidateQueries({ queryKey: ["document-governance-versions", documentId] })]),
  });
  return <details className={knowledge.details}><summary>Manage authority</summary>
    <form className={knowledge.formGrid} onSubmit={(event) => {
      event.preventDefault();
      mutation.mutate({ version_id: current.version_id!, expected_generation: current.governance_generation,
        owner_user_id: owner || null, knowledge_area: area.trim() || null,
        review_due_at: review || null, authority_status: authority,
        effective_at: effective === current.effective_at?.slice(0, 10) ? current.effective_at : effective ? `${effective}T00:00:00Z` : null,
        superseded_by_version_id: authority === "superseded" ? replacement || null : null });
    }}>
      <KnowledgeOwnerSelect label="Accountable owner" value={owner} onChange={setOwner} />
      <Input label="Knowledge area" value={area} maxLength={120} onChange={(e) => setArea(e.target.value)} />
      <Input label="Effective date (UTC)" type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />
      <Input label="Review due date" type="date" value={review} onChange={(e) => setReview(e.target.value)} />
      <Select label="Authority status" value={authority} options={["unreviewed", "draft", "approved", "superseded"].map((value) => ({ value, label: value.charAt(0).toUpperCase() + value.slice(1),
        disabled: value === "superseded" && current.version_id === currentVersionId }))}
        onChange={(e) => setAuthority(e.target.value as DocumentGovernance["authority_status"])} />
      {authority === "superseded" ? <Select label="Approved replacement version" required value={replacement}
        options={[{ value: "", label: "Choose the current approved version" }, ...versions.filter((version) => version.version_id === currentVersionId && version.authority_status === "approved")
          .map((version) => ({ value: version.version_id!, label: `Version ${version.version_number ?? "unknown"}` }))]}
        onChange={(event) => setReplacement(event.target.value)} /> : null}
      {authority === "approved" ? <p className={`${knowledge.lead} ${knowledge.full}`}>Approval requires an active owner and an explicit effective date.</p> : null}
      <div className={`${knowledge.actions} ${knowledge.full}`}><Button type="submit" variant="primary" data-action-id="knowledge.authority.save" pending={mutation.isPending}>Save authority</Button></div>
      {mutation.isError ? <p className={knowledge.full} role="alert">Could not save. Check the fields and reload authority details if another administrator changed this version.</p> : null}
      {mutation.isSuccess ? <p className={knowledge.full} role="status">Authority saved.</p> : null}
    </form>
  </details>;
}
