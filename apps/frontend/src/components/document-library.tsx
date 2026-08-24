/**
 * Document library: import drawer, loaded-row filter, ingestion inspector.
 * Mutations stay in this root. Children are controlled views.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { DocumentList } from "./documents/document-list";
import {
  INGESTION_STATUS_POLL_MS,
  IngestionInspector,
  ingestionStatusIsTerminal,
} from "./documents/ingestion-inspector";
import {
  ImportSourceSheet,
  type ImportSourceTab,
} from "./documents/import-source-sheet";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  enqueueWebsiteCrawl,
  fetchMe,
  fetchMeta,
  fetchVersionStatus,
  finalizeUpload,
  listDocuments,
  reserveUpload,
  retryIngestionJob,
  type ApiAuth,
} from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import {
  ATTESTATION_POLICY_VERSION,
  CRAWL_CONTENT_CLASS_DEFAULT,
  CRAWL_MAX_DEPTH_DEFAULT,
  CRAWL_MAX_PAGES_DEFAULT,
  type DeclaredCategory,
} from "../lib/attestation";
import { evaluatePaidHandshake } from "../lib/handshake";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { showCrawlConvenience, showUploadConvenience } from "../lib/roles";
import {
  objectNameForUpload,
  sha256Hex,
  uploadReservedObject,
} from "../lib/upload-client";
import type { DocumentResponse } from "../lib/types";
import styles from "./documents/documents.module.css";

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
 */
export function DocumentLibrary() {
  const queryClient = useQueryClient();
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
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<string | null>(null);
  const [startUrl, setStartUrl] = useState("");
  const [approvedDomain, setApprovedDomain] = useState("");
  const [statusVersionId, setStatusVersionId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<ImportSourceTab>("file");
  const [filter, setFilter] = useState("");
  const [pageVisible, setPageVisible] = useState(true);

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
    queryFn: () => listDocuments(auth as ApiAuth),
    enabled: auth !== null,
  });

  const versionQuery = useQuery({
    queryKey: keys.versionStatus(statusVersionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, statusVersionId as string),
    enabled: auth !== null && statusVersionId !== null,
    refetchInterval: (query) => {
      if (!pageVisible || statusVersionId === null) {
        return false;
      }
      const status = query.state.data?.version?.status;
      if (!status || ingestionStatusIsTerminal(status)) {
        return false;
      }
      return INGESTION_STATUS_POLL_MS;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || file === null) {
        throw new Error("upload_missing_file");
      }
      if (!handshake.allowPaidPost) {
        throw new Error("handshake_blocked");
      }
      const idempotencyKey = newIdempotencyKey();
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
      setUploadPhase(null);
      setUploadNote(
        `Uploaded “${result.finalized.document_id}”. The file is in quarantine until ingestion finishes.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => {
      setUploadPhase(null);
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
        idempotency_key: newIdempotencyKey(),
        max_depth: CRAWL_MAX_DEPTH_DEFAULT,
        max_pages: CRAWL_MAX_PAGES_DEFAULT,
        content_class: CRAWL_CONTENT_CLASS_DEFAULT,
        graph_eligible: false,
        attestation_policy_version: ATTESTATION_POLICY_VERSION,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
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

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <h2>Documents</h2>
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
  const loaded = documentsQuery.data ?? [];
  const visibleDocs = loaded.filter((doc) => documentMatchesFilter(doc, needle));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2>Document library</h2>
          <p className={styles.lead}>
            Manage authorized sources and follow ingestion status. Filters apply
            only to documents already loaded.
          </p>
        </div>
        {showUpload || showCrawl ? (
          <Button
            type="button"
            variant="primary"
            onClick={() => setImportOpen(true)}
          >
            Import source
          </Button>
        ) : null}
      </header>
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
      </div>

      {documentsQuery.isPending ? (
        <p className={styles.muted}>Loading documents</p>
      ) : (
        <DocumentList
          documents={visibleDocs}
          onLoadStatus={(versionId) => setStatusVersionId(versionId)}
        />
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
          allowPaidPost={handshake.allowPaidPost}
          onUpload={() => uploadMutation.mutate()}
          uploadPhase={uploadPhase}
          uploadNote={uploadNote}
          uploadError={
            uploadMutation.error instanceof Error ? uploadMutation.error : null
          }
          startUrl={startUrl}
          onStartUrl={setStartUrl}
          approvedDomain={approvedDomain}
          onApprovedDomain={setApprovedDomain}
          onCrawl={() => crawlMutation.mutate()}
          crawlError={crawlMutation.isError}
        />
      ) : null}

      {statusVersionId !== null && versionQuery.data ? (
        <IngestionInspector
          payload={versionQuery.data}
          onClose={() => setStatusVersionId(null)}
          onRetry={(jobId) => retryMutation.mutate(jobId)}
        />
      ) : null}
    </div>
  );
}
