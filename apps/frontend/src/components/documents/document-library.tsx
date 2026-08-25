/**
 * Document library: import drawer, loaded-row filter, ingestion inspector.
 * Mutations stay in this root. Children are controlled views.
 */

"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { HandshakeBanner } from "../auth/auth-screens";
import { DocumentList } from "./document-list";
import {
  INGESTION_STATUS_POLL_MS,
  IngestionStatus,
  ingestionStatusIsTerminal,
} from "./ingestion-status";
import {
  ImportSourceSheet,
  type ImportSourceTab,
} from "./import-source-sheet";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { PageHeader } from "../ui/page-header";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import {
  DOCUMENT_LIST_PAGE_SIZE,
  deleteDocument,
  enqueueWebsiteCrawl,
  fetchMe,
  fetchMeta,
  fetchVersionStatus,
  finalizeUpload,
  isClassifiedApiError,
  listDocuments,
  nextDocumentCursor,
  reserveUpload,
  retryIngestionJob,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import {
  ATTESTATION_POLICY_VERSION,
  CRAWL_CONTENT_CLASS_DEFAULT,
  CRAWL_MAX_DEPTH_DEFAULT,
  CRAWL_MAX_PAGES_DEFAULT,
  type DeclaredCategory,
} from "../../lib/attestation";
import { evaluatePaidHandshake } from "../../lib/handshake";
import { publicQueryKeys, sessionQueryKeys } from "../../lib/query-keys";
import { isOwnerOrAdmin, showCrawlConvenience, showUploadConvenience } from "../../lib/roles";
import {
  objectNameForUpload,
  sha256Hex,
  uploadReservedObject,
} from "../../lib/upload-client";
import type {
  DocumentIngestionStatusResponse,
  DocumentResponse,
} from "../../lib/types";
import styles from "./documents.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

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
 * Document library and upload/crawl convenience.
 *
 * @returns Library surface.
 * @remarks
 * File import is still reserve → Storage JWT → finalize. Polling stops on
 * terminal status, closed inspector, hidden tab, sign-out, or unmount.
 * Duplicate upload clicks reuse one idempotency key until success.
 */
export function DocumentLibrary() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DeclaredCategory>("allowed");
  const [title, setTitle] = useState("");
  const [attested, setAttested] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<string | null>(null);
  const [startUrl, setStartUrl] = useState("");
  const [approvedDomain, setApprovedDomain] = useState("");
  const [crawlTitle, setCrawlTitle] = useState("");
  const [maxDepth, setMaxDepth] = useState(CRAWL_MAX_DEPTH_DEFAULT);
  const [maxPages, setMaxPages] = useState(CRAWL_MAX_PAGES_DEFAULT);
  const [crawlNote, setCrawlNote] = useState<string | null>(null);
  const [statusVersionId, setStatusVersionId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<ImportSourceTab>("file");
  const [filter, setFilter] = useState("");
  const [pageVisible, setPageVisible] = useState(true);
  const [pages, setPages] = useState<DocumentResponse[][]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletedNotice, setDeletedNotice] = useState(false);
  const uploadKeyRef = useRef(newIdempotencyKey());
  const crawlKeyRef = useRef(newIdempotencyKey());

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

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

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

  const loadedStatus = versionQuery.data;
  const statusByVersionId: Record<string, DocumentIngestionStatusResponse> =
    statusVersionId !== null && loadedStatus != null
      ? { [statusVersionId]: loadedStatus }
      : {};

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || file === null) {
        throw new Error("upload_missing_file");
      }
      if (!handshake.allowPaidPost) {
        throw new Error("handshake_blocked");
      }
      const idempotencyKey = uploadKeyRef.current;
      setUploadPhase("Reserving");
      const reserved = await reserveUpload(auth, file.size, idempotencyKey);
      const objectName = objectNameForUpload(reserved.storage_path, file.name);
      const hash = await sha256Hex(file);
      const supabase = session.supabase;
      if (supabase !== null && reserved.signed_url === null) {
        setUploadPhase("Uploading");
        const uploaded = await uploadReservedObject(
          supabase,
          reserved.storage_bucket,
          objectName,
          file,
        );
        if (!uploaded.ok) {
          throw new Error(`storage_upload_failed:${uploaded.error ?? "unknown"}`);
        }
      }
      setUploadPhase("Finalizing");
      const finalized = await finalizeUpload(auth, {
        reservation_id: reserved.reservation_id,
        object_name: objectName,
        content_hash: hash,
        actual_bytes: file.size,
        media_type: file.type || null,
        declared_category: category,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
        idempotency_key: idempotencyKey,
        document_title: title || file.name,
      });
      return { reserved, finalized };
    },
    onSuccess: (result) => {
      uploadKeyRef.current = newIdempotencyKey();
      setUploadPhase("Queued");
      setUploadNote(
        `Created document ${result.finalized.document_id}, version ${result.finalized.version_id}, job ${result.finalized.job_id}. The file is in quarantine until ingestion finishes.`,
      );
      void queryClient.invalidateQueries({ queryKey: keys.documents });
    },
    onError: () => {
      setUploadPhase("Failed");
    },
  });

  const crawlMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      return enqueueWebsiteCrawl(auth, {
        start_url: startUrl,
        approved_domain: approvedDomain,
        idempotency_key: crawlKeyRef.current,
        document_title: crawlTitle.trim() === "" ? null : crawlTitle,
        max_depth: maxDepth,
        max_pages: maxPages,
        content_class: CRAWL_CONTENT_CLASS_DEFAULT,
        graph_eligible: false,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
      });
    },
    onSuccess: (result) => {
      crawlKeyRef.current = newIdempotencyKey();
      setCrawlNote(
        `Created document ${result.document_id}, job ${result.job_id}.`,
      );
      void queryClient.invalidateQueries({ queryKey: keys.documents });
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
      if (isClassifiedApiError(error)) {
        if (error.failure.kind === "auth") {
          setDeleteError("You cannot delete this document.");
          return;
        }
        if (error.failure.kind === "deleted") {
          setDeleteError("Document not found.");
          return;
        }
        if (error.failure.kind === "rate") {
          setDeleteError("Too many attempts. Try later.");
          return;
        }
      }
      setDeleteError("Document could not be deleted.");
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <PageHeader title="Documents." />
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const role = meQuery.data?.role;
  const showUpload = showUploadConvenience(role, meQuery.data?.upload_enabled);
  const showCrawl = showCrawlConvenience(role);
  const needle = filter.trim().toLowerCase();
  const loaded = pages.flat();
  const visibleDocs = loaded.filter((doc) => documentMatchesFilter(doc, needle));
  const canDelete = isOwnerOrAdmin(role);
  const showDeleted = deletedNotice || searchParams.get("deleted") === "1";
  const importButton =
    showUpload || showCrawl ? (
      <Button
        type="button"
        variant="primary"
        data-action-id="documents.import"
        onClick={() => setImportOpen(true)}
      >
        Import source
      </Button>
    ) : null;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Documents."
        description="Upload files or add approved websites, then track search and graph readiness. Filters apply only to documents already loaded."
        actions={importButton}
      />
      <HandshakeBanner />

      {showUpload ? null : (
        <p className={styles.muted}>
          Upload controls are hidden as convenience only. The server still
          denies viewers and callers without upload_enabled.
        </p>
      )}
      {showCrawl ? null : (
        <p className={styles.muted}>
          Website crawl is hidden for this role. The server still denies members
          and viewers.
        </p>
      )}

      <div className={styles.toolbar}>
        <Input
          label="Filter loaded documents"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <p className={styles.toolbarSummary}>
          Showing {String(visibleDocs.length)} of {String(loaded.length)} loaded
        </p>
      </div>

      {documentsQuery.isPending ? (
        <p className={styles.muted}>Loading documents</p>
      ) : (
        <>
          {showDeleted ? (
            <StatusBanner kind="success" role="status">
              Document deleted.
            </StatusBanner>
          ) : null}
          <DocumentList
            documents={visibleDocs}
            statusByVersionId={statusByVersionId}
            onLoadStatus={(versionId) => {
              setStatusVersionId(versionId);
              setInspectorOpen(true);
            }}
            onViewDetails={(documentId) => {
              router.push(`/documents/${documentId}`);
            }}
            canDelete={canDelete}
            onDelete={(doc) => {
              setDeleteError(null);
              setDeleteTarget(doc);
            }}
            emptyAction={loaded.length === 0 ? importButton : null}
            emptyTitle={
              loaded.length === 0
                ? "No documents yet."
                : "No matching loaded documents."
            }
            emptyBody={
              loaded.length === 0
                ? "Import a file or approved website to create searchable company knowledge."
                : "Filters apply only to documents already loaded."
            }
          />
          {nextCursor !== null ? (
            <Button
              type="button"
              variant="secondary"
              onClick={() => loadMoreMutation.mutate()}
            >
              Load more
            </Button>
          ) : null}
        </>
      )}

      {importOpen && (showUpload || showCrawl) ? (
        <ImportSourceSheet
          onClose={() => setImportOpen(false)}
          tab={importTab}
          onTabChange={setImportTab}
          showUpload={showUpload}
          showCrawl={showCrawl}
          file={file}
          onFile={setFile}
          category={category}
          onCategory={setCategory}
          title={title}
          onTitle={setTitle}
          attested={attested}
          onAttested={setAttested}
          allowPaidPost={handshake.allowPaidPost}
          onUpload={() => uploadMutation.mutate()}
          uploadPhase={uploadPhase}
          uploadNote={uploadNote}
          uploadError={
            uploadMutation.error instanceof Error ? uploadMutation.error : null
          }
          uploadPending={uploadMutation.isPending}
          startUrl={startUrl}
          onStartUrl={setStartUrl}
          approvedDomain={approvedDomain}
          onApprovedDomain={setApprovedDomain}
          crawlTitle={crawlTitle}
          onCrawlTitle={setCrawlTitle}
          maxDepth={maxDepth}
          onMaxDepth={setMaxDepth}
          maxPages={maxPages}
          onMaxPages={setMaxPages}
          onCrawl={() => crawlMutation.mutate()}
          crawlError={
            crawlMutation.error instanceof Error ? crawlMutation.error : null
          }
          crawlNote={crawlNote}
          crawlPending={crawlMutation.isPending}
        />
      ) : null}

      {inspectorOpen && statusVersionId !== null && versionQuery.data ? (
        <IngestionStatus
          payload={versionQuery.data}
          layout="timeline"
          asSheet
          onClose={() => setInspectorOpen(false)}
          onRetry={(jobId) => retryMutation.mutate(jobId)}
        />
      ) : null}
      {deleteTarget !== null ? (
        <Sheet
          title="Delete document?"
          onClose={() => {
            setDeleteTarget(null);
            setDeleteError(null);
          }}
        >
          <p className={styles.confirmBody}>
            “<UserText value={deleteTarget.title ?? deleteTarget.document_id} />”
            will be removed from retrieval and scheduled for cleanup. This cannot
            be undone.
          </p>
          {deleteError ? (
            <StatusBanner kind="error" role="alert">
              {deleteError}
            </StatusBanner>
          ) : null}
          <div className={styles.toolbar}>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDeleteTarget(null);
                setDeleteError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              data-action-id="documents.delete"
              pending={deleteMutation.isPending}
              pendingLabel="Deleting…"
              onClick={() => deleteMutation.mutate(deleteTarget.document_id)}
            >
              Delete document
            </Button>
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}
