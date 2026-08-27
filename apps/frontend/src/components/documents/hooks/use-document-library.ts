/**
 * Document library queries, pagination, inspector, and delete.
 */

"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  DOCUMENT_LIST_PAGE_SIZE,
  deleteDocument,
  fetchMeta,
  fetchVersionStatus,
  listDocuments,
  nextDocumentCursor,
  retryIngestionJob,
  type ApiAuth,
} from "../../../lib/api";
import { useApiAuth } from "../../../lib/auth/use-api-auth";
import { useSession } from "../../../lib/auth/session-provider";
import { evaluatePaidHandshake } from "../../../lib/handshake";
import { useCurrentUser } from "../../../lib/hooks/use-current-user";
import { publicQueryKeys, sessionQueryKeys } from "../../../lib/query-keys";
import { isOwnerOrAdmin, showCrawlConvenience, showUploadConvenience } from "../../../lib/roles";
import type {
  DocumentIngestionStatusResponse,
  DocumentResponse,
} from "../../../lib/types";
import { ingestionStatusIsTerminal, INGESTION_STATUS_POLL_MS } from "../ingestion-status";
import {
  classifyDocumentDeleteFailure,
  documentDeleteFailureCopy,
} from "../document-delete-sheet";
import { useDocumentLibraryImport } from "./use-document-library-import";

/**
 * Return whether a loaded document matches the local filter.
 *
 * @param doc - List row.
 * @param needle - Lowercased filter text.
 * @returns True when title or visibility contains the needle.
 */
function documentMatchesFilter(doc: DocumentResponse, needle: string): boolean {
  if (needle === "") {
    return true;
  }
  const title = (doc.title ?? doc.document_id).toLowerCase();
  return title.includes(needle) || doc.visibility.toLowerCase().includes(needle);
}

/**
 * Own library queries and paid import/delete mutations.
 *
 * File import is reserve → Storage JWT → finalize. Duplicate upload clicks
 * reuse one idempotency key until success. List status is fetched per loaded
 * version, page-bounded. Polling stops on terminal status, hidden tab, or
 * unmount.
 *
 * @returns Controlled library state. Does not claim client-side authorization.
 */
export function useDocumentLibrary() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const { currentUser } = useCurrentUser();
  const [statusVersionId, setStatusVersionId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [pageVisible, setPageVisible] = useState(true);
  const [pages, setPages] = useState<DocumentResponse[][]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletedNotice, setDeletedNotice] = useState(false);

  useEffect(() => {
    function onVisibility(): void {
      setPageVisible(document.visibilityState === "visible");
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
  });
  const handshake = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );
  const importer = useDocumentLibraryImport(auth, handshake);
  const documentsQuery = useQuery({
    queryKey: keys.documents,
    queryFn: async () => {
      const page = await listDocuments(auth as ApiAuth, {
        limit: DOCUMENT_LIST_PAGE_SIZE,
      });
      setPages([page]);
      setNextCursor(nextDocumentCursor(page, DOCUMENT_LIST_PAGE_SIZE));
      return page;
    },
    enabled: auth !== null,
  });
  const versionQuery = useQuery({
    queryKey: keys.versionStatus(statusVersionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, statusVersionId as string),
    enabled: auth !== null && statusVersionId !== null,
    refetchInterval: (query) => {
      if (!pageVisible || !inspectorOpen || statusVersionId === null) {
        return false;
      }
      const status = query.state.data?.version?.status;
      if (!status || ingestionStatusIsTerminal(status)) {
        return false;
      }
      return INGESTION_STATUS_POLL_MS;
    },
  });
  const retryMutation = useMutation({
    mutationFn: async (jobId: string) => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      return retryIngestionJob(auth, jobId);
    },
    onSuccess: () => {
      if (statusVersionId) {
        void queryClient.invalidateQueries({
          queryKey: keys.versionStatus(statusVersionId),
        });
      }
    },
  });
  const loadMoreMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || nextCursor === null) {
        return [];
      }
      return listDocuments(auth, { cursor: nextCursor, limit: DOCUMENT_LIST_PAGE_SIZE });
    },
    onSuccess: (page) => {
      setPages((current) => {
        const seen = new Set(current.flat().map((row) => row.document_id));
        const extra = page.filter((row) => !seen.has(row.document_id));
        return extra.length === 0 ? current : [...current, extra];
      });
      setNextCursor(nextDocumentCursor(page, DOCUMENT_LIST_PAGE_SIZE));
    },
  });
  const deleteMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      await deleteDocument(auth, documentId);
    },
    onSuccess: (_void, documentId) => {
      setDeleteTarget(null);
      setDeleteError(null);
      setDeletedNotice(true);
      setPages((current) =>
        current.map((page) => page.filter((row) => row.document_id !== documentId)),
      );
      void queryClient.invalidateQueries({ queryKey: keys.documents });
      void queryClient.invalidateQueries({ queryKey: keys.document(documentId) });
    },
    onError: (error) => {
      setDeleteError(
        documentDeleteFailureCopy(classifyDocumentDeleteFailure(error)),
      );
    },
  });
  const role = currentUser?.role;
  const loaded = useMemo(() => pages.flat(), [pages]);
  const versionIds = useMemo(
    () =>
      Array.from(
        new Set(
          loaded
            .map((doc) => doc.current_version_id)
            .filter((id): id is string => typeof id === "string" && id !== ""),
        ),
      ),
    [loaded],
  );
  const statusQueries = useQueries({
    queries: versionIds.map((versionId) => ({
      queryKey: keys.versionStatus(versionId),
      queryFn: () => fetchVersionStatus(auth as ApiAuth, versionId),
      enabled: auth !== null,
      refetchInterval: (query: {
        state: { data?: DocumentIngestionStatusResponse | null };
      }) => {
        if (!pageVisible) {
          return false;
        }
        const status = query.state.data?.version?.status;
        if (!status || ingestionStatusIsTerminal(status)) {
          return false;
        }
        return INGESTION_STATUS_POLL_MS;
      },
    })),
  });
  const statusByVersionId = useMemo(() => {
    const next: Record<string, DocumentIngestionStatusResponse> = {};
    versionIds.forEach((id, index) => {
      const payload = statusQueries[index]?.data;
      if (payload) {
        next[id] = payload;
      }
    });
    return next;
  }, [statusQueries, versionIds]);
  const pendingStatusIds = useMemo(() => {
    const pending = new Set<string>();
    versionIds.forEach((id, index) => {
      if (statusQueries[index]?.isPending) {
        pending.add(id);
      }
    });
    return pending;
  }, [statusQueries, versionIds]);
  return {
    signedIn: session.ready && session.accessToken !== null,
    showUpload: showUploadConvenience(role, currentUser?.upload_enabled),
    showCrawl: showCrawlConvenience(role),
    canDelete: isOwnerOrAdmin(role),
    allowPaidPost: handshake.allowPaidPost,
    filter,
    onFilter: setFilter,
    loaded,
    visibleDocs: loaded.filter((doc) =>
      documentMatchesFilter(doc, filter.trim().toLowerCase()),
    ),
    documentsPending: documentsQuery.isPending,
    showDeleted: deletedNotice || searchParams.get("deleted") === "1",
    nextCursor,
    loadMore: () => loadMoreMutation.mutate(),
    loadMorePending: loadMoreMutation.isPending,
    statusByVersionId,
    pendingStatusIds,
    openInspector: (versionId: string) => {
      setStatusVersionId(versionId);
      setInspectorOpen(true);
    },
    inspectorOpen,
    inspectorPending:
      statusVersionId !== null && pendingStatusIds.has(statusVersionId),
    inspectorPayload:
      versionQuery.data ??
      (statusVersionId !== null ? statusByVersionId[statusVersionId] : undefined),
    closeInspector: () => setInspectorOpen(false),
    retryJob: (jobId: string) => retryMutation.mutate(jobId),
    retryPending: retryMutation.isPending,
    ...importer,
    deleteTarget,
    deleteError,
    deletePending: deleteMutation.isPending,
    openDelete: (doc: DocumentResponse) => {
      setDeleteError(null);
      setDeleteTarget(doc);
    },
    closeDelete: () => {
      setDeleteTarget(null);
      setDeleteError(null);
    },
    confirmDelete: () => {
      if (deleteTarget !== null) {
        deleteMutation.mutate(deleteTarget.document_id);
      }
    },
  };
}

/** Controller returned by `useDocumentLibrary`. */
export type UseDocumentLibraryResult = ReturnType<typeof useDocumentLibrary>;
