/**
 * Authorized document detail queries, retry, and delete.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  deleteDocument,
  fetchDocument,
  fetchVersionStatus,
  listTables,
  retryIngestionJob,
  type ApiAuth,
} from "../../../lib/api";
import { useApiAuth } from "../../../lib/auth/use-api-auth";
import { useSession } from "../../../lib/auth/session-provider";
import { useCurrentUser } from "../../../lib/hooks/use-current-user";
import { sessionQueryKeys } from "../../../lib/query-keys";
import { isOwnerOrAdmin } from "../../../lib/roles";
import type { DocumentResponse } from "../../../lib/types";
import { INGESTION_STATUS_POLL_MS, ingestionStatusIsTerminal } from "../ingestion-status";
import {
  classifyDocumentDeleteFailure,
  documentDeleteFailureCopy,
} from "../document-delete-sheet";

/**
 * Load one document, poll its version while visible, and own delete/retry.
 *
 * A 404 or fetch error never exposes a title. `missing` is true instead.
 *
 * @param documentId - Route document id.
 * @returns Detail controller. Server `/me` remains the role authority.
 */
export function useDocumentDetail(documentId: string) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const { currentUser } = useCurrentUser();
  const [pageVisible, setPageVisible] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    function onVisibility(): void {
      setPageVisible(document.visibilityState === "visible");
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const documentQuery = useQuery({
    queryKey: keys.document(documentId),
    queryFn: () => fetchDocument(auth as ApiAuth, documentId),
    enabled: auth !== null,
  });

  const versionId =
    documentQuery.data?.ok === true
      ? documentQuery.data.document.current_version_id
      : null;

  const versionQuery = useQuery({
    queryKey: keys.versionStatus(versionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, versionId as string),
    enabled: auth !== null && versionId !== null,
    refetchInterval: (query) => {
      if (!pageVisible || versionId === null) {
        return false;
      }
      const status = query.state.data?.version?.status;
      if (!status || ingestionStatusIsTerminal(status)) {
        return false;
      }
      return INGESTION_STATUS_POLL_MS;
    },
  });

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => retryIngestionJob(auth as ApiAuth, jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: keys.versionStatus(versionId),
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      await deleteDocument(auth, documentId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.documents });
      void queryClient.invalidateQueries({ queryKey: keys.document(documentId) });
      router.push("/documents?deleted=1");
    },
    onError: (error) => {
      const kind = classifyDocumentDeleteFailure(error);
      if (kind === "deleted") {
        setDeleteOpen(false);
        router.push("/documents");
        return;
      }
      setDeleteError(documentDeleteFailureCopy(kind));
    },
  });

  const recordBase =
    documentQuery.data?.ok === true ? documentQuery.data.document : null;
  const listed = queryClient.getQueryData<DocumentResponse[]>(keys.documents);
  const listedCreated =
    listed?.find((row) => row.document_id === documentId)?.created_at ?? null;
  const record =
    recordBase === null
      ? null
      : {
          ...recordBase,
          created_at: recordBase.created_at ?? listedCreated,
        };
  const missing =
    !documentQuery.isPending &&
    (documentQuery.data?.ok === false || documentQuery.isError || record === null);

  return {
    signedIn: session.ready && session.accessToken !== null,
    pending: documentQuery.isPending,
    missing,
    record,
    versionPayload: versionQuery.data,
    versionPending: versionId !== null && versionQuery.isPending,
    tables: (tablesQuery.data ?? []).filter(
      (item) => record !== null && item.document_id === record.document_id,
    ),
    canDelete: isOwnerOrAdmin(currentUser?.role),
    retryJob: (jobId: string) => retryMutation.mutate(jobId),
    retryPending: retryMutation.isPending,
    deleteOpen,
    deleteError,
    deletePending: deleteMutation.isPending,
    openDelete: () => {
      setDeleteError(null);
      setDeleteOpen(true);
    },
    closeDelete: () => {
      setDeleteOpen(false);
      setDeleteError(null);
    },
    confirmDelete: () => deleteMutation.mutate(),
  };
}

/** Controller returned by `useDocumentDetail`. */
export type UseDocumentDetailResult = ReturnType<typeof useDocumentDetail>;
