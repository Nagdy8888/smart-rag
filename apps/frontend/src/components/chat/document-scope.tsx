"use client";

import { Icon } from "../ui/icon";
import styles from "../ui/styles/knowledge.module.css";
import { useEffect, useId } from "react";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createConversation, listDocuments, nextDocumentCursor } from "../../lib/api";
import { knowledgeScope } from "../../lib/api/knowledge-scope";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { sessionCacheScope } from "../../lib/query-keys";
import { displayText } from "../../lib/safe-text";
import scopeStyles from "./document-scope.module.css";
import { Button } from "../ui/button";

/** Single-document v1 scope persists across follow-ups and can be explicitly cleared. */
export function DocumentScope({ conversationId, onConversationId, running, onPendingChange }: {
  conversationId: string | null; onConversationId: (id: string) => void; running: boolean;
  onPendingChange: (pending: boolean) => void;
}) {
  const fieldId = useId();
  const auth = useApiAuth();
  const client = useQueryClient();
  const user = sessionCacheScope(auth?.accessToken ?? null);
  const scope = useQuery({ queryKey: ["knowledge-scope", user, conversationId],
    queryFn: () => knowledgeScope(auth!, conversationId!), enabled: auth !== null && conversationId !== null });
  const documents = useInfiniteQuery({ queryKey: ["scope-documents", user], initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listDocuments(auth!, { cursor: pageParam }), enabled: auth !== null,
    getNextPageParam: (lastPage) => nextDocumentCursor(lastPage) ?? undefined });
  const mutation = useMutation({ mutationFn: async (documentId: string | null) => {
    const id = conversationId ?? (await createConversation(auth!, null)).conversation_id;
    const result = await knowledgeScope(auth!, id, documentId);
    return { id, result };
  }, onSuccess: ({ id, result }) => {
    client.setQueryData(["knowledge-scope", user, id], result);
    onConversationId(id);
    void client.invalidateQueries({ queryKey: ["conversations", user] });
  } });
  useEffect(() => {
    onPendingChange(mutation.isPending);
    return () => onPendingChange(false);
  }, [mutation.isPending, onPendingChange]);
  const rows = documents.data?.pages.flat().filter((item) => item.current_version_id) ?? [];
  const selected = scope.data?.document_id ?? "";
  return <div className={scopeStyles.scope} aria-label="Company document scope">
    <div className={scopeStyles.controls}>
      <div className={scopeStyles.picker}>
        <label className={scopeStyles.label} htmlFor={fieldId}>Company document scope</label>
        <Icon className={scopeStyles.documentIcon} name="documents" aria-hidden="true" />
        <select id={fieldId} className={scopeStyles.select} data-action-id="knowledge.scope.select"
          value={selected} aria-busy={mutation.isPending}
          disabled={running || mutation.isPending || scope.isError || (conversationId !== null && scope.isPending)}
          onChange={(event) => mutation.mutate(event.target.value || null)}>
          <option value="">All authorized company documents</option>
          {selected && !rows.some((item) => item.document_id === selected) ? <option value={selected}>{displayText(scope.data?.title ?? "Selected document")}</option> : null}
          {rows.map((item) => <option key={item.document_id} value={item.document_id}>{displayText(item.title ?? "Untitled document")}</option>)}
        </select>
        <Icon className={scopeStyles.chevron} name="chevron" aria-hidden="true" />
      </div>
      {selected || scope.data?.unavailable ? <Button className={scopeStyles.clear} data-action-id="knowledge.scope.clear" variant="ghost" size="compact" aria-label="Clear document scope" disabled={running || mutation.isPending} onClick={() => mutation.mutate(null)}><Icon name="close" aria-hidden="true" /><span className={scopeStyles.clearLabel}>Clear</span></Button> : null}
    {documents.hasNextPage ? <Button variant="ghost" size="compact" pending={documents.isFetchingNextPage} onClick={() => void documents.fetchNextPage()}>Load more documents</Button> : null}
    </div>
    {scope.data?.unavailable ? <p className={styles.scopeNote} role="alert">The saved source is unavailable. Clear the scope or choose another document before asking.</p> : null}
    {scope.data && !scope.data.enabled ? <p className={styles.scopeNote}><Icon name="help" aria-hidden="true" />Document selection is saved; scoped answering will apply when reliability mode is enabled.</p> : null}
    {selected && scope.data?.enabled && !scope.data.unavailable ? <p className={styles.scopeNote}><Icon name="documents" aria-hidden="true" />Follow-up questions use this document until you clear the scope.</p> : null}
    {mutation.isError || scope.isError || documents.isError ? <p className={styles.scopeNote} role="alert">Document scope could not be loaded or saved. <button className={styles.textAction} onClick={() => { void scope.refetch(); void documents.refetch(); }}>Retry loading</button></p> : null}
  </div>;
}
